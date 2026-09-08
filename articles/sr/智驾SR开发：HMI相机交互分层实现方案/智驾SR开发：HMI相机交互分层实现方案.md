---
title: "智驾SR开发：HMI相机交互分层实现方案"
date: 2026-05-21
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 之前的文章 : [座舱3D HMI相机环视：搞定滑动手感的三个机制](https://mp.weixin.qq.com/s/boJ5a-Looy4GV4aQkKzfNw) 讲到了环视这个基础的能力。然而对于SR开发，产品和设计为了在不同的SR视角下充分满足用户的交互需求，大概率会提出更多的功能要求，比如行车时要环视周车，全览时要拉远看整条路线，选楼层或车位时要平移地图。

所以我们需要准备一个能力更综合的、通过手势驱动相机动效的模块，同时具备环绕旋转、距离缩放、单指平移、双指平移等能力。

---

## 一、总览

相机手势控制系统采用 **事件驱动 + 策略模式** 的方案，由以下核心组件协作完成：

*[配图见公众号原文]*

---

## 二、能力清单

`CamGestureCtrl` 通过枚举定义了 5 种手势能力：


| 枚举值         | 能力名称       | 输入方式 | 适用场景       |
| ----------- | ---------- | ---- | ---------- |
| `Orbit`     | 环绕旋转（轨道旋转） | 单指滑动 | SR 模式、全览模式 |
| `Zoom`      | 距离缩放（前后推拉） | 双指捏合 | 所有模式       |
| `SinglePan` | 单指平移       | 单指滑动 | 地面全览/导航选择  |
| `DualPan`   | 双指平移       | 双指滑动 | AVP 全览模式   |


---

## 三、实现详解

### 3.1 环绕旋转（Orbit）

> **本文不展开环绕旋转的详细实现**。关于轨道相机的三层节点结构、触摸输入→角速度→RotateAround 的基本流程，以及惯性/上划阻尼/下划回弹三个手感机制的原理与代码，已在  [座舱3D HMI相机环视：搞定滑动手感的三个机制](https://mp.weixin.qq.com/s/boJ5a-Looy4GV4aQkKzfNw)  中完整描述，此处不再赘述。

本节仅补充上文未涉及的内容——**环绕旋转在本系统中的事件驱动集成方式**。

#### 3.1.1 事件驱动集成

*[配图见公众号原文]*

#### 3.1.2 与动画系统的协作

*[配图见公众号原文]*

### 3.2 距离缩放（Zoom）

#### 3.2.1 逻辑

缩放通过双指捏合手势控制相机沿自身 Z 轴前后移动，改变相机与目标点之间的距离。距离被 Clamp 在 `[minDist, maxDist]` 区间内，松手后通过惯性因子继续滑行。

#### 3.2.2 关键代码

```csharp
private void OnPinchEvt(object sender, BaseEventArgs args)
{
    var e = args as OnPinchEvt;
    // 像素增量转为单位增量后放大 100 倍作为速度
    _zoomVel = ScreenUtil.PixelsToUnits(e.ScaleDeltaDelta) * 100;
}

private void TickZoom()
{
    _zoomVel *= _zoomInertia;  // 惯性衰减
    if (_zoomVel >= -0.01f && _zoomVel <= 0.01f)
    {
        _zoomVel = 0.0f;
        return;
    }
    var distance = Mathf.Abs(_camTrans.localPosition.z)
                   + -_zoomVel * _zoomSpd * Time.deltaTime;
    float clampedDist = Mathf.Clamp(distance, _minDist, _maxDist);
    _camTrans.SetLocalPositionZ(-clampedDist);
}

```

> **注意**：相机 localZ 为负值（面向目标点）所以是`-clampedDist` 。缩放方向的正负由 `ScaleDeltaDelta` 的符号决定。

---

### 3.3 单指平移（SinglePan）

#### 3.3.1 逻辑

单指平移，将手指的屏幕滑动增量转化为相机在自身局部坐标 X/Y 方向的位置偏移。**关键在于**平移量根据当前相机的 FOV 和相机距离进行了缩放，使得不同缩放级别下的平移速度体感一致。

#### 3.3.2 关键代码

```csharp
private void TickSinglePan()
{
    _singlePanVel *= _panInertia;
    var posX = _camTrans.localPosition.x;
    var posY = _camTrans.localPosition.y;

    // 核心：根据 FOV 和距离计算视锥体高度，作为平移缩放因子
    float halfFovRad = Mathf.Deg2Rad * _camera.fieldOfView / 2;
    float height = 2 * -_camTrans.localPosition.z * Mathf.Tan(halfFovRad);

    if (Mathf.Abs(_singlePanVel.x) > 0.01f)
        posX += -_singlePanVel.x * _xPanSpd * height * Time.deltaTime;
    if (Mathf.Abs(_singlePanVel.y) > 0.01f)
        posY += -_singlePanVel.y * _yPanSpd * height * Time.deltaTime;

    posX = Mathf.Clamp(posX, -_xPanLimit, _xPanLimit);
    posY = Mathf.Clamp(posY, -_yPanLimit, _yPanLimit);
    _camTrans.SetLocalPositionX(posX);
    _camTrans.SetLocalPositionY(posY);
}

```

> **注意**：单指平移**不更新**观察目标点，即平移后相机中心偏离了原始注视点，仅在记忆泊车的地图全览/导航选择等视图场景下使用。

---

### 3.4 双指平移（DualPan）

#### 3.4.1 逻辑

双指平移，与单指平移的位移算法完全一致（同样使用 FOV 缩放），但有差异：**双指平移会同步更新** `_focusTarget` **目标点位置**。这保证了在记忆泊车建图结果全览模式下，平移后继续做环绕旋转时，旋转中心能正确。

#### 3.4.2 关键代码

```csharp
private void TickDualPan()
{
    _dualPanVel *= _panInertia;
    // ... 位移计算同 SinglePan（省略）...

    // ★ 关键差异：同步更新环绕目标点
    var worldPos = _camTrans.TransformPoint(
        new Vector3(0, 0, -_camTrans.localPosition.z));
    SetFocusPos(new Vector3(worldPos.x, 0, worldPos.z));
}

```

> **重设逻辑**：将相机局部坐标 `(0, 0, -localZ)` 变换到世界坐标，即"相机正前方距离为 localZ 处"的世界点，然后取其 XZ 分量（Y 归零）作为新的 `_focusTarget` 位置。

---

## 四、场景与手势映射

不同驾驶/功能场景下，手势能力集和参数组合不同：


| 场景模式                                                           | 手势能力               | 缩放范围  | 平移方式 | 自动重置 |
| -------------------------------------------------------------- | ------------------ | ----- | ---- | ---- |
| **SR 模式**：General、HighSpeed、CrossWait、PdcOverlook、Park、Neutral | 环绕旋转 + 双指缩放        | 9~50  | 无    | 是    |
| **记忆泊车地图全览**                                                   | 环绕旋转 + 双指缩放 + 双指平移 | 40~动态 | 双指   | 否    |
| **记忆泊车单层地面全览**                                                 | 单指平移 + 双指缩放        | 30~80 | 单指   | 否    |


> **记忆泊车 AVP** 根据建图结果计算观察参数的方法将在下一篇文章中详述。

---

## 五、手势事件管理

### 5.1 事件示意图

整体关系图：

*[配图见公众号原文]*

相机动画状态：

*[配图见公众号原文]*

### 5.2 冲突与优先级处理

设置 `_activeGestures` 决定哪个被优先执行，从而实现同一种输入在不同模式下驱动不同行为。

```csharp
// 缩放与单指滑动允许同时执行（双指缩放时可能伴随滑动）
_pinchGesture.AllowSimultaneousExecution(_singleSlideGesture);

// UI 层拦截：触摸到 UI 层物体时不传递给手势系统
FingerEngine.Instance.CaptureGestureHandler = OnCaptureHandler;
private bool? OnCaptureHandler(GameObject go)
{
    if (go.layer == LayerMask.NameToLayer("UI"))
        return true;  // 拦截，不处理
    return false;     // 放行
}

// 手势优先级：Tap(10) > SingleSlide(9) > Scale(8)
_tapGesture.Priority = 10;
_singleSlideGesture.Priority = 9;
_pinchGesture.Priority = 8;
```

---

## 六、小结

这一套机制不依赖Cinemachine，整体采用分层事件驱动的架构结合状态策略模式，自身足够轻量，针对智驾SR不同场景下的多手势相机交互需求适配性很强，当前业务场景够用。



&nbsp;