---
title: "座舱 SR 数据回放工具：从录制到回放的完整设计"
date: 2026-06-05
series: tools
no: 
status: published
visibility: public
wechat_url: ""
---

> 座舱 SR（Surround Reality）的bug单一般都是最多的那个应用，分析这些bug，高度依赖智驾数据的回放模拟。所以要有一套数据录制—回放工具，把车上的真实数据带回来，在编辑器里逐帧复现，那排查问题的效率就会高很多。

本文章分享的是我做过的这样的回放工具时的设计思路和实践方案。一套完整的回放工具需要考虑的是三个问题：**数据怎么存**、**数据怎么读**、**数据怎么解析注入**。

本文分享的方向是：

- **数据记录端**：安卓平台上的数据如何接入、以什么策略写入文件。
- **文件格式定义**：设计目标、格式选型、带时间戳的变长帧二进制格式。
- **回放工具**：从全量加载到按需读取的优化路径，以及时间驱动回放的实现方式。
- **数据传输层**：进程内注入与跨进程网络传输的利弊取舍。
- **交互设计**：控件布局与关键交互逻辑

---

## 一、整体架构

整个工具链由三个核心模块组成：**数据记录器**（运行在安卓端，负责将 SR 数据写入文件）、**回放工具**（负责读取录制文件并驱动渲染）、**交互面板**（提供人为控制回放的能力）。

关系如下：

*[配图见公众号原文]*

### 回放端的形式

是独立一个3D工程，未来输出成exe呢？还是就把它做到3D工程的编辑器内，作为一个工具面板存在？我推荐的决策依据是：**通信链路决定工具形态**

**场景一：安卓端与引擎端通过 Socket 通信**

如果你的 SR 主程序在安卓设备上通过 Socket 接收原生服务的数据，那么回放工具应当选择**独立可执行程序**，同样通过网络将录制数据发送给 SR 主程序。

原因：回放工具应当**贴近真实的通信链路**。只有走同样的 Socket 通道，你才能在回放过程中暴露出真实通信中才会出现的问题

> 比如单帧数据超过 65535 字节时的分片与重组、UDP 丢包时的表现、粘包时的解析行为。这些网络层面的问题，进程内注入测不出来。

**场景二：安卓端与引擎端通过 JNI 通信**

如果你的 SR 主程序通过 `AndroidJavaProxy`、`DirectByteBuffer` 等 JNI 机制接收数据，那么通信本身就是依赖业务模块的，所以此时回放工具就得做在引擎进程内部，**编辑器面板**是自然的选择。数据从文件读取后，直接调用场景的解析 API 注入到渲染链路。

#### 两种形态的完整对比


|          | 编辑器面板                                       | 独立可执行程序                                                                      |
| -------- | ------------------------------------------- | ---------------------------------------------------------------------------- |
| **原理**   | 在 Unity Editor 中，直接将帧数据注入场景解析链路。            | 导出为独立 exe，通过网络将数据发送给正在运行的 SR 主程序。                                            |
| **优点**   | 调试方便，协议随版本迭代自动同步。                           | 与主程序完全解耦；能验证通信链路本身的问题；可**分发给测试人员**用笔记本联车机去复现问题。                            |
| **缺点**   | 外发或者台架调试不够方便；工位**只有一台显示器**的话，面板争抢屏幕空间 - -！ | 协议变动时需同步更新独立程序。比如报文头加了个时间戳，就要改。但是报文体protobuf变动无所谓，因为不关心byte[]内部组成。它就是个发送器。 |
| **适用场景** | JNI 通信场景下的日常开发调试。                           | Socket 通信场景；测试人员也需要。                                                         |


根据通信链路选择形态——Socket 通信选独立程序，JNI 通信选面板。如果两种链路都存在，则两者都做，共享同一套文件读取逻辑，区别仅在于数据输出方式。

日常开发中，面板因为能更方便地实现数据结构观察和数据搜索，使用频率更高；独立程序在验证通信问题和给测试人员使用时更有价值。

---

## 二、数据记录端

数据记录可能发生在链路的不同环节，具体在哪里记录取决于你的调试需求。我实践过两种方案：

