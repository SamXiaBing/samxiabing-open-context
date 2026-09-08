---
title: "智驾 SR 开发：泊车OCC可视化从体素网格到障碍表面的两种工程实现"
date: 2026-05-12
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

---
title: "智驾 SR 开发：泊车OCC可视化从体素网格到障碍表面的两种工程实现"
author: "冰棒"
date: "2026-05-12"
---

*[配图见公众号原文]*

> 在智驾座舱 SR（Surround Reality）泊车界面里，障碍物常常不是一张现成三角网，而是一串被占用的体素格子。智驾数据协议把格子尺寸和占用索引丢给应用层，怎么变成屏幕上看得见、像一堆挡在那里的实体，是渲染侧需要实现的事。

本文整理泊车 OCC 里常见的两条路：**按占用点实例化小立方体**，以及**把点云分层后做水平外包络再挤出成壳状 Mesh**。每种写法对应什么数据形态、实现步骤、优化注意点，都按工程里能跑通的思路拆开写，方便你对照选型。

---

## 1. 数据处理

智驾检测到障碍物，会将障碍物拆解成一个个方块，以一张占用点坐标清单，配合每个占用点方块尺寸，给到应用层去渲染。

### 1.1 数据形式

可以把整个泊车区域想象成一个大乐高积木盒：


| 数据组成    | 数据意义             | 实际作用                                                |
| ------- | ---------------- | --------------------------------------------------- |
| 每个方格的尺寸 | 单个小乐高块长、宽、高是几厘米  | 定义单个体素的实际物理大小（比如0.2米×0.2米×0.25米）这个一般是约定或是效果验证之后的结果。 |
| 占用索引列表  | 哪几个格子是障碍物，要显示乐高块 | 只记录有障碍物的格子的序号坐标，是三维整数序号，不是真实的米数。                    |


### 1.2 数据转换

1. **算大小**：把序号乘以单个格子的尺寸，从"第几块"变成离起点多少米（比如i是3，步长0.2米，那就是3×0.2=0.6米）
2. **固定对齐**：在换到3D引擎世界坐标系之前，因为智驾供应商本身的缘故，可能会遇到需要对协议数据的坐标做一次固定平移，即固定需要添加一个offset偏移变量。
3. **调换方向**：智驾传感器的方向定义（比如上下前后用哪个轴），和3D引擎的习惯不一样，把坐标顺序换一下，让障碍物方向不颠倒。比如 new Vector3(-y, z, x) 就是在做 分量重排 + 某一轴取反。

---

## 2. 表现形式一：体素立方体 

这个风格就是：我的世界。就是给每个有障碍物的格子，都画一个小立方体，用批量渲染节省性能。

### 2.1 实现步骤

*[配图见公众号原文]*

1. **确认位置**：把上一步转好的每个世界坐标点，直接当成小立方体的中心点就行，一个点对应一块小积木。
2. **准备立方体模板**：启动的时候，实例化1个边长为1的立方体模型（Mesh）存起来，后面所有小方块都复用这个模板，不用每个都重新创建。
3. **构建Transform列表**：给每个中心点，生成一个 Transform信息，组合成TRS矩阵：把模板立方体缩放到你想要的大小（通常每个边是几厘米到十几厘米，具体看设计要求）。
4. **批量绘制**：用GPU支持的批量实例化接口（比如Unity的Graphics.DrawMeshInstanced），一次性把所有小方块画出来。千万不要每个方块建一个独立的游戏对象（GameObject），那样会卡爆。

### 2.2 优化经验

- **提前申请Transform列表**：存变换信息的列表，避免频繁动态扩容。
- **使用批量实例化的GPU的绘制方法**
- **旧方块及时清**：按照固定的时间间隔清空上一帧的变换信息，避免累积。

*[配图见公众号原文]*

### 2.3 示例代码

体素索引乘步长、偏置与换轴请按协议标定替换占位；立方体缩放与渲染层按项目填。

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

public sealed class VoxelCubeInstancingHost : MonoBehaviour
{
    public Material instancingMaterial;
    public int renderLayer = 0;

    Mesh _unitCubeMesh;
    readonly List<Matrix4x4> _matrices = new List<Matrix4x4>(8192);
    Vector3 _cubeScale = new Vector3(0.08f, 0.08f, 0.08f);

    void Awake()
    {
        var temp = GameObject.CreatePrimitive(PrimitiveType.Cube);
        _unitCubeMesh = temp.GetComponent<MeshFilter>().sharedMesh;
        Destroy(temp);
    }

    /// <summary>体素格 (ix,iy,iz) 转世界点：乘 cell 米制步长，再减偏置、做轴向重排。</summary>
    public static Vector3 CellIndexToWorld(uint ix, uint iy, uint iz, Vector3 cellMeters)
    {
        float ax = ix * cellMeters.x - BiasA;
        float ay = iy * cellMeters.y - BiasB;
        float az = iz * cellMeters.z - BiasC;
        return RemapAxes(ax, ay, az);
    }

