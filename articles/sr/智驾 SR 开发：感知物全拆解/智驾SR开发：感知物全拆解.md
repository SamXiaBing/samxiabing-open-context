---
title: "智驾 SR 开发：感知物全拆解"
date: 2026-05-13
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> SR中的感知物，最常见的就是以类型来预设的物体，这些物体并不需要复杂的绘制，因为它们的外观仅实现示意+空间占位+状态表达的作用。

本文整理智驾SR开发中，常见感知物的三种数据表达形态：点+类型、框/角点+类型、有序点列+类型，另外补充多帧更新方案。每种形态的适用场景、输入字段、处理步骤和可复用落地代码都做了清晰整理，你可以对照协议快速对接参考。

![三种数据形态与感知物帧更新横切总览](./fig_perception_overview.png)

---

## 1. 动态感知物与静态感知物

**动态感知物**：协议侧把它当成会参与交通行为、状态随时间变化的目标。数据里除了位姿、类型外，往往还带**速度**以及**灯态、高亮、骑行或步行语义**等与运动或交互相关的字段。座舱里典型是机动车、非机动车、行人等：

**静态感知物**：协议侧把它当成相对道路的固定存在，例如设施类障碍、路面标线、斑马线、停止线、闸机挡杆状态等。数据侧重**位置、朝向、尺寸或角点轮廓**，而不是一整套动态障碍语义。客户端常见是摆预制体、或在路面上建面、贴花。

属于动态还是静态，最终以**协议类型**为准，不看是否每帧在变。

![动态与静态感知物示意对比](./fig_dynamic_static.png)

---

## 2. 点+类型

即贴地中心点+朝向+物体类型枚举。

### 适用场景

覆盖多数独立实体类感知物：

- 动态物体：机动车、行人、骑行者
- 静态物体：路锥、静态交通标志、固定障碍物

![贴地中心点 + 朝向 + 类型枚举示意](./fig_point_type.png)

### 输入字段

一般包含以下核心信息：


| 字段              | 含义                                                        |
| --------------- | --------------------------------------------------------- |
| `planeX/planeY` | 车体坐标系下平面参考点坐标                                             |
| `yaw`           | 绕竖轴航向角（单位为度数或弧度）                                          |
| `kind`          | 物体类型枚举（车/人/锥桶等）                                           |
| 动态附加            | `velX/velY`（平面速度分量）、`brake/leftTurn/rightTurn`（制动/转向灯光状态） |


### 解析步骤

1. **坐标系转换**：将协议平面坐标转换为引擎世界坐标，常规处理为交换分量+取反+抬升显示高度，保证航向与真实方向一致。
2. **实例化**：根据类型枚举匹配对应预制体，放置到转换后坐标位置，按航向角旋转对齐。
3. **动态状态更新**：行人与骑行者用可以用速度驱动动画播放速度，也可以都只给一个恒定动画速度，当判断速度不为0时播放；交通灯则通过灯态更新材质显示效果。
4. **状态切换处理**：闸机等可动的静态物体，一般会因为不同状态的动画准备不同的预制体。当ID保持不变，但类型发生切换时，需要先释放旧实例，再更换对应预制体重新播放动画。

### 示意代码

```csharp
// 核心枚举与数据包定义（示意：协议若给弧度，先乘 Mathf.Rad2Deg 再传入 yawDeg）
public enum ObstacleKind { Car, Pedestrian, Cyclist, Cone, GateOpen, GateClosed }
public struct ObstaclePacket
{
    public long Id;              // 与第五节帧同步字典键一致；协议用字符串时可哈希或映射表
    public ObstacleKind Kind;
    public float planeX, planeY, yawDeg;
    public float velX, velY;
}

// 坐标系转换工具（与文中「交换分量 + 取反 + 抬升」一致；具体轴约定以实车/引擎前向为准）
public static class VehicleFrameToWorld
{
    public static Vector3 Position(float planeX, float planeY, float displayHeight)
    {
        return new Vector3(-planeY, displayHeight, planeX);
    }
    /// <summary>Quaternion.Euler 的 Y 单位为角度（度），非弧度。</summary>
    public static Quaternion Orientation(float yawDeg)
    {
        return Quaternion.Euler(0f, yawDeg, 0f);
    }
}

// 动态物体应用逻辑
public sealed class DynamicObstacleView : MonoBehaviour
{
    public Animator animator;
    public float displayHeight = 0.35f;
    public void Apply(in ObstaclePacket p)
    {
        transform.SetPositionAndRotation(
            VehicleFrameToWorld.Position(p.planeX, p.planeY, displayHeight),
            VehicleFrameToWorld.Orientation(p.yawDeg));
        
        if (animator != null) {
            bool isLegPowered = p.Kind is ObstacleKind.Pedestrian or ObstacleKind.Cyclist;
            float speed = isLegPowered ? Mathf.Sqrt(p.velX*p.velX + p.velY*p.velY) : 0f;
            animator.SetFloat("MoveSpeed", speed);
        }
    }
}
```

