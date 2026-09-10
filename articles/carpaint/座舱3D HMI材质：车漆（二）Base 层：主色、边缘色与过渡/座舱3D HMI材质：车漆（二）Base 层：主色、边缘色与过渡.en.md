---
title: "Cockpit 3D HMI Materials: Car Paint (Part 2) — The Base Layer: Main Color, Edge Color, and Transition"
lang: en
date: 2026-07-29
series: carpaint
no: 2
status: published
visibility: public
wechat_url: ""
---

> The previous article covered car paint's three-layer structure: Base / Flake / ClearCoat. This one starts from the first layer, Base, and walks through what the color-coat part involves.

What the Base layer does can be broken into several steps; the overall flow is shown below:

![image](./图1.png)

The processing flow has three steps: first the color blend (main color + edge color), then the primer's lighting parameters, and finally a smoothness falloff using AO.

![image](./图2.png)

# 1. Main Color and Edge Color

Step one of the Base layer: determine the paint's fundamental color — but using a single color for both head-on and side views is not enough. It should be one color when seen from the front, shifting darker and cooler when seen from the side; that creates a sense of layering.

The code uses two color values together with a transition factor:

```hlsl
_BaseColor("BaseColor", Color) = (1,1,1,0)
_EdgeColor("EdgeColor", Color) = (0.5,0.5,0.5,0)
_EdgeFactor("EdgeFactor", Range(0.01, 10)) = 1
```

`_BaseColor` is the color when viewed head-on, `_EdgeColor` is the color when viewed from the side, and `_EdgeFactor` controls how fast the transition happens.

The computation in the fragment shader:

```hlsl
float NDotV = 1.0 - saturate(dot(WorldNormal, WorldViewDirection));
float albedoFresnel = pow(NDotV, _EdgeFactor);
float4 baseEdge = lerp(_BaseColor, _EdgeColor, albedoFresnel);
```

1. `dot(WorldNormal, WorldViewDirection)` uses the dot product to compute the angle between the normal and the view direction.
2. `NDotV = 1.0 - saturate(...)` flips the angle's characteristic: close to 0 when viewed head-on, close to 1 from the side. This value feeds the fresnel-coefficient computation.
3. `pow(NDotV, _EdgeFactor)` turns the linear relationship into a curve. The larger `_EdgeFactor`, the narrower the region of the whole gradient occupied by the edge color.
4. `lerp(_BaseColor, _EdgeColor, albedoFresnel)` blends the two colors with a weight computed from the view angle and similar parameters — head-on leans toward the main color, side/edge leans toward the edge color.

This yields the base color the Base layer outputs. Flake and ClearCoat will be layered on top of it for further processing.

> `albedoFresnel` is just an empirical view weight used to drive the color transition, not the Fresnel reflection formula of physical optics. The clearcoat layer will have its own specular Fresnel — one handles the diffuse base color, the other handles specular reflection.

# 2. Primer Metallic and Smoothness

The Base layer also has two parameters: `_Metallic` and `_Smoothness`.

```hlsl
_Metallic("Metallic", Range(0, 1)) = 0
_Smoothness("Smoothness", Range(0, 1)) = 0.5
```

These two parameters describe the lighting characteristics of the color coat/primer itself. In real processes the color coat leans matte with a weak metallic feel; the mirror-like quality comes mainly from the clearcoat. So the values here are usually kept low:

- `_Metallic` close to 0, or raised slightly to give a metallic-paint foundation
- `_Smoothness` low-to-mid is fine; don't max it out

The final smoothness output is also combined with the Flake layer's parameter:

```hlsl
float ResultSmoothness = flake + _Smoothness;
```

# 3. Smoothness Attenuation from AO.a

The Base layer has one more supplementary treatment: using the AO texture's alpha channel to influence the smoothness of edge regions.

This requires an `_OcclusionMap`; the roles of the different channels are:

- **G channel**: regular AO, providing the ambient occlusion effect.
- **A channel**: multiplied into smoothness, controlled by the `_IsAOAlphaSmooth` toggle

```hlsl
float edgeSmoothness = AO.a * _IsAOAlphaSmooth + (1.0 - _IsAOAlphaSmooth);
float smoothness = ResultSmoothness * edgeSmoothness;
```

With the toggle on, AO.a is multiplied into both the primer smoothness and the clearcoat smoothness. Seams, dents, and dirt are drawn dark in AO.a; smoothness drops accordingly, and the highlights tighten up a bit.

This one is not mandatory. Without an AO.a channel, `_BaseColor` / `_EdgeColor` / `_EdgeFactor` alone can still produce the color transition. Having it just adds one more layer of texture quality.

# Putting the Code Together

The code from the three steps above is concatenated in order in the fragment shader, roughly like this:

```hlsl
// Fragment shader excerpt

// 1. Color blend: main color → edge color
float NDotV = 1.0 - saturate(dot(WorldNormal, WorldViewDirection));
float albedoFresnel = pow(NDotV, _EdgeFactor);
float4 baseEdge = lerp(_BaseColor, _EdgeColor, albedoFresnel);

// 2. Primer lighting parameters
float metallic = _Metallic;
float smoothness = _Smoothness;

// 3. AO.a smoothness attenuation
float edgeSmoothness = AO.a * _IsAOAlphaSmooth + (1.0 - _IsAOAlphaSmooth);
float ResultSmoothness = smoothness * edgeSmoothness;

// 4. Feed into URP PBR
// baseEdge → Albedo (Flake and paint protection film layers get stacked on later)
// ResultSmoothness → smoothness
// metallic → metallic
```

Once the Base layer is done, `baseEdge` and `ResultSmoothness` are handed to URP's lighting function; the Flake layer (metal flakes) and ClearCoat layer (clearcoat) are stacked on in subsequent steps.

# 4. Tuning

## Color Difference

The edge color is generally deeper than the main color; on dark metallic paints the edge can approach black. When multiple colors of one vehicle share the same shader, each color needs its own EdgeColor.

## EdgeFactor

`_EdgeFactor` controls the range of the edge-color transition: **the smaller the value**, the wider the range the edge color covers, and from a side view you transition to the EdgeColor's look very quickly. Recommended: fix `_BaseColor` and `_EdgeColor` first, then tune `_EdgeFactor` separately.

# Conclusion

Real car paint's view-dependent color shift comes from oriented pigment alignment and multiple scattering. In shader development, you reach for two colors plus a gradient control to approximate it. This, to me, reflects a very characteristic engineering ability of technical art: translating the physical world, compressing parameters, and fitting approximations until performance is controllable and the effect is good enough.