    static Vector3 RemapAxes(float ax, float ay, float az)
    {
        return new Vector3(ax, ay, az);
    }

    const float BiasA = 0f, BiasB = 0f, BiasC = 0f;

    public void RebuildFromCells(IReadOnlyList<(uint ix, uint iy, uint iz)> cells, Vector3 cellMeters)
    {
        _matrices.Clear();
        int n = cells.Count;
        for (int i = 0; i < n; i++)
        {
            var c = cells[i];
            Vector3 p = CellIndexToWorld(c.ix, c.iy, c.iz, cellMeters);
            _matrices.Add(Matrix4x4.TRS(p, Quaternion.identity, _cubeScale));
        }
    }

    void LateUpdate()
    {
        if (_unitCubeMesh == null || instancingMaterial == null || _matrices.Count == 0)
            return;

        instancingMaterial.enableInstancing = true;
        Graphics.DrawMeshInstanced(
            _unitCubeMesh,
            0,
            instancingMaterial,
            _matrices,
            _matrices.Count,
            null,
            ShadowCastingMode.On,
            receiveShadows: true,
            renderLayer);
    }

    /// <summary>若只需画单块调试体，可用单矩阵版本（非实例化主路径）。</summary>
    public void DrawSingleDebugCube(Vector3 worldCenter)
    {
        if (_unitCubeMesh == null || instancingMaterial == null) return;
        var mtx = Matrix4x4.TRS(worldCenter, Quaternion.identity, _cubeScale);
        Graphics.DrawMesh(_unitCubeMesh, mtx, instancingMaterial, renderLayer, null, 0, null, ShadowCastingMode.On, true);
    }
}
```

## 3. 表现形式二：按轮廓，分层挤出外壳

这是把离散点收成**带厚度外壳**的常见做法，视觉上更接近一整块障碍物，顶点数量比方块方式的可控性更强些。

### 3.1 数据形式

输入仍然是同一串世界坐标点云。额外需要调试的参数是：


| 参数      | 大白话作用                         | 常用值参考                |
| ------- | ----------------------------- | -------------------- |
| 层厚      | 把障碍物垂直切成一片片，每一片多厚             | 一般0.2-0.3米，可根据效果调    |
| 聚类倍数    | 决定多远以内的点算"同一个障碍物"             | 一般是水平格子平均边长 × 2-2.5倍 |
| 每层最多点数量 | 防止这一层点太多，算起来卡                 | 自己设上限，超了就只采一部分点      |
| 轮廓边最长多少 | 凸包出来的边太长，挤出后会很生硬，超过这个长度就切分成小段 | 按需调                  |


### 3.2 实现步骤

*[配图见公众号原文]*

这个方法是把零散点拼成一块完整的"壳状障碍物"，以下所说只是我的处理方式，并不一定是最标准最优解。步骤是切分层→分组→找轮廓→挤出3D面：

1. **按高度分层切片**
  1. 先找这一帧所有点里最低的高度当起始零点，每个点算自己离零点差多高，除以层厚取整数，得到属于哪一层。
  2. 后面同一层的点放在一起，算水平方向的形状，一般0.2-0.3米切一层就行，数值可以调。
2. **同一层里分组（聚类）**
  1. 一层里可能不止一个障碍物（比如同时有墙和柱子），要按距离远近分成好几组：两个点距离小于阈值，就算同一个障碍物。
  2. 阈值就是水平格子平均边长 × 你提前调的聚类倍数，默认2.5倍效果就不错。
  3. 如果是薄墙，只在水平面上分组就行；如果是单独立柱，可以用三维空间分组。点太多的时候，可以只抽一部分点算，或者限制最多处理几层，防止单帧计算量太大卡住。
3. **找每组的最外圈轮廓（水平凸包）**
  1. 每组点都从头顶往下看（XZ平面），算出把所有点包起来的最外圈多边形，就是凸包。
  2. 好处是算法简单好实现，但缺点是原来形状凹进去的地方会被填平——这是故意的取舍，省算力就得牺牲一点凹细节。
4. **给轮廓加细（加密折线）**
  1. 凸包顶点一般很少，挤出来的侧面会一块一块很生硬。所以我们按你设定的最大边长，在长边上插几个中间点，让轮廓线更密。
  2. 最后把所有点的高度统一改成这一层的中心高度，保证所有轮廓点都在同一个水平面上。
5. **挤出成3D网格（三角网）**
  1. 把这一圈轮廓线，在层中心往上和往下各挪半个层厚，得到上面一圈点（顶环）和下面一圈点（底环）。
  2. 顶面和底面各自再做一次凸包，把凸多边形切成一个个小三角形（扇形剖分），注意正反面顺序：顶面法线朝上，底面法线朝下，这样渲染才不会穿模。
  3. 侧面就顺着轮廓顺序，相邻的上下四个点连成一个四边形，再拆成两个三角形，法线朝外（让外表面能看见）。
  4. 最后把所有顶点和三角形存进Mesh，重新计算法线；如果想要某些块状颜色变化的效果或者按PDC距离变色，那么需要再给顶点加上颜色信息或者传给Shader参数。

### 3.3 优化经验


| 优化点        | 核心做法                                                    | 作用                      |
| ---------- | ------------------------------------------------------- | ----------------------- |
| 层数&点数兜底    | 超过maxPointsPerLayer先等间隔抽稀；总层数超过maxProcessLayers只处理最下层N层 | 硬上限防单帧算力爆栈，避免卡顿         |
| 聚类半径自适应    | 阈值 = (X+Z方向体素尺寸)/2 × 聚类倍数，不写死常数                         | 随协议体素尺寸自动适配，不用重复调参数     |
| 默认2D GPU聚类 | 优先GPU计算邻域，传结果回CPU做DBSCAN；Shader失败回退CPU均匀网格搜邻            | 适合薄墙类场景，速度更快，省CPU       |
| 可选3D聚类     | 关闭2D后，走全点对三维DBSCAN，无空间哈希优化                              | 适配孤立立柱场景，点密时更吃CPU，按需开启  |
| Mesh内存复用   | 顶点/索引/顶点色用成员List，每帧只清空不重建，提前按估算设容量                      | 减少频繁内存分配，降低GC卡顿         |
| 后台线程解析     | 大体积protobuf用UniTask切线程池计算，结果回主线程渲染                      | 解析不卡主线程，保持界面流畅；开关跟随项目配置 |


### 3.4 示例代码

只保留分层、聚类半径与挤出壳的核心骨架；凸包与三角剖分请接你项目里的工具类。

```csharp
using System.Collections.Generic;
using UnityEngine;

