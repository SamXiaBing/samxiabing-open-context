---
title: "智驾SR开发：从输入数据看“线”的五种生成方式"
date: 2026-05-08
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇我们聊了智驾SR最基础的点与坐标系，顺着往下走，自然就要讲到**画线**，比如SR软件中看到的道路线、引导线、轨迹线等，本篇文章尝试从数据输入的角度，梳理一下这些“线”是怎么画出来的。

**我们屏幕上看到的"线"，本质上都不是线，是一块面片，贴在地面上的条带网格**：有顶点、有三角面、最后再贴上对应纹理，才变成我们看到的线。咱们从最基础的地方切入：总结一下不同输入数据，分别是怎么生成网格的。

---

## 一、一组有序点 + 线宽

**输入**：这是我们日常开发最常碰到的情况，比如行车引导线，泊车轨迹线大多是这种输入。用一串排好顺序的三维点数组（至少两个点）表达线的中心线，再额外给一个线宽参数。

> 有时线宽是取默认值，上游也不一定给，比如轨迹线宽度默认给3.5米去算。

**怎么生成 Mesh**：用这种数据去绘制线，就如同拿着一根铁丝，沿着点的顺序掰弯。在每个点上，我们先算一下铁丝往哪个方向走（切线方向），然后垂直于这个方向，贴在地面**往左往右各偏移半个线宽**，这样我们就得到了左右两条边界的点。

最后把左右顶点按顺序一对一对连起来，每两个相邻的对拼成一个四边形，再把四边形拆成两个三角形，一块完整的条带Mesh就出来了。

*[配图见公众号原文]*

**代码示例（中心折线 → 左右顶点 + 三角条带索引）**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class RibbonFromCenterLine
{
    /// <summary>折线顶点 i 处的切向：端点用单侧差分，中间用前后平均。</summary>
    public static Vector3 TangentAt(IReadOnlyList<Vector3> path, int i)
    {
        int last = path.Count - 1;
        if (i <= 0) return path[1] - path[0];
        if (i >= last) return path[last] - path[last - 1];
        return (path[i + 1] - path[i - 1]);
    }

    /// <summary>输出顶点顺序：每截面 [左, 右] 交替，共 2*path.Count 个顶点。</summary>
    public static void BuildVertices(IReadOnlyList<Vector3> path, float lineWidth, Vector3 worldUp,
        List<Vector3> verts)
    {
        verts.Clear();
        float half = 0.5f * lineWidth;
        for (int i = 0; i < path.Count; i++)
        {
            Vector3 t = TangentAt(path, i);
            if (t.sqrMagnitude < 1e-10f) { verts.Add(path[i]); verts.Add(path[i]); continue; }
            t.Normalize();
            Vector3 side = Vector3.Cross(worldUp, t).normalized;
            verts.Add(path[i] - half * side);
            verts.Add(path[i] + half * side);
        }
    }

    /// <summary>条带三角索引：与 BuildVertices 的顶点顺序一致。</summary>
    public static void BuildTriangleStripIndices(int pathVertexCount, List<int> indices)
    {
        indices.Clear();
        for (int i = 0; i < pathVertexCount - 1; i++)
        {
            int l0 = i * 2, r0 = l0 + 1, l1 = l0 + 2, r1 = l0 + 3;
            indices.Add(l0); indices.Add(r0); indices.Add(l1);
            indices.Add(r0); indices.Add(r1); indices.Add(l1);
        }
    }
}

```

---

## 二、左右各一组有序点

**输入**：这种输入是直接给出**条带的左右两条边缘**：左边一串点、右边一串点，一般两边点数一致（如果不一致需要先插值对齐）

**怎么生成 Mesh**：其实和第一种方法逻辑几乎完全一样，只是不需要我们自己做左右偏移了。只要保证左右点按序号一一对应，同一序号的左右点连起来就是一条横截边，顺着路径把这些横截边连起来，就能得到完整条带，三角索引的生成方式和第一种完全一样，可以直接复用代码。

*[配图见公众号原文]*

**代码示例（左右轨顶点 → 四边形条带索引）**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class RibbonFromDualRails
{
    /// <summary>left[i] 与 right[i] 为同一截面上的左右点，二者长度须相等。</summary>
    public static void BuildVertices(IReadOnlyList<Vector3> left, IReadOnlyList<Vector3> right,
        List<Vector3> verts)
    {
        verts.Clear();
        int n = left.Count;
        for (int i = 0; i < n; i++)
        {
            verts.Add(left[i]);
            verts.Add(right[i]);
        }
    }

    public static void BuildTriangleStripIndices(int railVertexCount, List<int> indices)
    {
        indices.Clear();
        for (int i = 0; i < railVertexCount - 1; i++)
        {
            int l0 = i * 2, r0 = l0 + 1, l1 = l0 + 2, r1 = l0 + 3;
            indices.Add(l0); indices.Add(r0); indices.Add(l1);
            indices.Add(r0); indices.Add(r1); indices.Add(l1);
        }
    }
}

```

---

## 三、三次多项式参数

**输入**：这里的三次多项式指最高次为3的一元多项式，一般写成公式：

*[配图见公众号原文]*

