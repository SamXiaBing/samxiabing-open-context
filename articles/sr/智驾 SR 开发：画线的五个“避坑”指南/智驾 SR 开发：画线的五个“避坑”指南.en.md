---
title: "Smart-Driving SR Development: Five Pitfalls to Avoid When Drawing Lines"
lang: en
date: 2026-05-09
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> In smart-driving cockpit SR (Surround Reality) development, generating 3D ribbon meshes from a centerline or from left/right boundaries (used for trajectory lines, guidance lines, lane bands, etc.) is a very common requirement. But all too often, geometry and data-quality issues produce unexpected rendering artifacts.

This post covers the five most common pitfalls: **twisting and wrinkling on longitudinal slopes, sparse polyline segments, performance problems with overly dense polylines, fold-back spikes, and index mismatch between dual boundaries**. These are the five pitfalls and their fixes I've collected from mass-production development.

---

## 1. Visible Wrinkles in the Trajectory Line on Downhill Curves

*[Figures omitted; see the original WeChat article]*

### Symptom

In the mapping result of a memory-parking feature, as the path enters an underground garage with a **downhill + turn** section, it develops **wrinkles/bumps**, like a thin sheet of paper that has been folded. The visual artifact comes from multiple triangles bulging and collapsing; when the trajectory material is semi-transparent, you can also see shifts in color shading.

### Root Cause

If you compute the lateral offset directly from the 3D path tangent, the direction carries a pronounced longitudinal component, so the lateral offset no longer lies in the horizontal plane. After offsetting, the Y values of the left/right vertices become inconsistent, and the ribbon naturally cannot lie flat on the road. In other words, **at the same point index the left and right vertices are at different heights**; with segments alternating high and low, triangulation easily produces some faces pulled upward and others pushed downward.

### Fix

Rebuild the tangent by **projecting it onto the horizontal plane** (say, the XZ plane): keep only the horizontal component and normalize it, then compute the offset with the original formula. That way, at every index, **both the left and right vertices inherit the original height of the centerline point**. Longitudinal slopes are expressed by the centerline itself, so the lateral offset no longer introduces any height difference.

### Example Code

```csharp
using UnityEngine;

/// <summary>Sketch: widen only within the horizontal (XZ) plane; left/right edges share the same Y as the centerline at the same index, preventing ribbon twisting on longitudinal slopes.</summary>
static class RibbonExpandFlat
{
    static Vector3 FlattenXZ(Vector3 v) => new Vector3(v.x, 0f, v.z);

    const float FlatEps2 = 1e-10f;

    /// <summary>Interior vertex: same directed-edge convention as the common polyline Expand (incoming segment along prev→cur, outgoing along the horizontal projection of cur→next).</summary>
    public static Vector3 OffsetPointInterior(Vector3 prev, Vector3 cur, Vector3 next, float signedHalfWidth)
    {
        Vector3 curIn = FlattenXZ(prev - cur);   // Horizontal direction pointing to the previous point
        Vector3 curOut = FlattenXZ(next - cur); // Horizontal direction pointing to the next point
        if (curIn.sqrMagnitude < FlatEps2) curIn = curOut;
        if (curOut.sqrMagnitude < FlatEps2) curOut = curIn;
        curIn.Normalize();
        curOut.Normalize();

        float halfTurnDeg = Vector3.Angle(curIn, curOut) * 0.5f;
        Vector3 cross = Vector3.Cross(curIn, curOut);
        float signedHalfDeg = cross.y >= 0f ? halfTurnDeg : -halfTurnDeg;

        // Rotate the "incoming segment" around the vertical axis by the signed half angle to get the unit normal along the corner bisector (still within the horizontal plane)
        Vector3 nor = Quaternion.AngleAxis(signedHalfDeg, Vector3.up) * curIn;
        nor.y = 0f;
        if (nor.sqrMagnitude < FlatEps2)
            nor = Quaternion.AngleAxis(90f, Vector3.up) * curIn;
        nor.Normalize();

        float miter = Mathf.Abs(signedHalfDeg) < 1f
            ? 1f
            : 1f / Mathf.Sin(Mathf.Abs(signedHalfDeg) * Mathf.Deg2Rad);

        return cur - nor * (signedHalfWidth * miter);
    }

    /// <summary>Start point: outgoing segment only; the normal is the outgoing segment rotated 90° counterclockwise (matches the common Expand first-point convention).</summary>
    public static Vector3 OffsetPointStart(Vector3 cur, Vector3 next, float signedHalfWidth)
    {
        Vector3 curOut = FlattenXZ(next - cur);
        if (curOut.sqrMagnitude < FlatEps2) return cur;
        curOut.Normalize();
        Vector3 nor = Quaternion.AngleAxis(-90f, Vector3.up) * curOut;
        nor.y = 0f;
        nor.Normalize();
        return cur - nor * signedHalfWidth;
    }

    /// <summary>End point: incoming segment only; the normal is the incoming segment rotated 90° clockwise (matches the common Expand last-point convention).</summary>
    public static Vector3 OffsetPointEnd(Vector3 prev, Vector3 cur, float signedHalfWidth)
    {
        Vector3 curIn = FlattenXZ(prev - cur);
        if (curIn.sqrMagnitude < FlatEps2) return cur;
        curIn.Normalize();
        Vector3 nor = Quaternion.AngleAxis(90f, Vector3.up) * curIn;
        nor.y = 0f;
        nor.Normalize();
        return cur - nor * signedHalfWidth;
    }
}

```

