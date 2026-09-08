---
title: "座舱3D HMI场景：全局模糊优化的毛玻璃材质方案"
date: 2026-07-01
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 在智能座舱的 3D HMI 场景中，玻璃材质广泛应用于车窗、车壳半透明区域、车灯的灯罩等。它需要能保证透光性，又需要呈现一些模糊的质感。

车载场景中的毛玻璃效果，本质上是在**屏幕空间**上模拟光线穿过磨砂玻璃时的折射与散射现象。

# 之前做法

传统思路是写一个真实的折射 Shader，核心是GrabPass + 法线偏移

1. GrabPass  抓取当前屏幕的渲染图像。在渲染玻璃物体之前，把当前屏幕的渲染结果拷贝到_RefractionTex纹理里。

```
// 在SubShader里抓取屏幕图像
GrabPass{"_RefractionTex"}
```

2. 顶点着色器：计算屏幕采样坐标 scrPos，准备切线空间到世界空间的转换矩阵TtoW。
3. 片元着色器：从法线贴图里采样切线空间的法线，然后用顶点着色器准备的TtoW矩阵转换到世界空间。

```
fixed3 tanNormal = UnpackNormal(tex2D(_BumpMap, i.uv.zw));
fixed3 worldNormal = mul(TtoW, tanNormal);
```

4. 用切线空间法线的XY分量（刚好对应屏幕空间的偏移方向）乘扭曲强度和像素大小，得到偏移量，然后加到屏幕坐标上。

```
float2 offset = tanNormal.xy * _Distortion * _RefractionTex_TexelSize.xy;
i.scrPos.xy += offset;
```

5. 用偏移后的屏幕坐标采样GrabPass抓取的图像，得到折射后的颜色。

```
fixed3 refractCol = tex2D(_RefractionTex, i.scrPos.xy / i.scrPos.w).xyz;
```

GrabPass 把当前屏幕的渲染结果拷贝到一张纹理是昂贵的操作。

如果有多个玻璃类物体，每个都要单独Grab一遍。而且，每个像素都要采样法线贴图、计算偏移。

# 当前思路

所以为了性能，采用了以下的做法：

1. **统一所有玻璃物体的采样图：**URP Renderer Feature 在透明物体渲染完成后，对相机 Color Buffer 做一次高斯模糊，得到一张全局模糊纹理。所有玻璃物体都来采样这张图，不用每个都自己算一遍。
2. **偏移采样**：渲染玻璃的时候，不直接采样当前像素的颜色，而是偏移屏幕UV去采样那张模糊纹理。偏移量根据法线方向和视线角度计算，模拟光线穿过玻璃后的扭曲效果。
3. **叠加细节**：用Fresnel公式区分玻璃的内外侧。正面看偏透、斜着看偏白。如果需要，还可以叠加环境反射，让玻璃看起来更真实。这些细节都是可选的。

> 优点：全局只做一次模糊，所有玻璃物体共享结果，性能优异。
>
> 缺点：玻璃背后的内容不是真实折射的，但座舱场景下这个可以接受。

---

## 一、全局模糊纹理

创建一个URP的Render Feature，在所有透明物体后触发。

这个 Feature 先对当前画面做降采样，然后进行多次高斯模糊，最后把结果设置为全局纹理供所有毛玻璃 Shader 采样。

降采样（宽高各缩小 8 倍）的目的是减少后续模糊 Pass 的计算量。这样模糊计算所需的像素数只有原来的 1/64，能显著降低 GPU 带宽压力。

降采样完成后，接下来是模糊循环，每一轮包含一个水平方向的高斯 Pass 和一个垂直方向的高斯 Pass，通过这种"可分离"的方式，原本需要 25 次采样的 5×5 高斯核可以缩减到 10 次采样（5 次水平 + 5 次垂直），大幅提升性能。

模糊完成后，通过 `SetGlobalTexture` 把结果注册为 `_GlobalBlurTexture`。这样所有 Shader 都能直接用这个名字采样，无需手动传递参数。

示意代码：

