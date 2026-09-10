---
title: "Cockpit 3D HMI Performance: Material Instantiation and Memory Leaks"
date: 2026-07-27
series: perf
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered the GC problem of periodic frame drops. This time it's a different category: memory keeps growing after long-running sessions, and doesn't come back down after scene switches. The longer it runs, the more memory it occupies — until OOM and the system kills the process.

# Symptoms

Test feedback:

> "The driving/parking integrated desktop ran for ten-plus minutes, and memory grew from 400+ MB to 700+ MB. Switching to any fullscreen app and back to the desktop barely reduced memory. Switching the desktop's mode or scene (scene mode, day/night, weather) a few times very likely crashes it."

This pattern almost certainly indicates a memory leak — meaning some objects are definitely being created without being released.

---

# Memory Profiler

For investigating memory leaks, you can use the **two-snapshot comparison** method. In the current app, grab one `.snap` first, then perform some feature switches inside the app, and grab another one a few minutes later. Compare which object types only grow and never shrink.

Open Memory Profiler and load the files. In the Unity Objects view, under Description, you can see how `Material` type objects changed:


| Observation               | First snapshot                          | Second snapshot            |
| ------------------------- | --------------------------------------- | -------------------------- |
| Material instance count   | 30+                                     | 80+                        |
| Same-named Material share | Mostly with `(Instance)` suffix         | Even higher proportion     |
| Total memory trend        | —                                       | Keeps growing, no fall-back |


Material instances only grow, never shrink, and most carry the `(Instance)` suffix. That means these aren't prefabricated materials from assets — they were cloned at runtime. Each time you enter a different scene, the scene's objects each create a batch of instantiated materials, and when you exit the scene these instances aren't destroyed — they stay in memory.

Illustration:

*[Figures omitted; see the original WeChat article]*

---

# renderer.material 

Both `material` and `sharedMaterial` are properties of `renderer`. The logic of `material` can be understood from the following code, which isn't the real implementation but serves as an illustration:

```csharp
public Material material {
    get {
        if (_sharedMaterial == _material) {
            return _material;
        }
        _material = new Material(_sharedMaterial);  // Clone one copy
        _sharedMaterial = _material;
        return _material;
    }
    set {
        _sharedMaterial = value;
        _material = new Material(_sharedMaterial);  // Clone yet another copy
    }
}
```

When you access `renderer.material`, `new Material(_sharedMaterial)` creates a copy, assigned to both `_material` and `_sharedMaterial`. Subsequent accesses won't clone again. But:

1. **The many Renderers in a scene are each independent**. Every mesh has its own `material` property, and each access generates a clone — creating too many instances.
2. **Scene switches don't destroy them**. Instances created through `renderer.material` aren't reclaimed automatically by Unity. When a GameObject is destroyed, the Renderer component goes with it, but the Material instance still hangs around in memory. Unless you manually call `Destroy(mat)`, or wait for `Resources.UnloadUnusedAssets` to trigger a cleanup.

---

# Code Analysis

The culprit turned out to be the rendering setup of lane-line pieces:

```csharp
// LaneLinePiece.cs
private void SetLineColor(Vector4 baseColor, Vector4 baseNightColor) {
    mr.material.SetColor("_BaseColor", baseColor);
    mr.material.SetColor("_NightBaseColor", baseNightColor);
}

private void ChangeOffset(float offset) {
    float normalized_offset = (offset / 9f) - MathF.Floor(offset / 9f);
    mr.material.SetFloat("_LaneLineAnimOffset", normalized_offset);
}
```

Each lane-line segment needs its own color and animation offset set, and the code uses `renderer.material` to change properties. The first access to `mr.material` clones a new material. 30 segments means 30 cloned instances. Looking at other places:

```csharp
// LaneEffect.cs
if (material == null) {
    MeshRenderer mr = body.GetComponent<MeshRenderer>();
    material = mr.material;  // Gets the cloned instance, caches it but never Destroys it
}
```

```csharp
// TrafficLightSymbolDisplay.cs
renderer.material = new Material(renderer.sharedMaterial);  // Explicit new, with no paired destroy
```

```csharp
// DrivableAreaRenderer.cs
return quadRenderer.material;  // Clones on every call
```

There are quite a few usage points of `renderer.material` in the project. Some are implicit (`mr.material.SetColor`), some are explicit `new Material`.

---

# The Fixes

1. If all the instances behave identically — like most perception objects such as other vehicles and road signs — then change `material` to `sharedMaterial`, since every instance of each material type behaves the same way.

2. If instances of the same material may behave differently, consider two approaches:  
   (1) Keep using `renderer.material`, but verify and observe whether the places using it trigger frequently. If the trigger rate is low — not several or a dozen-plus Hz every second — you can keep using it.

   (2) Keep using `renderer.material` when you can't determine whether it's frequent, but you do know when it's needed and when it's not — then Destroy manually. Illustrative code:

```
// DrivableAreaRenderer.cs — release proactively when done
private void CleanupMaterial() {
    if (material != null && drivableAreaShader != null) {
        Destroy(material);
        material = null;
    }
}
```

   (3) Use `MaterialPropertyBlock`. This way the material stays shared, and when you need to change a specific instance's appearance, you just populate a new property block. Illustrative code:

```csharp
// Illustrative code
private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
private static readonly int NightBaseColorId = Shader.PropertyToID("_NightBaseColor");
private static readonly int AnimOffsetId = Shader.PropertyToID("_LaneLineAnimOffset");

private MaterialPropertyBlock mpb = new MaterialPropertyBlock();

private void SetLineColor(Vector4 baseColor, Vector4 baseNightColor) {
    mr.GetPropertyBlock(mpb);
    mpb.SetColor(BaseColorId, baseColor);
    mpb.SetColor(NightBaseColorId, baseNightColor);
    mr.SetPropertyBlock(mpb);
}

private void ChangeOffset(float offset) {
    float normalized_offset = (offset / 9f) - MathF.Floor(offset / 9f);
    mr.GetPropertyBlock(mpb);
    mpb.SetFloat(AnimOffsetId, normalized_offset);
    mr.SetPropertyBlock(mpb);
}
```

---

# Closing Thoughts

Material instantiation is a fairly common situation. In daily development, you should keep this hazard in mind to avoid the pitfalls of frequent instantiation.
