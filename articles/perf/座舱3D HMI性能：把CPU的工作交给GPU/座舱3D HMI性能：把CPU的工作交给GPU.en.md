---
title: "Cockpit 3D HMI Performance: Offloading CPU Work to the GPU"
date: 2026-08-10
series: perf
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered the fingerprint-based approach to skipping redundant rebuilds in the HPA mapping scenario. But it doesn't work for the perception objects encountered while driving in SR — lane lines, other vehicles, road markings, and so on. During driving, these objects are always changing, so constantly calling SetDirty is neither possible nor meaningful.

# Symptoms

Test feedback:

> "While driving in SR, when reaching complex intersections, the frame rate dropped noticeably multiple times during a left turn."

# CPU Usage

The Profiler data shows clear spikes. Expanding the Hierarchy view, the top time-consuming nodes are: `Mesh.SetVertices`, `Mesh.SetTriangles`, and `Mesh.RecalculateNormals`. But these aren't absolutely huge — because the intersection is complex, there's also a lot of object-pool operations and GameObject.Instantiate happening alongside.

In this scenario, lanes and drivable areas suddenly become more numerous and wider in a short span of time. Meanwhile, the data changes every frame — whether from data jitter or changes in the surroundings — so the mesh definitely has to be rebuilt. So what do we do? Since the CPU can't keep up, hand the work to the GPU — Compute Shader.

![Figure 1](./图1.png)

---

# The Solutions

## Option 1: Bitmap Grid → Render Texture

When the drivable-area (FreeSpace) data is a bitmap grid, each bit represents the drivable state of one grid cell. The data volume is fairly fixed, but the change frequency is high. The CPU approach parses the bitmap byte by byte and generates a RenderTexture. Doing this every frame is a non-trivial CPU cost. So we move this step to the GPU:

```csharp
// Illustrative code
void ProcessWithComputeShader(byte[] freeSpaceData, int width, int length) {
    uint[] uintData = ConvertByteArrayToUIntArray(freeSpaceData);
    computeBuffer.SetData(uintData);

    shader.SetBuffer(kernel, "_RawDataBuffer", computeBuffer);
    shader.SetTexture(kernel, "_OutputTexture", drivableTexture);

    int threadGroupsX = Mathf.CeilToInt(width / 8.0f);
    int threadGroupsY = Mathf.CeilToInt(height / 8.0f);
    shader.Dispatch(kernel, threadGroupsX, threadGroupsY, 1);
}
```

Inside the GPU shader's core, each thread processes one pixel:

```hlsl
// Illustrative code
[numthreads(8, 8, 1)]
void ProcessDrivableArea(uint3 id : SV_DispatchThreadID) {
    uint bitIndex = id.y * _TotalWidthGrids + id.x;
    uint uintIndex = bitIndex / 32;
    uint bitOffset = bitIndex % 32;

    uint packed = _RawDataBuffer[uintIndex];
    bool isDrivable = (packed >> bitOffset) & 1;

    float4 color = isDrivable ? float4(0, 1, 0, 0.3) : float4(0, 0, 0, 0);
    color.a *= EdgeFade(id.x, id.y);
    _OutputTexture[id.xy] = color;
}
```

The CPU only does data preparation and dispatch; the actual per-pixel computation is handled by the GPU in parallel. `numthreads(8,8,1)` means each thread group processes 64 pixels, so a 200x200 bitmap needs roughly 625 thread groups. Compared with per-pixel CPU processing, the speedup is significant.

## Option 2: Polygon Vertices → Mesh