### 2.1 方案一：安卓原生侧录制

这是最直接也最可靠的录制方式。数据在安卓原生服务中产生后、发送给 Unity 之前，直接在原生层写入文件。因为录制点位于数据源头，不存在 Unity 侧接收过程中可能引入的错误。

```csharp
// 安卓原生侧的录制器（Java 示意）
public class PacketRecorder {
    private static final String RECORD_DIR = "RecordData";
    private static final long MAX_FILE_SIZE = 50 * 1024 * 1024;  // 50MB
    private static final int MAX_FILE_COUNT = 50;
    private static final int FLUSH_BUFFER_THRESHOLD = 1024 * 1024; // 1MB
    private static final int FLUSH_TIMEOUT_MS = 2000;              // 2秒
    private LinkedBlockingDeque<byte[]> writeQueue;
    private Thread writerThread;
    private BufferedOutputStream outputStream;
    private long lastFlushTime;
    private int bufferedBytes;

    // 在发送路径上调用：每发一个包，同时录一份
    public void record(byte[] packetData) {
        if (writeQueue == null) return;
        writeQueue.offer(packetData);  // 非阻塞入队
    }

    // 异步写盘线程
    private void writerLoop() {
        while (isRecording) {
            byte[] data = writeQueue.poll(2, TimeUnit.SECONDS);
            if (data != null) {
                // 写入时间戳 + 数据长度 + 数据体
                outputStream.write(longToBytes(System.currentTimeMillis()));
                outputStream.write(intToBytes(data.length));
                outputStream.write(data);
                bufferedBytes += 12 + data.length;
            }
            // 缓冲刷新：数据量超阈值 或 距上次刷新超时
            if (bufferedBytes >= FLUSH_BUFFER_THRESHOLD
                || System.currentTimeMillis() - lastFlushTime >= FLUSH_TIMEOUT_MS) {
                outputStream.flush();
                bufferedBytes = 0;
                lastFlushTime = System.currentTimeMillis();
            }
        }
    }

    // 文件轮转：当前文件超限时，关闭并压缩为 zip，创建新文件
    private void checkAndRotateFile() {
        if (currentFileSize < MAX_FILE_SIZE) return;

        outputStream.flush();
        outputStream.close();

        // 压缩旧文件
        zipFile(currentFilePath, currentFilePath + ".zip");
        deleteFile(currentFilePath);

        // 管理文件总数
        manageFileCount();

        // 创建新文件
        currentFilePath = generateNewFilePath();
        currentFileSize = 0;
        outputStream = new BufferedOutputStream(new FileOutputStream(currentFilePath));
        lastFlushTime = System.currentTimeMillis();
    }

    // 文件总数管理：超过上限时删除最旧的 zip
    private void manageFileCount() {
        File[] files = new File(RECORD_DIR).listFiles((d, n) -> n.endsWith(".zip"));
        Arrays.sort(files, Comparator.comparingLong(File::lastModified));
        while (files.length >= MAX_FILE_COUNT) {
            files[0].delete();
            files = Arrays.copyOfRange(files, 1, files.length);
        }
    }
}

```

**设计要点**：

1. **异步写入**：数据频率高，数据量大，所以要异步线程写入。
2. **缓冲刷新**：不每帧都 flush，而是缓冲区数据量超过阈值（如 1MB），或距离上次刷新超过一定时间（如 2 秒）。这样避免频繁 I/O。
3. **文件轮转**：单文件 50MB，上限 50 个文件。超过上限时将旧文件压缩为 zip 存档，兼顾历史数据保留。

### 2.2 方案二：Unity 侧录制

在某些场景下（比如你想录制的是 Unity 经过 JNI 接收后的数据，而非安卓原生发出的原始报文），可以在 Unity 侧录制。此时录制点在 JNI 桥接层的回调中，写入使用同步 BinaryWriter。

**录制触发点 — JNI 回调**：