---

## 2. Sharp Corners at the Tip of the Guidance Line

*[Figures omitted; see the original WeChat article]*

### Symptom

A sharp corner occasionally appears at the top of the guidance line in front of the vehicle. It is clearly caused by the smart-driving data, but we still need a defensive fix.

### Root Cause

In the centerline point array, the points maintain a constant spacing at first, but then suddenly **two points end up spanning several meters**. When extruding and widening the ribbon, the lateral offset direction at each vertex is computed jointly from the tangents of the polyline segments before and after — whether you use angle bisecting, mitering, or endpoint single-sided tangent extrapolation. When the incoming segment is extremely short and the outgoing one extremely long (or vice versa):

1. The combined tangent/normal at the vertex is almost entirely dominated by the extra-long segment; the short edge contributes almost nothing to the corner.
2. The next vertex switches to a different long/short ratio, so the lateral direction jumps from point to point.

In the end, the left/right silhouette of the mesh changes direction abruptly in that local area — what you see is a jarring geometric spike. Even if the material texture isn't stretched, the silhouette itself is already warped.

### Fix

The core goal is to make the geometry on both sides of each vertex contribute "evenly" to the tangent computation, preventing a single extra-long side from dominating the direction: set a segment-length cap as a safety net — whenever the distance between two points ||P_{i+1}-P_i|| > L_max, insert linearly interpolated points along that segment so that every segment stays within the threshold.

### Example Code

```csharp
using System.Collections.Generic;
using UnityEngine;

static class PolylineSubdivide
{
    /// <summary>Whenever two points are farther apart than maxSegLen, inserts linearly interpolated intermediate points.</summary>
    public static List<Vector3> LimitSegmentLength(IReadOnlyList<Vector3> src, float maxSegLen)
    {
        var dst = new List<Vector3> { src[0] };
        float maxSqr = maxSegLen * maxSegLen;
        for (int i = 0; i < src.Count - 1; i++)
        {
            Vector3 a = src[i], b = src[i + 1];
            Vector3 ab = b - a;
            float len = ab.magnitude;
            if (len < 1e-6f) continue;

            int cuts = Mathf.CeilToInt(len / maxSegLen);
            for (int k = 1; k < cuts; k++)
                dst.Add(Vector3.Lerp(a, b, (float)k / cuts));
            dst.Add(b);
        }
        return dst;
    }
}

```

---

## 3. Heavy Performance Cost When Many Long Trajectory Lines Are Drawn

*[Figures omitted; see the original WeChat article]*

### Symptom

On every data frame, regardless of line length, hundreds or thousands of vertices are all sent to be computed and built into the mesh. Both the background thread and the main thread show timing spikes, seriously hurting frame-rate stability.

### Root Cause

Too many redundant vertices add needless compute, memory, and rendering cost — completely unnecessary.

### Fix

**Decimation**: merge adjacent points whose distance is below a threshold (typically 0.1 m) directly.

> Don't reverse the order of decimation and the interpolation/subdivision from the previous step: in general, first merge near points to denoise, then add points according to the maximum segment length — otherwise the two operations cancel each other out.

### Example Code

```csharp
using System.Collections.Generic;
using UnityEngine;

static class PolylineDedup
{
    public static List<Vector3> DropNearDuplicates(IReadOnlyList<Vector3> src, float minDist)
    {
        var dst = new List<Vector3>(src.Count) { src[0] };
        Vector3 last = src[0];
        float minSqr = minDist * minDist;
        for (int i = 1; i < src.Count; i++)
        {
            if ((src[i] - last).sqrMagnitude >= minSqr)
            {
                dst.Add(src[i]);
                last = src[i];
            }
        }
        return dst;
    }
}

```

---

## 4. Spikes Where the Parking Trajectory Folds Back

*[Figures omitted; see the original WeChat article]*

### Symptom

Real driving frequently involves avoidance maneuvers and repeated in-and-out parking adjustments, producing local fold-backs like "**forward → reverse → forward again**". The point sequence is still monotonic by index, but the ribbon generates extremely long miters or **needle-like triangles**, which look very strange.

### Fix

**Scan repeatedly and delete the middle spike points of large-angle fold-backs**: scan the point list continuously; whenever the dot product of the directions before and after three consecutive points falls below a threshold (corresponding to a fold angle greater than 100°, nearly a U-turn), delete the middle spike point; scan repeatedly until no deletable spikes remain, eliminating the seeds of the needle-like triangles caused by local fold-backs.

