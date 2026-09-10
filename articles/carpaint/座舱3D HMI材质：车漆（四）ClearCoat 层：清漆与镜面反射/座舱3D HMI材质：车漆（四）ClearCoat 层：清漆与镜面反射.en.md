---
title: "Cockpit 3D HMI Materials: Car Paint (Part 4) — The ClearCoat Layer: Clearcoat and Mirror Reflection"
lang: en
date: 2026-08-12
series: carpaint
no: 4
status: published
visibility: public
wechat_url: ""
---

> The previous article covered the Flake layer's metal flakes and pearlescent effects. This one is the ClearCoat layer's turn, mainly introducing the clearcoat's gloss and mirror reflection.

Real car paint's "shine" does not come from cranking the color coat's Smoothness to 1. The gloss sits outside the color coat: the clearcoat provides gloss and reflects the environment, while the color coat and flakes beneath are seen through this layer of shine. Without the clearcoat layer, highlights are loose and hazy; with it, you get a sharp, thin mirror that can pull in the environment. The color coat's highlights are looser, the clearcoat's are sharper; stacked together, they create the lighting depth of real car paint. The paint's premium feel depends mainly on this layer of gloss.

![ClearCoat comparison](./ClearCoat对比.png)

# Illustrative Code

```hlsl
// 1. Clearcoat parameter definitions
_CoatIntensity("CoatIntensity", Range(0, 1)) = 0.8
_CoatSmoothness("CoatSmoothness", Range(0, 1)) = 0.9

// 2. Write into SurfaceData in the fragment shader
#ifdef _CLEARCOAT
    CoatMask = _CoatIntensity;
    CoatSmoothness = _CoatSmoothness * EdgeSmoothness; // multiplied by AO.a for local attenuation
#endif

// 3. Hand to the URP lighting function
surfaceData.clearCoatMask       = saturate(CoatMask);
surfaceData.clearCoatSmoothness = saturate(CoatSmoothness);
```

# How It Works

**1. Clearcoat parameters**

The clearcoat layer has just two knobs: `_CoatIntensity` controls the gloss coverage strength, `_CoatSmoothness` controls the mirror sharpness. Unlike the Base layer with its pile of parameters (Metallic, Smoothness, EdgeColor), the clearcoat's parameters are simple. `clearCoatMask` is coverage: 1 means this area got a full clearcoat spray, 0 means none, and intermediate values blend the two states proportionally. It is not a physical thickness — the real-time pipeline does not simulate the absorption that thickness would cause.

**2. Writing into SurfaceData**

Controlled in the fragment shader via the `_CLEARCOAT` toggle. When on, `_CoatIntensity` is assigned to `clearCoatMask`, and `_CoatSmoothness` multiplied by EdgeSmoothness is assigned to `clearCoatSmoothness`. EdgeSmoothness comes from the AO texture's alpha channel; its role is to weaken the clearcoat highlight in seams and recessed grooves, so the whole car doesn't gleam oily-bright.

**3. Handing to the URP lighting function**

Why is the clearcoat's highlight sharp? Light goes from air (refractive index about 1.0) into the clearcoat (resin, about 1.5), and at the interface a portion is reflected outright. This reflectance varies with viewing angle; URP uses a simplified Schlick approximation, `F = 0.04 + 0.96 × (1 − N·V)⁴`: head-on, only about 4% bounces off; the more grazing the view, the more reflection, approaching 100% at grazing angles. This is also one of the important reasons car paint edges always show a bright rim.

The remaining light passes through the clearcoat to the color coat (basecoat), is reflected by it, and passes back out. Strictly speaking, transmittance should be multiplied once for each pass in and out, but real-time rendering uses a single weighted blend — this is the approach the glTF clearcoat spec prescribes for energy conservation. What the clearcoat dims is the color coat's entire reflection (diffuse plus specular darken together), which is why clearcoated paint looks deeper and richer when viewed at an angle, producing that "lustrous" feel.

The final highlight = the clearcoat's direct reflection (white, sharp, thin) + the discounted color-coat reflection (colored, loose). The clearcoat acts on environment reflections the same way; in URP, much of the clearcoat's mirror feel comes from the stacking of environment reflections.

# Parameter Descriptions

```
// Note the value ranges
_CoatIntensity("CoatIntensity", Range(0, 1)) = 0.8
_CoatSmoothness("CoatSmoothness", Range(0, 1)) = 0.9
```

| Parameter | What it controls | Visual when decreased | Visual when increased |
|------|--------|-----------|-----------|
| `_CoatIntensity` | Gloss coverage strength | The clearcoat layer is barely visible; highlights are loose and hazy | Strong gloss feel, but dark-colored cars easily develop a whitish film |
| `_CoatSmoothness` | Mirror sharpness | Highlights go soft, like a semi-matte clearcoat | Highlights are razor sharp, like a freshly waxed mirror |

`_CoatSmoothness` governs the roughness of the clearcoat's microsurface, not its strength. The clearcoat mirror's strength is decided by the fixed Fresnel term; Smoothness only affects how sharp or blurry the highlight is.

# Conclusion

The clearcoat layer has just two parameters — simpler than both Base and Flake. The key to tuning is keeping the color coat's and clearcoat's smoothness separate: color coat low and loose, clearcoat high and sharp; don't twist them into one layer. If the car doesn't look shiny enough, raise CoatSmoothness first — don't touch the color coat. Once the clearcoat is on, environment reflections become more prominent, and thin distant highlights shimmer more easily — those are the next-layer problems that only show up once the clearcoat is done right. The next article deals specifically with reflections and anti-aliasing.