```csharp
// 接收 Direct ByteBuffer 的处理逻辑
private unsafe void ProcessData(IntPtr nativePtr, int dataLength)
{
    // 将原生指针封装为非托管内存流，实现零拷贝读取
    using (var stream = new UnmanagedMemoryStream(
        (byte*)nativePtr.ToPointer(), dataLength))
    {
        // 录制路径：此处需要拷贝，因为原生内存在回调返回后即失效
        if (isRecording)
        {
            byte[] buffer = new byte[dataLength];
            stream.Read(buffer, 0, dataLength);
            stream.Position = 0; // 重置流位置，供后续解析使用
            Recorder.WriteFrame(buffer);  // Recorder 即下面定义的 FrameRecorder 实例
        }
        // 解析路径：直接从流读取，无需额外拷贝
        Parser.ParseStream(stream);
    }
}

```

**写入实现 — FrameRecorder**：

`Recorder.WriteFrame(buffer)` 的写入策略是 **同步写入 + 带缓冲的 BinaryWriter**。

```csharp
public class FrameRecorder
{
    private FileStream fileStream;
    private BinaryWriter writer;
    private const float MaxFileSizeMB = 100f;
    private const int MaxFileCount = 10;
    private int currentFileIndex;

    public void StartRecording(string directory)
    {
        ManageFileCount(directory); // 清理旧文件
        string filePath = GetNewFilePath(directory);
        fileStream = File.OpenWrite(filePath);
        writer = new BinaryWriter(fileStream);

        // 写入文件头
        writer.Write(Encoding.UTF8.GetBytes("REC"));  // 魔数 3 字节
        writer.Write((uint)1);                         // 格式版本号
        writer.Write((ulong)GetCurrentTimestampMs());  // 录制起始时间戳
    }

    public void WriteFrame(byte[] frameData)
    {
        if (writer == null) return;

        CheckAndRotateFile(); // 检查文件大小，必要时轮转

        writer.Write(DateTime.Now.Ticks);   // 帧时间戳 (Int64, 8 bytes)
        writer.Write((uint)frameData.Length); // 帧数据长度 (UInt32, 4 bytes)
        writer.Write(frameData);              // 帧原始数据
    }

    public void StopRecording()
    {
        writer?.Flush();
        writer?.Close();
        fileStream?.Close();
        writer = null;
        fileStream = null;
    }
}

```

> 优先选择在安卓原生侧录制。它录的是最原始、最完整的数据，回放时比较省心。
>
> 但如果你的 通信服务 对 3D 侧和智驾侧使用的协议不同，那就 Unity 侧录制作为补充。

---

## 三、文件数据定义

文件格式的合理性直接决定了回放端的实现难度和性能上限。文件格式应当满足的四个目标：

1. 文件头包含足够信息，不需要靠文件名约定来传递版本。
2. 支持流式读取。
3. 能快速定位到第 N 帧而不用扫描前面所有帧。
4. 版本迭代演进仍能兼容老文件。

### 3.1 格式选型

不用纯JSON，是因为纯Json产生的文件太大。一般使用自定义二进制，然后套 Protobuf：

- 自定义报文头（头字符串 + 版本号 + 时间戳）。
- Protobuf 负责消息体的序列化，两层解耦。

### 3.2 文件结构

```
[FileHeader: "REC"(3B) + version(4B) + startTimestamp(8B)]
[Frame0: timestamp(8B, DateTime.Ticks) + length(4B) + data]
[Frame1: timestamp(8B, DateTime.Ticks) + length(4B) + data]
...

```

- 每帧前 8 字节的时间戳使用 `.NET DateTime.Ticks`（表示自 `0001-01-01 00:00:00` 以来的百纳秒数）。回放端据此还原真实的帧间时序。长度字段用 `uint32`（4 字节），字段在帧头中的位置固定使得如果你想跳着扫描帧数据，可以在不解析具体data的情况下定位每一帧。
- data是完整的 Protobuf 序列化后的字节流。在 SR 场景中，一个帧数据包可能包含多种消息类型（如车道线、障碍物、轨迹线等）

### 3.3 大端序与小端序

建议统一使用小端序（Little-Endian）。.NET 的 `BinaryWriter` / `BinaryReader` 默认就是小端序。如果某些场景需要与大端序的服务交换数据（比如安卓端 Java 的 `DataOutputStream` 默认写大端序），就相应做高低位转换处理，不在文件格式混合字节序。

