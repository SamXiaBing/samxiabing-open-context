---
title: "Intelligent Driving SR Development: Three Engineering Approaches for Rendering the Drivable Area"
date: 2026-05-11
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In intelligent driving cockpit SR (Surround Reality) development, rendering the drivable area output by perception/planning as a semi-transparent pattern laid over the road surface is a must-have capability for virtually any SR application. Drivable area rendering is a typical manifestation of OCC (Occupancy Grid) technology: it not only enriches the visual expressiveness of the SR interface, but also helps users build basic trust in the perception system.

This article covers the three most common drivable-area implementation approaches in cockpit SR: **checkerboard bitmask, left/right dual boundary strips, and an ordered vertex list along the region boundary**. For each one I'll lay out the implementation logic, the engineering optimizations, and the common pitfalls, so you can quickly match one to your project scenario.

---

## 1. Bitmask Checkerboard

This is a common category of data input, suited to protocols that deliver the data as a **bitmask**.

### 1.1 Data Format

Picture the area around the vehicle as a **fixed-size sheet of grid paper**: each cell occupies exactly **1 bit**, and that bit says whether the cell **is or isn't** drivable. All the cells' bits are then packed, per the agreed convention—for example starting from the bottom-right cell of the grid, right to left, bottom to top—into a **byte array** and sent to the application layer. Sometimes the data is converted to a base64 string for transmission instead.

(See the diagram below for the top-down grid layout: usually centered on the vehicle, longer ahead than behind, symmetric left-right 👇)

![occ_02_grid_layout_car](./occ_02_grid_layout_car.png)

### 1.2 Implementation Steps

We don't need to build triangles for every individual cell. In practice, 4 vertices (one large quad) are enough to cover the entire drivable area:

1. **Spatial grid**: Lay a large rectangular grid on the road surface beneath the vehicle. Its size must exactly match the OCC range defined by the ADAS supplier, and it should be raised slightly above the ground to avoid Z-fighting flicker with the ground model.

2. **Texture preparation**: Create a RenderTexture in advance whose width × height resolution matches the drivable area, to store the per-cell passability information as alpha values.

3. **GPU parallel decoding**: Use a Compute Shader to spin up parallel threads, one per grid pixel. Each thread extracts the bit at its position from the byte stream per the protocol convention and writes the result into the RenderTexture (semi-transparent if passable, fully transparent if not).

4. **Final shading**: An ordinary fragment shader just samples this mask texture and multiplies it by the corresponding color and opacity. Depending on the design requirements, you'll usually also add edge softening and day/night mode responses.

*[Figures omitted; see the original WeChat article]*

### 1.3 Optimization Tips

- **Duplicate detection**: Each time OCC data arrives, first check—based on the data's characteristics—whether it's identical to the previous frame. If it is, skip decoding and all subsequent compute/draw work.  
- **Resource reuse**: As long as the grid resolution doesn't change, create the RenderTexture and ComputeBuffer only once and just update their contents each time, avoiding repeated allocation and release.

- **Reduced update frequency**: When the protocol push rate is **significantly higher** than the rate the visuals actually need, you can update every other frame or merge refreshes—as long as the result stays visually acceptable—to relieve decode and GPU write pressure.  
- **Visual polish:** soften the edges to avoid aliasing.

### 1.4 Sample Code

**Outer orchestration**