static class LayeredOccupancyShell
{
    /// <summary>按高度分桶：layer = floor((y - minY) / layerThickness)。</summary>
    public static void BucketByHeight(
        IReadOnlyList<Vector3> worldPoints,
        float minY,
        float layerThickness,
        Dictionary<int, List<Vector3>> outByLayer)
    {
        outByLayer.Clear();
        float h = layerThickness > 1e-6f ? layerThickness : 0.25f;
        for (int i = 0; i < worldPoints.Count; i++)
        {
            Vector3 p = worldPoints[i];
            int layer = Mathf.FloorToInt((p.y - minY) / h);
            if (!outByLayer.TryGetValue(layer, out var list))
            {
                list = new List<Vector3>();
                outByLayer[layer] = list;
            }
            list.Add(p);
        }
    }

    /// <summary>聚类距离：水平体素步长均值 × 倍数，与协议 VoxelGrid.x / .z 一致。</summary>
    public static float ClusterRadiusMeters(Vector3 cellMeters, float multiplier)
    {
        return (cellMeters.x + cellMeters.z) * 0.5f * multiplier;
    }

    // 层内聚类：量产在此调用平面 DBSCAN 封装（XZ）或三维 DBSCAN 封装，
    // 输入为单层点列、ClusterRadiusMeters 返回值、最小点数等。

    /// <summary>对一条 XZ 闭合轮廓挤出侧面；顶底面需在各自高度再做凸包扇剖分后并入同一 Mesh。</summary>
    public static void ExtrudeClosedContour(
        IReadOnlyList<Vector3> ringXZAtLayerMid,
        float layerMidY,
        float halfThickness,
        List<Vector3> verts,
        List<int> tris)
    {
        verts.Clear();
        tris.Clear();
        float topY = layerMidY + halfThickness;
        float bottomY = layerMidY - halfThickness;
        int n = ringXZAtLayerMid.Count;
        for (int i = 0; i < n; i++)
        {
            Vector3 xz = ringXZAtLayerMid[i];
            verts.Add(new Vector3(xz.x, topY, xz.z));
            verts.Add(new Vector3(xz.x, bottomY, xz.z));
        }
        for (int i = 0; i < n; i++)
        {
            int next = (i + 1) % n;
            int t0 = i * 2, t1 = next * 2, b0 = t0 + 1, b1 = t1 + 1;
            tris.Add(t1); tris.Add(b0); tris.Add(t0);
            tris.Add(b1); tris.Add(b0); tris.Add(t1);
        }
    }
}
```

---

## 结语

除了本文整理的这两种落地的方案，业界也在不断探索更高效的可视化方法。但是，泊车OCC渲染是SR里对性能要求很高的模块，哪怕是“我的世界”模式，也很容易触碰到车机系统的性能红线，落地时需要重点优化算力开销。