---

## 3. 框+类型

### 适用场景

针对需要占据路面区域的感知物：停止线、斑马线、路面箭头、减速带、占道施工区域。

### 输入字段

分为两种常用格式：


| 形式    | 包含字段                 | 适用场景           |
| ----- | -------------------- | -------------- |
| 框+类型  | 中心坐标 + 长宽 + 航向 + 子类型 | 规则矩形区域（停止线、箭头） |
| 角点+类型 | 有序四个角点坐标 + 子类型       | 不规则四边形（整段斑马线）  |

![框 / 角点 + 类型：条带、四边形、减速带拼接示意](./fig_box_type.png)

### 解析步骤

1. **方案选择**：角点数量不足时，回退至「中心+长宽+航向」矩形方案；角点存在漂移时，使用默认长宽避免模型拉伸变形。
2. **网格生成**：
  - **条带类（停止线/箭头）**：将中心折线向两侧偏移半宽得到边线，剖分为四边形网格，纹理UV沿折线方向重复排列
  - **四边形类（斑马线）**：角点按逆时针排序，拆分为两个三角形，沿长边设置纹理重复
3. **减速带特殊处理**：减速带属于点+类型的变种，由于视觉上需要呈现为一块路面凸起，因此归类到这里；部分协议会提供角点信息，但应用层不一定会实际使用，通常还会额外补充横向总宽参数

### 示意代码

```csharp
// 折线生成条带网格（停止线/箭头通用；ExpandLine / BuildMesh 为沿法向偏移与写 Mesh 的实现，此处省略）
public static class StripMeshBuilder
{
    public static void RebuildStripMesh(Mesh mesh, IReadOnlyList<Vector3> centerLine, float halfWidth, float uvRepeat)
    {
        mesh.Clear();
        if (centerLine.Count < 2) return;

        var left = ExpandLine(centerLine, -halfWidth);
        var right = ExpandLine(centerLine, halfWidth);
        BuildMesh(mesh, left, right, uvRepeat);
    }
}

// 四角生成斑马线网格（SortCorners / GenVertices 将角点排序并升到 XZ 平面上的 Vector3[]）
public static class ZebraQuadBuilder
{
    public static void RebuildQuad(Mesh mesh, Vector2[] cornersXZ, float tileAlongLongSide)
    {
        mesh.Clear();
        var ordered = SortCorners(cornersXZ);
        mesh.vertices = GenVertices(ordered);
        mesh.triangles = new[] { 0, 1, 2, 2, 3, 0 };
        mesh.RecalculateBounds();
    }
}

// 减速带拼接逻辑（仅示意：假设 root 下子物体均为模块段；moduleWidth 须大于 0）
public void RebuildSpeedBump(Transform root, float totalWidth, float moduleWidth, GameObject prefab)
{
    if (moduleWidth <= 0f || prefab == null || root == null) return;
    foreach (Transform c in root) c.gameObject.SetActive(false);
    int count = Mathf.FloorToInt(totalWidth / moduleWidth);
    float start = -totalWidth * 0.5f + moduleWidth * 0.5f;
    for (int i = 0; i < count; i++) {
        Transform seg = i < root.childCount ? root.GetChild(i) : Instantiate(prefab, root).transform;
        seg.gameObject.SetActive(true);
        seg.localPosition = new Vector3(0, 0, start + i * moduleWidth);
    }
}
```

