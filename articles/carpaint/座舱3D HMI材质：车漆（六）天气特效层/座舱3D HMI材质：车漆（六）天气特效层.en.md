---
title: "Cockpit 3D HMI Materials: Car Paint (Part 6) — The Weather Effects Layer"
lang: en
date: 2026-08-26
series: carpaint
no: 6
status: published
visibility: public
wechat_url: ""
---

> Following the paint-protection-film mask layer, this article finishes off the effects layer. Since charging/discharging effects were already covered in an earlier article, this one writes up the remaining weather effects — mainly how rain and snow are handled on car paint.

From the material layer's perspective, switching between sunny, rainy, and snowy is essentially state switching. A Toggle is used as the switch here, isolating each effect from the main flow. The rain effect mainly does normal perturbation, making the surface look like it has water droplets and trailing streaks; for snow, a suitable noise mask drives a Lerp, creating the realistic texture of snow settling on upward-facing surfaces.

![Weather comparison](./Weather对比.png)

# Rain

The rainy-day visual feel splits into the strike impact of falling raindrops and the flowing of rain streaks trailing down.

![1](./1.png)

The whole diagram boils down to one sentence: **two masks each contribute one normal perturbation; they are stacked, multiplied by strength and the global rain amount, and finally added to the main normal.** Base Color is untouched — the rain-on-paint effect is simulated purely through normal changes.

Below, the two contributions are taken apart and explained one by one.

## Parameters

First, an overview of the parameters:

```
// Note the value ranges
[Toggle(_ISWATER_ON)] _IsWater("IsWater", Float) = 0
_DropMask("DropMask", 2D) = "white" {}           // droplet strike normal + animation mask
_DroplineMask("DroplineMask", 2D) = "white" {}   // dropline normal mask
_Distrotion("Distrotion", Float) = 1
_DropTilling("DropTilling", Vector) = (4,3,0,0)
_DropStrengh("DropStrengh", Range(0, 1)) = 1
_DropStrikeSpeed("DropStrikeSpeed", Range(0, 2)) = 0.3
_DroplineSpeed("DroplineSpeed", Range(-0.5, 2)) = 0.2
```

## Key Functions

```hlsl
// SampleDropStrike: "smashes" one droplet out in one go
float4 SampleDropStrike(sampler2D mask, float2 uv, float strength, float strikeSpeed)
{
    float4 t = tex2D(mask, uv);
    float2 normal = (t.rg * 2.0 - 1.0);        // RG channels converted to a normal perturbation
    // alpha is the droplet animation phase: add time then take frac; it lights up only when phases align, realizing drop-by-drop strikes
    float phase = frac(t.b - _Time.y * strikeSpeed);
    float strike = step(1.0 - strength, phase); // the higher the strength, the more droplets can light up
    return float4(normal * strike, 0, strike);
}
```

**Raindrop strike (SampleDropStrike)**

The inputs are the `_DropMask` texture and three parameters: `strength` for intensity, `strikeSpeed` for refresh cadence.

The core logic:

1. **RG channels to normal direction**: the texture's R and G channels are multiplied by 2 and subtract 1, mapping into the [-1, 1] range, serving as each droplet's normal perturbation direction.
2. **B channel stores the phase; raindrops light up one by one over time**: the Blue channel stores each droplet's initial phase; subtract `_Time.y * strikeSpeed` and take `frac`, and the phase advances with time. Different droplets on the same texture have different Blue values, so as time sweeps across, droplets are lit up by `step` one after another, giving the rhythm of "raindrops landing on the paint one after another".
3. **Strength control**: `step(1.0 - strength, phase)` — the higher the strength, the lower the threshold, and the more droplets pop up simultaneously in a frame.

```hlsl
// SampleDropLine: droplines sweep downward along gravity
float4 SampleDropLine(sampler2D mask, float2 uv, float flowSpeed)
{
    // BA channels encode the dropline direction (B horizontal, A vertical); uv shifts down by _Time.y * flowSpeed
    float2 dir = (tex2D(mask, uv).ba - 0.5) * 2.0;
    float2 flowUV = uv + float2(0.0, _Time.y * flowSpeed) + dir * 0.1;
    float4 t = tex2D(mask, flowUV);
    return float4(t.b, t.a, 0, 1) * _DroplineStrength;
}
```

