---
title: "座舱3D HMI场景：车窗的透明玻璃材质"
date: 2026-07-02
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇写了毛玻璃 —— [《座舱3D HMI场景：全局模糊优化的毛玻璃材质方案》](https://mp.weixin.qq.com/s/hx1XGh2fdBDcPpxR8GJXRQ)，对于 3D 场景来说，其实见到更多的是透明玻璃的需求，比如车窗玻璃、车灯灯罩、车壳半透明区域。它的特点是要兼顾通透感以及适当的折射反射视觉效果。

透明玻璃效果是去模拟光线穿过透明介质的折射、反射和 Fresnel 边缘响应。在 3D HMI 的车机应用中，常常还需要叠加清漆层高光和环境反射，让玻璃既有通透感又有立体感。

---

## 一、折射

毛玻璃的"屏幕空间扭曲"是偏移 UV 去采样全局模糊纹理。透明玻璃不做模糊，它的折射是物理的：用法线的 XY 分量偏移屏幕 UV 去采样**清晰的屏幕颜色**。偏移量的大小由折射率参数控制，折射率越大偏移越大。

> 前挡风玻璃材质倾向于关闭折射，因为前挡风面积大、曲率小，折射会让人觉得有点过度表达而失真了；车灯玻璃和车窗玻璃会开启折射，面积小、曲率大，折射效果能增强立体感。

示意代码，与毛玻璃不同，这里是采样`_CameraOpaqueTexture` 做物理折射：

```hlsl
// 透明玻璃的折射偏移：法线 XY × 折射率偏移系数
// 注意：毛玻璃用的是 ddx(fresnel) 和 ddy(fresnel)，这里用的是法线直接驱动
float2 refractionOffset = worldNormal.xy * _BumpRefraction * (_IOR - 1.0);

// 采样清晰的屏幕颜色（毛玻璃采样的是 _GlobalBlurTexture）
float2 screenUV = ComputeScreenPos(positionCS).xy / ComputeScreenPos(positionCS).w;
float3 refractionColor = tex2D(_CameraOpaqueTexture, screenUV + refractionOffset).rgb;
```

---

## 二、Fresnel

透明玻璃拿到 Fresnel 值之后，不做毛玻璃那种内外侧的颜色混合，而是做**多层边缘高光叠加**。偏移视线方向和世界空间法线做点积，分别计算出两个边缘高光颜色，直接叠加到最终结果上。这种做法让玻璃边缘不只是"发白"，而是有细微的色相差异，更接近真实玻璃边缘的彩虹色散效果。

示意代码，基础 Fresnel 计算和毛玻璃完全相同，不再重复：

```hlsl
// 以下代码是透明玻璃独有的，毛玻璃没有这部分
// 第一层边缘高光：偏移视线方向后做点积
float3 offsetViewDir1 = normalize(viewDir + _ViewDirOffset_One);
float edgeHighlight1 = pow(max(1.0 - dot(worldNormal, offsetViewDir1), 0.0001), _Power);
float3 edgeColor1 = lerp(_FCol_One, _NightFCol_One, _IsNight) * edgeHighlight1;

// 第二层边缘高光：另一个偏移方向
float3 offsetViewDir2 = normalize(viewDir + _ViewDirOffset_Sec);
float edgeHighlight2 = pow(max(1.0 - dot(worldNormal, offsetViewDir2), 0.0001), _Power);
float3 edgeColor2 = lerp(_FCol_Sec, _NightFCol_Sec, _IsNight) * edgeHighlight2;

// 叠加到最终颜色（毛玻璃是 lerp 插值，这里是 add 叠加）
finalColor = refractionColor + edgeColor1 + edgeColor2;
```

---

## 三、法线贴图

透明玻璃的法线贴图**直接参与折射 UV 偏移**。第一章节的折射代码中，`worldNormal.xy` 就是法线贴图采样后转换到世界空间的法线。这意味着法线贴图的凹凸纹理会直接体现在背景的扭曲上，而不是像毛玻璃那样只间接影响 Fresnel。

此外，透明玻璃的法线贴图还参与了天气系统中的雨滴法线叠加。雨滴的法线会直接叠加到玻璃法线上，改变折射方向，模拟雨滴对光线的扰动。

---

## 四、环境反射

透明玻璃的环境反射比毛玻璃丰富，有两套实现：

第一套是 Cubemap 反射，在能源界面需要显示透明车壳的时候有用。用日夜两套 Cubemap 纹理，可以自定义反射内容，白天反射蓝天白云、夜晚反射城市灯光。毛玻璃没有 Cubemap 反射。

第二套是 URP 内置环境反射，和毛玻璃用的是同一个，就是`GlossyEnvironmentReflection`，默认开启。这里就用到了 smoothness了。

> 车窗玻璃材质 `_Smoothness` 接近 1，几乎是镜面反射；
>
> 车灯玻璃材质 `_Smoothness` 接近 0.5，反射比较模糊。

此外，透明玻璃还多一个功能：自定义高光。

它通过 `CustomLightDir` 参数指定一个固定方向的光源计算高光区域，模拟固定方向主光的高光效果。

示意代码，不含 URP 内置环境反射的代码（和毛玻璃文章中相同）：

```hlsl
// 以下代码是透明玻璃独有的，毛玻璃没有这部分
// Cubemap 反射：日夜两套纹理插值
float3 reflectDir = reflect(-viewDir, worldNormal);
float3 dayReflection = texCUBE(_CubeDay, reflectDir).rgb;
float3 nightReflection = texCUBE(_CubeNight, reflectDir).rgb;
float3 cubemapReflection = lerp(dayReflection, nightReflection, _IsNight);

// 自定义高光：固定方向光源
float customSpec = dot(normalize(_CustomLightDir), worldNormal);
customSpec = smoothstep(_SpecularRange, _SpecularRange + _EdgeWidth, customSpec);
customSpec = pow(customSpec, _CustomDirectLightPow);
float3 specColor = lerp(_Day_SpecularColor, _Night_SpecularColor, _IsNight) * customSpec;
```

---

## 五、清漆层

清漆层（ClearCoat）是透明玻璃特有的，这层清漆会产生独立的高光反射，叠加在底层玻璃之上。

实现方式是在原有表面之上再加一层高光：用清漆层法线计算反射方向，采样环境反射，乘以清漆层强度和色调。清漆层平滑度通常很高（接近 1.0 ），产生锐利的高光点。

> 车灯玻璃和车窗玻璃通常会开启清漆层，前挡风玻璃会关闭清漆层。
>
> 因为清漆高光在大面积上会显得过于"油腻"。

```hlsl
// 以下代码是透明玻璃独有的，毛玻璃没有这部分
float3 coatReflectDir = reflect(-viewDir, worldNormal);
float coatRoughness = 1.0 - _ClearCoatSmoothness;
float3 coatReflection = GlossyEnvironmentReflection(
    coatReflectDir, worldPosition, coatRoughness, 1.0, screenUV
);
float3 coatColor = coatReflection * _CoatSpecularIntensity * _CoatTint.rgb;
finalColor += coatColor * _ClearCoatMask;
```

---

## 六、日夜切换

透明玻璃的日夜切换比毛玻璃精细得多。几乎每个关键参数都有独立的夜晚版本：Fresnel、反射强度、光滑度、法线强度、自定义高光方向都有日夜两个版本。Cubemap 反射也分白天和夜晚两套纹理。

```hlsl
// 以下代码是透明玻璃独有的参数级日夜切换，毛玻璃只做底色 lerp
float currentPower = lerp(_Power, _NightPower, _IsNight);
float currentRefIntensity = lerp(_RefIntensity, _NightRefIntensity, _IsNight);
float currentSmoothness = lerp(_Smoothness, _NightSmoothness, _IsNight);
float currentBumpScale = lerp(_BumpScale, _NightBumpScale, _IsNight);

// Cubemap 也分日夜（毛玻璃没有 Cubemap）
float3 envReflection = lerp(
    texCUBE(_CubeDay, reflectDir).rgb,
    texCUBE(_CubeNight, reflectDir).rgb,
    _IsNight
);
```

---

## 七、天气系统

这是 3D 车模桌面场景常有的需求：雨天时玻璃表面有雨滴附着和流水痕迹，雪天时有积雪，雾天时有雾气覆盖。

雨滴效果通过雨滴法线贴图和流水遮罩贴图实现。雨滴法线叠加到玻璃法线上，直接改变折射方向。流水遮罩控制雨滴分布区域，流动速度用时间函数驱动 UV 偏移。

积雪效果用 BaseMap、NormalMap 和 RoughnessMap 模拟积雪外观。

雾气效果用遮罩控制雾的分布和浓度。

```hlsl
// 以下代码是透明玻璃独有的，毛玻璃没有这部分
// 雨滴法线：采样并叠加到玻璃法线，影响折射方向
float3 rainDropNormal = UnpackNormal(tex2D(_RainDropTexture, uv * _RainDropTiling + float2(0, _Time.y * _RainDropSpeed)));
rainDropNormal *= _RainDropNormalStrength * rainDripMask;
worldNormal = normalize(worldNormal + rainDropNormal);

// 积雪：用遮罩混合积雪颜色
float snowMask = tex2D(_SnowMaskTexture, uv).r;
float3 snowColor = tex2D(_SnowBaseMap, uv).rgb;
finalColor = lerp(finalColor, snowColor, snowMask * _SnowIntensity);

// 雾气：用遮罩叠加雾色
float fogMask = tex2D(_FogMaskTexture, uv).r;
finalColor = lerp(finalColor, _FogColor.rgb, fogMask * _FogAlpha);
```

---

## 结语

透明玻璃从整个流程上看，比毛玻璃更复杂。因为它和业务需求的耦合更深，比如天气效果以及日夜模式。但复杂也意味着可调整的余地很多，能适配和变化的情况更多。