Road surfaces, lane lines, and similar geometry data come as polygon vertices, or as a centerline plus a width. Some drivable-area solutions also provide polygon vertex arrays for you to draw with, rather than bitmap data (though I don't think that approach is great). The CPU approach computes direction point by point, widens, builds triangles, computes UVs. With many points and many segments, CPU costs stack up. This geometry generation can also be handed to the GPU:

**GPU side: the ComputeShader kernel**

```hlsl
// Illustrative code
// Input data structure: position and direction of each path point
struct PointData {
    float3 position;    // Path point coordinates
    float3 direction;   // Forward direction (precomputed on CPU or computed via GPU prefix sum)
    float length;       // Current segment length
    float distance;     // Accumulated distance from the start, used for the UV's V coordinate
};

// Output data structure: one vertex contains position, normal, and two UV sets
struct VertexOutput {
    float3 position;
    float3 normal;
    float2 uv0;   // First UV set: x marks left/right edge (0/1), y is the distance along the path
    float2 uv1;   // Second UV set: normalized path progress 0~1
};

// 16 threads per group, each thread handles one path point
[numthreads(16, 1, 1)]
void CSMain(uint3 id : SV_DispatchThreadID) {
    uint i = id.x;

    // Read the current path point from the input buffer
    PointData pt = pointDataBuffer[i];

    // Use the cross product to get the left/right direction: cross(up, direction) gives
    // the right vector perpendicular to the forward direction
    // Offset by pathWidth on both sides to generate the strip's two boundary vertices
    float3 rightOffset = cross(float3(0,1,0), pt.direction) * pathWidth;
    float3 left  = pt.position - rightOffset;
    float3 right = pt.position + rightOffset;

    // Write two vertices: left vertex UV.x = 0, right vertex UV.x = 1
    // UV.y uses the accumulated distance so the texture flows along the path
    vertexBuffer[i * 2]     = {left,  float3(0,1,0), float2(0, pt.distance), float2(0, pt.distance / totalLength)};
    vertexBuffer[i * 2 + 1] = {right, float3(0,1,0), float2(1, pt.distance), float2(1, pt.distance / totalLength)};

    // Generate triangle indices: two triangles per segment, forming one quad face
    // Left vertex at i*2, right vertex at i*2+1; next segment's left/right at (i+1)*2 and (i+1)*2+1
    trianglesBuffer[i * 6]     = i * 2;       // Triangle 1: left, right, next-left
    trianglesBuffer[i * 6 + 1] = i * 2 + 1;   // 
    trianglesBuffer[i * 6 + 2] = i * 2 + 2;   // 
    trianglesBuffer[i * 6 + 3] = i * 2 + 1;   // Triangle 2: right, next-left, next-right
    trianglesBuffer[i * 6 + 4] = i * 2 + 2;   //
    trianglesBuffer[i * 6 + 5] = i * 2 + 3;   //
}
```

**C# side: driving this ComputeShader**

Once the ComputeShader is written, the C# side needs to: stuff the data into GPU buffers, dispatch the computation, and read the results back to assemble the Mesh.

```csharp
// Illustrative code
// 1. Initialization: create buffers, bind them to the ComputeShader's kernel
void Initialize(ComputeShader shader) {
    int kernel = shader.FindKernel("CSMain");
    pointDataBuffer = new ComputeBuffer(MAX_POINTS, System.Runtime.InteropServices.Marshal.SizeOf(typeof(PointData)));
    vertexBuffer    = new ComputeBuffer(MAX_POINTS * 2, typeof(VertexOutput));
    trianglesBuffer = new ComputeBuffer(MAX_POINTS * 6, typeof(int));

    shader.SetBuffer(kernel, "pointDataBuffer", pointDataBuffer);
    shader.SetBuffer(kernel, "vertexBuffer", vertexBuffer);
    shader.SetBuffer(kernel, "trianglesBuffer", trianglesBuffer);
}

// 2. Submit: upload the path point data, dispatch the GPU computation, read back the results
void Dispatch(List<Vector3> path, float width, Mesh mesh) {
    // Prepare input data: compute per-point direction and accumulated distance
    PointData[] points = PreparePathData(path, width);
    pointDataBuffer.SetData(points);

    // Dispatch: one thread group per 16 points
    int threadGroups = Mathf.CeilToInt(path.Count / 16.0f);
    shader.SetInt("pathWidth", ...);
    shader.Dispatch(kernel, threadGroups, 1, 1);

    // Read back the GPU computation results
    VertexOutput[] vertices = new VertexOutput[path.Count * 2];
    int[] triangles = new int[path.Count * 6];
    vertexBuffer.GetData(vertices);
    trianglesBuffer.GetData(triangles);

    // Assemble the Unity Mesh
    mesh.SetVertexBufferParams(vertices.Length, layout);
    mesh.SetVertexBufferData(vertices);
    mesh.SetTriangles(triangles, 0);
    mesh.RecalculateBounds();
}

// 3. High-level call: business code only collects path points; the rest goes to the framework
void UpdateLaneMesh(List<Vector3> centerLine, float width, Mesh mesh) {
    pathToMeshComputer.Dispatch(centerLine, width, mesh);
}
```

The CPU pushes the path point data into the `ComputeBuffer`. The remaining direction computation, widening, UV assignment, and triangle index generation are all done in parallel on the GPU. `[numthreads(16,1,1)]` means 16 path points can be processed simultaneously — 100 points need only 7 thread groups. Compared with per-point CPU `SetVertices` followed by `SetTriangles`, it eliminates multiple copies.

# Closing Thoughts

Compute Shader provides an excellent bridge for the CPU to shift part of its burden onto the GPU. During the framework-building phase of a software team's ADAS-type delivery, you can embed Compute Shader support at the development-framework level, so that all the fundamental 3D drawing methods go through this path. That way, you hopefully won't end up writing a dedicated Compute Shader for every performance problem that comes along — avoiding redundancy and duplicated effort.
