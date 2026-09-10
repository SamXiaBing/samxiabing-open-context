---
title: "Cockpit 3D HMI Scenes: Implementing Planar Reflections in URP"
date: 2026-05-27
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> When developing special effects for cockpit HMI, requirements for reflections/projections come up often. Think of the highly reflective wall in a car-wash scene, or the epoxy-mirror look of a garage floor. Do you rely on reflection probes, use screen-space reflections, or fall back to the old trick of duplicating a set of objects behind the mirror?

This article introduces a lightweight, general-purpose planar reflection approach: **one quad, one extra camera, one RenderTexture**. Whether it's a wall or the ground, you can consider using this approach.

## Comparing the Options

The following "true reflection" approaches generally don't suit in-vehicle units or flat-design scenes:

- **Reflection probes**: Static baking won't work, because the vehicle in the scene is always dynamic. Real-time probes are relatively expensive, and what a reflection image needs from the viewpoint isn't always a single point—sometimes you need the geometric correspondence of a whole flat mirror.
- **Screen-space reflections**: At the time this project was delivered, SSR hadn't officially landed in URP yet. The fullscreen pass it brings requires multiple depth-buffer samples, which is a performance concern. And for walls, you may need to reflect objects outside the screen.
- **Mirrored duplicates**: They eat extra vertices, the cost-effectiveness is poor, and keeping the duplicated objects in sync is a pain.

The planar reflection route: **use a reflection matrix to mirror the camera to the other side of the plane, take a shot there, then paste the image back onto the original plane**. No physical reflection is simulated, but for the cost of one extra render you get geometric alignment identical to a true mirror.

## Approach Overview

The whole solution splits into a C# rendering side and a shader sampling side:

1. **C# side**: Use a Householder reflection matrix to mirror the main camera's transform to the other side of the plane, create a reflection camera that renders the scene into a RenderTexture, and use oblique near-plane clipping to cut away geometry behind the plane that would otherwise break the illusion. All the following code lives in a single script.
2. **Shader side**: Sample the RenderTexture with screen-space UVs, multiply by alpha, and add it onto the base color.

## 1. The Reflection Matrix

The core of planar reflection is simulating this process: **place a camera behind the mirror—what it captures is exactly the reflection the mirror should display**. This operation is implemented with a **Householder reflection matrix**: given the plane normal `N` and position `P₀`, you construct a 4×4 transform matrix that maps any point in space to its mirror image about the plane.

The whole logic lives in one script, in two steps: `Start()` performs one-time initialization, and `RenderObject()` executes the render every frame.

### Initialization: Start()

`Start()` does three things: create the reflection camera, create the RenderTexture, and register a per-frame callback.

Several options must be turned off when creating the reflection camera: shadows (`renderShadows = false`), the color/depth prepass (`requiresColorOption / requiresDepthOption = Off`)—the reflection camera only needs color information, so all of these are pure overhead.

Culling needs two layers set: `~(1 << 4)` culls the Water layer to prevent a "mirror within the mirror" recursion, and `LayersToReflect` (a LayerMask, all layers by default) excludes the layer the reflection plane itself sits on to prevent self-reflection. Neither can be omitted.

The camera type is marked as `CameraType.Reflection` and automatic rendering is disabled (`enabled = false`); the script triggers rendering manually from the callback.

The RenderTexture resolution is controlled by `ReflectionTexResolution` (int, default 512, must be a power of two). The format defaults to ARGB32; when `HDR` (bool, default false) is enabled, it switches to ARGBFloat to preserve highlight information, at the cost of doubled video memory.

**Code sketch:**

