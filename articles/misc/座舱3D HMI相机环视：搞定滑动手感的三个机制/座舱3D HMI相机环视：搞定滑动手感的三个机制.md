---
title: "座舱3D HMI相机环视：搞定滑动手感的三个机制"
date: 2026-05-20
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 3D车模桌面是当前智能座舱HMI的标志性应用，也是座舱HMI的标配，围绕自车车模跟随触摸交互的虚拟相机环视功能就是3D车模桌面的标配。本文基于之前交付经验，针对单指触摸环视做介绍。

车模环视效果，如之前相机状态机的文章所说的，cinemachine已经提供了基于轨道的不同高度的环视能力的组件，用起来也比较方便。但是如果有一些效果上更细腻的要求（下划回弹，上划阻尼，惯性）或者有些业务需求（随着拖拽显隐车控图标，交互能力开关）会耦合起来，会因此想要自己写一套这个基本功能。

---

## 1. 基本原理：

### 1.1 环视相机的三层结构

本文所说的自车环视场景，基于的是 [用Adobe After Effects思维做Unity相机动画：相机运动模块3D HMI实践](%5Bhttps://mp.weixin.qq.com/s/oZkMQoVgXFcE5-f98MGuZg%5D(https://mp.weixin.qq.com/s/oZkMQoVgXFcE5-f98MGuZg)) 所描述的是相机节点三层结构：

```
Center（位于自车中心，旋转中心）
└── Root（绕 Y 轴水平旋转 → 负责「转车」）
    └── Main Camera（绕 X 轴俯仰旋转 → 负责「抬头低头」）

```

- **水平旋转**发生在 Root 层：Root 绕 lookAt（自车中心）、沿 世界 Y 轴 做 `RotateAround`，Main Camera 作为子节点一起绕自车转。
- **俯仰旋转**也发生在 Root 层：Root 绕 lookAt（自车中心）、沿 自身 right 轴 做 `RotateAround`，Main Camera 随 Root 一并俯仰。

这意味着：

> 手指左右滑，驱动的是 Root 绕自车中心的世界 Y 向 orbit；
>
> 手指上下滑，驱动的是 Root 绕自车中心的 right 向 orbit；
>
> 相机始终看向自车中心，是因为 lookAt 锚定在车心，且水平、俯仰都对该点做 `RotateAround`。

```
// 1. 把自身位置绕指定轴（axis）旋转指定角度（angle）
// 2. 旋转后自身位置到 point 的距离不变（始终恒定）
// 3. 朝向会自动调整，使新位置正好看向 point
Transform.RotateAround(point, axis, angle)`

```

三层节点的父子关系，作用是保证 Main Camera 跟随 Root 一起运动。

### 1.2 触摸输入

手指在屏幕上滑动的原始数据是**像素位移**（dx, dy）。我们的目标是把屏幕上的 dx/dy 变成**角度增量**（deltaYaw, deltaPitch），代码提炼的简要逻辑：

**第一步：触摸输入 → 角速度**

拖动中，每次收到本帧 dx/dy，乘以 sensitivity 写入 `_velocity`：

```csharp
// sensitivity 是第一参数：同一套旋转公式下，决定划同样距离，车转多快
_velocity.x = data.delta.x * sensitivity;
_velocity.y = data.delta.y * sensitivity;

```

**第二步：每帧 LateUpdate，角速度 → 角度增量**

在 `LateUpdate` 中，用 deltaTime 把角速度转化成角度增量，施加到 `_angles`：

```csharp
// _velocity 每帧都在衰减（见下一节），这里乘以 deltaTime 是为了把角速度转成这一帧实际转过的角度
float deltaYaw   = _velocity.x * speed.x * Time.deltaTime;
float deltaPitch = _velocity.y * speed.y * Time.deltaTime;

_angles.x += deltaPitch;  // 俯仰角
_angles.y += deltaYaw;    // 水平角

```

**第三步：角度 → RotateAround 绕 lookAt 旋转相机**

把累积的角度增量施加到相机旋转，同时保持相机始终朝向自车中心：

```csharp
transform.RotateAround(lookAt.position, Vector3.up, deltaYaw);      // 水平：绕世界 Y 轴
transform.RotateAround(lookAt.position, transform.right, deltaPitch); // 垂直：绕相机局部 X 轴

```

**关键点**：我们改变的始终是**角度**，不是位置。这就是环视相机区别于普通位置移动的关键——无论手指划多快划多远，改变的只是相机该朝哪个方向看。

### 1.3 交互参数

**目标与手感**


| 变量            | 类型        | 典型默认      | 含义                             |
| ------------- | --------- | --------- | ------------------------------ |
| `lookAt`      | Transform | —         | 旋转中心，通常为车辆中心                   |
| `speed`       | Vector2   | (15, -15) | 水平 / 垂直角速度系数；y 常为负，与屏幕 Y 轴方向对齐 |
| `sensitivity` | float     | 8         | 触摸位移 → 角速度的倍率                  |
| `inertia`     | float     | 0.8       | 每帧速度衰减，越大松手后滑行越远               |


**俯仰限制**


| 变量         | 类型    | 典型默认 | 含义        |
| ---------- | ----- | ---- | --------- |
| `pitchMin` | float | 0°   | 俯仰下限（硬边界） |
| `pitchMax` | float | 40°  | 俯仰上限（硬边界） |


**边界阻尼与回弹**


| 变量                  | 类型    | 典型默认 | 含义                   |
| ------------------- | ----- | ---- | -------------------- |
| `pitchMinDampRange` | float | 15°  | 接近下边界时，阻尼生效的角度区间     |
| `pitchMaxDampRange` | float | 20°  | 接近上边界时，阻尼生效的角度区间     |
| `pitchMinBounce`    | float | 4    | 下边界外的软回弹区幅度          |
| `pitchMaxBounce`    | float | 0    | 上边界外的软回弹区幅度          |
| `maxDampFactor`     | float | 0.9  | 阻尼强度上限，越接近 1 边界处越「粘」 |


**运行时状态**


| 变量              | 含义                                             |
| --------------- | ---------------------------------------------- |
| `_angles`       | 当前俯仰 / 水平角                                     |
| `_velocity`     | 当前角速度，由输入写入、由惯性逐帧衰减                            |
| `_isDragging`   | 手指是否仍在屏幕上                                      |
| `_interactable` | 是否响应输入；与 `activeInHierarchy` 一起决定是否 `IsActive` |


---

## 2. 手感：惯性、上划阻尼、下划回弹

*[配图见公众号原文]*

### 2.1 惯性

松手后，相机不会立刻停下，而是继续滑行一段距离。这靠的是 `_velocity` 每帧乘以 `inertia` 衰减：

```csharp
// inertia ∈ (0, 1)；越大衰减越慢，松手后滑得越远
_velocity *= inertia;
if (Mathf.Abs(_velocity.x) < threshold) _velocity.x = 0;
if (Mathf.Abs(_velocity.y) < threshold) _velocity.y = 0;

```

水平旋转是纯惯性，只受 `inertia` 控制。

### 2.2 上划阻尼

接近下边界（低头极限）时继续向下压，角速度会按距离边界的远近线性缩小，手感像“软墙”——越往下边界推越推不动：

```csharp
// damp ∈ [0, maxDampFactor]；越贴边界越小
damp = maxDampFactor;
if (pitch < pitchMin + pitchMinBounce && velocity.y < 0)
    damp = (pitch - (pitchMin - pitchMinBounce)) / pitchMinDampRange;

// 阻尼生效：本帧俯仰增量乘以 damp²，平方让减速更陡
deltaPitch = _velocity.y * speed.y * Time.deltaTime * damp * damp;

```

### 2.3 下划回弹

当俯仰角已经超出 pitchMax（即已经顶到上方极限），继续下划，本帧俯仰增量会被直接**截断**——增量为零，这一帧相当于什么都没发生。体感就是已经到顶了，推不动了。

然后，同时兼顾软回弹（bounce），在松手后、俯仰角仍在 pitchMaxBounce 区间内时才会触发。即松开后，相机在惯性作用下缓慢滑回 pitchMax 边界内。

所以：

- **推到顶继续推**：手感是顶死（增量截断）
- **松手后还在软区**：手感是弹回（bounce 衰减）

回弹的代码实现：

```csharp
deltaPitch = _velocity.y * speed.y * Time.deltaTime * damp * damp;
if (pitch + deltaPitch > pitchMax + pitchMaxBounce)
    deltaPitch = pitchMax + pitchMaxBounce - pitch;  // 截断到上边界
else if (pitch + deltaPitch < pitchMin - pitchMinBounce)
    deltaPitch = pitchMin - pitchMinBounce - pitch;  // 截断到下边界

```

---

## 3. 小结

本文只是描述了环视能力的组件能力，然而随着交互越来越复杂，只有拖拽是不够的，还会需要通过双指来缩放视角，通过双指平移来移动视角。尤其是SR的开发中，所以后续会再写一篇有这些复合需求的实现方式。