---
title: "Cockpit 3D HMI Materials: Car Paint (Part 3) — The Flake Layer: Metallic Flakes and Pearlescence"
lang: en
date: 2026-08-05
series: carpaint
no: 3
status: published
visibility: public
wechat_url: ""
---

> The previous post covered the Base layer's base-coat color. This post is the Flake layer's turn, mainly introducing metallic flakes and the pearlescent effect.

![image](./图1.png)

The aluminum flakes in metallic paint and the mica platelets in pearlescent paint are both grouped into the **Flake layer** in car paint materials. This layer mainly needs a flake texture as input, then computes the intensity and the sparkle color from view-dependent parameters. Solid-color paint can theoretically skip Flake. But 3D HMI rarely has scenes very close to the body (say, the camera pushing in next to the front wheel while adjusting the suspension); without getting close enough, you can't even tell whether there's a flake effect. Still, car paint shader development generally keeps this layer, and if it's unused, you simply don't assign a texture.

![image](./图2.png)

# Sketch Code

```hlsl
// 1. Sample the FlakeMap; Density controls the density
float flake = tex2D(_FlakeMap, uv * _FlakeDensity).r;

// 2. View weight: sparkles a lot when viewed head-on, suppressed from the side
float viewWeight = 1.0 - pow(NDotV, _FlakeFactor);

// 3. Combine intensity and view
flake *= viewWeight * _FlakeReflection;

// 4. Sparkle color: a power-based specular of the reflection direction against the view direction
float3 specColor = pow(max(0.0, dot(normalize(reflect(-L, N)), V)), _FlakeColorPower)
                 * _FlakeColor.rgb;

// 5. Add the final flake contribution to the Albedo
float3 flakeContribution = specColor * flake;
Albedo += flakeContribution;
```

# How It Works

**1. Sampling the FlakeMap**

Sample the R channel of `_FlakeMap` with `uv * _FlakeDensity` to get the flake mask. The larger the Density, the more the texture repeats, the denser the flakes, and the smaller each bright point; conversely, sparser flakes and larger bright points. The texture itself needs to be high-frequency noise.

![T_FlakeMap_Demo](./图3.png)

**2. Computing the View Weight**

`1 - pow(NDotV, _FlakeFactor)` gives the view weight: a high weight and clearly visible bright points when viewed head-on; a low weight and suppressed brightness when viewed from the side. The NDotV here is shared with the Base layer — the Base layer uses it to blend the edge color, while Flake uses it to dim the side-view bright points.

**3. Combining the Total Intensity**

Multiply the sampling result by the view weight, then by `_FlakeReflection`, to get the final flake intensity. Reflection is a global gain that raises or lowers the effect uniformly.

**4. Computing the Sparkle Color**

Take the reflection direction `reflect(-L, N)` and compute the dot product with the view direction. After measuring how much the reflection direction differs from the view direction, raise that difference to a power to get the specular intensity. Finally, multiply by `_FlakeColor` to get the color form of the sparkle.

`_FlakeColorPower` controls the specular sharpness: the larger it is, the steeper the power curve, and the narrower, sharper, more point-like the highlight; conversely, the smaller it is, the softer the metallic feel. Metallic paint uses a cold-leaning white; pearlescent paint shifts the color toward the target hue.

**5. Adding to the Albedo**

Add `specColor * flake` onto the Albedo computed by the Base layer, additively. The flake value can also be added to the Smoothness at the same time, raising the smoothness of the flaked areas.

# Parameter Reference

```
// Watch the value ranges
_FlakeMap("FlakeMap", 2D) = "white" {}
_FlakeDensity("FlakeDensity", Float) = 0
_FlakeFactor("FlakeFactor", Range(0.01, 1)) = 0.01
_FlakeReflection("FlakeReflection", Range(0, 10)) = 0
_FlakeColor("FlakeColor", Color) = (0,0,0,0)
_FlakeColorPower("FlakeColorPower", Range(1, 20)) = 10
```


| Parameter | What it governs | Visual effect when lowered | Visual effect when raised |
| ------------------ | ------ | ---------------- | ------------------ |
| `_FlakeDensity` | Flake density | Sparse flakes, large points; up close it looks like a few aluminum flakes | Dense flakes, fragmented points; from afar it easily smears into noise |
| `_FlakeFactor` | Front/side proportion | Sparkle points concentrate in the head-on region; the sides barely sparkle | The sides also show clear sparkle points, with a more even distribution |
| `_FlakeReflection` | Overall brightness | As if Flake were off; the flakes are barely perceptible | The body goes whitish, washing out the Base color underneath |
| `_FlakeColorPower` | Sparkle sharpness | The sparkle spreads out; a soft metallic feel over a large area | The sparkle narrows into a point-like highlight that pops noticeably |
| `_FlakeColor` | Sparkle hue | Neutral white/cool gray; a pure metallic glint | A clear hue shift (purple/gold/cyan); a pearlescent feel |


# Closing

Tuning depends on which FlakeMap you chose, so no absolute recommended values can be given. If the FlakeMap's contrast is low, Density and Reflection will need to be higher. Then go tune Factor and Color/ColorPower. Once you find that barely-there feel, flickering at the edge of the highlight regions, I'd say the effect is about right.
