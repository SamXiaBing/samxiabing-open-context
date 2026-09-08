---
title: "座舱3D HMI性能：LINQ写得爽，GC火葬场"
date: 2026-07-20
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇分享了在运行时触发基于3D引擎自身的性能报告的抓取方案，也说到了需要补充使用具体数据进行分析和解决问题的案例，因此本篇就先讲第一个：周期性掉帧/卡顿。

# 问题表现

测试反馈：

> “大部分时间挺顺，就是隔一会儿会卡一下（或者是屏幕角落上显示的FPS会突然下降），马上又好了。”

---

# CPU Usage

打开自动捕获下来的 Profiler 的数据文件，先看帧时间曲线。形态大致可能是这样：

*[配图见公众号原文]*

- 正常帧数据：16ms左右，帧率在 60fps。
- 异常帧数据：50ms左右，帧率在 20fps，尖刺状，升高得快降回去也快。
- 异常时机：通过和运行时场景观察，比较有规律，大约每次都是隔了几秒。

这是**周期性 + 马上恢复**，基本就会把方向定在：高频代码执行链路上，持续在托管堆上产生生命周期极短的托管对象。这些对象不会立刻回收，但会持续推高托管堆的占用，最终触发周期性的GC回收。

---

# Hierarchy

为了印证这个方向，此时就会去切换到 Hierarchy 选项：

展开 `PlayerLoop` → `Update.ScriptRunBehaviourUpdate`，把 **Self ms** 和 **GC Alloc** 两列一起看：

*[配图见公众号原文]*

1. `GC.Collect` 会产生对 Self ms 的需求。
2. 某条业务路径 Alloc 持续数百 KB～数 MB。
3. 分配栈常见会落到 `Enumerable.Select…` / `List.ToArray`。

> 前提：
>
> ![image](./image.png)

到这一步，就得去查指向的代码了，去找和List操作相关的代码。

---

# 代码分析

工程里定位到的代码，在车道线感知点集做坐标系转换时：

```csharp
// LaneDataProcessor.cs
laneline_piece_points[i] = LanelinePiece.PointsCurve.Points
    .Select(point => new UnityEngine.Vector3(-point.Y, point.Z, point.X))
    .ToList()
    .ToArray();
```

同一个文件里不止一处这么写，还有先 Select ToList 生成一个临时 List，再 AddRange 到目标集合的写法。这些写法的目的，都是为了把感知坐标系的点转换成 Vector3，但问题是这是一个很高频的数据处理链路，Piece 段数很多的时候，这里就会产生大量临时变量。

最终只想要一个 Vector3的数组，但 `Select(...).ToList().ToArray()` 这条链路上至少产生了三个堆对象：WhereSelect 迭代器、中间 List<Vector3>（还可能带扩容浪费）、最终数组。就算简化成 Select(...).ToArray()，迭代器和结果数组的分配也还在。

*[配图见公众号原文]*

# 改法

所以热路径上别再 `Select().ToList().ToArray()` 这类链式分配，用 for + 复用 buffer：

```csharp
int ConvertPointsNonAlloc(IList<ProtoVec3> src, ref Vector3[] buffer)
{
    int n = src.Count;
    if (buffer == null || buffer.Length < n)
        buffer = new Vector3[Mathf.NextPowerOfTwo(n)];
    for (int i = 0; i < n; i++)
    {
        var p = src[i];
        buffer[i] = new Vector3(-p.Y, p.Z, p.X);
    }
    return n;
}
```

改成 for 直接往复用 buffer 写 Vector3 时，不再为“中转”去 new 迭代器和临时 List，短命托管对象就消掉了。约定：下游只吃返回值 `n`（有效长度），不要用 `buffer.Length`。另：这里只扩不缩，偶发超大点集后稳态内存会抬着，长跑项目要盯峰值。

---

# 同类问题

### 1）无意义拷贝

`ToArray()` / `ToList()` 

```csharp
// 示意：已经有 List，却每次拷出新数组交给下游
mesh.SetVertices(tempList.ToArray());

```

若下游 API 有 `List<T>` / `NativeArray` 重载，直接传 List。

### 2）字符串插值与 Format

```csharp
Log.Info($"lane={id} piece={i} count={count}");

string pieceID = string.Format("{0}_{1}", id, i);
```

C# 里字符串不可变，每次 Format / $"{id}_{i}" 都会在堆上 new 一个新的 string 对象。拼完若只用来打日志或临时当 key，用完就没人引用，就变成短命垃圾，一样会贡献 GC Alloc。但是它一般不是主要影响的因素，所以能不拼就不拼。如果是日志，发布版本就要关掉这个打印。

### 3）API 隐藏分配


| API                                        | 发生了什么                                      |
| ------------------------------------------ | ------------------------------------------ |
| `renderer.material`                        | 下一篇分享                                      |
| `GetComponents<T>()` / `FindObjectsOfType` | 无参重载新数组；优先 `GetComponents(List)` 非分配重载 |
| `new Mesh()` / 每帧 `mesh.vertices = ...`    | 托管→Native 一次拷贝；少赋值，优先 `SetVertices`     |


---

# 结语

问题不在 LINQ 本身，而在热路径上的链式堆分配。不合适的地方（链式）“优雅”，事后可能是（加班）“狼狈”。