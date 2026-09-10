---
title: "Cockpit 3D HMI Scene: Discharge Effect"
lang: en
date: 2026-05-29
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article covered the charging dissolve effect: [Cockpit 3D HMI Scene: Charging Effect](https://mp.weixin.qq.com/s/11f-tEIeHAuRpgG9jKMdpg) — including injecting the dissolve origin through a global variable, C#-side Keyword switching, and the shader-side ring scan wave + triangle-wave pulse + pow(2) + teal-green color scheme. This article won't repeat those shared parts; **it only covers how discharge differs from charging**.

Discharge and charging are actually written in the same Function of the same shader tool plugin (Shader Graph, ASE). They share the spatial origin of the dissolve, and both are ultimately layered on top of the Albedo. However, the discharge effect introduced here has different design requirements from charging: it doesn't spread outward from a point, but instead creates a "breathing light" effect within the charging port cover area, to convey the sense that energy is being supplied. The development differences concentrate on three points: **intensity calculation**, **timing rhythm**, and **color**.

---

## 1. The C# side

For discharge, you only need to enable one extra Keyword on top of charging: `_ISDISCHARGE_ON`. Inside the Function, it flips the node-graph wiring path over to the discharge logic. Everything else (the master switch, the dissolve origin) is identical to charging, so I won't repeat it.

---

## 2. The shader side

### 2.1 Intensity calculation: distance gradient → pow(10) for sharp focus

The charging effect builds a ring scan wave with `frac + smoothstep`. Discharge doesn't need a scan animation — **it applies falloff directly using the pixel's distance to the charging port**:

```hlsl
float maxRadius = 6.0;        // effective influence radius
float normalizeFactor = 5.0;  // normalization span
float gradient = clamp((maxRadius - dist) / normalizeFactor, 0.0, 1.0);
```

Here `gradient` is 1 (bright) near the origin and 0 (dark) far from it, dropping to zero beyond 6 units. After multiplying by the breathing value, apply `pow(10)`:

```hlsl
float rawIntensity = gradient * breath;
float intensity = pow(rawIntensity, 10.0);
```


| dist | gradient | rawIntensity (breath=1) | intensity = pow(x, 10) |
| ---- | -------- | ---------------------- | ---------------------- |
| 0    | 1.0      | 1.0                    | 1.000                  |
| 1    | 1.0      | 1.0                    | 1.000                  |
| 2    | 0.8      | 0.8                    | 0.107                  |
| 3    | 0.6      | 0.6                    | 0.006                  |
| 4    | 0.4      | 0.4                    | 0.0001                 |
| 6    | 0.0      | 0.0                    | 0.000                  |


pow(10) produces a pronounced **threshold effect** here: when gradient is above 0.8, intensity is close to 1; once gradient falls below 0.6, intensity collapses rapidly to zero. Visually, the glow is **highly concentrated within roughly 2 units around the charging port** and vanishes sharply beyond that — completely different from the wide, soft band of charging's `pow(2)`.

### 2.2 Timing rhythm: sine breathing instead of a triangle-wave pulse

The charging effect builds a triangle-wave pulse with `frac + abs`: sharp-edged, with a period of about 1 second. Discharge instead simply uses Unity's built-in _SinTime and takes its absolute value:

```hlsl
float breath = clamp(abs(_SinTime.w), 0.0, 1.0);
```

`_SinTime.w` is essentially the sine of `_Time.y * π/2`, at a frequency of about 0.25Hz (a full sine cycle takes 4 seconds). `abs` performs full-wave rectification, flipping the negative half-cycle into the positive half — which shortens the final period to 2 seconds (the value goes 0→1→0→1→0). Compared with charging's 1-second triangle wave, the discharge breathing changes more slowly and transitions more smoothly.

### 2.3 Applying color: blue

The discharge color is chosen per the design requirements, usually blue (for example, (0.29, 0.48, 0.75)). Color switching is done through the `_ISDISCHARGE_ON` Keyword, with branch selection inside the same Function.

---

## 3. Comparison


|         | Charging | Discharge |
| ------- | ----------------------- | ---------------------- |
| Spatial pattern | Ring scan wave: frac + smoothstep | Distance gradient: maxRadius - dist |
| Timing rhythm | Triangle-wave pulse | Sine breathing |
| Falloff exponent | pow(2) — wide soft band | pow(10) — sharp focus |
| Color | Teal green | Blue-purple |
| Keyword | `_ISDISCHARGE_ON` = off | `_ISDISCHARGE_ON` = on |
| Visual metaphor | Energy **pouring into** the car body from the charging port | The charging port in an **actively supplying** state |


---

## Closing thoughts

The discharge effect shown here is fairly simple, so there isn't much to write about. Still, the takeaway is this: any scenario that needs to switch visual modes on the same material (rain/snow, cleaning, color changes) can adopt this **Keyword branching** approach — shared inputs and outputs, internal paths that fork by mode, unselected branches culled at compile time, and each mode carrying only its own share of the computation.