```hlsl
// 降采样 Pass：将原图拷贝到 1/8 分辨率的临时纹理
// 在 C# 端通过 RenderTextureDescriptor 指定宽高缩小比例
cmd.Blit(sourceTexture, downsampledTexture);

// 水平高斯模糊 Pass：沿 X 轴采样 5 个像素
float weights[5] = {0.0545, 0.2442, 0.4026, 0.2442, 0.0545};
int offsets[5] = {-2, -1, 0, 1, 2};

float3 horizontalBlur = float3(0, 0, 0);
for (int i = 0; i < 5; i++)
{
    float2 sampleUV = uv + float2(_MainTex_TexelSize.x * offsets[i], 0);
    horizontalBlur += SAMPLE_TEXTURE2D(_MainTex, sampleUV).rgb * weights[i];
}

// 垂直高斯模糊 Pass：沿 Y 轴采样 5 个像素
float3 verticalBlur = float3(0, 0, 0);
for (int i = 0; i < 5; i++)
{
    float2 sampleUV = uv + float2(0, _MainTex_TexelSize.y * offsets[i]);
    verticalBlur += SAMPLE_TEXTURE2D(horizontalResult, sampleUV).rgb * weights[i];
}
```

---

## 二、Fresnel 边缘过渡

毛玻璃的 Fresnel 效果不仅是要能看到"边缘发光"，还需要能区分玻璃的内外侧，从而实现双层着色。正面看玻璃时，我们会看到更透亮的效果；斜着看时，玻璃边缘会变得更亮、更白，这种变化需要通过 Fresnel 值来驱动内外侧颜色的混合比例。

Fresnel 的计算公式使用经典的菲涅尔近似式：

```
fresnel = bias + scale * pow(max(1.0 - dot(N, V), 0.0001), power)
```

- `N`: 表面法线方向
- `V`: 视线方向
- `bias`: 基础亮度(即使正面看也有一点亮)
- `scale`: 边缘发光强度
- `power`: 控制发光的"锐度"(值越大,边缘越窄)

用法线和视线的点积来反映视线与表面的夹角：当视线垂直于表面时，点积为 1，Fresnel 值接近基础偏移；当视线越来越斜时，点积趋近于 0，Fresnel 值经过幂函数放大后迅速增大。

公式中的 `bias` 控制基础亮度，`scale` 控制发光强度，`power` 决定发光的锐度。

有了 Fresnel 值后，内外侧颜色混合就变得简单：

- 内侧颜色是模糊背景与内部色调的叠加
- 外侧颜色是模糊背景与外部色调的叠加

两者用 Fresnel 作为插值系数进行混合。这种双层混合比单纯的边缘发光更真实。能做到正面看时看到背后的模糊景象，斜看时边缘会呈现类似白瓷的质感。示意代码：

```hlsl
// 计算 Fresnel 值：基础偏移 + 缩放 * (1 - 法线视线点积) 的幂
float3 worldNormal = normalize(input.normalWS);
float3 viewDir = normalize(_WorldSpaceCameraPos - input.positionWS);
float NdotV = dot(worldNormal, viewDir);

// 避免除零，最小值设为 0.0001
float fresnel = _Bias + _Scale * pow(max(1.0 - NdotV, 0.0001), _Power);

// 内外双层着色
float4 blurredBG = SampleBlurTexture(distortedUV);  // 采样全局模糊纹理
float4 innerColor = _GlassInColor * blurredBG;       // 正面看：内侧色调
float4 outerColor = blurredBG * _GlassOutColor;      // 斜着看：外侧色调
```

---

## 三、屏幕空间扭曲

对采样坐标做偏移可以模拟光线穿过磨砂玻璃后的扭曲效果。这个偏移量由两个主要分量构成：Fresnel 导数偏移和法线偏移。

Fresnel 导数计算的是 Fresnel 值在屏幕空间的梯度，即 Fresnel 值在 X 方向和 Y 方向的变化率。因为 Fresnel 值在边缘区域变化剧烈，其导数正好反映了玻璃表面的"弯曲程度"。导数偏移再乘以 `_DistortIntensity` 参数，就能控制扭曲的强度。