```csharp
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>Demonstrates only "upload → dispatch → bind material"</summary>
public sealed class LatticeMaskHost : MonoBehaviour
{
    public ComputeShader bitUnpackCs;     // may be a different asset name in a real project
    public Material groundTintMat;
    public int cols = 240;
    public int rows = 440;

    RenderTexture _occupancyAtlas;
    ComputeBuffer _gpuWords;
    byte[] _freezeForDiff;

    public void OnNewBlob(byte[] blob)
    {
        if (blob == null || blob.Length == 0) return;
        if (_freezeForDiff != null && _freezeForDiff.Length == blob.Length && BytesLikelySame(_freezeForDiff, blob))
            return;

        _freezeForDiff = (byte[])blob.Clone();

        PrepareTargets(blob.Length);
        var packed = PackLittleEndianWords(blob); // fictional: real endianness/alignment rules follow the protocol
        _gpuWords.SetData(packed);

        int handle = bitUnpackCs.FindKernel("Cs_ScribbleLattice"); // fictional kernel name
        bitUnpackCs.SetBuffer(handle, "_WordHeap", _gpuWords);
        bitUnpackCs.SetTexture(handle, "_ScratchAtlas", _occupancyAtlas);
        bitUnpackCs.SetInts("_LatticeDims", cols, rows);

        int tgX = (cols + 15) / 16;   // not tied to real thread-group sizing, illustration only
        int tgY = (rows + 15) / 16;
        bitUnpackCs.Dispatch(handle, tgX, tgY, 1);

        groundTintMat.SetTexture("_LatticeAlpha", _occupancyAtlas);
    }

    static bool BytesLikelySame(byte[] x, byte[] y)
    {
        for (int i = 0; i < x.Length; i++)
            if (x[i] != y[i]) return false;
        return true;
    }

    void PrepareTargets(int blobBytes)
    {
        if (_occupancyAtlas == null || _occupancyAtlas.width != cols || _occupancyAtlas.height != rows)
        {
            _occupancyAtlas?.Release();
            _occupancyAtlas = new RenderTexture(cols, rows, 0, RenderTextureFormat.ARGB32)
            {
                enableRandomWrite = true,
                filterMode = FilterMode.Bilinear
            };
            _occupancyAtlas.Create();
        }

        int wordSlots = (blobBytes + 3) / 4;
        if (_gpuWords == null || _gpuWords.count != wordSlots)
        {
            _gpuWords?.Release();
            _gpuWords = new ComputeBuffer(wordSlots, sizeof(uint));
        }
    }

    /// <summary>Illustrative: packs words little-endian, four bytes at a time; may not match production packing.</summary>
    static uint[] PackLittleEndianWords(byte[] blob)
    {
        int wordCount = (blob.Length + 3) / 4;
        var words = new uint[wordCount];
        for (int w = 0; w < wordCount; w++)
        {
            uint acc = 0;
            for (int b = 0; b < 4; b++)
            {
                int idx = w * 4 + b;
                uint octet = idx < blob.Length ? blob[idx] : 0u;
                acc |= octet << (8 * b);
            }
            words[w] = acc;
        }
        return words;
    }

    void OnDestroy()
    {
        _gpuWords?.Release();
        _occupancyAtlas?.Release();
    }
}

```

**Compute (bit extraction with placeholder logic)**

```hlsl
#pragma kernel Cs_ScribbleLattice

StructuredBuffer<uint> _WordHeap;
RWTexture2D<float4> _ScratchAtlas;
uint2 _LatticeDims;

[numthreads(16, 16, 1)]
void Cs_ScribbleLattice(uint3 tid : SV_DispatchThreadID)
{
    if (tid.x >= _LatticeDims.x || tid.y >= _LatticeDims.y) return;

    // Fictional mapping: row/column → linear pixel index → assumed word/bit (production must align with the protocol table)
    uint linear = tid.y * _LatticeDims.x + tid.x;
    uint wordIx = linear >> 5;
    uint bitIx = linear & 31u;
    uint chunk = _WordHeap[wordIx];
    bool passable = (chunk & (1u << bitIx)) != 0;

    float feather = 1;
    _ScratchAtlas[tid.xy] = passable ? float4(1, 1, 1, 0.55 * feather) : 0;
}

```

**Fragment (fictional uniforms; one Built-in-compatible sampling style)**

```hlsl
sampler2D _LatticeAlpha;
half4 _DryPalette;
half4 _WetPalette;
half _NightMix;

half4 FragTint(float2 uv : TEXCOORD0) : SV_Target
{
    half mask = tex2D(_LatticeAlpha, uv).a;
    half4 baseCol = lerp(_DryPalette, _WetPalette, saturate(_NightMix));
    return half4(baseCol.rgb, baseCol.a * mask);
}

```

---

## 2. Left/Right Dual Boundary Strips

Suited to scenarios with **two independent boundary curves, left and right**, this is another fairly limited form of strip-shaped drivable area in cockpit SR delivery.

### 2.1 Data Format

The protocol delivers curve coefficients for the left and right boundaries. After sampling, the application layer gets two polyline paths, each an ordered sequence of 3D vertices.