---

## 4. 有序点列 + 类型

### 适用场景

这一类描述的是**一条沿道路展开的几何物体**，用**一串有序顶点**表达形状，再配上**线型或设施类型**（颜色、虚实、路沿/车道等语义）。它和「点 + 类型」的差别在于：不能只用一个参考点概括整条线；和「框 / 角点」的差别在于：通常**不是**一块闭合矩形路面片，而是**开放折线**或沿折线挤出的条带。

比如 **车道与路沿**。

![有序点列折线、条带挤出与虚实线 UV 思路示意](./fig_polyline_lane.png)

### 输入字段


| 字段思路     | 含义                               |
| -------- | -------------------------------- |
| 有序点列     | 车体或世界平面上一串 `(x,y)` 或三维点，顺序表示沿线路径 |
| 线型 / 类型  | 虚实线、颜色、单双线、路沿材质等枚举或分段属性          |
| （可选）每段属性 | 长折线可拆为多段，每段类型或宽度不同               |


### 解析步骤

1. **坐标转换与顶点顺序**：对整串点执行和点+类型一致的平面坐标到世界坐标转换；处理过程中需要严格保留原始顶点顺序，顶点顺序颠倒会导致生成条带的法线方向错误，或纹理拉伸方向反转。
2. **条带网格挤出**：利用相邻顶点构造折线段，再根据线宽向法线两侧偏移，生成连续的四边形条带网格。整体思路和前文停止线的条带生成逻辑一致，区别在于此处折线更长，且支持多段不同类型的线属性切换。
3. **异常处理与顶点优化**：当顶点数量过少时，直接跳过渲染或降级显示为短线段；若顶点过密，则可以按折线弧长进行重采样，控制最终网格顶点数量。

### 示意代码

1. 基础网格生成：先按照第三节停止线的条带生成逻辑，把输入的有序点列向法线两侧偏移，挤出得到左右边界，拼接成完整的四边形条带网格，这一步和普通路面标线生成逻辑完全一致。
2. 实线/虚线的区分方案：不需要在代码里通过逻辑判断逐段绘制虚实片段，而是用纹理+UV的方式统一实现：
  1. 虚线：直接使用带间隔空白的横纹纹理，UV坐标的V轴数值设置为「当前点沿折线的累积弧长 ÷ 虚线实际周期（单位：米）」，这样纹理里的空白和实线段就会按照真实物理长度，自动在路面上重复排列
  2. 实线：替换成纯色实心纹理即可，V轴依旧沿用同样的累积弧长计算方式也不影响显示效果，不需要额外做特殊处理
3. 双线处理：如果需要生成双车道线，直接把原来的单侧半宽参数乘以2，重复上述挤出流程即可，其他逻辑不需要修改。

```csharp
using System.Collections.Generic;
using UnityEngine;

public enum LaneStroke { Solid, Dashed }

/// <summary>线型只决定用哪张横纹贴图；周期米数控制虚线在路上的疏密。</summary>
static void BindStrokeMaterial(Material mat, LaneStroke stroke)
{
    string key = stroke == LaneStroke.Dashed ? "lane_dashed" : "lane_solid";
    var tex = Resources.Load<Texture2D>(key);
    if (tex == null || mat == null) return;
    // URP/Lit 常用 _BaseMap；Built-in Standard 多为 _MainTex，按管线二选一
    if (mat.HasProperty("_BaseMap")) mat.SetTexture("_BaseMap", tex);
    else if (mat.HasProperty("_MainTex")) mat.SetTexture("_MainTex", tex);
}

/// <summary>核心：中心折线 center → 左右偏移 → 条带；V = 弧长 / 周期。left/right 须等长且同序。</summary>
static void FillStripUvAndTris(
    IReadOnlyList<Vector3> left, IReadOnlyList<Vector3> right,
    List<Vector3> verts, List<Vector2> uv, List<int> tris, float dashCycleM)
{
    verts.Clear(); uv.Clear(); tris.Clear();
    if (left.Count != right.Count || left.Count < 2) return;
    float unit = Mathf.Max(dashCycleM, 1e-3f);
    float acc = 0f;
    for (int i = 0; i < left.Count; i++)
    {
        if (i > 0) acc += Vector3.Distance(left[i], left[i - 1]);
        verts.Add(left[i]);  uv.Add(new Vector2(0f, acc / unit));
    }
    acc = 0f;
    for (int i = 0; i < right.Count; i++)
    {
        if (i > 0) acc += Vector3.Distance(right[i], right[i - 1]);
        verts.Add(right[i]); uv.Add(new Vector2(1f, acc / unit));
    }
    int n = left.Count;
    for (int i = 0; i < n - 1; i++)
    {
        int a0 = i, a1 = i + 1, b0 = n + i, b1 = n + i + 1;
        tris.Add(a0); tris.Add(b0); tris.Add(a1);
        tris.Add(a1); tris.Add(b0); tris.Add(b1);
    }
}

// 使用顺序：协议点列转世界 → 按顶点法向左右扩 halfWidth 得到 left/right 两列
// → FillStripUvAndTris → mesh.SetVertices / SetUVs / SetTriangles
// → BindStrokeMaterial(mat, LaneStroke.Dashed) 或 Solid
```

