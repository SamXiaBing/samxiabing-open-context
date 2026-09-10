---
title: "Intelligent Driving SR Development: Occlusion Detection and Semi-Transparency from the Ego-Vehicle View"
date: 2026-08-06
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered how StyleCatalog handles SR reskinning. Today let's talk about a more specific little feature: when the SR camera looks toward the ego car, if other vehicles or certain perceived objects sit in the line of sight, those perceived objects need to turn semi-transparent.

When the camera rotates to a certain angle, other vehicles or large obstacles may stand in front of the ego car along the line of sight. If those objects are fully opaque, the ego car gets hidden and the user can't see its state. This directly affects the communication of key information.

Implementing this feature is fairly obvious in principle, but during development you often hit problems like: it's already occluded yet hasn't turned semi-transparent; or it clearly isn't occluded yet but turns semi-transparent anyway. Such problems may be related to the approach, but I believe any scheme that can reach mass production after performance considerations will struggle to avoid every extreme case. So this feature itself can be allowed a little tolerance margin.

---

# Business Logic

![Figure 1](./图1.png)

---

# Detection Logic

## **Executed Every Frame**

1. **Compute the ray**: use `WorldToScreenPoint` to convert the ego car's position (the world origin) into screen coordinates, then cast a ray from the camera position toward that screen coordinate.
2. **Iterate and test**: for each perceived object registered for occlusion detection, determine whether its collider's bounding box intersects the ray.
3. **Set the state**: on intersection call `SetOcclusion(true)`, otherwise `SetOcclusion(false)`
4. **Clean up sleeping objects**: once a perceived object enters the sleep state, force it back to opaque and remove it from the list.

**Sketch code:**

```csharp
public class OcclusionDetection : BaseController
{
    private List<PerceptionObject> _occlusionList;

    public void RegisterObject(PerceptionObject obj)
    {
        if (obj.EnableOcclusion && !_occlusionList.Contains(obj))
        {
            _occlusionList.Add(obj);
        }
    }

    public void CheckOcclusion()
    {
        Ray ray = sceneMgr.MainCamera.ScreenPointToRay(
            sceneMgr.MainCamera.WorldToScreenPoint(Vector3.zero));

        foreach (PerceptionObject obj in _occlusionList)
        {
            if (obj.Entity.sleep || !obj.EnableOcclusion)
            {
                obj.SetOcclusion(false);
                continue;
            }

            bool hit = obj.OcclusionBounds.bounds.IntersectRay(ray);
            obj.SetOcclusion(hit);
        }
    }

    private void Update()
    {
        CheckOcclusion();
    }
}
```

## Perceived-Object Registration

When created, a perceived object registers itself into the occlusion detection system like this:

```csharp
public void UpdateState(PerceptionObjectStatus status, PerceptionObjectDebugInfo debug)
{
    if (occlusionDetect == null)
    {
        occlusionDetect = SceneManager.Instance.GetController<OcclusionDetection>();
    }
    occlusionDetect.RegisterObject(this);
    // other state updates
}
```

Each perceived object has a switch, `EnableOcclusion`. Per product design requirements, you can control on the prefab whether it participates in occlusion detection. Not all perceived objects need occlusion transparency—usually only large objects (vehicles) do.

---

# Material Presentation

## Perceived-Object Material Management

Two materials are attached to each perceived-object prefab: `NormalMat` (opaque) and `OcclusionMat` (semi-transparent).

```csharp
[Header("Occlusion")]
public bool EnableOcclusion;
public MeshRenderer OcclusionBounds;
public Material NormalMat;
public Material OcclusionMat;

public void SetOcclusion(bool occlusion)
{
    if (!EnableOcclusion) return;
    if (this.InOcclusion == occlusion) return;

    this.InOcclusion = occlusion;

    if (_bodyRenderer != null)
    {
        _bodyRenderer.material = occlusion ? OcclusionMat : NormalMat;
    }
    if (_bodyRendererSub != null)
    {
        _bodyRendererSub.material = occlusion ? OcclusionMat : NormalMat;
    }
}
```

**State deduplication**: `if (this.InOcclusion == occlusion) return;` — if you reassign the material every frame regardless of whether the state changed, Unity triggers extra material instantiation operations, adding GC pressure. Switch only when the state truly changes.

# UI Occlusion Detection

Besides perceived objects, sometimes requirements demand that if UI occludes, it also needs semi-transparency. For example, the parking button:

```csharp
// For each perceived object participating in occlusion detection
// determine whether its bounding box intersects the button's bounding box
if (button.buttonRenderers[0].bounds.Intersects(obj.OcclusionBounds.bounds))
{
    obj.SetOcclusion(true);
}
else
{
    obj.SetOcclusion(false);
}
```

Detection method: rely on the UI API and bounding-box intersection tests—check whether the perceived object's bounding box spatially overlaps the button's bounding box; if it blocks, go semi-transparent.

---

# A Bug That Illustrates the Bad Case

## The Symptom

While the ego car was waiting at a red light, a vehicle at least 1.5 meters directly behind it turned semi-transparent. But judged by eye, that car was clearly behind the ego car—the line of sight was not blocked.

## Root Cause

The problem lies in the detection method. `bounds.IntersectRay(ray)` uses an **axis-aligned bounding box**, not an exact Mesh collider. The other car's collider is a rectangular box, one size larger than the car body's actual outline. The ray is cast from the camera to the ego car's ground center point; even though the other car's actual body doesn't block the line of sight, the ray passes through the **upper-front portion** of the other car's bounding box. Visually, that region belongs to the space above the other car rather than its body—but since the detection only looks at the bounding box and doesn't care about body shape, it's judged as occlusion.

![fig_aabb_false_positive](./fig_aabb_false_positive.png)

> As for how to fix it, my suggestion is: don't. On one hand, we're not going to switch to a MeshCollider—that could explode performance. On the other hand, don't bother trying to tweak the collider either: no matter how far you tweak it, someone will always find you a bad case—after all, this is a shortcoming of the approach itself.

---

## Closing Thoughts

Occlusion detection from the ego-vehicle view looks like a tiny feature, but it involves raycasting, material switching, and state management. The most critical engineering problem is the trade-off between precision and performance: using AABB bounding boxes for detection performs well but has limited precision. Don't let QA define this as a misjudgment—it is merely the result of an imprecise determination.