### 2.2 Implementation Steps

1. **Arc-length resampling alignment**: First compute the total arc length of each boundary separately, then resample both at a fixed step size so every pair of vertices corresponds to the same mileage position along the road.
2. **Build the triangle mesh**: Pair up the resampled left/right vertices, connect adjacent indices into quads, then split each quad into two triangles. I recommend accumulating UV coordinates in sync with arc length, so the texture stripes don't twist like a braid. 

(See the diagram below for the aligned result 👇)

*[Figures omitted; see the original WeChat article]*

### 2.3 Common Pitfalls

In big S-curves, don't blindly trust **hard pairing by original index**: left and right points at the same original index may be far apart in space, producing thin triangles that cut across the inside of the curve—the result is completely wrong.

*[Figures omitted; see the original WeChat article]*

For the solution, see Chapter 5 of "Intelligent Driving SR Development: Five Pitfalls to Avoid When Drawing Lines", which covers arc-length resampling.

### 2.4 Optimization Tips

- Tie the arc-length resampling step size to vehicle speed and camera distance: larger steps (fewer samples) far away, smaller steps (denser sampling) up close, balancing quality and performance.
- If your project has both the grid and dual-boundary approaches, hard-code the priority in advance to avoid rendering both.
- Raise all meshes uniformly slightly above the ground to avoid Z-fighting flicker with the ground model.

### 2.5 Sample Code

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>Fictional: resamples two independent polylines by "approximate arc-length parameter".</summary>
public static class CorridorResampler
{
    public static void StretchRailsUniform(
        IReadOnlyList<Vector3> polyWest,
        IReadOnlyList<Vector3> polyEast,
        float chopLength,
        List<Vector3> westOut,
        List<Vector3> eastOut)
    {
        westOut.Clear();
        eastOut.Clear();

        float spanWest = MeasurePolyline(polyWest);
        float spanEast = MeasurePolyline(polyEast);
        float runway = Mathf.Max(spanWest, spanEast);

        int slices = Mathf.Max(1, Mathf.CeilToInt(runway / Mathf.Max(chopLength, 1e-4f)));
        for (int slice = 0; slice <= slices; slice++)
        {
            float mileage = Mathf.Min(runway, slice * chopLength);
            westOut.Add(LocateAlong(polyWest, Mathf.Min(mileage, spanWest)));
            eastOut.Add(LocateAlong(polyEast, Mathf.Min(mileage, spanEast)));
        }
    }

    static float MeasurePolyline(IReadOnlyList<Vector3> pts)
    {
        float acc = 0f;
        for (int i = 1; i < pts.Count; i++)
            acc += Vector3.Distance(pts[i - 1], pts[i]);
        return acc;
    }

    /// <summary>Finds a position along a polyline by arc length: linear scan for illustration; use binary search in production.</summary>
    static Vector3 LocateAlong(IReadOnlyList<Vector3> pts, float mileage)
    {
        if (pts.Count == 0) return default;
        if (pts.Count == 1) return pts[0];

        float walked = 0f;
        for (int i = 0; i < pts.Count - 1; i++)
        {
            float seg = Vector3.Distance(pts[i], pts[i + 1]);
            if (walked + seg >= mileage - 1e-5f)
            {
                float u = seg > 1e-6f ? Mathf.Clamp01((mileage - walked) / seg) : 0f;
                return Vector3.Lerp(pts[i], pts[i + 1], u);
            }
            walked += seg;
        }
        return pts[^1];
    }
}