---

## 四、回放工具

回放工具需要解决：**如何快速加载大文件**、**如何按时间节奏驱动回放**、**如何在回放过程中支持随机跳转**。

### 4.1 加载策略

全量加载就不考虑了，解bug就像催命，大文件等不起那个时间，而且还频繁要加载。

所以我们肯定得用**索引扫描 + 按需读取**

第一次读取时只扫描帧索引（帧在文件中的偏移量、数据长度、时间戳），不读取帧的实际数据。帧的实际数据在回放时按需读取。

```
文件头 → 扫描所有帧索引 (每帧仅读 12 字节：8B时间戳 + 4B长度，跳过数据区)
    → List<FrameIndex> (内存占用极小，3GB 文件的索引约几十 MB)
    → 回放/查看某帧时，Seek 到对应偏移量读取数据

```

```csharp
// 帧索引结构（仅元信息，不含数据）
public struct FrameIndex
{
    public DateTime Timestamp;
    public long     Position;    // 帧数据在文件中的偏移量
    public long     DataLength;  // 帧数据长度
}

// 索引扫描
public List<FrameIndex> ScanFrameIndices(string filePath)
{
    var indices = new List<FrameIndex>();
    using (var br = new BinaryReader(File.OpenRead(filePath)))
    {
        // 跳过文件头
        br.ReadBytes(3);  // "REC"
        uint version = br.ReadUInt32();
        br.ReadUInt64();  // start timestamp

        long fileLength = br.BaseStream.Length;

        while (br.BaseStream.Position < fileLength)
        {
            long remaining = fileLength - br.BaseStream.Position;
            if (remaining < 12) break; // 不够一帧头

            var idx = new FrameIndex();
            idx.Timestamp = new DateTime(br.ReadInt64());  // 8 bytes
            idx.DataLength = br.ReadUInt32();                 // 4 bytes
            idx.Position = br.BaseStream.Position;           // 数据起始位置

            // 验证数据长度合理性
            if (idx.DataLength == 0 || idx.DataLength > remaining - 12)
                break;

            br.BaseStream.Position += idx.DataLength; // 跳过数据区
            indices.Add(idx);
        }
    }

    // 按时间戳排序（确保回放时时间递增）
    indices.Sort((a, b) => a.Timestamp.CompareTo(b.Timestamp));
    return indices;
}

```

```csharp
// 按需读取某帧的数据
public byte[] LoadFrameData(string filePath, FrameIndex index)
{
    using (var br = new BinaryReader(File.OpenRead(filePath)))
    {
        br.BaseStream.Position = index.Position;
        return br.ReadBytes((int)index.DataLength);
    }
}

```

**优化1：缓存 BinaryReader**

如果回放时每帧都 `new BinaryReader`，文件打开/关闭的开销不可忽视。建议缓存一个 `BinaryReader`，回放期间保持打开，仅在停止回放时关闭：

```csharp
private BinaryReader cachedReader;
private string cachedReaderPath;

private BinaryReader GetCachedReader(string filePath)
{
    if (cachedReader == null || cachedReaderPath != filePath)
    {
        cachedReader?.Close();
        cachedReader = new BinaryReader(File.OpenRead(filePath));
        cachedReaderPath = filePath;
        // 跳过文件头
        cachedReader.ReadBytes(3);
        cachedReader.ReadUInt32();
        cachedReader.ReadUInt64();
    }
    return cachedReader;
}

```

**优化2：下一帧预加载**

在播放当前帧的同时，可以提前将下一帧的数据读入内存。这样当回放推进到下一帧时，数据已经在内存中，消除了播放中的 I/O 等待。发送当前帧后立即触发下一帧的异步读取：

```csharp
// 发送当前帧后，预加载下一帧
byte[] nextFrameData = null;
if (frameIdx + 1 < recordFrames.Count)
    nextFrameData = LoadFrameData(recordFrames[frameIdx + 1]);

```

**优化3：索引缓存**：

