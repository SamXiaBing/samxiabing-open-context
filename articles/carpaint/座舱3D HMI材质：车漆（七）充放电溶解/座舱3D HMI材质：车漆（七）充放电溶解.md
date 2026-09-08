---
title: "座舱3D HMI材质：车漆（七）充放电溶解"
date: 2026-08-05
series: carpaint
no: 7
status: published
visibility: public
wechat_url: ""
---

> 上一篇讲了车衣遮罩与样式复用。这篇轮到充放电溶解，主要介绍一下怎么把充电视效挂进主漆 Pass。

充放电视效的实现常见三条路：独立特效材质、整车改 Transparent、挂进主漆 Keyword。项目里走第三条：车身保持 Opaque Lit，仍是同一份车漆在受光，只在 Albedo 出口叠上一圈能量色。前两条路的问题也很直接，独立特效和车漆是两套光照语言，整车 Transparent 会把排序和深度搅乱。

# 示意代码

```hlsl
#ifdef _ISCHARGEDISSOLVE_ON
    // 1. 按 AC/DC 选溶解原点
    float3 origin = DcDissolvePoint;
    #ifdef _ISACCHARGE_ON
        origin = AcDissolvePoint;
    #endif

    float time = _TimeParameters.x;
    float dist = distance(origin, WorldPosition);

    #ifdef _ISDISCHARGE_ON
        // 2a. 放电：静态径向辉光，乘 |sin(t)| 呼吸
        float glow = clamp((6.0 - dist) / 5.0, 0.0, 1.0);
        float intensity = pow(glow * abs(sin(time)), 10.0);
        float3 col = float3(0.295, 0.481, 0.750);     // 放电蓝，Shader 内常量
    #else
        // 2b. 充电：frac 推波前，两次 smoothstep 收成环带
        float phase = frac((time + 0.6) / 2.0) * 6.0; // 2 秒周期，波前走 6 个单位
        float dWave = dist - phase;
        float ring = smoothstep(0.0, 1.0, dWave) - smoothstep(1.0, 1.2, dWave);
        float pulse = abs(frac(time * 0.5) - 0.5) * 2.0;
        float intensity = pow(ring * pulse, 2.0);
        float3 col = float3(0.354, 0.600, 0.584);     // 充电青绿，Shader 内常量
    #endif

    // 3. 加法叠入 Albedo，不替换底色，不另开 Pass
    albedo.rgb += col * intensity;
#endif
```

# 流程说明

**1. 三个 Keyword 开关**

`_ISCHARGEDISSOLVE_ON` 是总开关，`multi_compile __` 声明，关闭时整段代码裁掉。`_ISACCHARGE_ON` 切换 AC/DC 的溶解原点，`_ISDISCHARGE_ON` 切到放电的辉光形态。三个开关相互独立，充电、放电、AC/DC 的组合都靠它们拼出来。

**2. 原点用全局向量喂**

`DcDissolvePoint` / `AcDissolvePoint` 声明在 CBUFFER 之外，是全局 Shader 变量，C# 侧用 SetGlobalVector 喂：

```csharp
Shader.SetGlobalVector("DcDissolvePoint", dcOrigin);
Shader.SetGlobalVector("AcDissolvePoint", acOrigin);
```

同一套车漆材质贴在前后门、引擎盖上，换车型只改这两个点，不必拆材质。

**3. 充电：世界距离环带**

取世界坐标到原点的距离，`frac` 推波前，2 秒一个周期，波前向外走 6 个单位。两次 `smoothstep` 把波前收成环带 mask，再乘 2 秒周期的三角脉冲，pow 2 收窄亮度。环带从原点扫过整车，脉冲让它一明一暗地往前推。

**4. 放电：静态径向辉光**

放电不走波前。亮度按 `(6 - dist) / 5` 随距离衰减，乘 `|sin(t)|` 呼吸，pow 10 收尖，光集中在放电点附近一团，节奏比充电慢。充放两种形态共用同一段框架，靠 `_ISDISCHARGE_ON` 分支。

**5. 周期、范围、颜色都是常量**

波前周期 2 秒、扫描范围 6、环带宽度 1、充放两个颜色，都是溶解子图里写死的常量，材质面板上没有对应参数，改节奏改色都要动 Shader。

**6. 加法叠色，保持 Opaque**

Base 的 Fresnel、Flake 颗粒、ClearCoat 高光都算完之后，环带在 Albedo 出口加上去，底色不替换。车身表面类型不换，仍是 Opaque Lit 走同一套光照。非充放电状态记得 DisableKeyword，别全局常开。

# 参数说明

```
//三个 Keyword，取值开/关
#pragma multi_compile __ _ISCHARGEDISSOLVE_ON
#pragma multi_compile __ _ISDISCHARGE_ON
#pragma multi_compile __ _ISACCHARGE_ON
```

| 名称                       | 类型    | 作用            |
| ------------------------ | ----- | ------------- |
| `_ISCHARGEDISSOLVE_ON`   | Keyword | 总开关，关闭时整段裁掉   |
| `_ISACCHARGE_ON`         | Keyword | 选 AC 充电原点     |
| `_ISDISCHARGE_ON`        | Keyword | 切到放电径向辉光      |
| `DcDissolvePoint`        | 全局向量  | DC 充电溶解原点     |
| `AcDissolvePoint`        | 全局向量  | AC 充电溶解原点     |

# 结语

充放电溶解挂进主漆，说到底就三件事：Keyword 打进主漆 Pass，和车身走同一套 Lit 光照；充电是距离波前环带，放电是径向辉光，都做加法叠进 Albedo；表面类型保持 Opaque，别为了动画把整车改成 Transparent。