```

---

## 3. Ordered Vertex List Along the Region Boundary

This approach is designed for a single closed drivable region. The key difference from the first two is clear: the input is just **one ordered loop of vertices around the region**, and the goal is to fill in the complete interior mesh of the region, not merely generate an edge strip.

Use case: the protocol delivers an ordered loop of vertices (an area point list) whose semantics are "drivable area" or "OCC polygon boundary" (usually closed, visualized within one plane). Unlike Chapter 2's "two independent curves", there is only **one boundary loop** here, and the target is the **planar triangle mesh of the region interior**, not a strip extruded along a path.

### 3.1 Data Format

The input is a 3D vertex sequence forming **one ordered closed boundary**, with the following conventions:

- **Consistent winding**: Keep the boundary consistently clockwise or counterclockwise; a reversed order flips the triangle normals, which can make the entire region invisible via backface culling.
- **Closed-loop semantics**: Whether the first point is repeated at the end depends on the protocol; in engineering, normalize everything into a "closed loop" before feeding it to triangulation.
- **Project onto the driving plane**: Automotive SR mostly visualizes on the road surface, so vertices are usually **flattened onto the XZ plane (or the agreed horizontal plane)** at a fixed uniform height to avoid Z-fighting with the ground mesh; triangulation then runs on the equivalent 2D polygon.
- **Dirty data**: Self-intersections, duplicate points, collinear spikes, and narrow slits cause triangulation failures or degenerate triangles; they need to be cleaned up during parsing or preprocessing.

### 3.2 Implementation Steps

1. **Step 1: Get the boundary vertices.** First, parse the drivable region's boundary vertex data out of the ADAS communication protocol, yielding an **ordered sequence of vertex coordinates** (either relative to the vehicle body or in global world coordinates).  
You must agree on this with the protocol team in advance: is this vertex sequence already a closed loop (the first and last points are the same point), or does the application layer need to append a point itself to connect head and tail into a closed loop?
2. **Step 2: Project and flatten onto the road.** Since the drivable area is laid over the road surface, we don't need to keep the 3D elevation details, so two operations:
  1. **Project** all 3D vertices **onto the 2D plane of the road**: we usually use the X-Z plane to represent the horizontal plane (the Y axis for height), so only the vertices' X and Z coordinates participate in subsequent geometric calculations.
  2. Uniformly set the Y coordinate (height) to a value **slightly above the road**, so the drivable area mesh doesn't interpenetrate the road model and cause flicker (the classic Z-fighting problem).
3. **Step 3: Clean the dirty data.** Raw data may contain dirty data that breaks later triangulation, so clean up in order:
  1. Remove duplicate vertices that are too close: when two points nearly coincide, keep just one to reduce computation.
  2. Normalize the closure state: if the raw data already repeats the same point at head and tail, drop the redundant one so the closed loop contains no duplicate vertices.
  3. Optionally simplify collinear points: if three points lie on one straight line, drop the middle one—likewise reduces unnecessary computation.
  4. Unify the winding direction: all clockwise or all counterclockwise; a reversed direction flips the triangle normals and the entire region disappears.  
  The classic ear-clipping algorithm's input model is a **planar simple polygon** (no self-intersections, no holes). If the boundary comes from stitching multiple trajectories and ends up self-intersecting, that precondition no longer holds: you must switch to a triangulation implementation that supports non-simple topology, or have upstream guarantee a simple closed loop.
4. **Step 4: Generate the triangle mesh.** Now that we have a clean closed 2D polygon, the next step is to split it into small triangles (only triangles can be rendered by the engine). This step is called triangulation:
  1. **A handy trick for convexity tests**: because we projected onto the XZ plane and the road normal points up (along the Y axis), computing a polygon vertex's convexity only requires taking the Y component of the 3D cross product—it's equivalent to doing the 2D calculation directly in the XZ plane, no extra coordinate conversion needed.
  2. **Output format**: the triangulation outputs a list of indices whose total length is the triangle count × 3; every three indices correspond to one triangle's three vertices. Generally prefer storing the mesh as shared vertices + indices, which saves memory.
  3. **Reliability advice**: if you hit polygons with holes, multiple connected components, extremely narrow slits, or floating-point errors from very large coordinates, just hand the problem to a mature third-party triangulation library. Hand-written ear clipping only works where the protocol already guarantees a very clean contour; in complex scenarios, hand-rolled code almost always breaks.
5. **Step 5: Import into the engine for rendering (write the Mesh).** Assemble the triangulated result into a Mesh asset your engine (say, Unity/Unreal) can consume:
  1. The structure is simply a vertex list + a triangle index list.
  2. Set all normals to point up (or to the local road-surface normal if the road has a slope).
  3. If you only need a flat color fill, the UV coordinates can all be (0,0) for now—it doesn't affect display.
6. **Optional: edge fade (boundary gradient).** If the product requires the drivable area's edges to fade out naturally (rather than hard edges), extra work is needed:
  1. Compute each vertex's distance to the region boundary on the CPU, storing the distance in vertex color or a second UV set.
  2. Alternatively, build a narrow skirt geometry around the edge, or generate a small mask RenderTexture that stores the distance information.
  3. Finally, use a smoothstep function in the fragment shader to adjust opacity based on the distance information, achieving a natural boundary fade.

(See the diagram below for the triangulated fill result 👇)

![occ_05_polygon_triangulation_fill](./occ_05_polygon_triangulation_fill.png)

### 3.3 Sample Code

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>Closed drivable area: preprocessing → XZ-plane triangulation → Unity Mesh (shared vertices + indices)</summary>
public sealed class ClosedLoopDriveAreaBuilder
{
    readonly float _dedupeEpsilon;
    readonly float _roadYOffset;

    public ClosedLoopDriveAreaBuilder(float dedupeEpsilon = 0.05f, float roadYOffset = 0.02f)
    {
        _dedupeEpsilon = dedupeEpsilon;
        _roadYOffset = roadYOffset;
    }

    public bool TryBuildMesh(IReadOnlyList<Vector3> boundaryWorld, Mesh targetMesh)
    {
        if (boundaryWorld == null || boundaryWorld.Count < 3)
            return false;

        var ring3 = new List<Vector3>(boundaryWorld.Count);
        for (int i = 0; i < boundaryWorld.Count; i++)
            ring3.Add(boundaryWorld[i]);

        StripClosingDuplicate(ring3);
        DedupeAdjacent(ring3, _dedupeEpsilon);
        if (ring3.Count < 3)
            return false;

        float avgY = 0f;
        for (int i = 0; i < ring3.Count; i++)
            avgY += ring3[i].y;
        avgY /= ring3.Count;
        float liftY = avgY + _roadYOffset;

        var poly2 = new List<Vector2>(ring3.Count);
        for (int i = 0; i < ring3.Count; i++)
            poly2.Add(new Vector2(ring3[i].x, ring3[i].z));

        EnsureWindingForUpFacing(poly2);

        var indices = new List<int>();
        if (!EarClipTriangulation.TryTriangulate(poly2, indices))
            return false;

        var verts = new List<Vector3>(ring3.Count);
        for (int i = 0; i < ring3.Count; i++)
            verts.Add(new Vector3(ring3[i].x, liftY, ring3[i].z));

        var normals = new List<Vector3>(ring3.Count);
        var uvs = new List<Vector2>(ring3.Count);
        for (int i = 0; i < ring3.Count; i++)
        {
            normals.Add(Vector3.up);
            uvs.Add(Vector2.zero);
        }

        targetMesh.Clear();
        targetMesh.SetVertices(verts);
        targetMesh.SetNormals(normals);
        targetMesh.SetUVs(0, uvs);
        targetMesh.SetTriangles(indices, 0);
        targetMesh.RecalculateBounds();
        return true;
    }

    static void StripClosingDuplicate(List<Vector3> ring)
    {
        if (ring.Count >= 2 && (ring[0] - ring[^1]).sqrMagnitude < 1e-8f)
            ring.RemoveAt(ring.Count - 1);
    }

    static void DedupeAdjacent(List<Vector3> ring, float eps)
    {
        float sq = eps * eps;
        for (int i = ring.Count - 1; i >= 1; i--)
        {
            if ((ring[i] - ring[i - 1]).sqrMagnitude <= sq)
                ring.RemoveAt(i);
        }
        while (ring.Count >= 2 && (ring[0] - ring[^1]).sqrMagnitude <= sq)
            ring.RemoveAt(ring.Count - 1);
    }

    /// <summary>Makes the polygon counterclockwise in XZ projection (viewed from +Y), consistent with the common convention of up-facing normals and default backface culling.</summary>
    static void EnsureWindingForUpFacing(List<Vector2> xzPoly)
    {
        if (SignedAreaXZ(xzPoly) < 0f)
            xzPoly.Reverse();
    }

    static float SignedAreaXZ(IReadOnlyList<Vector2> p)
    {
        double s = 0;
        int n = p.Count;
        for (int i = 0; i < n; i++)
        {
            var q = p[(i + 1) % n];
            s += (double)p[i].x * q.y - (double)p[i].y * q.x;
        }
        return (float)(0.5 * s);
    }
}

/// <summary>Ear clipping for simple polygons (no holes). Fine as a placeholder for small vertex counts; switch to a library for complex data.</summary>
public static class EarClipTriangulation
{
    public static bool TryTriangulate(IReadOnlyList<Vector2> poly, List<int> outTriangles)
    {
        outTriangles.Clear();
        int n = poly.Count;
        if (n < 3) return false;

        var ring = new List<int>(n);
        for (int i = 0; i < n; i++) ring.Add(i);

        int guard = n * n;
        while (ring.Count > 3 && guard-- > 0)
        {
            bool clipped = false;
            int m = ring.Count;
            for (int i = 0; i < m; i++)
            {
                int ip = ring[(i + m - 1) % m];
                int ic = ring[i];
                int inext = ring[(i + 1) % m];

                if (!IsConvexCorner(poly[ip], poly[ic], poly[inext]))
                    continue;

                if (!IsEar(poly, ring, ip, ic, inext))
                    continue;

                outTriangles.Add(ip);
                outTriangles.Add(ic);
                outTriangles.Add(inext);
                ring.RemoveAt(i);
                clipped = true;
                break;
            }
            if (!clipped)
                return false;
        }

        if (ring.Count == 3)
        {
            outTriangles.Add(ring[0]);
            outTriangles.Add(ring[1]);
            outTriangles.Add(ring[2]);
            return true;
        }
        return false;
    }

    /// <summary>Walking the boundary prev→curr→next, a left turn means a convex vertex (valid for polygons already normalized to CCW).</summary>
    static bool IsConvexCorner(Vector2 prev, Vector2 cur, Vector2 next)
    {
        Vector2 eIn = cur - prev;
        Vector2 eOut = next - cur;
        return eIn.x * eOut.y - eIn.y * eOut.x > 1e-8f;
    }

    static bool IsEar(IReadOnlyList<Vector2> poly, List<int> boundary, int ia, int ib, int ic)
    {
        Vector2 a = poly[ia], b = poly[ib], c = poly[ic];
        for (int k = 0; k < boundary.Count; k++)
        {
            int iv = boundary[k];
            if (iv == ia || iv == ib || iv == ic) continue;
            if (PointInTriangle(poly[iv], a, b, c))
                return false;
        }
        return true;
    }

    static bool PointInTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
    {
        float c1 = Cross2(a, b, p), c2 = Cross2(b, c, p), c3 = Cross2(c, a, p);
        bool neg = (c1 < 0) || (c2 < 0) || (c3 < 0);
        bool pos = (c1 > 0) || (c2 > 0) || (c3 > 0);
        return !(neg && pos);
    }

    static float Cross2(Vector2 a, Vector2 b, Vector2 c)
    {
        return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    }
}
```

Fragment example (vertex color `.r` stores the normalized edge distance, written separately on the CPU side)

```hlsl
half4 FragArea(half4 vtxColor : COLOR) : SV_Target
{
    half d = saturate(vtxColor.r);
    half a = _AreaAlpha * smoothstep(0.0h, _Feather, d);
    return half4(_FillRgb, a);
}
```

---

## Summary


| **Approach** | **Typical input** | **Key points** |
| ----------- | ------------------------ | ------------------------------ |
| Bitmask checkerboard | 2D grid bits assembled from a byte stream / base64 | GPU decode writes into an RT, a quad samples it; mapping and resolution must align with the protocol |
| Left/right dual boundary strips | Two independent polylines (or sampled curves), left and right | Align by arc-length parameter before pairing and triangulating; never hard-pair by index |
| Ordered vertex list along the region boundary | Ordered closed vertex loop | Project into a simple polygon, then triangulate; holes/self-intersections require a different algorithm or upstream constraints |


---

## Closing Thoughts

Driving OCC protocol formats vary widely across suppliers. **When both options are equally available**, the bitmask grid is usually the easier one for the application layer: the decoding rules are clear, and you rarely run into vertex-topology headaches (vertex count explosions, complex concave contours, edge spikes, triangulation stability).

