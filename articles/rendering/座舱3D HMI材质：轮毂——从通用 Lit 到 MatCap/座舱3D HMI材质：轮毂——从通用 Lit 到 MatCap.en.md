---
title: "Cockpit 3D HMI Materials: Wheel Rim — From Generic Lit to MatCap"
lang: en
date: 2026-09-16
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> When we look at how the car model renders on the 3D car-model desktop, besides the car paint material we also pay attention to the wheel rim. The metallic feel and detail of the rim can visibly raise a car's sense of premium quality. But if it is done poorly — dim and rough-looking — the car starts to feel less real.

![fig_wheel_real](./fig_wheel_real.jpg)

This is a photo of a real wheel. The most eye-catching part is the multi-spoke alloy rim: sunlight hits from the side, the polished faces of the spokes reflect highlights, the recesses between spokes fall into dark shadow, and the tire rubber is nearly pure black — yet up close you can still make out its texture. What we need to do is reproduce these key points.

In past projects, the car-model desktop used a general-purpose Lit material with tuned parameters, while the SR approach used MatCap to pre-paint the reflection into a texture. The overall structure of this article:

*[Figures omitted; see the original WeChat article]*

---

# The Generic Lit Approach

The first time I made a wheel rim material, I used the car-wide, engine built-in URP Lit material. The metallic feel came from PBR parameter tuning, textures, and scene light placement — that is: **Metallic, Smoothness, BaseColor (dark gray), a normal map, and an AO map**.

## Metallic

Metallic is the most critical of all the parameters; it directly defines the character of the material. From the shader code you can see:

```hlsl
half oneMinusReflectivity = OneMinusReflectivityMetallic(metallic);
half3 brdfDiffuse  = albedo * oneMinusReflectivity;       // Diffuse is attenuated by metallic
half3 brdfSpecular = lerp(kDieletricSpec.rgb, albedo, metallic);       // F0 = lerp(0.04, base color, metallic)
outBRDFData.grazingTerm = saturate(smoothness + reflectivity);    // Grazing edges, approximating Fresnel

```

First, **diffuse is inversely related to metallic**. The higher the metallic value, the weaker the diffuse term — metal has no diffuse reflection of its own; light that arrives is reflected straight back out.

Second, **the base color of specular reflection interpolates between the dielectric value and the albedo**. `kDieletricSpec.rgb` is the 0.04 of a half4, which means a non-metal's Fresnel reflectance is 0.04, while a metal's Fresnel reflectance is the albedo itself. Metallic acts as the lerp factor, transitioning proportionally between the two.

Third, **the grazing edge is determined jointly by smoothness plus reflectivity**.

For the wheel rim parameters specifically, **0.5** means F0 sits roughly halfway between 0.04 and the dark gray base color. Half of a dark base is mixed into the reflection, the gloss is somewhat restrained, and — unlike full metal — it doesn't drown out the shapes of the spokes.

![fig_metal_052](./fig_metal_052.png)

What happens if you push it to 1? F0 becomes the full base color, the spoke shapes get swallowed by the reflection, and it looks like a chrome mirror. What about pushing it down to 0? Only diffuse remains, the highlights are gone, and it looks like plastic. Semi-metal sits exactly in the middle: it has the cool sheen of metal without losing shape. That is where the "piano black" rim quality comes from.

*[Figures omitted; see the original WeChat article]*

## Smoothness

Smoothness decides how sharp the highlights on this metal are. Lower it and the highlights spread out like a frosted surface; raise it and the highlights sharpen and blow out. So we generally set it around 0.5 as well, letting the highlight read as a clear bright band without blowing out into a white line.

As for `saturate(smoothness + reflectivity)` in the code — smoothness plus reflectivity, clamped to the 0–1 range — it brightens the edge by a ring. The "bright edge" effect comes from here; the Fresnel effect traces out the silhouette.

## Normal and AO Maps

Parameters can only give a rough sense of the material's character; the real detail needs textures.

*[Figures omitted; see the original WeChat article]*

I won't belabor the normal map — its job is to express **the bumps and recesses of the model surface**.

The AO map is there to express **the depth of the gaps** — between spokes, and where the spokes join the wheel center. Those places should read relatively darker. The AO map does this through one channel (say G):

```
float ResultAO = lerp(1.0, tex2D(_OcclusionMap, uv).g, _Occlusion);
```

The deeper the gaps, the stronger the sense of depth — but don't overdo it; too much and it starts to look dirty.

## The Tire

The tire uses the same Lit material, just with another set of parameters: **Metallic 0.2, Smoothness 0.4, a near-black base color**.

Rubber is a low-reflectance material, so both metallic and smoothness are kept lower than the rim's. For one thing, the tire's curved surface easily catches light and gets brighter. For another, keeping the tire dark hands the visual contrast over to the rim and creates a sense of layering.

If the tire needs to handle rain or snow effects, it can be adapted based on the car paint material.

---

# The MatCap Approach

Real-time reflection is fairly expensive, involving environment sampling and view calculations. The 3D desktop scene can afford it, but for an application like SR, where the per-frame load is already high, reflection is a place worth considering for savings.

Pre-store the environment reflection in a "metal ball" texture; at runtime, use the normal direction as an index to look up that image, and a single texture sample gives you a color that "looks like a reflection." That is the MatCap approach.

![fig_matcap_ball](./fig_matcap_ball.jpg)

The image above is a sample matcap texture. Its sampling principle: transform the normal into view space, take the xy components, scale and offset them to 0–1, and use them as the UV to sample the texture. Equivalent code reconstructed from the node graph:

```hlsl
float2 matcapUV = normalViewSpace.xy * 0.5 + 0.5;
float3 matcap = tex2D(_MatCapLookup, matcapUV);
```

Faces pointing straight at the camera sample the center of the texture; normals at the silhouette are perpendicular to the view direction and sample the edges. So the richness and realism of this reflection depend heavily on the matcap texture itself — you may need to try several matcap textures and compare. Below is a comparison with Lit: on the left, generic Lit computes lighting in real time; on the right, the SR-mode rim material with matcap.

![fig_lit_vs_matcap](./fig_lit_vs_matcap.png)

The cost of this approach is that the reflection content is fixed — rotate the camera and the highlight won't sweep across the way a real reflection would. But for SR, that's a good deal.

---

# Closing Thoughts

A wheel rim's final look is not decided by material parameters alone; it is also strongly tied to the scene lighting setup. In the current scheme, the rim is affected by a single directional light, and beyond that by the global ambient light. The ambient is configured as a Gradient — three heights, each corresponding to a different color.
