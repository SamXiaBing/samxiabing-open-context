---
title: "智驾 SR 开发：记忆泊车全览视角的自动构图方法"
date: 2026-07-16
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 做记忆泊车时，有一个比较有意思的功能：将所记忆的泊车过程的感知物和轨迹线显示出来，用一个镜头看全所有。生成这些建图结果物体并不难，但是这个视角要既能看全所有建图结果，又能看上去比较美观就比较麻烦，因为你不知道你会遇到什么样的建图情况。

有的停车场扁得像一条走廊，有的像多层蛋糕往下叠；有的轨迹刚拐两弯就到车位，有的要绕半个地库。这意味着：内容不能被裁切，楼层层次还得能分辨出来。

本文分享我曾经使用过的一套做法，在给定一个空间范围的情况下，尝试算出一组稳定、可复现的镜头位姿的方法。

![01-overview-camera-geometry](./01-overview-camera-geometry.png)

---

## 步骤一：构建包围盒（Bounds）

### 输入

- 各楼层**道路中心线**采样点（建图轨迹的主体）
- 目标停车位所在楼层的所有**车位角点**
- **入口 / 消星点**（GPS 信号丢失锚点）
- **目标车位中心点**

### 算法

把所有点合并为一个列表，对各轴取极值，得到轴对齐包围盒（AABB）：

$$
\text{center} = \frac{\min + \max}{2}, \quad \text{size} = \max - \min
$$

全览模式下，各楼层点一并参与计算，不按楼层拆开，目的是让镜头覆盖**整次建图走过的空间**。

### 输出

- `Bounds.center`：后续机位的注视中心
- `Bounds.extents`：后续距离与安全校验的尺寸依据

### 示意代码

```csharp
Bounds CalcBounds(List<Vector3> points)
{
    Vector3 min = points[0], max = points[0];
    foreach (var p in points)
    {
        min = Vector3.Min(min, p);
        max = Vector3.Max(max, p);
    }
    return new Bounds((min + max) * 0.5f, max - min);
}

// 全览点集 = 道路点 + 入口锚点 + 目标车位（+ 可选 Y padding）

```

---

## 步骤二：估算观察距离

### 输入

- 步骤一的 `Bounds`（`extents` 记为 \(e_x, e_y, e_z\)）
- 相机**竖向 FOV** \(\theta_v\)（来自 Virtual Camera 镜头的配置参数）
- 输出相机**宽高比** \(\text{aspect}\)（取实际渲染相机的 pixelRect，分屏或者UI布局的需求会改变有效宽高比）
- 距离微调系数（经验值，默认 1.0）

### 算法

全览采用斜视，包围盒在 XZ 平面和 Y 方向都会进入画面，距离分两路估算后取大：

1. 由竖向 FOV 和宽高比换算水平 FOV：
  $$
  \theta_h = 2\arctan\!\left(\tan\frac{\theta_v}{2} \times \text{aspect}\right)
  $$
2. XZ 向（地面跨度）：
  $$
  d_{XZ} = \frac{\sqrt{e_x^2 + e_z^2}}{\tan(\theta_h / 2)}
  $$
3. Y 向（楼层高度差）：
  $$
  d_Y = \frac{e_y}{\tan(\theta_v / 2)}
  $$
4. 初值：\(d_0 = \max(d_{XZ},\, d_Y) \times \text{adjust}\)

### 输出

- 观察距离初值 \(d_0\)（沿相机视线到包围盒中心的直线距离）

### 示意代码

```csharp
float CalcOverviewDistance(Bounds b, float verFov, float aspect, float adjust = 1f)
{
    float horFov = Camera.VerticalToHorizontalFieldOfView(verFov, aspect);
    float tanHW = Mathf.Tan(horFov * 0.5f * Mathf.Deg2Rad);
    float tanHV = Mathf.Tan(verFov * 0.5f * Mathf.Deg2Rad);

    float dXZ = Mathf.Sqrt(b.extents.x * b.extents.x + b.extents.z * b.extents.z) / tanHW;
    float dY  = b.extents.y / tanHV;
    return Mathf.Max(dXZ, dY) * adjust;
}

```