### Example Code

```csharp
using System.Collections.Generic;
using UnityEngine;

static class PolylineFoldback
{
    const float DotThreshold = -0.3f; // Roughly a fold angle greater than 100°

    /// <summary>Scans repeatedly and removes interior points that create sharp fold-backs.</summary>
    public static void RemoveZigZagSpikes(List<Vector3> pts)
    {
        bool removed;
        do
        {
            removed = false;
            for (int i = 0; i < pts.Count - 2; i++)
            {
                Vector3 d1 = (pts[i + 1] - pts[i]).normalized;
                Vector3 d2 = (pts[i + 2] - pts[i + 1]).normalized;
                if (Vector3.Dot(d1, d2) < DotThreshold)
                {
                    pts.RemoveAt(i + 1);
                    removed = true;
                    break;
                }
            }
        } while (removed);
    }
}

```

---

## 5. Twisted, Misaligned Ribbon on S-Curves and Wide Bends

![pitfall_05_dual_rail_resample](./pitfall_05_dual_rail_resample.png)

### Symptom

Smart driving sometimes delivers **left/right lane lines or road boundaries** directly, with the same point count and a **semantically same-index** correspondence. On **gentle curves** this pairing is fine; on **S-curves/wide bends**, the left and right points at the same index can be **far apart in space**, and forcing triangle strips between them produces **sliver triangles that cut across the interior of the curve**, with odd texture and lighting.

### Root Cause

The array index `i` is being treated as the correspondence of **the same mileage cross-section**. What we actually need is correspondence in **arc-length parameter**, not index correspondence.

### Fix

**Compute the cumulative arc lengths separately, then resample both boundaries at a unified step to align them:**

1. First compute the cumulative arc length of the left and right boundary polylines separately.
2. Starting from 0, take sample points at a fixed step; at each step position, interpolate on both boundaries to obtain the corresponding vertices.
3. Build the ribbon from the resampled, aligned vertex pairs, ensuring that the left/right vertices at the same sample position are aligned in arc-length parameter, rather than paired simply by array index.

### Example Code

```csharp
using System.Collections.Generic;
using UnityEngine;

static class DualRailResample
{
    static float[] CumulativeLengths(IReadOnlyList<Vector3> poly)
    {
        var c = new float[poly.Count];
        for (int i = 1; i < poly.Count; i++)
            c[i] = c[i - 1] + Vector3.Distance(poly[i - 1], poly[i]);
        return c;
    }

    static Vector3 SampleAtArcLength(IReadOnlyList<Vector3> poly, float[] cum, float s)
    {
        // Binary search or linear scan to find the containing segment, then Lerp — abbreviated here as a linear scan for illustration
        int seg = 0;
        while (seg < poly.Count - 1 && cum[seg + 1] < s) seg++;
        seg = Mathf.Clamp(seg, 0, poly.Count - 2);
        float t = Mathf.InverseLerp(cum[seg], cum[seg + 1], s);
        return Vector3.Lerp(poly[seg], poly[seg + 1], t);
    }

    public static void BuildMatchedStrip(
        IReadOnlyList<Vector3> left, IReadOnlyList<Vector3> right,
        float stepMeters, List<Vector3> outL, List<Vector3> outR)
    {
        outL.Clear(); outR.Clear();
        float[] lC = CumulativeLengths(left);
        float[] rC = CumulativeLengths(right);
        float total = Mathf.Max(lC[^1], rC[^1]);
        for (float s = 0f; s <= total; s += stepMeters)
        {
            outL.Add(SampleAtArcLength(left, lC, Mathf.Min(s, lC[^1])));
            outR.Add(SampleAtArcLength(right, rC, Mathf.Min(s, rC[^1])));
        }
    }
}

```

---

## Summary


| **Pitfall** | **Core Problem** | **Fix** |
| ------ | --------------- | --------------- |
| Longitudinal-slope wrinkles | 3D tangent offset causes height differences between left/right vertices | Rebuild tangents in the horizontal plane; widen horizontally |
| Sharp corners from large gaps | Geometric undersampling; abrupt direction change | Cap the maximum segment length; insert interpolated points |
| Poor performance from over-dense points | Redundant vertices add needless cost | Shape-preserving decimation; distance filtering |
| Fold-back spikes | Sharp local angles cause numerical blow-up | Fold-angle detection + window trimming; limit miter length |
| Dual-boundary mismatch distortion | Index alignment ≠ arc-length alignment | Compute arc lengths separately; resample on a unified parameter |


---

## Closing Thoughts

At this point we've fully covered the basic logic and engineering issues of "lines" in smart-driving SR. But SR reconstructs the real driving environment with more than line elements like paths and lane markings — it also needs occupancy grids (OCC) to represent drivable areas, that is, "surfaces". In the next post, we'll look at the engineering problems of drawing "surfaces".