**Droplines (SampleDropLine)**

The inputs are the `_DroplineMask` texture and the `flowSpeed` flow-rate parameter.

The core logic:

1. **BA channel directional offset**: the texture's B and A channels each store a direction component (B horizontal, A vertical); subtract 0.5 and multiply by 2, mapping into [-1, 1], giving each dropline an initial directional offset.
2. **UV flows downward along the y axis**: `flowUV = uv + (0, _Time.y * flowSpeed) + dir * 0.1` — the main direction is downward along the y axis (gravity), with a directional offset layered on for fine-tuning, so the water trails bend a little naturally instead of being perfectly straight lines.
3. **Finally multiply by strength:** resample the texture with the flowed UV, take the BA channels as output, then multiply by `_DroplineStrength` to control the overall strength.

---

# Snow

The essence of snow accumulation is mixing a mask map.

## Parameters

```
// Note the value ranges
[Toggle(_ISSNOW_ON)] _IsSnow("IsSnow", Float) = 0
_SnowMaskMap("SnowMaskMap", 2D) = "white" {}     // snow density noise mask
_SnowMap("SnowMap", 2D) = "white" {}              // snow surface texture
_SnowBaseColor("SnowBaseColor", Color) = (0.85,0.85,0.85,1)
_SnowMetallic("SnowMetallic", Range(0, 1)) = 0
_SnowSmoothness("SnowSmoothness", Range(0, 1)) = 0
```

## Code

```hlsl
#ifdef _ISSNOW_ON
    // Weight: mask noise × upward component × scene snow intensity × vehicle-level coverage
    float mask = pow(tex2D(_SnowMaskMap, uvMask).r, 2.0) * 8.0;
    float up = max(normalize(WorldNormal).y - 0.1, 0.0);
    float w = clamp(max(SnowIntensity - 1.0, 0.0)
                  + min(SnowIntensity, 1.0) * mask * up, 0.0, 1.0)
            * CarSnowIntensity;

    albedo      = lerp(albedo, tex2D(_SnowMap, uvSnow).rgb * _SnowBaseColor.rgb, w);
    metallic    = lerp(metallic, _SnowMetallic, w);
    smoothness  = lerp(smoothness, _SnowSmoothness, w);
    normalWS    = BlendSnowNormal(mainNormalWS, snowNormalWS, w);
#endif
```

The weight w combines three inputs:

1. The noise mask from `_SnowMaskMap`. Squaring and multiplying by 8 stretches the noise's contrast, magnifying what were originally soft gray-level differences, so the final snow shows dense and sparse variation;
2. The world normal's upward component `normal.y` minus 0.1, lessening snow accumulation on some slanted surfaces;
3. The `SnowIntensity` parameter — beyond 1, the excess converts into forced full coverage, no longer constrained by mask or orientation.

If `SnowIntensity` is between 0 and 1, snow accumulation is determined by the influences of points 1 and 2 above; the excess directly becomes forced coverage. Once the weight w is computed, Albedo transitions toward SnowMap × SnowBaseColor, and so do metallic and smoothness. Because the snow surface's texture differs from the paint surface's, the normal should change as well.

> The BlendSnowNormal function blends the snow normal into the main normal according to the snow amount. It is three-stage, each stage handling one band of snow amount.
>
> **Low snow band (w ≤ 0.2)**: the snow is thin and cannot cover the paint; the original normal is used directly — the snow is just a thin dusting of powder and does not affect the surface texture.
>
> **High snow band (w ≥ 1)**: the snow has piled up fully; the snow surface has its own undulation and grain, breaking the mirror-flatness of the car paint, replaced by the snow's own rough texture.
>
> **Middle band (0.2 < w < 1)**: the snow normal's y component is multiplied by the weight — if W is small (say 0.2), y gets squashed; if W approaches 1, it is not compressed. After normalization, the normal direction thus achieves a transition from the original normal to the snow normal.

---

# Conclusion

At this point, the main components of the car paint have all been written up. In the time ahead, new requirements may still appear, and the car paint will gain more features accordingly.