索引扫描虽然只读每帧的 12 字节，但对于数 GB 的文件，扫描仍需数秒。可以将索引结果持久化（如存入 `EditorPrefs` 或独立的索引文件），下次打开同一录制文件时直接从缓存恢复，做到"秒开"。

```csharp
bool IsCacheValid(string filePath, CachedIndex cache)
{
    var info = new FileInfo(filePath);
    return info.Length == cache.FileSize
        && info.LastWriteTimeUtc == cache.LastModified;
}

```

**优化4：大文件扫描的分帧处理**

对于 上GB 的录制文件，即使只扫描帧索引，同步执行也会导致编辑器短暂卡顿。可以将扫描分散到多帧 `EditorApplication.update` 中执行，每帧扫描若干帧索引后 yield，让编辑器保持响应。扫描完成后回调通知 UI 刷新。

### 4.2 回放方式

#### **（1）线程 + Sleep**

这一般就是适合给独立运行数据模拟发送程序的方案用的，作为数据发送端，可以起一个独立线程去循环取数据，然后做socket的发送。sleep就是用来控制倍速播放的。

```
// 独立程序的回放线程
private Thread replayThread;
private volatile bool isReplaying;
private volatile bool isPaused;
private ManualResetEvent pauseEvent = new ManualResetEvent(true); // 初始为有信号（不暂停）

public void StartReplay()
{
    isReplaying = true;
    isPaused = false;
    replayThread = new Thread(ReplayLoop);
    replayThread.IsBackground = true;
    replayThread.Start();
}

private void ReplayLoop()
{
    DateTime recordStart = frameIndices[0].Timestamp;
    DateTime replayStart = DateTime.Now;
    int frameIdx = 0;

    while (isReplaying && frameIdx < frameIndices.Count)
    {
        // 暂停时阻塞，恢复时继续
        pauseEvent.WaitOne();

        TimeSpan elapsed = DateTime.Now - replayStart;
        TimeSpan frameOffset = frameIndices[frameIdx].Timestamp - recordStart;

        if (frameOffset > elapsed)
        {
            // 时间未到，Sleep 等待
            int sleepMs = (int)(frameOffset - elapsed).TotalMilliseconds;
            Thread.Sleep(Math.Max(1, sleepMs));
            continue;
        }

        // 发送所有已经到达时间的帧
        while (frameIdx < frameIndices.Count &&
               frameIndices[frameIdx].Timestamp - recordStart <= elapsed)
        {
            byte[] data = LoadFrameData(frameIndices[frameIdx]);
            DeliverFrame(data);
            frameIdx++;
        }
    }
}

public void Pause()  { isPaused = true;  pauseEvent.Reset(); }  // 阻塞线程
public void Resume() { isPaused = false; pauseEvent.Set(); }    // 释放线程

public void StopReplay()
{
    isReplaying = false;
    pauseEvent.Set();       // 确保线程不会被 WaitOne 卡住
    replayThread?.Join();   // 等待线程安全退出，不用 Thread.Abort
}

```

**设计要点**：

1. **暂停/恢复**：用 ManualResetEvent 实现：Reset() 把线程卡住，Set() 放行。
2. **退出机制**：isReplaying 加 volatile 保证线程间可见。停的时候先置标志位，再 Set() 释放暂停阻塞，最后 Join() 等线程自己退出。
3. **时间对齐**：这种回放也是"追赶式回放"：算已过时间，把到期的帧全发出去。等待方式是 Thread.Sleep。

#### **（2）Unity 协程 + 时间对齐**

协程方式就是为编辑器面板来做回放工具而设计的，也是"追赶式回放"，不试图精确控制帧间间隔，而是以 Unity 的帧为单位，每帧检查"当前时间应该播放到哪里了"，然后把所有到期的帧一次性发送出去。这种方式的好处是：天然支持暂停/恢复（修改状态位即可）；可以在协程中调用 Unity API；倍速播放只需将 `elapsed` 乘以倍速系数。

