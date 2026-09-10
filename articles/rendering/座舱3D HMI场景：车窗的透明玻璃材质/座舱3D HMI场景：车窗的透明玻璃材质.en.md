---
title: "Cockpit 3D HMI Scenes: Transparent Glass Materials for Car Windows"
date: 2026-07-02
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered frosted glass — [Cockpit 3D HMI Scenes: A Frosted Glass Material Approach Based on Global Blur Optimization](https://mp.weixin.qq.com/s/hx1XGh2fdBDcPpxR8GJXRQ). In 3D scenes, though, what you encounter far more often is the need for transparent glass: car windows, lamp covers, semi-transparent regions of the car body. Its defining trait is balancing a see-through quality with appropriate refractive and reflective visual effects.

The transparent glass effect simulates light refracting through a transparent medium, along with reflection and the Fresnel edge response. In 3D HMI in-vehicle applications, we often also layer clearcoat highlights and environment reflections on top, so the glass feels both transparent and three-dimensional.

---

## 1. Refraction

Frosted glass's "screen-space distortion" offsets UVs to sample a globally blurred texture. Transparent glass does no blurring—its refraction is physical: it uses the normal's XY components to offset screen UVs and sample the **sharp screen color**. The offset magnitude is controlled by the index-of-refraction parameter; the higher the IOR, the larger the offset.

> Windshield materials tend to disable refraction: the windshield covers a large area with low curvature, and refraction there reads as over-expressed and distorted. Lamp glass and window glass enable refraction—smaller areas with higher curvature, where refraction enhances the sense of volume.

Sketch code; unlike frosted glass, here we sample `_CameraOpaqueTexture` for physical refraction:

```hlsl
// Refraction offset for transparent glass: normal XY × refraction offset coefficient
// Note: frosted glass uses ddx(fresnel) and ddy(fresnel); here the normal drives it directly
float2 refractionOffset = worldNormal.xy * _BumpRefraction * (_IOR - 1.0);

// Sample the sharp screen color (frosted glass samples _GlobalBlurTexture)
float2 screenUV = ComputeScreenPos(positionCS).xy / ComputeScreenPos(positionCS).w;
float3 refractionColor = tex2D(_CameraOpaqueTexture, screenUV + refractionOffset).rgb;
```

---

## 2. Fresnel

Once transparent glass obtains its Fresnel value, it doesn't do the frosted-glass-style inner/outer color blending. Instead it does **multi-layer edge highlight stacking**: dot the offset view direction with the world-space normal to compute two separate edge highlight colors, and add them directly onto the final result. This keeps the glass edges from merely "whitening"—instead they carry subtle hue variations, closer to the rainbow dispersion seen on real glass edges.

Sketch code; the base Fresnel calculation is identical to frosted glass, so it isn't repeated:

```hlsl
// The code below is unique to transparent glass; frosted glass has none of this
// First edge highlight layer: dot product after offsetting the view direction
float3 offsetViewDir1 = normalize(viewDir + _ViewDirOffset_One);
float edgeHighlight1 = pow(max(1.0 - dot(worldNormal, offsetViewDir1), 0.0001), _Power);
float3 edgeColor1 = lerp(_FCol_One, _NightFCol_One, _IsNight) * edgeHighlight1;

// Second edge highlight layer: another offset direction
float3 offsetViewDir2 = normalize(viewDir + _ViewDirOffset_Sec);
float edgeHighlight2 = pow(max(1.0 - dot(worldNormal, offsetViewDir2), 0.0001), _Power);
float3 edgeColor2 = lerp(_FCol_Sec, _NightFCol_Sec, _IsNight) * edgeHighlight2;

// Add onto the final color (frosted glass lerps; here we add)
finalColor = refractionColor + edgeColor1 + edgeColor2;
```

---

## 3. Normal Maps

The transparent glass normal map **participates directly in the refraction UV offset**. In the refraction code of section 1, `worldNormal.xy` is exactly the normal sampled from the normal map and transformed into world space. This means the normal map's bumps show up directly as distortion of the background, rather than only indirectly influencing Fresnel as in frosted glass.

Additionally, the transparent glass normal map also joins the raindrop normal overlay in the weather system. The raindrop normals are added directly onto the glass normal, changing the refraction direction to simulate raindrops perturbing the light.

---

## 4. Environment Reflection

Transparent glass has richer environment reflection than frosted glass, with two implementations:

The first is Cubemap reflection, useful when the energy screen needs to show a transparent car shell. It uses a day/night pair of Cubemap textures with customizable reflection content: blue sky and white clouds by day, city lights at night. Frosted glass has no Cubemap reflection.

The second is URP's built-in environment reflection, the same one frosted glass uses: `GlossyEnvironmentReflection`, enabled by default. This is where smoothness comes into play.

> The window glass material's `_Smoothness` is close to 1, nearly mirror-like;
>
> the lamp glass material's `_Smoothness` is close to 0.5, giving a fairly blurred reflection.

Transparent glass also has one extra feature: a custom highlight.

It uses a `CustomLightDir` parameter to specify a fixed-direction light for computing the highlight region, simulating the highlight of a main light in a fixed direction.

Sketch code, excluding URP's built-in environment reflection (identical to the frosted-glass article):

```hlsl
// The code below is unique to transparent glass; frosted glass has none of this
// Cubemap reflection: interpolating the day/night texture pair
float3 reflectDir = reflect(-viewDir, worldNormal);
float3 dayReflection = texCUBE(_CubeDay, reflectDir).rgb;
float3 nightReflection = texCUBE(_CubeNight, reflectDir).rgb;
float3 cubemapReflection = lerp(dayReflection, nightReflection, _IsNight);

// Custom highlight: a fixed-direction light source
float customSpec = dot(normalize(_CustomLightDir), worldNormal);
customSpec = smoothstep(_SpecularRange, _SpecularRange + _EdgeWidth, customSpec);
customSpec = pow(customSpec, _CustomDirectLightPow);
float3 specColor = lerp(_Day_SpecularColor, _Night_SpecularColor, _IsNight) * customSpec;
```

---

## 5. Clearcoat

The clearcoat layer is unique to transparent glass. This coat produces an independent specular reflection layered on top of the underlying glass.

The implementation adds one more highlight layer over the existing surface: use the clearcoat normal to compute the reflection direction, sample environment reflection, then multiply by the clearcoat intensity and tint. The clearcoat's smoothness is usually very high (near 1.0), producing sharp specular points.

> Lamp glass and window glass usually enable the clearcoat; the windshield disables it.
>
> Because a clearcoat highlight across a large area looks too "oily."

```hlsl
// The code below is unique to transparent glass; frosted glass has none of this
float3 coatReflectDir = reflect(-viewDir, worldNormal);
float coatRoughness = 1.0 - _ClearCoatSmoothness;
float3 coatReflection = GlossyEnvironmentReflection(
    coatReflectDir, worldPosition, coatRoughness, 1.0, screenUV
);
float3 coatColor = coatReflection * _CoatSpecularIntensity * _CoatTint.rgb;
finalColor += coatColor * _ClearCoatMask;
```

---

## 6. Day/Night Switching

Transparent glass's day/night switching is far finer-grained than frosted glass's. Almost every key parameter has its own night variant: Fresnel, reflection intensity, smoothness, normal strength, and custom highlight direction all come in day and night versions. The Cubemap reflection also has separate day and night textures.

```hlsl
// The code below is parameter-level day/night switching unique to transparent glass; frosted glass only lerps the base color
float currentPower = lerp(_Power, _NightPower, _IsNight);
float currentRefIntensity = lerp(_RefIntensity, _NightRefIntensity, _IsNight);
float currentSmoothness = lerp(_Smoothness, _NightSmoothness, _IsNight);
float currentBumpScale = lerp(_BumpScale, _NightBumpScale, _IsNight);

// The Cubemap is split day/night too (frosted glass has no Cubemap)
float3 envReflection = lerp(
    texCUBE(_CubeDay, reflectDir).rgb,
    texCUBE(_CubeNight, reflectDir).rgb,
    _IsNight
);
```

---

## 7. Weather System

This is a common requirement for 3D car-model desktop scenes: raindrops and running-water streaks on the glass when it rains, snow accumulation when it snows, fog covering the glass in foggy weather.

The raindrop effect is built from a raindrop normal map and a flowing-water mask. Raindrop normals are added onto the glass normal, directly changing the refraction direction. The flow mask controls where raindrops appear, and the flow speed drives a UV offset with a time function.

The snow effect uses BaseMap, NormalMap, and RoughnessMap to simulate the look of accumulated snow.

The fog effect uses a mask to control the fog's distribution and density.

```hlsl
// The code below is unique to transparent glass; frosted glass has none of this
// Raindrop normals: sample and add onto the glass normal, affecting the refraction direction
float3 rainDropNormal = UnpackNormal(tex2D(_RainDropTexture, uv * _RainDropTiling + float2(0, _Time.y * _RainDropSpeed)));
rainDropNormal *= _RainDropNormalStrength * rainDripMask;
worldNormal = normalize(worldNormal + rainDropNormal);

// Snow: blend the snow color using a mask
float snowMask = tex2D(_SnowMaskTexture, uv).r;
float3 snowColor = tex2D(_SnowBaseMap, uv).rgb;
finalColor = lerp(finalColor, snowColor, snowMask * _SnowIntensity);

// Fog: overlay the fog color using a mask
float fogMask = tex2D(_FogMaskTexture, uv).r;
finalColor = lerp(finalColor, _FogColor.rgb, fogMask * _FogAlpha);
```

---

## Closing

Looking at the whole pipeline, transparent glass is more complex than frosted glass, because it couples more deeply with business requirements—weather effects and day/night mode, for instance. But complexity also means plenty of room for adjustment, and more situations it can adapt to and vary across.
