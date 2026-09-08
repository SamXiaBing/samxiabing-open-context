---
title: "座舱3D HMI材质：车漆（六）车衣遮罩与样式复用"
date: 2026-08-04
series: carpaint
no: 6
status: published
visibility: public
wechat_url: ""
---

> 上一篇讲了反射与抗锯齿。这篇轮到车衣遮罩，主要介绍一下样式复用和换色分工。

整车换色靠材质实例改参数，遮罩贴图只管区域显示，这两件事分开，资产组织和变体治理才顺。项目里用一套 Shader 同时接住两条路：纯色车走 Base/Edge，带车衣的车多开一条 SkinMap 的 Albedo 支路。

# 示意代码

```hlsl
// 1. 底漆颜色：Base ↔ Edge 的 Fresnel 过渡
float3 baseEdge = lerp(_BaseColor.rgb, _EdgeColor.rgb, fresnel);

// 2. 车衣遮罩：_IsUV1 选 UV0/UV1，采样 SkinMap
float2 uvSelect = lerp(uv0, uv1, _IsUV1);
float3 skin = tex2D(_SkinMap, uvSelect).rgb;

// 3. 合成：_HasMaskMap 选底漆还是车衣
float3 albedo = lerp(baseEdge, skin, _HasMaskMap);

// 4. Flake 颗粒层照常叠加
albedo += flakeColorTerm;
```

# 流程说明

**1. 整车换色走材质实例**

同一款车要十几种车身色时，一套 Shader，多份材质实例，每份改 `_BaseColor`、`_EdgeColor` 即可。颜色是连续参数，美术调色盘改几个 float 就够。做成每个颜色换一张全屏铺色贴图的话，每个颜色多一张图，内存和包体一起涨，还会和真正的车衣通道抢语义。

**2. 区域遮罩走 SkinMap**

车衣、腰线贴花、局部彩绘需要遮罩。`_HasMaskMap` 是开关：无车衣时走 Base/Edge，有车衣时开 SkinMap 支路。UV 用 `_IsUV1` 在 UV0、UV1 之间选，车漆本体跟模型 UV0，车衣、贴花经常要独立展开，用 UV1。

**3. Flake 照常叠加**

遮罩不影响颗粒层，Flake 项同样加到 Albedo 上，带车衣的车颗粒感来自同一套参数。

**4. 换色检查单**

切色时改了 Base 忘了 Edge，正面看着对，车机俯视里侧缘仍发灰，换色时把 `_EdgeColor` 一并勾上。命名上把色号材质和带车衣材质分开，例如 `CarPaint_Blue` 与 `CarPaint_Blue_Skin`，避免把 SkinMap 误挂到纯色车上。

# 参数说明

```
//注意取值范围
[Toggle]_IsUV1("IsUV1", Float) = 0
[Toggle]_HasMaskMap("HasMaskMap", Float) = 0
[NoScaleOffset]_SkinMap("SkinMap", 2D) = "white"
```

| 参数            | 管什么     | 取 0              | 取 1                |
| ------------- | ------- | ---------------- | ------------------ |
| `_HasMaskMap` | 车衣支路开关  | Albedo 走 Base/Edge 底漆 | Albedo 走 SkinMap 车衣 |
| `_IsUV1`      | 车衣采样 UV | 用 UV0（车漆 UV）     | 用 UV1（车衣独立 UV）     |

# 结语

整车换色改 `_BaseColor` / `_EdgeColor` 这些实例参数，SkinMap 只做区域遮罩。`_HasMaskMap` 加 `_IsUV1` 两个开关把支路接起来，颜色、遮罩、颗粒各管各的，别堆成超级 Keyword。