*[配图见公众号原文]*

---

## 步骤三：确定斜视机位与朝向

### 输入

- 步骤一得到的`Bounds.center`
- 步骤二得到的距离 \(d\)
- 俯视倾斜角 \(\alpha\)（约 35°）

> 这里默认**倾斜角约 35°**，这是全览的俯仰角，也是一个经验值。

### 算法

**1. 距离分解**

沿观察方向把 \(d\) 拆成竖向与水平分量：

$$
h = d\sin\alpha, \quad l = d\cos\alpha
$$

**2. 固定角点朝向**

取包围盒底面**固定索引角点**（如 `(minX, minY, maxZ)`）指向中心的 XZ 投影方向，作为相机水平朝向。

这个做法的好处是该方向由包围盒几何形态决定，无论轨迹起止点在哪，目标车位在哪，同一类建图结果每次全览朝向都会是一致的。

> 本来第一版的想法是尽量还原 HMI UI 稿，即尽量总是让轨迹起点在建图结果画面的左上方、终点在右下方。做法大致是：
>
> 1. 用轨迹起终点构造走向向量（代码里取的是终点 → 起点）：
>
> ```
> direction = (start - end).normalized;
> ```
>
> 2. 在包围盒底面 / 顶面的轴对齐边上找最长的一条，得到 `longEdgeDirection`（只比较水平棱，不含竖边；用主轴近似「整张图该横着摆还是竖着摆」）。
>
> 3. 用点积给长边定极性：若与 `direction` 反向则翻转，保证长边正方向与轨迹走向同侧。
>
> 4. 取水平面内垂直于长边的侧向，再 `LookRotation`：
>
> ```
> perpendicular = Cross(longEdgeDirection, Vector3.up).normalized;
> return LookRotation(-perpendicular) * euler;
> // 相机站在长边一侧看向盒子；长边（及对齐后的起终点走向）大致落在画面左右轴上
> ```
>
> 但这套做法在同一建图结果上出现过全览朝向差约 180° 的问题。根因是朝向强依赖轨迹起 / 终点：建图结果全览与巡航全览传入的点的值不同（有空值可能），长边极性或相邻观测侧被翻转，视角就反了。因此后来改成固定角点，不再用轨迹定朝向。

**3. 落位**

相机放在：从中心沿水平朝向的反方向退 \(l\)，再抬高 \(h\)：

$$
\text{position} = \text{center} - \hat{n}_{horiz} \cdot l + \text{up} \cdot h
$$

旋转取看向中心的方向：`LookRotation(normalize(center - position))`。

### 输出

- `cameraPosition`：候选相机世界坐标
- `cameraRotation`：候选相机旋转

### 示意代码

```csharp
void CalcObliquePose(Bounds bounds, float distance, float tiltDeg,
    out Vector3 position, out Quaternion rotation)
{
    float rad = tiltDeg * Mathf.Deg2Rad;
    float h = distance * Mathf.Sin(rad);
    float l = distance * Mathf.Cos(rad);

    // 固定角点 → 中心的水平方向
    Vector3 corner = /* 底面固定角点，如 (minX, minY, maxZ) */;
    Vector3 horiz = (bounds.center - corner);
    horiz.y = 0;
    horiz.Normalize();

    position = bounds.center + Vector3.up * h + horiz * l;
    rotation = Quaternion.LookRotation((bounds.center - position).normalized);
}

```

---

## 步骤四：安全距离校验

### 输入

- 步骤三得到的候选 `cameraPosition`、`cameraRotation`
- `Bounds` 的 8 个角点
- \(\theta_v\)、\(\text{aspect}\)

### 算法

公式距离是近似解，斜视时个别角点仍可能贴边或被裁。校验做法：

1. 把每个角点变到相机局部坐标系；
2. 对每个角点，分别计算在水平和竖向半视锥内刚好可见时，它应该具备的最小深度；
3. 取所有角点中的最大值作为 `requiredDistance`；
4. 若 \(d < \text{requiredDistance}\)，把 \(d\) 抬到 `requiredDistance`，并按步骤三重新落位。

