---
title: "智驾 SR 开发：共享内存是条必经之路"
date: 2026-06-26
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 随着智驾的能力不断迭代，越来越多的功能，越来越大的数据量，越来越频繁的信息量随之而来。我记得最初我们就用点Socket UDP就能满足 SR 的 ACC/LCC 的视觉表达和交互需求。但是随着APA/AVP/OCC的接踵而至，Socket来做这些数据的转发，就会遇到性能瓶颈。

使用JNI或Socket去处理需要实时绘制的车道线、障碍物、轨迹线这些**高频、结构化**的二进制数据流会有什么瓶颈的表现？

- CPU 占用偏高：Socket 接收线程频繁收包、主线程逻辑处理任务时间长。
- GC 频率升高：频繁创建字节数组，用完即弃。
- 画面抖动/丢帧：消费速率 > 生产速率，处理不及时了。

数据搬运的方式决定了数据消费方能多快运行，而这些通讯方式(Socket/JNI)在传输过程中存在数据的多次拷贝，导致无法适应这种“持续灌入、逐帧消费”的流式场景。

> 比如Socket：
>
> 1. 安卓进程调发送函数，数据从应用层缓冲区拷进内核的 socket 发送缓冲区（第 1 次拷贝）
> 2. 内核协议栈封包 ，从发送缓冲区传输到接收缓冲区
> 3. Unity 进程调接收函数，数据从内核 socket 接收缓冲区拷到应用层托管数组（第 2 次拷贝）
> 4. C# 侧为了交给 `SomeipHandler`，可能还得再 `Marshal.Copy` 或 `Buffer.BlockCopy` 一次（第 3 次拷贝）

因此，我们需要更换成更低拷贝的跨进程传输方案，共享内存方案就浮现眼前。

---

# 共享内存

Android 上每个 App 进程有独立虚拟地址空间。**不能直接互访对方堆内存**，以免一个越界了，不至于把隔壁的进程给炸穿。进程传数据必须经过 IPC：Binder、Socket、共享内存等。

### Ashmem 共享内存（Android）

**Ashmem**（Android Shared Memory）是 Android 特有的共享内存实现。它这个思路就是要把上面的流程砍到只剩一次，甚至零次拷贝。

> 在内核中分配一块物理页，然后让多个进程各自调用`mmap` 映射到自己的虚拟地址。那么安卓进程写入偏移 0x100 的字节，Unity 进程读偏移 0x100，看到的**就是同一个字节**。

### **典型步骤**：

1. **创建方**（Android App/中间件）创建 Ashmem 区域，得到文件描述符 fd；
2. 通过 Binder / AIDL / Intent 把 fd 交给**读取方**（Unity 进程内的 native 层）；
3. 读取方 `mmap(fd)` 后，内核把物理页映射到 Unity 的虚拟地址空间，读写字节与创建方**零拷贝共享**。

![图1](./图1.png)

> fd  在跨进程共享内存的场景下扮演的角色像一把钥匙，传 fd 就是授权。由于智驾数据敏感，QNX 那边通常会先接到 SOME/IP 数据做一层过滤，再由它来决定把哪个 fd、包含了哪些数据、交给哪个进程。

### 带来的好处

共享内存由此带来的好处是：

- 数据传的快：搬运次数减少到0-1次；
- 调用开销小：地址映射建立之后，没有系统开销；
- 内存利用率高：分配固定的映射区可以复用；

但是也有不方便的地方，比如调试不方便，想知道内存里面存了什么，需要额外的dump能力。而且如果写入端出了啥问题，数据可能就错乱了。

---

# MMKV

如果裸共享内存，用起来很麻烦，数据结构是会变更的，一旦变更，你之前定好的数据偏移就要重算，然后双端同步双端修改。所以，如果能在共享内存之上，构建出一层 key-value 的索引，那肯定会方便很多。开发者不需要关心它的每一个具体的数据要放在第几个字节。

MMKV 是腾讯开源的高性能键值存储库。它有两个比较重要的能力：

- **多进程模式**：同一个 MMKV 实例可以被多个进程同时打开、读写。
- **Ashmem 模式**（Android 限定）：存储区不落地到磁盘文件，而是建在 Ashmem 共享内存上。写入的内容不经过文件系统，不触发磁盘 IO，纯内存操作。

> MMKV 可以被 3D HMI理解为进程间的 `Dictionary<string, byte[]>`。同一个 Dictionary，安卓往里塞，Unity 往外取。底层的所有偏移管理、扩容、并发控制，MMKV 自己做了。

