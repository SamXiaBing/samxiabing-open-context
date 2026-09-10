---
title: "Intelligent Driving SR Development: Two Engineering Implementations for Parking OCC Visualization, from Voxel Grid to Obstacle Surfaces"
lang: en
date: 2026-05-12
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

---
title: "Intelligent Driving SR Development: Two Engineering Implementations for Parking OCC Visualization, from Voxel Grid to Obstacle Surfaces"
author: "Bingbang"
date: "2026-05-12"
---

*[Figures omitted; see the original WeChat article]*

> In the SR (Surround Reality) parking interface of an intelligent-driving cockpit, obstacles usually don't arrive as a ready-made triangle mesh — they come as a list of occupied voxel cells. The ADAS data protocol hands the cell size and occupancy indices over to the application layer, and turning that into something visible on screen that looks like a solid mass blocking the way is the renderer's job.

This article walks through the two common approaches for parking OCC: **instancing small cubes at the occupied points**, and **slicing the point cloud into layers, computing horizontal outer contours, and extruding them into a shell-like mesh**. For each approach I'll cover the data shape it fits, the implementation steps, and the optimization gotchas — all broken down the way it actually works in a shipping project, so you can compare and choose.

---

## 1. Data Processing

When the ADAS stack detects an obstacle, it decomposes the obstacle into individual cubes and delivers a list of occupied-cell coordinates, together with the cube size for each occupied cell, to the application layer for rendering.

### 1.1 Data Format

You can picture the entire parking area as a big box of LEGO bricks:


| Data component | What it means | What it actually does                                                |
| ------- | ---------------- | --------------------------------------------------- |
| Size of each cell | The length, width, and height of a single LEGO brick in centimeters  | Defines the actual physical size of a single voxel (e.g. 0.2 m × 0.2 m × 0.25 m). This is usually fixed by convention or determined after visual validation. |
| Occupancy index list  | Which cells are obstacles and should show LEGO bricks | Records only the index coordinates of cells that contain obstacles — 3D integer indices, not real meters.                    |


### 1.2 Data Conversion