```csharp
void Start()
{
    targetCam = Camera.main;

    // Create the reflection camera, with shadows and prepasses disabled
    // Cull the Water layer + LayersToReflect excludes the plane's own layer
    // Mark as Reflection type, disable automatic rendering
    reflectionCamera = /* ... */;
    reflectionCamera.cullingMask = ~(1 << 4) & LayersToReflect.value;
    reflectionCamera.cameraType = CameraType.Reflection;
    reflectionCamera.enabled = false;

    // Create the RenderTexture
    // ReflectionTexResolution controls resolution, HDR controls the float format
    reflectionTexture = new RenderTexture(
        ReflectionTexResolution, ReflectionTexResolution, 16, format
    ) { isPowerOfTwo = true };

    // Register the per-frame render callback
    RenderPipelineManager.beginCameraRendering += this.RenderObject;
}
```

### Per-Frame Rendering: RenderObject()

`RenderObject()` is registered on the `beginCameraRendering` callback and fires every frame before the main camera renders. Internally it runs five steps.

**Code sketch:**

```csharp
void RenderObject(ScriptableRenderContext context, Camera cam)
{
    // Run only for the main camera, so the reflection camera doesn't trigger recursion
    if (isRendering || cam != targetCam) return;
    isRendering = true;

    // ---- 1. Sync reflection camera parameters (FOV, clipping planes, aspect ratio, etc.) ----
    reflectionCamera.fieldOfView = cam.fieldOfView;
    reflectionCamera.aspect = cam.aspect;
    // Disable the skybox—no sky should appear in the reflection
    reflectionCamera.clearFlags = CameraClearFlags.SolidColor;
    reflectionCamera.backgroundColor = Color.clear;

    // ---- 2. Build the reflection matrix ----
    // The normal comes from the quad's transform.up—a vertical wall faces horizontally, a horizontal floor faces straight up
    Vector3 normal = transform.up;
    Vector3 position = transform.position;
    // Offset (float, default 0.0): a fine-tuning offset of the reflection plane along its normal, controlling reflection fit
    Vector4 reflectionPlane = new Vector4(
        normal.x, normal.y, normal.z,
        -Vector3.Dot(normal, position) - Offset
    );
    // Householder reflection matrix: M = I - 2 * n * n^T
    // The 16 elements are expanded from reflectionPlane; per-element assignment omitted here
    Matrix4x4 reflectionMatrix = CalculateReflectMatrix(reflectionPlane);
    // Transform the view matrix and the world position
    reflectionCamera.worldToCameraMatrix = cam.worldToCameraMatrix * reflectionMatrix;
    reflectionCamera.transform.position = reflectionMatrix.MultiplyPoint(cam.transform.position);

    // ---- 3. Oblique near-plane clipping (detailed in the next section) ----
    // ...

    // ---- 4. Render the reflection camera ----
    // The mirror transform flips a left-handed coordinate system into a right-handed one; backface culling must be inverted
    GL.invertCulling = true;
    UniversalRenderPipeline.RenderSingleCamera(context, reflectionCamera);
    GL.invertCulling = false; // Restore immediately after rendering, or the main camera will render "inside-out" too

    // ---- 5. Inject the render result into the materials ----
    // BlurredReflection (bool, default false): whether to enable the blurred reflection
    foreach (var material in reflectionMats)
    {
        material.SetTexture(reflectionTexString, reflectionTexture);
        if (BlurredReflection) material.EnableKeyword(blurString);
        else material.DisableKeyword(blurString);
    }

    isRendering = false;
}
```

## 2. Clipping

Once the reflection camera flips to the other side of the plane, it will capture redundant geometry behind the plane—for example, a floor reflection would capture the buildings below ground. These artifacts must be clipped away.

We use **oblique near-plane clipping** for zero-cost clipping: directly modify the third row of the reflection camera's projection matrix so the near clip plane tilts to align with the reflection plane. The GPU hardware then automatically clips all pixels behind the plane.

### Code sketch