### MMKV 做法

MMKV 的 Ashmem 模式会把 key 的索引（一个哈希表）和 value 的实际数据全部放在这块共享内存区域里。关键的用法：

- **数据 key-value**：key 可以按消息类型来起，比如 `"ObjectList"`、`"LaneList"`、`"OccGrid"`。value 就是安卓那边已经封装好的二进制包（SOME/IP 的 Payload 或是 自己定义的 Protobuf 序列化结果）。
- **序列号 key-value**：用这一组键值对去做是否有数据更新的轮询，每次获取比如 `“ObjectList_Seq”`这个key，如果读到的值和上次不一样，那就去读`"ObjectList"`的value了。

### 示例代码

Android 侧创建

```java
MMKV.initialize(context);

// 给共享内存区域起个名字，创建方和读取方用同一个名字
String mmapId = "vehicle_sr_data";
// Ashmem 大小预分配，建议按"最大单消息 × key 数量 × 2"估算
int ashmemSize = 4096 * 64;

MMKV mmkv = MMKV.mmkvWithAshmemID(
    mmapId,
    ashmemSize,
    MMKV.SINGLE_PROCESS_MODE
);

// 智驾数据到达后写入
byte[] payload = buildOccGridPayload(...);
mmkv.putBytes("OccGrid", payload);
mmkv.putInt("OccGrid_Seq", seq++);

// 取出 fd，准备传给 Unity，一般unity启动时只传一次
ParcelFileDescriptor dataFd = mmkv.ashmemFD();
ParcelFileDescriptor metaFd = mmkv.ashmemMetaFD();
// dataFd.getFd() 和 metaFdVal 通过 JNI 传递给 Unity
```

Unity 侧打开共享内存：

```csharp
// 进程启动时调用一次
SharedKvBridge.Initialize(
    Application.persistentDataPath,
    Application.temporaryCachePath
);

// 拿到 Android JNI 传来的 fd 后打开
var store = SharedKvBridge.OpenWithAshmemFD(
    mmapId: "vehicle_sr_data",
    fd: receivedFd,
    metaFd: receivedMetaFd
);

// 之后就去轮询线程里面读需要的数据key-value
byte[] occData = store.GetBytes("OccGrid");
int occSeq  = store.GetInt("OccGrid_Seq", -1);
```

### 3D 侧的准备

**1. 一份专属 so 包**

当3D想要去调用mmkv的方法的时候，一种方法是：

- C# → Java → libmmkv.so（不需要3D自己的mmkv so包）

> 1. C# 通过 AndroidJavaClass 调用 Java 方法
> 2. Java 方法再调用 libmmkv.so

这种方式每次读写都要经过 Java 层，有 JNI 调用开销。

还有一种方法是：

- C# → lib3d-mmkv.so → libmmkv.so

> 1. C# 通过 [DllImport] 直接调用 lib3d-mmkv.so
> 2. lib3d-mmkv.so 是在 MMKV 官方给到的 libmmkv.so 的 C++接口上做的封装

这种方式绕过 Java层，走的是 Native方法调用，性能可能更好。

**2. Editor调试工具**

之前文章中讲到过的 [SR回放工具](https://mp.weixin.qq.com/s/NdT3XnN_FsSoYUPt1K5lEQ) 就也需要把 MMKV 这条通道的代码适配上去，当某一帧数据是我们需要走 MMKV 通道的时候：1. 创建 MMKV 实例 2 fd传给 3D 3 回放时，相关数据写入 MMKV。

# 常见问题

1. **打开共享内存失败**：通常是 fd 无效、mmapId 不一致或权限问题。建议在日志中打印 mmapId 和 fd，确认传 fd 的时机在 MMKV 创建之后；若仍失败，检查 AndroidManifest.xml 是否配置了正确的共享内存权限。
2. **CPU 仍高**：如果启用了共享内存但 CPU 占用未下降，大概率是没有使用序列号检测，导致 Unity 每毫秒都在 Parse 同一帧数据。

# 结语

智驾数据高频传输依赖 Socket/JNI 会遭遇性能瓶颈。共享内存方案通过减少拷贝次数，配合 MMKV 的键值索引，实现了流畅的跨进程通信，一般用在大数据体的情况中。用不用 MMKV 不一定，但是共享内存方案这是座舱 3D HMI SR 应用开发过程中的必经之路。

