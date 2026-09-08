---
title: "座舱3D HMI场景：充电特效"
date: 2026-05-28
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 充放电场景是3D车模必做的，为了表现能量的流动，大多会使用扫描效果去表达。曾在项目中实现过的，是一种能量波从充电口附近出发向外扩散，扫过车门和前舱的效果。它是车漆材质的一部分，是溶解效果的一种。

本文介绍的是一套基于**世界空间位置**的充电溶解特效方案：**一个世界坐标点作为溶解起点，由每个像素在世界空间中的实际坐标决定何时、以何种方式发光**，实现从充电口向外的依次扫描，而不会因为同一个材质分布在多个mesh上而混乱。

核心思路是：

- 以充电口为圆心，**环形波**向外扩展，带周期性脉冲，颜色青绿。
- 不同充电口位置仅改变溶解原点坐标（前充口 / 后充口）。
- 由 C# 侧通过全局 Keyword 控制。

可以概括为三步：**C# 侧根据充电状态切换 Keyword 和全局坐标 → Shader 读取 Keyword 选择溶解原点 → 计算发光的颜色并叠加到 Albedo上**。

---

## 一、全局变量

溶解效果需要一个世界空间中的"起点"——充电口所在位置。由于车体共享一套车漆材质，用全局 Shader 变量注入最直接。

以下为示意代码：

```csharp
// 溶解点坐标，在车辆模型控制器初始化时设置
public class VehicleModelController : MonoBehaviour
{
    // 后侧充电口的世界坐标
    public Vector4 RearChargeOrigin = new Vector4(-1f, 1f, -1f, 0);
    // 前侧充电口的世界坐标
    public Vector4 FrontChargeOrigin = new Vector4(-1f, 1f, 1f, 0);

    protected virtual void Awake()
    {
        // 全局注入，所有使用该变量名的材质自动生效
        Shader.SetGlobalVector("RearDissolvePoint", RearChargeOrigin);
        Shader.SetGlobalVector("FrontDissolvePoint", FrontChargeOrigin);
    }
}

```

---

## 二、C# 侧

车端信号（充电状态、插头类型、充电口盖开关）经模块处理器处理之后，统一控制 Shader的Keyword。


| Keyword                | 作用                     |
| ---------------------- | ---------------------- |
| `_ISCHARGEDISSOLVE_ON` | 特效总开关，控制最终是否叠加溶解色      |
| `_ISFRONTCHARGE_ON`    | 溶解原点切换，控制使用前侧还是后侧充电口坐标 |


以下为示意代码：

```csharp
public class VehicleChargeVisual : MonoBehaviour
{
    private void Awake()
    {
        CloseChargeEffect();
        // 监听充电状态、插头类型、口盖开关变化
        // ... RegisterOnValueChanged(OnXxxChanged)
    }

    private void UpdateEffect()
    {
        // 充电口盖关闭时 → 关闭特效
        // if (IsAllCapClosed()) { CloseChargeEffect(); return; }

        // 充电中 → 开启特效
        Shader.EnableKeyword("_ISCHARGEDISSOLVE_ON");

        // 非充电状态 → 关闭
        // default: CloseChargeEffect();
    }

    private void OnPlugTypeChanged(PlugType plugType)
    {
        // 前侧插头 → 使用前侧溶解点
        if (plugType == PlugType.Front)
            Shader.EnableKeyword("_ISFRONTCHARGE_ON");
        // 后侧插头 → 使用后侧溶解点
        else if (plugType == PlugType.Rear)
            Shader.DisableKeyword("_ISFRONTCHARGE_ON");
    }

    private void CloseChargeEffect()
    {
        Shader.DisableKeyword("_ISCHARGEDISSOLVE_ON");
        Shader.DisableKeyword("_ISFRONTCHARGE_ON");
    }
}

```

---

## 三、Shader 端

整个溶解效果可以封装为一个Shader工具的Function，输出 `FLOAT4`（RGB = 发光色，A = 强度），在车漆 Shader 中叠加到 Albedo这条线上。

### 3.1 时间-空间映射

