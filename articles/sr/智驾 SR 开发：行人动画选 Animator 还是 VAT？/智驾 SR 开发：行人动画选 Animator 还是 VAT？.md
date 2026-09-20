---
title: "智驾 SR 开发：行人动画选 Animator 还是 VAT？"
date: 2026-09-17
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> SR的感知物中，行人是个特殊的感知物，一方面是因为它是少有的使用 skinned mesh的物体，另一方面，也是因为它是一种可以有动画的，会动的感知物。那么如何让它运动起来？

# 1、常规做法：骨骼动画

角色动起来的标准做法，长期以来都是骨骼动画，然后使用引擎端的 Animator 状态机驱动。美术同事会在 DCC 软件里绑骨骼、K 帧，导出成动画片段。程序会导入这些 fbx（内含Animation），让运行时 Animator 组件根据状态切换动画片段。依靠骨骼层级逐节点更新Transform，蒙皮网格Skinned Mesh就跟着变形。程序上，以动画片段名和速度值为参数，控制动画状态机。这条路比较成熟，也很直观，绝大多数项目都这么做。

但之前的 SR 开发中去实现有动画的行人，并没有使用这个方法，而是把骨骼动画烘焙成了贴图，而动画的播放的控制放在 shader 里。

# 2、VAT：顶点动画纹理

这里行人感知物用的技术叫 VAT，Vertex Animation Texture，顶点动画纹理。思路是**把动画每一帧、每个顶点应该在的位置，烘焙成一张纹理，运行时顶点着色器按需，像查表一样去读图。**

## 离线烘焙：两张纹理

*[配图见公众号原文]*

烘焙环节在离线完成。美术做好行人的骨骼动画（站立、走路），用烘焙工具把两个片段逐帧输出成两张纹理：

- Position Map 位置纹理：每个顶点记录一个 RGB 值，就是这一帧它在空间中的位置 xyz，或者说是偏移量。
- Normal/Rotation Map 法线纹理：记录这一帧这个顶点的法线朝向。

纹理的组织方式：横轴按顶点编号排列，纵轴按动画帧排列。有多少个顶点，纹理就有多少列；走路这个动画时间有多长、烘焙有多少帧，纹理就有多少行。整段动画压缩成一张"顶点位置查找表"。

## 运行时 GPU 查表

运行时，行人的 Mesh 不再需要骨骼。顶点着色器里代码如下：

```csharp
// 顶点着色器：按 顶点ID + 当前帧号 查表
float2 frameUV = float2(
    v.vertexID + 0.5,                            // 列：我是几号顶点
    fmod(_TimeParameters.x, _VatAnimLength)      // 行：现在第几帧
        * _VatAnimFps + 0.5);

float3 pos = tex2Dlod(_VatPositionTex, frameUV).rgb;
v.vertex.xyz += pos;                             // 顶点直接拿到位置
v.ase_normal = tex2Dlod(_VatNormalTex, frameUV).rgb;
```

列号是顶点自己的编号，每个顶点查自己那一列；

行号由 shader 内置的 `_TimeParameters.x`（引擎时间）对动画时长取模再乘帧率得到，时间一走，帧号自动往下推，实现循环播放。

时间推进完全发生在 shader 内部，没有任何 C# 代码参与。动画从"CPU 逐帧更新骨骼变换"变成了"GPU 对纹理的读取"，这就是 VAT 有趣的地方。

## 怎么切换动画

时间如果是在shader里面自动推进，动画是自动在跑的，那我想切换不同的动画，怎么办？比如：行人站立时播放站立片段，识别到移动的时候切到走路片段。

首先会在 shader 代码中申明一个参数`_AniWalk`，根据参数，C#侧可以这么控制：

```csharp
// C# 侧：速度决定权重走向
if (base.Speed < 0.2f) {
    curProcess -= Time.deltaTime;               // 停下：权重回落
    if (curProcess < 0f) curProcess = 0f;
    Render.sharedMaterial.SetFloat("_AniWalk", curProcess);
} else {
    curProcess += Time.deltaTime;               // 走路：权重爬升
    if (curProcess > 1f) curProcess = 1.0f;
    Render.sharedMaterial.SetFloat("_AniWalk", curProcess);
}
```

`_AniWalk` 的取值在 0 到 1 之间，控制的就是两端动画的权重。如果识别物的速度在阈值以下，权重用大约一秒的时间从 1 降到 0；速度一旦高于阈值，权重再变回 1。走路循环本身一刻都没停，一直在 shader 里循环播放，变的只是这个姿势权重。

那 shader 侧收到权重后怎么做？本质是在做混合：

```csharp
// shader 侧：站立与走路两套烘焙纹理按权重插值
float3 pos    = lerp(positionTex_idle, positionTex_walk, _AniWalk);
float3 normal = lerp(normalTex_idle,   normalTex_walk,   _AniWalk);
```

权重是 0，行人保持站立姿势；权重是 1，正常走路；中间值就是从站到走的过渡姿态。它扮演了原本该由 Animator 状态机做的 Clip 切换与过渡。

# 3、性能对比

于是，写这篇文章之前，在编辑器里面做了一个demo去测试两种方案的性能，demo 的做法：取同一个行人模型（1977 个顶点、自带骨骼走路动画），分别用两种方式实例化：

- Animator 组：骨骼动画 + Animator 组件，每帧显式推进骨骼姿态（常规做法）；
- VAT 组：同一个 Mesh 换上 VAT 材质，播放由 shader 自动跑（VAT做法）。

行人数量从 20 加到 50，然后加到 100，每组预热后连续实测 200 帧，统计"动画驱动 + 相机渲染"的每帧耗时：

*[配图见公众号原文]*

结果和预期一致：

- **Animator 组随数量线性上涨**。20 个 1.76ms，100 个 3.76ms，平均每个行人摊到 0.028ms，这是 Animator 状态机和骨骼层级更新的成本；
- **VAT 组几乎没有变化**。100 个行人 1.14ms，空场景基线 0.97ms，一百个人走路对 CPU 没有明显的影响；
- 数量越大，差距越大。

数据来自编辑器环境逐帧实测（动画驱动 + 相机渲染），不含完整引擎 Player Loop 的其他开销，与真机会有出入；但我认为这里面的相对关系是真实的。

*[配图见公众号原文]*

# 结语

SR 选 VAT 去做行人，这个决策里面的条件很典型：同类角色数量大（感知行人成片出现）、动作集极小（站立和走路两段）、不需要个性表达、且动作节奏固定。这四个特征同时满足时，VAT 的批量优势才比得过表达力的损失。

反过来，主角角色需要精细表达、需要交互反馈的动画，Animator 依然是正解。