s常当作参数（例如沿路的里程、归一化到[0,1]的进度），c0至c3是系数，由要经过哪些点、端点斜率是多少等条件定下来。这种方式只用四个系数就能表达一条光滑参数曲线，工程上常用来压缩、传输整段弯曲线，不需要逐点发送坐标。

**怎么生成 Mesh**：我们只需要在曲线的有效参数范围内，按固定步长逐点计算坐标，把计算结果连成折线，之后就可以直接复用 **有序点+线宽** 的处理流程了。步长一般根据需求选：步长太小会生成过多顶点浪费性能，步长太大拐弯位置会变成明显的折线，宽线尤其明显，一般选0.1-0.5米步长就够用了。

*[配图见公众号原文]*

**代码示例（一维参数域上的三次多项式 → 有序空间点）**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class CubicCurveSampler
{
    /// <summary>标量三次：f(s)=(((c3*s+c2)*s+c1)*s+c0)，用于平面曲线时常见两组系数分别驱动 x、z。</summary>
    public static float EvalScalar(float c0, float c1, float c2, float c3, float s)
    {
        return ((c3 * s + c2) * s + c1) * s + c0;
    }

    /// <summary>在 [rangeStart, rangeEnd] 上按固定步长采样到 List（含首尾）。</summary>
    public static void SampleToPolylineXZ(float c0x, float c1x, float c2x, float c3x,
        float c0z, float c1z, float c2z, float c3z,
        float rangeStart, float rangeEnd, float step,
        float y, List<Vector3> path)
    {
        path.Clear();
        if (rangeEnd < rangeStart) (rangeStart, rangeEnd) = (rangeEnd, rangeStart);
        path.Add(new Vector3(EvalScalar(c0x, c1x, c2x, c3x, rangeStart), y,
            EvalScalar(c0z, c1z, c2z, c3z, rangeStart)));
        for (float s = rangeStart + step; s < rangeEnd - 1e-4f; s += step)
        {
            path.Add(new Vector3(EvalScalar(c0x, c1x, c2x, c3x, s), y,
                EvalScalar(c0z, c1z, c2z, c3z, s)));
        }
        path.Add(new Vector3(EvalScalar(c0x, c1x, c2x, c3x, rangeEnd), y,
            EvalScalar(c0z, c1z, c2z, c3z, rangeEnd)));
    }
}

```

---

## 四、只有两个点（停止线、简易标线）

**输入**：本质上就是两个端点，再加宽度和朝向约定。

**怎么生成 Mesh**：和第一种方法完全一样，只是它是最短的折线形式——只有两个顶点组成一段。

*[配图见公众号原文]*

**关键代码（与一类相同，仅输入长度为 2）**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class TwoPointRibbon
{
    public static void Build(Vector3 a, Vector3 b, float lineWidth, Vector3 worldUp,
        List<Vector3> verts, List<int> indices)
    {
        var path = new List<Vector3> { a, b };
        RibbonFromCenterLine.BuildVertices(path, lineWidth, worldUp, verts);
        RibbonFromCenterLine.BuildTriangleStripIndices(path.Count, indices);
    }
}

```

---

## 五、只要往一侧扩（警示条带、半边铺色）

**输入**：一条折线 + 约定往左还是往右扩（或直接把一侧宽度设为0），这种场景比较少见。

**怎么生成 Mesh**：和第一种方法很像，只是左右不对称：一侧贴着中心线不动，另一侧照常做偏移。

*[配图见公众号原文]*

**关键代码（一侧偏移为 0，另一侧为 整个线宽）**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class OneSidedRibbon
{
    public static void BuildVertices(IReadOnlyList<Vector3> path, float fullWidth, Vector3 worldUp,
        bool offsetToPositiveSide, List<Vector3> verts)
    {
        verts.Clear();
        float sign = offsetToPositiveSide ? 1f : -1f;
        for (int i = 0; i < path.Count; i++)
        {
            Vector3 t = RibbonFromCenterLine.TangentAt(path, i);
            if (t.sqrMagnitude < 1e-10f) { verts.Add(path[i]); verts.Add(path[i]); continue; }
            t.Normalize();
            Vector3 side = Vector3.Cross(worldUp, t).normalized;
            verts.Add(path[i]);
            verts.Add(path[i] + sign * fullWidth * side);
        }
    }
}

```

---

## 总结


| 输入        | 核心操作          |
| --------- | ------------- |
| 有序点 + 宽   | 沿路径左右扩，连四边形   |
| 左点列 + 右点列 | 左右点对齐连过去      |
| 曲线参数      | 先采样成点，再同上     |
| 只有两个点     | 最短的一条折线       |
| 只扩一侧      | 不对称偏移；注意三角形正反 |


---

## 结语

除了上述五种基础情况，还有一些组合场景：

① 数据结构组合：比如曲线参数+有序点混合输入；

② 多线段组合：分数组给出多个线段，每个线段都包含有序点数组。

这些组合场景，只需要基于上述基础方法，做区分和循环处理就可以了。

不过线的绘制总会碰到一些意外问题，需要HMI开发时在应用层做 **兜底** 处理，下一篇我会整理实际开发中碰到过的那些常见 **坑** 。