```hlsl
// frac 保证偏移量在 [0, 1) 内循环，乘以 speed 后波前以 3 单位/秒向外推进
float timePhase = frac((_TimeParameters.x - offset) / period);
float expandOffset = timePhase * speed;
float distFromWave = (dist - expandOffset) / 1.0;

```


| 参数     | 值    | 含义                    |
| ------ | ---- | --------------------- |
| offset | -0.6 | 起始偏移，确保 t=0 时波已有一定距离  |
| period | 2.0  | 周期，每 2 秒重复一次扩展        |
| speed  | 6.0  | 每周期移动的世界单位数，折合 3 单位/秒 |


`dist - expandOffset` 得到当前像素与波前的有符号距离：负值 = 波已扫过，正值 = 波未到达。

### 3.2 带状环形

通过两次smoothstep做边缘混合。

```hlsl
float innerEdge = smoothstep(0.0, 1.0, distFromWave);   // 波前内缘
float outerEdge = smoothstep(1.0, 1.2, distFromWave);   // 波前外缘
float ring = 1.0 - ((1.0 - innerEdge) + outerEdge);

```


| `distFromWave` 范围 | `innerEdge` | `outerEdge` | `ring` | 含义   |
| ----------------- | ----------- | ----------- | ------ | ---- |
| < 0               | ≈ 0         | ≈ 0         | ≈ 1    | 波已扫过 |
| 0 → 1             | 0 → 1       | ≈ 0         | 1 → 0  | 内缘过渡 |
| 1 → 1.2           | ≈ 1         | 0 → 1       | 0      | 外缘过渡 |
| > 1.2             | ≈ 1         | ≈ 1         | ≈ 0    | 波未到达 |


最终 `ring` 在波前附近形成一个约 **1.2 单位宽**的亮带，外缘有 0.2 单位的柔和过渡。

### 3.3 三角波脉冲 + 二次方衰减

通过三角波计算得到1Hz频率的周期性脉冲，让发光环产生呼吸效果，再用二次方幂让亮环中心更突出、边缘过渡更自然。

```hlsl
// frac(t×0.5) → 0~1 锯齿，减 0.5 取绝对值 → 0~0.5~0 三角波，×2 归一化到 0~1~0
// 周期 1 秒，让环以 1Hz 频率"呼吸"
float pulse = abs(frac(_TimeParameters.x * 0.5) - 0.5) * 2.0;

// 二次方让亮环中心突出、边缘锐利过渡
float intensity = pow(ring * pulse, 2.0);

```

### 3.4 颜色与输出

```hlsl
// 青绿色
float4 effectColor = IsGammaSpace()
    ? float4(0.35, 0.6, 0.58, 1)   // Gamma
    : float4(0.10, 0.32, 0.30, 1); // Linear

// 输出：RGB = 发光色 × 强度，A = 强度（用于混合）
float4 dissolveResult = float4(
    (intensity * effectColor).rgb,
    intensity
);

```

### 3.5 叠加到 Albedo

在车漆 Shader 中，溶解效果以 **加法混合** 叠加到基础色上：

```hlsl
#ifdef _ISCHARGEDISSOLVE_ON
    float4 finalAlbedo = baseAlbedo + dissolveResult;
#else
    float4 finalAlbedo = baseAlbedo;
#endif

```

---

## 四、处理流程

![充电溶解特效完整数据流](./flow-charge-dissolve.png)

---

## 七、注意事项

1. **溶解点需匹配车型**：不同车型的充电口位置不同，溶解点坐标需在控制器初始化时设置，换车型时需确保坐标正确。
2. **pow 2 的边缘柔和度**：二次方衰减在波前附近有一个较宽的过渡带。如果需要更锐利的边缘，可以提高到 pow 3~4；如果需要更柔和，可以降到 pow 1.5。

---

## 结语

包括充放电、雨雪效果在内，很多交互效果都和车漆材质有关。可以认为，车漆材质是由各种效果综合的结果。本文介绍的是充电，而放电由于效果表现不同，所以可能会另开一篇简介。