---

## 5. 感知物帧更新方案

为了稳定显示感知物，需要思考这一帧和上一帧是不是同一个对象，用来增删改、对象池复用、避免幽灵物体。每一帧上游给出**当前可见**的物体列表，每条数据带着 ID 和 最新几何/状态；客户端需自己做**本帧集合与缓存的差集**回收。

### 实现步骤

1. 帧开始：清空 本帧已见到 的 ID 集合。  
2. 对每条输入：用 ID 在缓存里找实例；没有则创建或从对象池借用；有则更新几何信息。  
3. 帧结束：缓存里未在本帧出现的 ID 一律回收并移除。

### 示意代码

```csharp
public sealed class PerceptionFrameSync : MonoBehaviour
{
    private Dictionary<long, ObstacleView> _alive = new();
    private HashSet<long> _currentFrame = new();
    private List<long> _toRemove = new();

    public void BeginFrame() => _currentFrame.Clear();

    /// <param name="id">与协议稳定 ID 一致；ObstaclePacket.Id 应与之相同。</param>
    public void Upsert(long id, ObstacleKind kind, in ObstaclePacket p, ObstacleViewPool pool)
    {
        _currentFrame.Add(id);
        if (!_alive.TryGetValue(id, out var view) || view == null) {
            view = pool.Borrow(kind);
            view.Attach(transform);
            _alive[id] = view;
        } else if (view.CurrentKind != kind) {
            pool.Release(view.CurrentKind, view);
            view = pool.Borrow(kind);
            view.Attach(transform);
            _alive[id] = view;
        }
        view.Apply(p);
    }

    public void EndFrame(ObstacleViewPool pool)
    {
        _toRemove.Clear();
        foreach (var kv in _alive)
            if (!_currentFrame.Contains(kv.Key)) _toRemove.Add(kv.Key);
        foreach (var id in _toRemove) {
            pool.Release(_alive[id].CurrentKind, _alive[id]);
            _alive.Remove(id);
        }
    }
}
```

---

## 6. 小结


| 感知物数据     | 典型物体          | 上游最少输出             | 客户端核心工作        |
| --------- | ------------- | ------------------ | -------------- |
| 点 + 类型    | 车、人、锥桶等独立实体   | 平面位姿、类型（动态可加速度、灯态） | 坐标转换、预制体、动画与灯态 |
| 框/角点 + 类型 | 停止线、斑马线、路面箭头等 | 中心+长宽+航向和/或角点、子类型  | 矩形或四角网格、UV     |
| 有序点列 + 类型 | 车道线、路沿        | 有序顶点列、线型/类型        | 折线条带挤出、顺序与衔接   |


从目前落地的实践来看，由于智驾感知方案本身的探测距离有限，只要做好面数优化和对象池复用，日常场景下的帧率表现都是可控的。但是，比如途经车辆行人密集的大型十字路口、自车大转弯瞬时视野内大量新感知物入网时，仍然可能出现帧率波动下降。这种极端场景的性能优化，仍然是值得我们后续持续投入打磨的方向。