1. **Compute the size**: Multiply the index by the size of a single cell, converting from "which brick" to "how many meters from the origin" (e.g. if i is 3 and the step is 0.2 m, that's 3 × 0.2 = 0.6 m).
2. **Fixed alignment**: Before converting into the 3D engine's world coordinate system, you may — depending on the ADAS vendor — need to apply a fixed translation to the protocol coordinates, i.e. always add a fixed offset variable.
3. **Swap the axes**: The ADAS sensor's axis conventions (e.g. which axis means up/down/front/back) differ from what a 3D engine expects, so rearrange the coordinate order so obstacles don't end up upside down or mirrored. For example, new Vector3(-y, z, x) performs a component permutation plus a sign flip on one axis.

---

## 2. Representation 1: Voxel Cubes

This style is basically Minecraft: draw a small cube for every occupied cell, and use batched rendering to save performance.

### 2.1 Implementation Steps

*[Figures omitted; see the original WeChat article]*

1. **Position**: Take each world-space point converted in the previous step and use it directly as the center of a small cube — one point, one brick.
2. **Prepare a cube template**: At startup, instantiate a unit cube mesh (edge length 1) and keep it around; all the small cubes reuse this template instead of creating a new mesh each time.
3. **Build the transform list**: For each center point, generate a transform and compose it into a TRS matrix, scaling the template cube to the size you want (typically a few to a dozen-odd centimeters per edge, depending on the design requirements).
4. **Draw in batches**: Use a GPU batch-instancing API (such as Unity's Graphics.DrawMeshInstanced) to draw all the cubes in one go. Never create a separate GameObject per cube — that will destroy your frame rate.

### 2.2 Optimization Tips

- **Pre-allocate the transform list**: Pre-size the list that stores transform data to avoid frequent dynamic resizing.
- **Use a batched GPU instancing draw method**
- **Clear stale cubes promptly**: Clear the previous frame's transform data at a fixed interval to prevent accumulation.

*[Figures omitted; see the original WeChat article]*

### 2.3 Sample Code

Replace the placeholders for voxel-index multiplication, bias, and axis remapping according to your protocol calibration; fill in the cube scale and rendering layer per project.

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

    /// <summary>Converts voxel cell (ix,iy,iz) to a world point: multiply by the cell size in meters, subtract the bias, then remap the axes.</summary>
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

    /// <summary>If you only need to draw a single debug cube, use the single-matrix version (the non-instanced path).</summary>
    public void DrawSingleDebugCube(Vector3 worldCenter)
    {
        if (_unitCubeMesh == null || instancingMaterial == null) return;
        var mtx = Matrix4x4.TRS(worldCenter, Quaternion.identity, _cubeScale);
        Graphics.DrawMesh(_unitCubeMesh, mtx, instancingMaterial, renderLayer, null, 0, null, ShadowCastingMode.On, true);
    }
}
```

## 3. Representation 2: Contour-Based, Layer-by-Layer Shell Extrusion

This is the common approach for consolidating discrete points into a **shell with thickness**. Visually it looks much closer to one solid obstacle, and the vertex count is more controllable than with the cube approach.

### 3.1 Data Format

The input is still the same list of world-space points. The extra parameters you'll need to tune are:


| Parameter | What it does in plain language | Typical value                |
| ------- | ----------------------------- | -------------------- |
| Layer thickness | How thick each slice is when cutting the obstacle vertically | Usually 0.2–0.3 m; adjust to taste    |
| Clustering multiplier | How close points need to be to count as "the same obstacle" | Typically the average horizontal cell edge length × 2–2.5 |
| Max points per layer | Keeps a layer from having so many points that computation stalls | Set your own cap; beyond it, sample only a subset      |
| Max contour edge length | Long hull edges look harsh after extrusion; edges longer than this get split into segments | Tune as needed                  |


### 3.2 Implementation Steps

*[Figures omitted; see the original WeChat article]*

This method assembles scattered points into a complete "shell-shaped obstacle". What follows is just how I handle it — not necessarily the most standard or optimal solution. The steps are: slice into layers → group → find contours → extrude into 3D faces:

1. **Slice into layers by height**
  1. First find the lowest height among all points in the frame and use it as the zero reference. Each point computes its height above that reference, divides by the layer thickness, and floors the result to get its layer index.
  2. Points in the same layer are then processed together to compute the horizontal shape. A 0.2–0.3 m layer height generally works fine; the value is tunable.
2. **Group within each layer (clustering)**
  1. A layer may contain more than one obstacle (say, a wall and a pillar at the same time), so split the points into groups by distance: two points closer than the threshold belong to the same obstacle.
  2. The threshold is the average horizontal cell edge length × the clustering multiplier you tuned beforehand; a default of 2.5× works well.
  3. For thin walls, grouping in the horizontal plane is enough; for standalone pillars, you can cluster in 3D space. When there are too many points, sample a subset for computation, or limit how many layers get processed, to keep single-frame computation from stalling.
3. **Find each group's outermost contour (horizontal convex hull)**
  1. Look at each group of points from above (the XZ plane) and compute the outermost polygon that wraps all of them — the convex hull.
  2. The upside is that the algorithm is simple to implement; the downside is that concave regions of the original shape get filled in — a deliberate trade-off: saving compute costs you some concave detail.
4. **Densify the contour (refine the polyline)**
  1. Convex hulls have few vertices, so the extruded sides come out chunky and harsh. Using your configured maximum edge length, insert a few intermediate points along long edges to densify the contour.
  2. Finally, set every point's height to the layer's center height so all contour points lie on the same horizontal plane.
5. **Extrude into a 3D mesh (triangle mesh)**
  1. Take this contour ring and offset it half a layer thickness up and down from the layer center, giving an upper ring of points (top ring) and a lower ring of points (bottom ring).
  2. Run the convex hull once more for the top and bottom faces and cut the convex polygon into small triangles (fan triangulation). Mind the winding order: the top face's normal points up, the bottom face's normal points down — otherwise rendering will show back-face artifacts.
  3. For the sides, walk the contour in order: connect the four adjacent top/bottom points into a quad, then split it into two triangles with outward-facing normals (so the outer surface is visible).
  4. Finally, store all vertices and triangles into a Mesh and recompute the normals. If you want blocky color variation or distance-based coloring driven by PDC ranges, you'll also need to add color information to the vertices or pass parameters to the shader.

### 3.3 Optimization Tips


| Optimization | Core technique                                                    | Benefit                      |
| ---------- | ------------------------------------------------------- | ----------------------- |
| Layer & point count caps    | When maxPointsPerLayer is exceeded, decimate at even intervals first; when the total layer count exceeds maxProcessLayers, process only the bottom N layers | Hard caps prevent single-frame compute blowups and stutter         |
| Adaptive clustering radius    | Threshold = average of the X/Z voxel dimensions × clustering multiplier, no hardcoded constant                         | Auto-adapts to protocol voxel sizes; no repeated tuning     |
| 2D GPU clustering by default | Compute neighborhoods on the GPU first, ship results back to the CPU for DBSCAN; fall back to CPU uniform-grid neighborhood search if the shader fails            | Suits thin-wall scenarios; faster and saves CPU       |
| Optional 3D clustering     | With 2D disabled, run full pairwise 3D DBSCAN with no spatial-hash optimization                              | Fits isolated-pillar scenarios; more CPU-hungry when points are dense — enable as needed  |
| Mesh memory reuse   | Keep vertices/indices/vertex colors in member Lists; clear each frame instead of rebuilding, and pre-size by estimate                      | Reduces frequent allocations and GC hitches         |
| Background-thread parsing     | Parse large protobuf payloads on a thread pool via UniTask; render results back on the main thread                      | Parsing never blocks the main thread; toggle follows project config |


### 3.4 Sample Code

Only the core skeleton for layering, the clustering radius, and shell extrusion is kept; plug in your project's own utilities for the convex hull and triangulation.

```csharp
using System.Collections.Generic;
using UnityEngine;

static class LayeredOccupancyShell
{
    /// <summary>Buckets points by height: layer = floor((y - minY) / layerThickness).</summary>
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

    /// <summary>Clustering distance: mean horizontal voxel step × multiplier, consistent with the protocol's VoxelGrid.x / .z.</summary>
    public static float ClusterRadiusMeters(Vector3 cellMeters, float multiplier)
    {
        return (cellMeters.x + cellMeters.z) * 0.5f * multiplier;
    }

    // In-layer clustering: in production, call your planar DBSCAN wrapper (XZ) or 3D DBSCAN wrapper here,
    // with the layer's point list, the value returned by ClusterRadiusMeters, the minimum point count, and so on.

    /// <summary>Extrudes the sides of a closed XZ contour; the top/bottom faces need their own convex hull + fan triangulation at their heights before merging into the same Mesh.</summary>
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

## Closing Thoughts

Beyond the two production-ready approaches covered in this article, the industry keeps exploring more efficient visualization methods. That said, parking OCC rendering is one of the most performance-hungry modules in SR — even the Minecraft-style approach can easily hit the infotainment system's performance red line, so compute overhead deserves top priority when you take it to production.