法线偏移则相对直接：把世界空间法线转换到视图空间后，取其 XY 分量作为偏移量。

采样得到模糊背景后，还需要与日夜底色混合，确保在夜晚场景下玻璃不会"消失"。白天时底色的 Alpha 为 0，完全显示模糊背景；夜晚时底色的 Alpha 大于 0，会叠加一层灰色调，让玻璃在暗环境中也能被看见。

示意代码：

```hlsl
// 计算 Fresnel 在屏幕空间的导数（变化率）
float2 fresnelGradient = float2(ddx(fresnel), ddy(fresnel));

// 世界空间法线转到视图空间，取 XY 分量作为偏移
float3 viewNormal = normalize(mul(UNITY_MATRIX_V, float4(worldNormal, 0.0)).xyz);

// 综合两个偏移分量
float2 distortionOffset = fresnelGradient * _DistortIntensity;
float2 normalOffset = viewNormal.xy * _NormalDitortIntensity;

// 计算偏移后的采样坐标
float2 distortedUV = screenUV + distortionOffset + normalOffset;

// 采样全局模糊纹理
float4 blurredSample = SAMPLE_TEXTURE2D(_GlobalBlurTexture, distortedUV);

// 与日夜底色混合
float4 dayColor = _BaseColor;
float4 nightColor = _NightBaseColor;
float4 baseColor = lerp(dayColor, nightColor, _IsNight);
float4 blurredBG = lerp(blurredSample, baseColor, baseColor.a);
```

---

## 四、法线贴图

法线贴图不参与 UV 偏移，而是通过法线间接改变 Fresnel 值和反射方向。这样做的好处是法线细节能自然地融入到毛玻璃的整体效果中，使得有凹凸纹理的地方，Fresnel 值会变化，反射方向也会改变，最终呈现出更丰富的视觉细节。

示意代码：

```hlsl
// 从法线贴图采样切线空间法线
float3 tangentNormal = UnpackNormal(SAMPLE_TEXTURE2D(_BumpMap, uv));
tangentNormal *= _BumpScale;  // 控制法线强度

// 通过 TBN 矩阵转换到世界空间
float3 worldNormal = normalize(mul(TBN, tangentNormal));

// 这个 worldNormal 会影响：
// 1. Fresnel 值计算（dot(worldNormal, viewDir)）
// 2. 反射方向（reflect(-viewDir, worldNormal)）
// 3. 环境反射采样（GlossyEnvironmentReflection）
```

---

## 五、环境反射叠加

为了让毛玻璃更有真实感，还可以添加对环境反射的支持。

环境反射的采样基于反射方向和世界空间位置，通过Unity的函数获取已模糊的环境光。这个函数需要反射向量和粗糙度。

最终输出颜色是纹理颜色和反射颜色的混合，混合系数就是反射强度，这样反射效果能自然地融入毛玻璃的整体效果中。

示意代码：

```hlsl
// 计算反射方向
half3 reflectDir = reflect(-viewDir, worldNormal);

// 采样环境反射（已做模糊）
float roughness = 1.0 - _Smoothness;
float3 envReflection = GlossyEnvironmentReflection(
    reflectDir,
    worldPosition,
    roughness,
    1.0,  // occlusion
    screenUV
);

// 与毛玻璃颜色混合
float4 texColor = SAMPLE_TEXTURE2D(_MainTex, uv) * glassColor;
float4 finalColor = lerp(texColor, float4(envReflection, 0.0), _RefIntensity);
```

---

# 流程总结

![图1](./图1.png)

# 结语

玻璃效果在实际使用中，需要根据不同的环境去调试各项参数。比如玻璃看起来太亮，就需要调低 BaseColor.a （0.2 - 0.4）；如果边缘发光太假，Power 的值就需要降低（1.0 - 1.2）；如果扭曲效果不太明显，DistorIntensity 就要提高（1.5 - 2）。