```csharp
private IEnumerator ReplayLoop()
{
    DateTime recordStart = recordFrames[0].Timestamp;
    DateTime replayStart = DateTime.Now;

    int frameIdx = 0;
    bool playing = true;

    while (playing && frameIdx < recordFrames.Count)
    {
        // 计算回放已经过的时间
        TimeSpan elapsed = DateTime.Now - replayStart;
        TimeSpan frameOffset = recordFrames[frameIdx].Timestamp - recordStart;

        // 如果当前帧的时间还未到，等待
        if (frameOffset > elapsed)
        {
            yield return null; // 下一帧再检查
            continue;
        }

        // 发送所有已经到达时间的帧（可能多帧同时到期）
        while (frameIdx < recordFrames.Count &&
               recordFrames[frameIdx].Timestamp - recordStart <= elapsed)
        {
            var frame = recordFrames[frameIdx];
            byte[] data = LoadFrameData(frame);
            DeliverFrame(data); // 注入到场景
            frameIdx++;
        }

        playing = frameIdx < recordFrames.Count;
        yield return null;
    }
}

```

倍速播放的实现：

```csharp
TimeSpan elapsed = (DateTime.Now - replayStart) * replaySpeed;

```

---

## 五、交互设计

### 5.1 面板布局

以下为编辑器面板的布局示意，UI相关代码就不展示了，这个时代，这种代码很容易实现：

![图2](./图2.png)

**设计意图**：

- **文件列表区：**在顶部，支持在面板内直接切换录制文件，避免每次都需要在外部选择文件。对于测试人员频繁切换不同路测记录的场景，这一区域比传统的"打开文件"对话框更高效。
- **搜索区：**支持按内容、按 ID、按类名搜索，是排查特定数据问题的关键入口。
- **回放控制区：**只在 Play 模式下激活，因为回放需要 Runtime 环境。
- **帧导航区：**使用 Slider 实现拖拽跳帧。拖拽过程中暂停回放，松开后从目标帧继续。
- **帧数据详情区：**每条消息可折叠展开，展开后以 JSON 格式显示。这里使用 `JsonConvert` 做格式化，方便阅读 Protobuf 的 `ToString()` 输出。

---

## 六、类图

以下是回放工具核心模块的类图，展示了各模块的职责划分和协作关系：

![图3](./图3.png)

**职责说明**：

- `FrameRecorder`：只管写帧数据到文件，不关心数据从哪来。
- `ReplayEngine`：回放工具。编辑器面板的形式，就直接调开发框架的消息处理器；独立程序的形式，就交给 FragmentSender 分片派发。
- `FragmentSender`：大帧数据的分片与发送，只在独立程序模式下出场。
- `ITransport`：传输层抽象。面板模式不需要传输层；独立程序模式走Socket。
- `ReplayPanel`：UI 层，只做展示和用户输入，操作全委托给 ReplayEngine。

---

## 七、完整流程

从录制到回放的完整流程：

![图4](./图4.png)

---

## 八、结语

这篇文章覆盖了座舱 SR 数据回放工具从记录到回放的完整设计，如果你正在做类似的工作，希望这些设计思路能提供一些参考。写到这里，想起以前使用它去开发和调试SR的过往经历，还得补充一下：

- 如果你选用了**编辑器面板**的形式，跟着应用走的话：
  - 在台架/车机调试的时候，要考虑好运行时的**UI操作面板**提供什么功能，不能只考虑编辑器面板了。
  - .rec 文件要 adb push 到设备上，准备好bat脚本吧。
- 如果你选用了**独立的回放**程序的方案：
  - 在台架/车机调试的时候，你得走**ADB 端口转发，绕过原定的socket通讯，另建一条路。**
    - 笔记本跑回放程序，`adb forward tcp:45558 tcp:45558` 建立端口转发。
    - 回放程序连 `127.0.0.1:45558`，数据经由 USB 到达台架设备上的 `45558` 端口。
    - SR应用的安卓端，在这里要写一个TCP Server去监听转发过来的数据，专门去接这一路模拟数据。
    - 实际操作流程是：先用 bat 脚本杀掉 SR 应用 → 回放程序建 ADB 转发 → 再拉起 SR 应用。此时 SR 启动后，发现 ADB 转发已经建好，就走 TCP 回放通道拿数据，而不是去连真实数据的服务。

