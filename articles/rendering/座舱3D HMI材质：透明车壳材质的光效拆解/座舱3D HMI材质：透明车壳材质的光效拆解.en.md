---
title: "Cockpit 3D HMI Materials: Breaking Down the Lighting of the Translucent Car Shell"
date: 2026-09-09
series: rendering
no: 
status: published
visibility: public
lang: en
wechat_url: ""
---

> Many HMI designs call for the car body to appear as a translucent shell on the energy management screen — a transparent inner cavity through which you can see the battery pack, with a ring of white-blue light glowing along the shell's edge. So how is this translucent material made?

To make the effect easy to see, the demo below uses a sphere in place of the car model, with an opaque white ball in the middle as the "battery pack" and the shell material from the project applied on the outside. You can see: the shell is a translucent blue-gray that tints the white ball inside with a layer of azure; the outer contour is brighter than the middle, whitish with a blue cast; and the environment reflection uses a procedurally generated gradient-sky cubemap.

![Translucent shell demo](./fig_ghost_main.png)

---

# I. The Translucent Shell

The translucent car shell is done in two steps: the first step uses alpha blending to make the shell translucent, and the second step uses the stencil test to make sure the shell only appears on the car body's surface, avoiding a "multi-layered skin" feel.

## 1. Blend Mode and Render Queue

The shell material's transparency choices:

```hlsl
Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
ZWrite Off
```

The render queue is set after the Geometry queue and before the Transparent queue, because the shell needs to sit over the car body and blend with it — it lives between the transparent layer and the opaque layer. So the opaque body and battery are drawn first, then the shell is drawn stacked on top.

The body color is a blue-gray BaseColor with an alpha of about 0.3. So the shell reads as a membrane "draped over" the outside, with the battery and interior showing through. Night mode needs a different color and a lower transparency to express that.

## 2. Stencil Test

The shell's visible area is controlled by the stencil test. This is the key design: the car shell does not decide where to draw — the marks in the stencil buffer do.

The stencil buffer can be understood as a "mask layer": whether a pixel can be drawn depends first on whether the corresponding position on the mask carries a stencil value.

```
Stencil {
    Ref [_Reference]       // Reference value: the number compared against the stencil buffer
    Comp [_Comparison]     // Comparison: the condition that must be met to draw
    Pass [_PassFront]      // What happens to the stencil buffer after the test passes
}
```

This material's default configuration is Comp = Disabled, so the comparison never passes and none of the car shell's own pixels are drawn — the shell is effectively "off" by default. Something external must first write the reference value into the stencil buffer, and then the shell's Comp is changed to Equal. That way, the shell is only drawn where "the stencil buffer is marked". Whatever shape the mark has, the shell has.

The benefit of this design is that the shell's shape can be controlled externally, without touching the car shell's mesh. The shell material itself is only responsible for "what it looks like" (translucency, rim light, reflection); as for "where it appears", that is entirely handed over to the stencil buffer.

---

# II. The Blue-and-White Light

How is the touch of white and blue at the shell's edge created?

## 1. The Main Fresnel

Faces pointing straight at you are dark; edges turned sideways toward you are bright. Like a glass ball or a soap bubble, the rim is always a ring brighter than the middle. The formula is still the standard Fresnel formula.

The main Fresnel's role here is not to produce the rim light. It controls which color the shell surface itself transitions from and to — that is, the body's color change. It makes the area facing you darker and grayer, and the edges brighter and bluer.

```
// Main Fresnel: dark when facing, bright at the edges
float NdotV = dot(normalWS, viewDirWS);
float fresnelBase = pow(max(1.0 - NdotV, 0.0001), _FresnelPower);

// Use the main Fresnel to transition between the inner and outer colors
float3 glassColor = lerp(_GlassInColor * baseColor, baseColor * _GlassOutColor, fresnelBase);
```

