---
title: "Smart Driving SR Development: Five Ways to Generate Lines from Input Data"
lang: en
date: 2026-05-08
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> In the previous article we covered the most basic elements of smart-driving SR: points and coordinate systems. Continuing from there, the next natural topic is **drawing lines** — the road lanes, guidance lines, trajectory lines and so on that you see in an SR application. In this article, I'll try to organize how these "lines" get drawn, from the perspective of data input.

**The "lines" we see on screen are not lines at all — deep down, every one of them is a strip mesh laid flat on the ground**: vertices, triangles, and finally a texture on top — that's what turns it into the line we see. Let's start from the basics: a rundown of how each type of input data gets turned into a mesh.

---

## 1. An ordered list of points + line width

**Input**: This is the case we run into most often in day-to-day development. Driving guidance lines and parking trajectory lines mostly use this kind of input. The centerline of the line is expressed as an ordered array of 3D points (at least two points), plus an extra line-width parameter.

> Sometimes the width just takes a default value — the upstream module doesn't necessarily provide one. For example, a trajectory line might default to 3.5 meters for the calculation.

**How the mesh is generated**: Drawing a line with this kind of data is like bending a piece of wire along the points in order. At each point, we first work out which direction the wire is heading (the tangent direction), then, perpendicular to that direction and flush with the ground, **offset half a line width to the left and to the right**. That gives us the points of the left and right boundaries.

Finally, connect the left and right vertices pair by pair in order. Every two adjacent pairs form a quad, and each quad is split into two triangles — and there you have a complete ribbon mesh.

*[Figures omitted; see the original WeChat article]*

**Code sample (center polyline → left/right vertices + triangle-strip indices)**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class RibbonFromCenterLine
{
    /// <summary>Tangent at polyline vertex i: one-sided difference at the endpoints, averaged forward/backward difference in the middle.</summary>
    public static Vector3 TangentAt(IReadOnlyList<Vector3> path, int i)
    {
        int last = path.Count - 1;
        if (i <= 0) return path[1] - path[0];
        if (i >= last) return path[last] - path[last - 1];
        return (path[i + 1] - path[i - 1]);
    }

    /// <summary>Vertex output order: [left, right] alternating per cross-section, 2*path.Count vertices in total.</summary>
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

    /// <summary>Triangle-strip indices: consistent with the vertex order produced by BuildVertices.</summary>
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

## 2. One ordered set of points on each side (left + right)

**Input**: This input directly provides **both edges of the ribbon**: one list of points for the left edge and one for the right, usually with the same point count on both sides (if not, they need to be aligned by interpolation first).

**How the mesh is generated**: The logic is almost identical to the first method — we simply don't have to do the left/right offsetting ourselves. As long as the left and right points correspond one-to-one by index, connecting the left and right points of the same index gives you a cross-section edge; string these cross-section edges along the path and you get the full ribbon. The triangle indices are generated exactly the same way as in the first method, so the code can be reused as is.

*[Figures omitted; see the original WeChat article]*

**Code sample (dual-rail vertices → quad ribbon indices)**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class RibbonFromDualRails
{
    /// <summary>left[i] and right[i] are the left/right points on the same cross-section; the two lists must have equal length.</summary>
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

## 3. Cubic polynomial parameters

**Input**: The cubic polynomial here means a univariate polynomial of degree at most 3, usually written as:

*[Figures omitted; see the original WeChat article]*

s is typically treated as the parameter (for example, mileage along the road, or a progress value normalized to [0,1]), while c0 through c3 are the coefficients, determined by conditions such as which points the curve must pass through and what the endpoint slopes are. This representation expresses a smooth parametric curve with only four coefficients, so it's commonly used in engineering to compress and transmit a whole curved segment without sending coordinates point by point.

**How the mesh is generated**: All we need to do is evaluate coordinates point by point at a fixed step across the curve's valid parameter range, connect the results into a polyline, and then reuse the **ordered points + line width** pipeline directly. The step size is usually chosen per requirements: too small a step generates too many vertices and wastes performance; too large a step makes corners turn into visible polylines — especially noticeable with wide lines. In practice, a step of 0.1–0.5 meters is good enough.

*[Figures omitted; see the original WeChat article]*

**Code sample (cubic polynomials over a 1D parameter domain → ordered spatial points)**

```csharp
using System.Collections.Generic;
using UnityEngine;

static class CubicCurveSampler
{
    /// <summary>Scalar cubic: f(s)=(((c3*s+c2)*s+c1)*s+c0). For planar curves, two coefficient sets typically drive x and z respectively.</summary>
    public static float EvalScalar(float c0, float c1, float c2, float c3, float s)
    {
        return ((c3 * s + c2) * s + c1) * s + c0;
    }

    /// <summary>Samples over [rangeStart, rangeEnd] at a fixed step into a List (both endpoints included).</summary>
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

## 4. Just two points (stop lines, simple road markings)

**Input**: Essentially just two endpoints, plus a width and an orientation convention.

**How the mesh is generated**: Exactly the same as the first method — it's just the shortest possible polyline, a single segment made of two vertices.

*[Figures omitted; see the original WeChat article]*

**Key code (same as case 1, with an input of length 2)**

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

## 5. Extrude to one side only (warning ribbons, half-width coloring)

**Input**: A polyline plus a convention for whether to extrude to the left or to the right (or simply set one side's width to 0). This case is relatively rare.

**How the mesh is generated**: Very similar to the first method, except that it's asymmetric: one side stays flush against the centerline, while the other side gets the usual offset.

*[Figures omitted; see the original WeChat article]*

**Key code (offset of 0 on one side, the full line width on the other)**

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

## Summary


| Input | Core operation |
| --------- | ------------- |
| Ordered points + width | Extrude left/right along the path, connect quads |
| Left point list + right point list | Align the left/right points and connect them |
| Curve parameters | Sample into points first, then same as above |
| Just two points | The shortest possible polyline |
| One side only | Asymmetric offset; mind the triangle winding |


---

## Closing thoughts

Beyond the five basic cases above, there are also some combined scenarios:

① Combined data structures: for example, mixed input of curve parameters + ordered points;

② Multiple segments: several line segments delivered as separate arrays, each containing its own ordered point array.

For these combined scenarios, you only need to build on the basic methods above, with some branching and looping.

That said, drawing lines always runs into unexpected problems, so as an HMI developer you need to add **fallback** handling at the application layer. In the next article, I'll go over the common **pitfalls** I've hit in real-world development.