### 输出

- 修正后的最终距离 \(d\)
- 修正后的 `cameraPosition`、`cameraRotation`

### 示意代码

```csharp
float RequiredDistance(Bounds b, Quaternion camRot, float verFov, float aspect)
{
    float tanHW = Mathf.Tan(HorFov(verFov, aspect) * 0.5f * Mathf.Deg2Rad);
    float tanHV = Mathf.Tan(verFov * 0.5f * Mathf.Deg2Rad);
    Quaternion inv = Quaternion.Inverse(camRot);
    float required = 0f;

    foreach (var corner in GetCorners(b))
    {
        Vector3 local = inv * (corner - b.center);
        float needX = Mathf.Abs(local.x) / tanHW - local.z;
        float needY = Mathf.Abs(local.y) / tanHV - local.z;
        required = Mathf.Max(required, Mathf.Max(needX, needY));
    }
    return Mathf.Max(0f, required);
}

// 若 distance < required → distance = required，重算 position
position = bounds.center - (rotation * Vector3.forward) * distance;

```

---

## 单层阅览

全览就是以上的做法了，然而咱们还有单层阅览的需求。

用户切换到某一楼层时，不再走斜视全览，改走正俯视。而比较有特点的需求是，如果单层阅览的楼层是目标停车位所在楼层时，目标车位要在视觉中心，而不是简单的看全。

### 输入

- 当前楼层的点集，即单层 `Bounds`
- 是否**目标车位层**（有车位中心 override）
- 目标车位层：车位中心、车位边偏航角、高度上限（如 50m）

### 算法

示意代码

```csharp
// 距离：同步骤二的 FOV 换算，但仅 XZ、用边长半宽（非对角线）
float horFov = Camera.VerticalToHorizontalFieldOfView(verFov, aspect);
float dW = (bounds.size.x * 0.5f) / Mathf.Tan(horFov * 0.5f * Mathf.Deg2Rad);
float dD = (bounds.size.z * 0.5f) / Mathf.Tan(verFov * 0.5f * Mathf.Deg2Rad);
float distance = Mathf.Max(dW, dD) * singleFloorAdjust;

Vector3 centerPoint = isTargetFloor ? parkingCenter : bounds.center;
if (isTargetFloor)
    distance = Mathf.Min(distance, maxHeight);   // 高度上限
else
{
    // 与步骤四相同的角点安全校验
    distance = Mathf.Max(distance, RequiredDistance(bounds, topDownRot, verFov, aspect));
}

// 位置：中心正上方（非步骤三斜视）
Vector3 position = centerPoint + Vector3.up * distance;
Quaternion rotation = TopDown(isTargetFloor ? slotYaw : 0f);
```


| 场景    | 距离                | 注视点       | 旋转           |
| ----- | ----------------- | --------- | ------------ |
| 普通单层  | 按 XZ 宽高分别适配，取较大值  | Bounds 中心 | 正俯视，偏航 0°    |
| 目标车位层 | `min(计算距离, 高度上限)` | **车位中心**  | 正俯视，按车位边对齐偏航 |


正俯视旋转不能用 `Euler(90, yaw, 0)`：俯仰 90° 时偏航会落到 roll 上，万向节死锁，画面方向错位。应指定相机朝下，屏幕上方朝北：

```csharp
Quaternion TopDown(float yawDeg)
{
    Vector3 forward = Vector3.down;
    Vector3 up = Quaternion.Euler(0f, yawDeg, 0f) * Vector3.forward;
    return Quaternion.LookRotation(forward, up);
}
```

---

## 结语

全览视角的计算我想也不会只有这一种做法，但是我想每一种做法，总会碰到一些不那么美观的情况，比如:

- 多楼层层高比较低，建图结果在俯视下，看上去道路线层叠，可读性并不高。
- 目标车位扎标被道路线遮挡。
- 停车轨迹将近3公里，全览的建图结果内全是“蚂蚁”。

目前由于全览并非是一个特别有雕琢价值的场景，所以大多时候这类问题是“得过且过”的。

