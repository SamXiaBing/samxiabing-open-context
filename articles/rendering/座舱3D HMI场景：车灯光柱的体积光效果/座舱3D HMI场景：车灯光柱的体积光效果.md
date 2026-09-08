---
title: "座舱3D HMI场景：车灯光柱的体积光效果"
date: 2026-07-15
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 3D HMI 的车模桌面，车灯的发光和灯柱效果是很常见的。尤其是夜间模式下，需要传递出清晰的"光线照射"感。从设计角度，车灯要表达三个重点：灯片的开关、光柱的体积感、空气中的灰尘流动。

本文介绍的方案是：**1个圆锥形Mesh + 1个自定义Shader + 屏幕空间噪声纹理**。

核心实现思路比较简单：

- 用一个圆锥形Mesh放置在灯片前方
- 通过透明Shader渲染，模拟光线在空气中照亮灰尘的效果
- 用屏幕空间UV采样噪声纹理，实现灰尘的流动感

![image](./图1.png)

# 一、光柱

## 1. 网格体

使用一个有点压扁了一些感觉的圆锥形Mesh，一个父圆锥里面套一个小圆锥。

> 这种方式是为了在下文所介绍的shader的影响下，体现出内层光柱更亮，外层暗淡一些的层次感。

Mesh有几百个三角面。

![image](./图2.png)

## 2. Shader

### （1）顶点着色器

#### 基础变换

先是标准的顶点变换和方向计算：

```hlsl
v2f vert (a2v v)
{
    v2f o;
    half4 worldPos = mul(UNITY_MATRIX_M, v.vertex);
    half3 worldDir = UnityObjectToWorldDir(half3(-1,0,0));
    
    half3 normal = UnityObjectToWorldNormal(v.normal);
    half3 OutwardNormal = UnityObjectToWorldDir(normalize(half3(0, v.normal.y, v.normal.z)));
    o.viewDir = normalize(WorldSpaceViewDir(v.vertex));
```

这里把顶点转到世界空间，其中`worldDir`作为光柱的主方向（沿X轴负方向，车灯向前），其他的都是基操。

#### 视角变形

接下来是视角相关变形逻辑：

```hlsl
    // 视角相关的光柱扩散变形
    half vd = max(0, dot(o.viewDir, worldDir));
    worldPos.xyz += OutwardNormal * _Spread * (1-v.uv0.x) * v.uv0.x * pow(vd,abs(_SpreadPow));
```

- `vd`：视角与光柱方向的点积，正面看接近1，侧面看接近0
- `(1-v.uv0.x) * v.uv0.x`：抛物线分布，中间扩散最大，两端为0
- `pow(vd,abs(_SpreadPow))`：视角敏感度，值越大视角变化影响越小
- 最终沿`OutwardNormal`方向偏移顶点，实现扩散效果

#### 屏幕空间UV

最后计算屏幕空间UV，用于灰尘纹理采样：

```hlsl
    o.worldY = worldPos.y;
    o.vertex = mul(UNITY_MATRIX_VP, worldPos);
    
    // 屏幕空间UV用于灰尘纹理采样
    o.screenUV = (o.vertex.xy + o.vertex.zz) * _ScreenScale + _Time.xx*_SmokeSpeed;
    
    o.localDir = worldDir;
    o.normalDir = normal;
    o.uv0 = v.uv0;
    o.uv1 = v.uv1;
    return o;
}
```

这里的关键是`screenUV`的计算：加入 `o.vertex.zz` 深度信息可以让远处的采样偏移更多，产生视差，相机移动的时候，远近灰尘移动速度不同，就会有一种立体感。而 `_Time.xx*_SmokeSpeed`就是让 UV 坐标随时间变化，噪声纹理采样位置不断变化，实现灰尘流动效果。

### （2）片元着色器

#### 纹理采样

片元着色器先采样噪声和遮罩纹理：

```hlsl
fixed4 frag (v2f i) : SV_Target
{
    // 采样噪声纹理，实现灰尘效果
    fixed alpha = min(1, tex2D(_NoiseTex, i.screenUV)+_SmokeInten).r;
    fixed mask = tex2D(_MaskTex, i.uv1).r;
    
    fixed3 viewDir = normalize(i.viewDir);
    fixed3 normal = normalize(i.normalDir);
    fixed3 localDir = normalize(i.localDir);
```

- `alpha`：从屏幕空间UV采样噪声，加上基础灰尘强度
- `mask`：遮罩纹理的目的，是为了让光柱渐变，即靠近灯片的区域的光柱透明。

#### 多层遮罩

然后计算四个独立的遮罩：

```hlsl
    // 边缘遮罩：模拟光柱边缘软化
    fixed edgeMask = pow(max(0, dot(i.normalDir, -i.viewDir)), _EdgePower);
    
    // 距离遮罩：控制光柱长度
    fixed farMask = min(1, i.uv0.x);
    
    // 视角相关亮度调整
    fixed vd = dot(viewDir, localDir)*.5 + .8;
    
    // 高度遮罩：避免光柱过高
    fixed heightClip = saturate(i.worldY * 2 + _HighCut);
```

- `edgeMask`：法线与视角的点积，边缘处值小，实现边缘软化
- `farMask`：UV.x控制长度，越远越透明
- `vd`：视角亮度，正面（其实是灯柱的正侧面）看更亮
- `heightClip`：世界空间Y坐标限制高度

#### 最终合成

最后把所有遮罩乘起来：

```hlsl
    fixed4 final = _Color;
    final.a = farMask * edgeMask * heightClip * alpha * _Color.a * _LightInten * vd * mask;
    return final;
}
```

透明度是所有遮罩的乘积，任何一个遮罩为0都会让该像素完全透明。

### （3）混合模式

```
Blend SrcAlpha One  // 加法混合
ZWrite Off          // 不写入深度
Cull Off            // 双面渲染
```

- 加法混合：光柱叠加时更亮
- 不写入深度：避免遮挡后方物体
- 双面渲染：任何角度都能看到

## 二、灯片

灯片的shader选择含有 ISEMISSION 属性，支持自发光的材质即可。需要搭配 Volume的Bloom后处理效果，才能看到辉光效果。

下面是控制灯片开关的脚本，通过Shader Keyword `_ISEMISSION_ON` 控制灯片的自发光状态，与光柱配合：

```csharp
public class LightEffectController : MonoBehaviour
{
    public Material lightMaterial;
    private bool _isLightOn = false;
    
    public void SetLightState(bool isOn)
    {
        _isLightOn = isOn;
        if (lightMaterial != null)
        {
            if (_isLightOn)
            {
                lightMaterial.EnableKeyword("_ISEMISSION_ON");
            }
            else
            {
                lightMaterial.DisableKeyword("_ISEMISSION_ON");
            }
        }
    }
}
```

## 结语

这套体积光方案实现起来不复杂，核心是用屏幕空间噪声和时间参数让灰尘流动起来，光柱就不再是死板的几何体，而是有动态感的光线。这种细节上的打磨是挺有意思的过程。