_FresnelPower controls how fast the transition happens: the larger the value, the narrower the bright band at the edge; the smaller the value, the more the bright region spreads toward the middle.

## 2. Two Offset Fresnels

A single Fresnel can only produce "one ring" at the edge, which is too thin. If you want a glow with some thickness, you can draw two staggered edges stacked on top of each other.

So, offset the view direction slightly to the side and compute Fresnel again — the bright edge's position shifts along with it. Stacking two bright edges offset in different directions makes the edge feel a bit thicker and heavier.

```
// Offset Fresnel 1: dark blue-gray, the base dark edge
float3 viewDirOffset1 = normalize(viewDirWS + _ViewDirOffset_One);
float fresnelRim1 = pow(max(1.0 - dot(normalWS, viewDirOffset1), 0.0001), _FresnelPower);
float3 rimColor1 = fresnelRim1 * _FCol_One;

// Offset Fresnel 2: pure blue, the accent bright edge
float3 viewDirOffset2 = normalize(viewDirWS + _ViewDirOffset_Sec);
float fresnelRim2 = pow(max(1.0 - dot(normalWS, viewDirOffset2), 0.0001), _FresnelPower);
float3 rimColor2 = fresnelRim2 * _FCol_Sec;
```

The two edges also differ in color: one is assigned a dark blue-gray as the base color, and the other is paired with pure blue as an accent. The stacked result is an edge with layers, not a single-color line.

At this point, all three Fresnels are in place: one manages the shell surface's color transition, and two staggered ones make the rim light.

## 3. Environment Reflection

With Fresnel alone, the edge would only get lighter in color — it wouldn't feel like it's "glowing". That touch of white comes from the environment reflection. The shell material samples a cube map (cubemap) as its environment.

```
// Environment reflection: sample the cubemap with the reflection vector
float3 reflDir = reflect(-viewDirWS, normalWS);
float3 envColor = texCUBE(_CubeDay, reflDir);

// Blend the body color and the environment reflection proportionally
float3 bodyColor = lerp(glassColor, envColor, _RefIntensity);
```

The face pointing at you reflects the environment behind you; the side faces reflect the environment to the side. Add the cubemap's own bright-top, dark-bottom gradient, and the contour naturally gets a ring of whitish highlight.

## 4. A Directionally Controllable Specular Band

Sometimes artists want a fixed bright band on a particular side of the car (for example, a sweep of light on the right shoulder to show off the car's side lines). That calls for a fourth player: a directionally controllable specular band.

Give it a custom light direction, use dot(light direction, normal) to find which faces point toward the light, then run it through smoothstep to produce a bright band:

```
// Specular band with a custom direction
float lightDot = dot(normalWS, _CustomLightDir);
float specBand = pow(saturate(smoothstep(_SpecularRange, _SpecularRange + _EdgeWidth, lightDot)), _CustomDirectLightPow);
float3 specColor = specBand * _Day_SpecularColor;
```

- _SpecularRange: where the bright band appears
- _EdgeWidth: how wide the bright band is
- _CustomDirectLightPow: how soft or hard the band's edge is
- _Day_SpecularColor: what color the bright band is

Whichever side should glow, point _CustomLightDir that way.

Combining all of the above gives the final color:

```
float3 finalColor = bodyColor + rimColor1 + rimColor2 + specColor;
finalColor = clamp(finalColor, 0, _ClampMaxValue);
```

bodyColor is the car shell surface's base color (main Fresnel transition + environment reflection), the two rimColors are the staggered rim lights, and specColor is the directionally controllable specular band. Stacked together, they form a shell whose midsection is a blue-gray reflective color, whose contour is a whitish-blue ring, and which carries a sweep of light on whatever side the artists specified.

---

# Closing Thoughts

I find these design details quite interesting: an effect that looks like a simple translucent shell can, because of one real requirement after another, be broken into more layers with different processing added to each, and finally combined to produce different results in different regions of a single frame.
