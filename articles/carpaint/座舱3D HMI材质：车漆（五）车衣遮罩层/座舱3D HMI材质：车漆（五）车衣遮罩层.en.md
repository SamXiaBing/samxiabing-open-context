---
title: "Cockpit 3D HMI Materials: Car Paint (Part 5) — The Wrap Mask Layer"
lang: en
date: 2026-08-19
series: carpaint
no: 5
status: published
visibility: public
wechat_url: ""
---

> As mentioned in previous posts, this one was originally meant to cover some reflection and anti-aliasing issues. But considering those issues are rather fragmentary and sprawling, I decided to finish the "layers" of the layered processing first, then organize the related problems we've dealt with.

For car paint, a common requirement is the digital wrap. Users can not only choose different paint colors but also pick from several preset wraps. They behave like decals, as shown:

![SkinMap对比](./SkinMap对比.png)

The solid red sphere on the left is the original paint without a wrap; the checkered sphere on the right is after applying one. The checkerboard is just for testing; in a real project you'd swap in your wrap pattern, racing stripes, or partial artwork. The rest of this post briefly describes the approach.

---

# The Wrap Layer

The car paint has two branches on its way to the final Albedo output:

![图2](./图2.png)

## Parameters

```
// Watch the value ranges
[Toggle]_HasMaskMap("HasMaskMap", Float) = 0
[Toggle]_IsUV1("IsUV1", Float) = 0
[NoScaleOffset]_SkinMap("SkinMap", 2D) = "white"
```

With the `_HasMaskMap` toggle set to 1, the entire Albedo block is replaced with the sampled result of the SkinMap texture. There's no per-pixel alpha blend weight here — it's a hard switch.

## Code

```hlsl
// 1. Base-coat color: BaseColor ↔ EdgeColor, blended by Fresnel
float3 baseEdge = lerp(_BaseColor.rgb, _EdgeColor.rgb, fresnel);

// 2. Sample the wrap
float3 skin = tex2D(_SkinMap, uv0).rgb;

// 3. Albedo output: _HasMaskMap swaps in the whole thing
float3 albedo =
        baseEdge * (1.0 - _HasMaskMap)   // take the base coat
      + skin     * _HasMaskMap;          // take the wrap

```

In the SkinMap texture, the base-coat color and the wrap pattern appear together. The wrap image is a pre-composited **finished image**: wherever paint should show, fill in the base-coat color; wherever the wrap should show, fill in the wrap pattern. This approach isn't mandatory — selecting the color based on alpha works too; either way you need one sample.

Whether or not the wrap toggle is on, everything still passes through the Flake layer's accumulation.

---

# Closing

In the project, different wraps get different materials, and switching means swapping the material, not tweaking parameters — as covered in earlier posts. When we have both domestic and overseas vehicle models, the wrap textures can be given two sets of UVs to fit the different models. Providing a UV-switch toggle in the code saves a bit.
