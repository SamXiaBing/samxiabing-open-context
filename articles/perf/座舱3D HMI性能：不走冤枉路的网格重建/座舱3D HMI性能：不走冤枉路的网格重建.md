---
title: "座舱3D HMI性能：不走冤枉路的网格重建"
date: 2026-08-03
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> 这篇计划在3D HMI的性能稳定性的范围内，分享一个比较小的点，可能相对来说也比较基础，就是在一些需要创建网格（Mesh）的场合，如果遇到了CPU偏高的性能问题，可以考虑加入的选择性创建Mesh的方案。

# 问题表现

测试反馈：

> "记忆泊车建图完成后，显示建图结果之前，画面会异常出现较长时间的卡顿，CPU占有率也会超过100%。"

# CPU Usage

打开 Profiler 数据，看帧时间曲线。卡顿发生的时间点跟建图结果到达的时间点吻合。卡顿期间帧时间冲到 100ms 以上，然后慢慢恢复。

展开 CPU Usage 的 Hierarchy 视图，按 Self ms 排序，卡顿帧的堆栈大致是这样的：

- `GameObject.Instantiate` — 大量创建新物体
- `MeshRenderer.SetMaterial` / `Material` 相关 — 设置材质
- `GraphicsMesh.CreateLinePerformance` — 创建道路线 Mesh
- `HPARoadController`, `HPAParkingSpaceController`, `HPARoadMarkController` 等 — 各模块的 Clear + 重建

这些堆栈有一个共同特征：**它们同时出现在同一帧里**。HPA 建图相关的所有模块，比如车位、道路、立柱，减速带等在同一帧做清空+重建。

# 根因分析

其实根因是比较明显的，就是建图结果显示的这个过程产生的。

具体来说，HPA 建图结果的体量很大：一个完整的 `ParkingInfo` 包含多层楼，每层楼有车位、道路、道路标记、障碍物，还有轨迹起终点、目标车位。`HandleHPAMap` 收到数据后，会先清空所有旧数据，再逐楼层重建。

但结合 Profiler，再去看 logcat，能发现这里不是一次重建，而是短时间内连续来了两三次。每次重建都耗费半秒到1秒，画面就卡住了。

为什么短时间内会收到同一份数据？据说是智驾侧担心大数据传输可能失败，所以建图结果会重复发送几次。每次发过来的 MapId 都是不变的，且当时来说，并没有其他的字段可以告诉 3D 数据是否有变化，是否必须更新。

# 解决方案

接口数据不直接提供标识，那就只能自己给自己算个标识出来。因此对数据会去做一层轻量指纹比较，数据没变就直接跳过，不进入处理链路。

```csharp
// 示意代码
public void HandleHPAMap(string id, ParkingInfo parkingInfo) {
    string fingerprint = ComputeParkingMapFingerprint(mapIdKey, parkingInfo);

    // 与构建中的指纹一致，忽略重复包
    if (mapBuildCoroutine != null && fingerprint == inFlightMapFingerprint)
        return;

    // 与上次处理完的指纹一致，跳过重建
    if (fingerprint == lastMapFingerprint)
        return;

    InternalHandleHPAMap(mapIdKey, parkingInfo, fingerprint);
}
```

这里所说的指纹，本质就是拿数据变化的关键值组成一串字符串，在这个场景中，我用了建图结果的 mapId + 轨迹起止点坐标 + 停车位、道路等元素的数量：

```csharp
// 示意代码
string ComputeParkingMapFingerprint(string mapIdKey, ParkingInfo info) {
    sb.Append("map:").Append(mapIdKey);
 // 起终点
 sb.Append("trace:")
.Append(traceStart.Lat).Append(",").Append(traceStart.Lon).Append("-")
.Append(traceEnd.Lat).Append(",").Append(traceEnd.Lon);
    // 目标车位 ID
    sb.Append("tp:").Append(targetParkingId); 
    // 各楼层元素数量
    foreach (var floor in floors) {
        sb.Append(floor.id).Append(",ps:").Append(parkingSpaceCount)
          .Append(",rd:").Append(roadCount)
          .Append(",mk:").Append(markCount);
    }
    return sb.ToString();
}
```

建图结果是否变化，只看"地图 ID、起终点、目标车位、各楼层元素数量"一般就够了，不需要逐点比对顶点坐标。

![](./image.png)

> 这里需要注意，计算指纹需要在创建建图结果物体之前而非之后。否则，可能会遇到在极端情况下，你一遍创建都还没有执行结束，指纹都还没生成，第二遍建图结果数据已经来了，第二遍解析若此时开始，是无法靠指纹跳过的。

# 拓展-可行驶区域

同样的思路也用在可行驶区域（FreeSpace）的渲染上，尤其是数据来源是棋盘格的类型。`DrivableAreaRenderer` 在收到数据时先做变化检测：

```csharp
bool HasDataChanged(byte[] newData) {
    if (lastData == null || lastData.Length != newData.Length)
        return true;

    // 先比首尾字节，快速判断
    if (lastData[0] != newData[0] ||
        lastData[lastData.Length - 1] != newData[lastData.Length - 1])
        return true;

    // 采样比较：均匀取 32 个点，命中差异就返回
    int length = newData.Length;
    int step = length / 32;
    for (int i = step; i < length; i += step)
        if (lastData[i] != newData[i])
            return true;

    // 采样通过，全量比较剩余部分
    for (int i = 0; i < length; i++)
        if (lastData[i] != newData[i])
            return true;

    return false;
```

`HasDataChanged` 先比较首尾字节快速判断，再按采样+逐块比较确认。

# 结语

CPU的上升，有的时候不一定是代码写得有问题，也有可能是此时要处理的顶点计算的任务太重。

以上这种跳过重建的方式，可能对于SR行车过程中需要绘制的道路线、他车、其他感知物来说并不适用，因为行车过程中这些物体总是在变的。然而，这种情景下也往往面临CPU占用过高的性能挑战，所以下一篇会分享下这种情况下的处理方式。