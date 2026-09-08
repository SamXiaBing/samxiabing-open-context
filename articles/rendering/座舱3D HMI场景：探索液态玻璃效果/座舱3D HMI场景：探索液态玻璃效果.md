---
title: "座舱3D HMI场景：探索液态玻璃效果"
date: 2026-07-02
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 在之前写了[《座舱3D HMI场景：全局模糊优化的毛玻璃材质方案》](https://mp.weixin.qq.com/s/hx1XGh2fdBDcPpxR8GJXRQ)之后，有朋友评论说想看看液态玻璃的内容。然而，液态玻璃我并没有在项目交付中用到过，所以本文是怀揣着学习探索的心态来做的记录。

苹果在 WWDC 2025 发布了"液态玻璃"（Liquid Glass）设计语言。它的视觉观感近似毛玻璃，但在细节丰富度和高级感维度远超普通毛玻璃。

液态玻璃的核心是三层结构：底部折射层、边缘折射反光层、表面高光层，三层协同作用才能呈现出真实的玻璃质感。

> 液态玻璃和普通毛玻璃的明显区别应在于边缘质感。普通毛玻璃只有均匀模糊，液态玻璃在边缘区域有专属的光线折射与反光质感，边缘的视觉层次远多于中心区域。

然而，我理解下来，液态玻璃是属于 UI 控件的材质范畴，并不是常见的需求场景。所以我当前的尝试还是从 3D 物体出发去复现，没有使用 UGUI 的组件。

![image](./image.jpg)

---

## 第一层：底部折射层

底部折射层的任务是采样背景画面并做模糊处理。它同时做了两件事：用法线驱动的折射偏移采样清晰的背景，以及用多采样 Box Blur 得到模糊背景，然后在两者之间做混合。

折射偏移的计算和透明玻璃文章中的原理相同。不同的是透明玻璃只采样清晰背景，液态玻璃在清晰采样的基础上还做了 8-tap Box Blur（上下左右 + 四个对角线方向各采样一次，取平均值），得到模糊版本。

混合时有一个设计：用 Fresnel 的边缘遮罩（edgeMask）控制混合比例。中心区域 edgeMask 接近 0，清晰背景占比高（看得清背后）；边缘区域 edgeMask 接近 1，模糊背景占比高（有包裹感）。这种"中心清晰、边缘模糊"的渐变是液态玻璃底层的视觉特征。

混合完成后还会叠加一层底色染色（_BaseColor），让玻璃有轻微的色调倾向，而不是完全无色。

示意代码：

```hlsl
// 折射偏移：法线 XY × (IOR - 1) × 系数
float2 refractionOffset = finalNormal.xy * (_IOR - 1.0) * 0.05;
float2 refractionUV = screenUV + refractionOffset;

// 清晰背景采样
float3 clearColor = SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV).rgb;

// 8-tap Box Blur 模糊背景采样
float2 texel = _BackgroundTex_TexelSize.xy * _BlurIntensity;
float3 blurColor = float3(0, 0, 0);
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV + float2(texel.x, 0)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV - float2(texel.x, 0)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV + float2(0, texel.y)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV - float2(0, texel.y)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV + float2(texel.x, texel.y)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV - float2(texel.x, texel.y)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV + float2(-texel.x, texel.y)).rgb;
blurColor += SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, refractionUV + float2(texel.x, -texel.y)).rgb;
blurColor /= 8.0;

// 用 edgeMask 控制混合：中心偏清晰，边缘偏模糊
float blurMix = lerp(_BlurMix * 0.3, _BlurMix, edgeMask);
float3 layer1 = lerp(clearColor, blurColor, blurMix);

// 底色染色
layer1 = lerp(layer1, layer1 * _BaseColor.rgb, _BaseColor.a);
```

---

## 第二层：边缘折射与反光层

这是液态玻璃区别于普通毛玻璃的关键。它只在面板的边缘区域生效，通过 edgeMask控制。中心为 0（不渲染），边缘为 1（完全渲染）。

更强的折射采样：折射偏移系数比第一层大（0.15 vs 0.05），在边缘产生更明显的背景扭曲，模拟玻璃边缘曲率更大的光线偏折。

边缘反光：用反射方向和光源方向的点积乘幂函数得到高光，模拟玻璃边缘在环境光下的反光质感。

两层叠加后用 edgeMask 掩码，确保只在边缘区域可见。

示意代码：

```hlsl
// 边缘折射：比第一层更强的偏移
float2 edgeRefractionOffset = finalNormal.xy * (_IOR - 1.0) * 0.15 * _EdgeRefractionIntensity;
float3 edgeRefraction = SAMPLE_TEXTURE2D(_BackgroundTex, sampler_BackgroundTex, screenUV + edgeRefractionOffset).rgb;

// 边缘反光：反射方向 × 光源方向
float3 reflectDir = reflect(-viewDirWS, finalNormal);
float edgeReflection = pow(max(dot(reflectDir, normalize(_LightDir.xyz)), 0.0), 8.0);
edgeReflection *= _EdgeReflectionIntensity;

// 叠加后用 edgeMask 掩码
float3 layer2 = edgeRefraction + edgeReflection * _EdgeColor.rgb;
layer2 = lerp(float3(0, 0, 0), layer2, edgeMask);
```

---

## 第三层：表面高光层

有了这一层，玻璃表面就有了被光源照亮的高光点。取光源方向和视线的半角向量，用法线和半角向量做点积，乘以幂函数得到锐利的高光点。高光的颜色、强度、锐度都可以通过参数调节。

除了主光源高光，再叠加一个顶部环境光高光带，模拟从顶部过来的环境光在玻璃表面的反射。这个高光带让玻璃看起来像在一个有顶光的环境中。

示意代码：

```hlsl
// 高光：法线 × 半角向量
float3 lightDir = normalize(_LightDir.xyz);
float3 halfDir = normalize(lightDir + viewDirWS);
float specHighlight = pow(max(dot(finalNormal, halfDir), 0.0), _SpecPower);
specHighlight *= _SpecIntensity;

// 顶部环境光高光带
float topGloss = pow(max(dot(finalNormal, float3(0, 1, 0)), 0.0), 5.0) * 0.3;

float3 layer3 = _SpecColor.rgb * specHighlight + float3(1, 1, 1) * topGloss;
```

---

## 三层合成

三层通过加法叠加得到最终颜色。合成后叠加一层 Fresnel 边缘高光和色调染色，让整体效果更完整。

交互响应是在片元着色器中计算当前像素到触摸点的距离，根据距离衰减产生法线形变。这个形变叠加到法线上后，会同时影响第一层的折射偏移、第二层的边缘折射方向、第三层的高光位置。实现一个交互效果。

示意代码：

```hlsl
// 触摸形变（在三层计算之前）
float distToTouch = distance(worldPos, _TouchPos.xyz);
float touchFalloff = saturate(1.0 - distToTouch / _TouchRadius);
float3 touchDir = normalize(worldPos - _TouchPos.xyz + float3(0.001, 0.001, 0.001));
float3 finalNormal = normalize(normalWS + touchDir * touchFalloff * _TouchIntensity * 0.5);

// 三层合成
float3 finalColor = layer1 + layer2 + layer3;
finalColor = lerp(finalColor, finalColor * _Tint.rgb, _Tint.a);
finalColor += _EdgeColor.rgb * fresnel * 0.2;
```

---

## 结语

以上内容权当作是参考，希望能对 Duanxx 有用。

这个事让我想起之前一次关于 Launcher 横排卡片的业务竞争。当时交互设计同事给到的方案中，桌面卡片要有类似毛玻璃的感觉。但是车模桌面的画面是由3D提供的，如果卡片给到安卓原生开发去做，就很麻烦和困难。

于是就交给了 3D 组去做。和之前毛玻璃的文章所写的内容相比：没有做 UV偏移，也没有菲涅尔的边缘过渡，由于是卡片这种2D UI，自然也不存在法线贴图，也没有加环境反射采样。我觉得这些不做的事情，是可以作为一个2D 毛玻璃的参考的。

