---
title: "Cockpit 3D HMI Materials: Car Paint (Part 1) — Layered Structure and Overall Composition"
lang: en
date: 2026-07-22
series: carpaint
no: 1
status: published
visibility: public
wechat_url: ""
---

> Starting to write the car paint shader — in this post I'll first share what a car paint might consist of. Later, starting from each component, I'll go through the details one by one.

The look of car paint is built up layer by layer. With just a reflective, metallic base color, it looks somewhat "fake". In past development, the common visual problems were an overall washed-out gray, a plasticky feel, and flickering highlights in places. To solve these, we tried decomposing the car paint effect into layers, and each will be explained in detail in the upcoming posts of this series.

![image](./图1 效果图.png)

# The Layered Structure

Real car spraying applies at least two coats: the base coat and the clear coat. Some finishes add a third: base coat + pearlescent coat + clear coat. For rendering, following this application process, we divide it into:

- **Base layer (primer/base coat)**: expresses the base color, solving the grayish look from the side
- **Flake layer (metallic/pearlescent paint)**: expresses the graininess, adding metallic feel and sparkle
- **ClearCoat layer (clear coat)**: expresses the mirror-like quality, providing a layer of soft reflective sheen

![图1_工艺涂层与渲染三层对照](./图1_工艺涂层与渲染三层对照.png)

# Breaking Down the Content

The three layers (Base / Flake / ClearCoat) are the visual foundation, but a production car-paint Shader involves more than that. You also have to consider what a body-color change must stay compatible with, what a charging effect requires, and so on.

## Visual Effects

### Base Layer: Base Color + Edge Color + Fresnel

The base coat expresses the car paint's fundamental color, but a BaseColor alone won't do here — it needs a companion EdgeColor. The color looks different from the front than from the side; use Fresnel (the angle between the view direction and the normal) to control the transition between the two, and the base color gains visual richness. This layer solves the basic problem of "car paint looking gray and plasticky".

```hlsl
_BaseColor("BaseColor", Color) = (1,1,1,0)
_EdgeColor("EdgeColor", Color) = (0.5,0.5,0.5,0)
_EdgeFactor("EdgeFactor", Range(0.01, 10)) = 1
_Metallic("Metallic", Range(0, 1)) = 0
_Smoothness("Smoothness", Range(0, 1)) = 0.5
```

Here the smoothness and metallic values are relatively low because this is the base coat; they'll be combined with the clear coat layer's smoothness/metallic later on.

### Flake Layer: Metallic Flakes and Pearlescent Color Shift

The aluminum flakes in metallic paint and the mica platelets in pearlescent paint both live in this layer. Viewed from different angles, there must be subtle sparkle points and color shifts to convey the texture of metallic and pearlescent paints. The core is a FlakeMap (flake texture) plus view-dependent color and reflection modulation.

Solid-color paint can skip this layer, but since scenes where you view the paint up close are rare, keeping metallic and pearlescent is common practice. Without the Flake layer, the paint has a metallic feel but no graininess — not a big issue when viewed from afar.

```hlsl
_FlakeMap("FlakeMap", 2D) = "white" {}
_FlakeDensity("FlakeDensity", Float) = 40
_FlakeColor("FlakeColor", Color) = (1,1,1,0)
_FlakeColorPower("FlakeColorPower", Range(1, 20)) = 10
_FlakeReflection("FlakeReflection", Range(0, 10)) = 1
_FlakeFactor("FlakeFactor", Range(0.01, 1)) = 0.2
```

`_FlakeMap` is the flake texture; `_FlakeDensity` controls how dense the flakes are; `_FlakeColor` and `_FlakeColorPower` govern the hue shift for pearlescent paint; `_FlakeReflection` and `_FlakeFactor` govern the flakes' reflection strength and overall proportion.

This layer solves the problem of the paint lacking metallic graininess.

### The ClearCoat Layer

The clear coat is the outermost layer of the finish and must visually convey reflectivity. It produces an independent specular highlight, making the paint look as if coated with a layer of glossy varnish.

The shine of real car paint comes from that outermost clear coat reflecting light. Without a ClearCoat, the paint's highlight is "scattered and hazy", like a matte surface rather than a mirror. The clear coat's smoothness is far higher than the base coat's; only with the two layers of highlights stacked together do you get the lighting depth of real car paint.

```hlsl
_CoatIntensity("CoatIntensity", Range(0, 1)) = 0.8
_CoatSmoothness("CoatSmoothness", Range(0, 1)) = 0.9
```

`_CoatIntensity` controls the clear coat's intensity; `_CoatSmoothness` its smoothness.

This layer solves the problem of the paint not being shiny enough and lacking reflectivity. The clear coat is the main source of a car paint's "premium feel".

> Each of the three layers above will get its own post in this series. Considering reflection characteristics and anti-aliasing needs, there will also be an additional post on how reflections and anti-aliasing are adapted to the car paint material.

## Style Variations

When one vehicle model comes in multiple body colors and different wraps, we need materials with different configurations. Clearly we won't create a material per color. So the car-paint shader must be reusable — one Shader able to carry all body-appearance requirements through parameters, textures, and variants.

### Wrap Mask

Use a SkinMap (or MaskMap) to mask parts of the body, implementing a wrap on its own, or combined with the wrap, decal effects.

### UV Switching

The paint's own textures use the model's UV (UV0), but wraps and decals may need a separate set of UVs (UV1) for drawing — which leads to different handling for the paint and the wrap.

## Business Extensions

The same Shader also has to handle cockpit-specific business requirements: charge dissolve, raindrops, snow, day/night mode switching... These aren't a new layer or a new "effect" — they are implemented on the existing shader layers by modifying color, normals, smoothness, and alpha.

This includes compatibility with the following effects:

- Charging effects: depending on requirements, may need to support height gradients and noise perturbation.
- Weather effects: raindrop flow and snow coverage, each at varying degrees of intensity.
- Day/night mode: drive material parameter adjustments with ambient lighting through global variables.
- Other effects: for example, a dirty body before a car wash, or localized scratches and wear.

## Foundational Choices

### 1. Extending URP Lit

Extend from the URP Lit template: stack the car-paint layers (Base / Flake / ClearCoat) and the business toggles on Lit's lighting skeleton. The code can get bloated (a different story if you use ASE or Shader Graph), but reflection and shadow computation stay consistent with the other Lit materials in the scene.

### 2. Surface Type

Apart from the transparent car shells prepared for special effects, everything using this paint is opaque. So: **Opaque**.

### 3. Single Pass

Base, Flake, and ClearCoat are all processed in one pass. This keeps DrawCalls under control and makes it easy to hang the business Keywords described in the next section on the same block of code.

### 4. Keywords

Charge dissolve, raindrops, snow, and the paint share one Shader, and each of them is computationally nontrivial — Keywords can help trim things down.

## Closing

The car paint shader will be covered across multiple posts. Stay tuned for the rest of this series.