```csharp
// Sign function: unlike Mathf.Sign, sgn(0) returns 0 instead of 1
static float Sgn(float a) => a > 0f ? 1f : a < 0f ? -1f : 0f;

// Transform the reflection plane from world space into the reflection camera's space
Matrix4x4 worldToCamera = reflectionCamera.worldToCameraMatrix;
Vector3 clipNormal = worldToCamera.MultiplyVector(normal).normalized;
Vector4 clipPlane = new Vector4(
    clipNormal.x, clipNormal.y, clipNormal.z,
    -Vector3.Dot(worldToCamera.MultiplyPoint(position + normal * Offset), clipNormal)
);

// Compute the oblique projection matrix
// Q is the far corner of the near clip plane in projection space; sgn determines its direction
Matrix4x4 projection = mainCamera.projectionMatrix;
Vector4 oblique = clipPlane * (2f / Vector4.Dot(
    clipPlane, 
    projection.inverse * new Vector4(Sgn(clipPlane.x), Sgn(clipPlane.y), 1f, 1f)
));
// Replace the third row of the projection matrix to finish the oblique clip
projection[2] = oblique.x - projection[3];
projection[6] = oblique.y - projection[7];
projection[10] = oblique.z - projection[11];
projection[14] = oblique.w - projection[15];

reflectionCamera.projectionMatrix = projection;
```

## 3. Screen-Space UV Sampling

The RenderTexture captured by the reflection camera must be pasted back onto the original plane, aligned with the main camera's view.

Using the UVs from the model's unwrap definitely won't work: UVs are fixed coordinates in model space, and the moment the main camera moves, the alignment breaks. The correct approach is to sample with **normalized screen-space UVs**:

URP provides the built-in `GetNormalizedScreenSpaceUV` method, which directly gives the current pixel's 0–1 screen coordinates. Since the reflection camera is already rendered as a mirror of the main camera's view, sampling with screen UVs aligns naturally.

### Shader code sketch

```hlsl
// Compute the current pixel's normalized screen-space UV
float2 screenUV = GetNormalizedScreenSpaceUV(i.clipPos);

// Sample the base color: _BaseColor (Color, default transparent black, overridden by the material) × _BaseMap (2D, the plane's base texture)
float3 baseColor = _BaseColor * tex2D(_BaseMap, i.uv).rgb;
// Sample the reflection color: _ReflectionWallTex (2D, the reflection RenderTexture injected from C#)
float3 reflectionColor = tex2D(_ReflectionWallTex, screenUV).rgb;

// Add the reflection; _RefAlpha controls intensity
float3 finalColor = baseColor + _RefAlpha * reflectionColor;
return float4(finalColor, 1);
```

Three key parameters:

- `_ReflectionWallTex` (2D): the reflection RenderTexture injected from the C# side. No manual assignment needed—it is set automatically after the reflection camera renders.
- `_RefAlpha` (Float, default 0): reflection intensity. At 0 no reflection is visible; at 1 the reflection fully covers the surface. A value of 0.4–0.7 is recommended. Let the reflection act as an atmospheric accent—don't let it overpower the plane's base color. This value stays in sync with `ReflectionAlpha` on the C# side.
- If you want a blurred reflection or water-ripple distortion, just add a normal-based perturbation to `screenUV`.

## 4. Complete Data Flow

The full processing pipeline:

![mermaid-diagram-2026-05-27T08-39-50](./mermaid-diagram-2026-05-27T08-39-50.png)



## 5. Caveats

1. **The main cost comes from rendering the reflection camera**: activate it only in scenes that need reflections, and destroy it on exit—don't keep it alive permanently.
2. **Multiple reflections stack their cost**: enabling several planar reflections in one scene at the same time is not recommended; performance may not survive it.
3. **Don't enable HDR casually**: ARGBFloat takes twice the video memory of ARGB32. Enable it only when light reflections need the preserved highlight information.

## Closing

This article only covers the basics of planar reflection. In real production use, you will likely need to layer on more capabilities: blur, Fresnel effects, moving the logic out of a standalone camera component into a pipeline BeforeOpaque stage, reflection fading with depth, and so on.
