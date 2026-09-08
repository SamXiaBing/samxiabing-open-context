---
title: "用Adobe After Effects思维做Unity相机动画：相机运动模块3D HMI实践"
date: 2026-05-18
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 使用3D引擎开发HMI应用，必然是要考虑相机运动模块的设计，毕竟这里既有根据不同驾驶状态显示不同视角的需求，又有触摸交互变化视角的需求。本文只针对前者，描述一种设计方案，这个方案在协作成本和效果还原能力上有一定的优势。

3D引擎一般都有自己的相机管理工具/插件，比如Unity的Cinemachine。我也参与过使用Cinemachine实现相机动画的量产车型项目。Cinemachine很强大，但它在工程实践中可能碰到两个问题：

1. **美术同事的专业背景**：并不是咱们对接的所有3D美术，都是深耕游戏行业多年，他们不是早以习惯在引擎中调试效果的TA（技术美术），而是更熟悉Adobe After Effects或是PR之类软件的美术师。这一点，在车企遇到的概率比较大。所以比较难让美术同事去接受并熟练使用Cinemachine/Sequencer。
2. **效果不符合预期**：在我之前的工作中，曾经遇到过使用cinemachine，无法还原镜头切换效果的情况，当然，不排除是我自身对cinemachine不足够熟练导致的：从一个视角切换到另一个视角，镜头要看上去舒服，美术的要求是相机永远是环绕的轨迹，且在环绕过程中按照预期的曲线去改变距离、角度等。然而，cinemachine有时会在运动过程中出现轨迹/朝向突变，也不支持单独调整细分参数的变化曲线。

所以我们曾针对美术同事熟悉的“推拉摇移”的镜头语言，**自己写一套模拟AE参数的相机模块**。让美术用他们熟悉的思维——FOV多少、推拉多少、左右偏多少——配置动画，美术可以在自己的开发工具中调好，开发这边也就直接复制参数即可。

---

## 1. 相机节点层级结构

### 1.1 三层节点设计

```
Center (位于自车中心，即被观测物的焦点)
└── Root (处理水平旋转+倾斜+整体位移，类似unreal的spring arm)
    └── Main Camera (处理推拉+偏移+相机自身旋转，主相机本体)
```

这是做相机系统原始的三层结构，每层只管自己的事情：


| 节点              | 控制的参数            | 对应AE参数 |
| --------------- | ---------------- | ------ |
| **Root**        | 水平旋转、倾斜角度、整体位移   | 相机位移   |
| **Main Camera** | 推拉、左右上下偏移、相机自身旋转 | 镜头参数   |


### 1.2 设计益处

- CameraRoot的旋转**不影响**Main Camera的localPosition
- Main Camera的推拉就是简单的Z轴平移，物理意义清晰

---

## 2. 相机脚本设计

*[配图见公众号原文]*

### 2.1 脚本包含

```
CameraStateController              → 状态机：根据档位/车速决定当前视角
CameraAnimationManager            → 动画管理：从ScriptableObject播放动画
CameraAnimationPlayer              → 动画驱动：每帧把动画参数应用到相机
AECameraAnimationScriptableObject  → 动画配置本体：14组参数的Clip列表
AECameraParamClip                 → 参数片段基类：包含delay/duration/curve/endValue
AECameraPositionClip              → 位置片段：AE像素→Unity米转换
AECameraRotationClip              → 旋转片段：支持角度短路径插值
AECameraFOVClip / AECameraSizeClip → FOV/正交尺寸片段
AECameraLensShiftClip             → 镜头偏移片段
```

### 2.2 CameraStateController：状态机

CameraStateController的核心是根据**车辆状态**自动切换视角。以下为示意代码。

```csharp
// 档位+行驶状态 → 视角枚举
switch (_carInfoModel.GearState.Value)
{
    case EnumData.GearState.D:
    case EnumData.GearState.R:
        switch (_carInfoModel.MoveStatus.Value)
        {
            case EnumData.MoveStatus.GENERAL:
                cameraStatus = CameraStatusEnum.General;  // 行车视角
                break;
            case EnumData.MoveStatus.HIGH_SPEED:
                cameraStatus = CameraStatusEnum.HighSpeed; // 高速视角
                break;
            case EnumData.MoveStatus.PDC:
                cameraStatus = CameraStatusEnum.Pdc; // PDC俯视
                break;
            // ...
        }
        break;
    case EnumData.GearState.P:
        cameraStatus = CameraStatusEnum.Park; // 驻车视角
        break;
}
CameraAnimationManager.Instance.Play(cameraStatus, false, allowGesture);
```

它还负责**自动重置视角**：用户一段时间不操作，就慢慢回到当前档位的默认视角。

### 2.3 CameraAnimationManager：动画管理器

一个单例，管理所有视角动画的播放，支持多种**相机状态的切换**，**可打断动画**和**不可打断动画，提供动画事件的监听**。以下为示意代码。

```csharp
public void Play(string cameraStatusEnum, bool immediateComplete = false, bool allowGesture = false)
{
    // allowGesture=true 表示动画播放中允许手势打断
    _allowGesture = allowGesture;
    CameraAnimationPlayer.Play(anim, immediateComplete);
}
```

### 2.4 CameraAnimationPlayer：动画播放器

管理根据AECameraAnimationScriptableObject驱动动画的实际执行，在`LateUpdate`中每帧更新：

```csharp
private void LateUpdate()
{
    if (isPlaying && _curPlayingAnimation != null)
    {
        if (_curPlayingAnimation.UpdateCamera(_camera, _animTime))
            _animTime += Time.deltaTime;  // 动画未结束，时间累加
        else
        {
            isPlaying = false;
            OnCompleted?.Invoke();  // 动画结束回调
        }
    }
}
```

### 2.5 AECameraAnimationScriptableObject：核心配置脚本

这是**最关键**的脚本——它以ScriptableObject的形式存储了14组动画参数，每组参数由多个Clip组成。以下为示意代码。

```csharp
/// <summary>
/// 动画配置本体：存储14组参数的Clip列表
/// </summary>
[CreateAssetMenu(menuName = "Camera/AECameraMotion")]
public class AECameraAnimationScriptableObject : ScriptableObject
{
    // 14组参数，每组是一个List<Clip>，支持多段动画

    // 镜头FOV
    public List<AECameraFOVClip> fieldOfView;

    // 正交模式尺寸
    public List<AECameraSizeClip> orthographicSize;

    // 水平旋转 (Root.rotation.y)
    public List<AECameraRotationClip> horizontalRotation;

    // 倾斜角度 (Root.rotation.x)
    public List<AECameraRotationClip> tiltAngle;

    // 镜头推拉 (MainCamera.position.z)
    public List<AECameraPositionClip> lensPushPull;

    // 镜头左右/上下偏移 (MainCamera.position.x/y)
    public List<AECameraPositionClip> lensOffsetX;
    public List<AECameraPositionClip> lensOffsetY;

    // 相机自身摇摆 (MainCamera.rotation)
    public List<AECameraRotationClip> verticalSway;
    public List<AECameraRotationClip> horizontalSway;

    // 整体位移 (Root.position)
    public List<AECameraPositionClip> verticalMove;
    public List<AECameraPositionClip> horizontalMove;
    public List<AECameraPositionClip> forbackwardMove;

    // 画面平移 (MainCamera.lensShift)
    public List<AECameraLensShiftClip> horizontalLensShift;
    public List<AECameraLensShiftClip> verticalLensShift;
}
```

#### 2.5.1 初始化与参数读取

```csharp
/// <summary>
/// 动画初始化：记录播放前的相机参数作为起始值
/// </summary>
/// <param name="camera">当前Unity相机对象</param>
public void InitCameraParam(Camera camera);

/// <summary>
/// 驱动动画播放：根据时间更新相机各项参数
/// </summary>
/// <param name="camera">当前Unity相机对象</param>
/// <param name="time">当前动画时间</param>
/// <returns>动画是否还在进行中</returns>
public bool UpdateCamera(Camera camera, float time);

/// <summary>
/// 获取动画最后定格的参数列表
/// </summary>
/// <returns>14个终点值列表</returns>
public List<float> GetLastValue();

/// <summary>
/// 获取相机Root的最终旋转角(XY)
/// </summary>
/// <returns>Vector2(最终倾斜角, 最终水平旋转角)</returns>
public Vector2 GetCameraRootEndEulerXY();
```

#### 2.5.2 动态修改动画终点

```csharp
/// <summary>
/// 设置推拉距离的终点值（运行时可调，用于AVP等动态计算距离的场景）
/// </summary>
/// <param name="value">推拉值（Unity米）</param>
public void SetLensPushPull(float value);

/// <summary>
/// 设置倾斜角度的终点值
/// </summary>
/// <param name="value">Root.rotation.x</param>
public void SetTiltAngle(float value);

/// <summary>
/// 设置水平旋转的终点值
/// </summary>
/// <param name="value">Root.rotation.y</param>
public void SetHorizontalRotation(float value);

/// <summary>
/// 设置上下摇的终点值
/// </summary>
/// <param name="value">MainCamera.rotation.x</param>
public void SetVerticalSway(float value);

/// <summary>
/// 设置左右摇的终点值
/// </summary>
/// <param name="value">MainCamera.rotation.y</param>
public void SetHorizontalSway(float value);

/// <summary>
/// 设置镜头Shift X轴偏移的终点值
/// </summary>
/// <param name="offset">LensShift.x</param>
public void SetLensShiftOffsetX(float offset);

/// <summary>
/// 设置镜头Shift Y轴偏移的终点值
/// </summary>
/// <param name="offset">LensShift.y</param>
public void SetLensShiftOffsetY(float offset);
```

#### 2.5.3 配置写入

```csharp
/// <summary>
/// 从当前Unity相机状态设置为动画终点（用于"复制当前位置到动画配置"）
/// </summary>
/// <param name="camera">当前Unity相机对象</param>
public void SetView(Camera camera);

/// <summary>
/// 从另一个动画配置复制终点值（用于"重置为另一个视角的终点"）
/// </summary>
/// <param name="source">源动画配置</param>
public void SetView(AECameraAnimationScriptableObject source);

/// <summary>
/// 逐参数设置动画终点（14参数版本）
/// </summary>
public void SetView(float fov, float size, float hRot, float tilt,
    float len, float lenX, float lenY,
    float vSway, float hSway,
    float vMove, float hMove, float fbMove,
    float hLensShift, float vLensShift);
```

### 2.6 AECameraParamClip：参数片段基类

每个动画参数（FOV、位置、旋转等）都由多个`Clip`组成，支持多段动画拼接。以下为示意代码。

```csharp
/// <summary>
/// 参数片段基类：定义单个动画片段的时间行为
/// </summary>
[Serializable]
public class AECameraParamClip
{
    public float delay;           // 延迟多久后开始（秒）
    public float duration;        // 持续时长（秒）
    public AnimationCurve curve;  // 缓动曲线
    public float endValue;        // 终点值（AE像素单位）

    /// <summary>
    /// 获取当前时刻的插值结果
    /// </summary>
    /// <param name="startValue">起始值（Unity单位）</param>
    /// <param name="timePoint">当前动画时间（秒）</param>
    /// <param name="output">输出的当前插值</param>
    /// <returns>动画是否还在进行中</returns>
    public virtual bool GetValue(float startValue, float timePoint, ref float output)
    {
        if (timePoint <= delay)
            return true;  // 延迟中，未开始
        else if (timePoint > (delay + duration))
        {
            output = GetUnityEndValue();  // 已结束，返回终点
            return false;
        }
        else
        {
            // 计算时间进度百分比
            float timePercentage = Mathf.Abs((timePoint - delay) / duration);
            // 用AnimationCurve计算值进度百分比
            float valuePercentage = curve.Evaluate(timePercentage);
            // 起始值 + 进度 * (终点 - 起始)
            output = valuePercentage * (GetUnityEndValue() - startValue) + startValue;
            return true;
        }
    }

    /// <summary>获取终点值（AE像素）</summary>
    public virtual float GetEndValue() => endValue;

    /// <summary>获取Unity单位终点值（可能涉及像素→米转换）</summary>
    public virtual float GetUnityEndValue() => endValue;

    /// <summary>设置终点值（AE像素）</summary>
    public virtual void SetEndValue(float value) => endValue = value;

    /// <summary>设置Unity单位终点值（需要反向转换为AE像素）</summary>
    public virtual void SetUnityEndValue(float value) => endValue = value;
}
```

**派生类特殊处理**：


| 派生类                     | 特殊处理                                                        |
| ----------------------- | ----------------------------------------------------------- |
| `AECameraPositionClip`  | 像素→米转换（系数的调试结果是378），重写`GetUnityEndValue`/`SetUnityEndValue` |
| `AECameraRotationClip`  | 角度短路径插值，重写`GetValue`解决0°/360°边界问题                           |
| `AECameraFOVClip`       | 无特殊处理，直接使用Unity值                                            |
| `AECameraSizeClip`      | 无特殊处理，直接使用Unity值                                            |
| `AECameraLensShiftClip` | 无特殊处理，直接使用Unity值                                            |


### 2.7 UpdateCamera的完整执行逻辑

`UpdateCamera`是驱动的核心，它遍历14组参数，每组调用`UpdateAnimationList`计算当前值，最终写入相机Transform。以下为示意代码。

```csharp
/// <summary>
/// 驱动动画播放：根据时间更新相机各项参数
/// </summary>
/// <param name="camera">当前Unity相机对象</param>
/// <param name="time">当前动画时间</param>
/// <returns>动画是否还在进行中</returns>
public bool UpdateCamera(Camera camera, float time)
{
    bool hasValueChanged = false;

    // 1. 更新FOV
    if (UpdateAnimationList(fieldOfView, time, _cameraFOVStart, ref _cameraFOV))
        hasValueChanged = true;
    camera.fieldOfView = _cameraFOV;

    // 2. 更新正交尺寸
    if (UpdateAnimationList(orthographicSize, time, _cameraSizeStart, ref _cameraSize))
        hasValueChanged = true;
    camera.orthographicSize = _cameraSize;

    // 3. 更新CameraRoot旋转（水平+倾斜）
    if (UpdateAnimationList(horizontalRotation, time, _cameraRootRotYStart, ref _cameraRootRotY))
        hasValueChanged = true;
    if (UpdateAnimationList(tiltAngle, time, _cameraRootRotXStart, ref _cameraRootRotX))
        hasValueChanged = true;

    // 4. 更新MainCamera位置（推拉+偏移）
    if (UpdateAnimationList(lensPushPull, time, _cameraPosZStart, ref _cameraPosZ))
        hasValueChanged = true;
    if (UpdateAnimationList(lensOffsetX, time, _cameraPosXStart, ref _cameraPosX))
        hasValueChanged = true;
    if (UpdateAnimationList(lensOffsetY, time, _cameraPosYStart, ref _cameraPosY))
        hasValueChanged = true;

    // 5. 更新MainCamera旋转（上下摇+左右摇）
    if (UpdateAnimationList(verticalSway, time, _cameraRotXStart, ref _cameraRotX))
        hasValueChanged = true;
    if (UpdateAnimationList(horizontalSway, time, _cameraRotYStart, ref _cameraRotY))
        hasValueChanged = true;

    // 6. 更新CameraRoot位置（整体位移）
    if (UpdateAnimationList(verticalMove, time, _cameraRootPosYStart, ref _cameraRootPosY))
        hasValueChanged = true;
    if (UpdateAnimationList(horizontalMove, time, _cameraRootPosXStart, ref _cameraRootPosX))
        hasValueChanged = true;
    if (UpdateAnimationList(forbackwardMove, time, _cameraRootPosZStart, ref _cameraRootPosZ))
        hasValueChanged = true;

    // 7. 更新镜头Shift
    if (UpdateAnimationList(horizontalLensShift, time, _cameraLensShiftXStart, ref _cameraLensShiftX))
        hasValueChanged = true;
    if (UpdateAnimationList(verticalLensShift, time, _cameraLensShiftYStart, ref _cameraLensShiftY))
        hasValueChanged = true;

    // 8. 写入相机Transform
    UpdateCameraRootLocalEuler(_cameraRootRotX, _cameraRootRotY, 0);
    UpdateCameraRootTransLocalPos(_cameraRootPosX, _cameraRootPosY, _cameraRootPosZ);
    UpdateCameraMainLocalEuler(_cameraRotX, _cameraRotY, 0);
    UpdateCameraMainTransLocalPos(_cameraPosX, _cameraPosY, _cameraPosZ);

    return hasValueChanged;
}

/// <summary>
/// 更新单个参数列表（支持多Clip串联）
/// </summary>
private bool UpdateAnimationList<T>(List<T> list, float time, float start, ref float value)
    where T : AECameraParamClip
{
    if (list.Count == 0)
        return false;

    for (int i = 0; i < list.Count; i++)
    {
        // 每个Clip的起始值是前一个Clip的终点（串联动画）
        float clipStart = i == 0 ? start : list[i - 1].GetUnityEndValue();
        // Clip的本地时间 = 总时间 - 前序Clip的总时长
        float clipTime = time - (i > 0 ? list[i - 1].delay + list[i - 1].duration : 0);

        if (list[i].GetValue(clipStart, clipTime, ref value))
        {
            return true;  // 动画还在进行中
        }
    }
    return false;  // 所有Clip都已结束
}
```

**关键设计理解**：

1. **多Clip串联**：同一组参数可以有多个Clip，第二个Clip的起始值=第一个Clip的终点，实现多段复杂动画
2. **时间偏移**：每个Clip有独立的delay和duration，串联时后一个Clip的时间需要减去前序Clip的总时长
3. **14组参数并行**：所有参数在同一帧内同时计算，互不干扰，最终一起写入Transform
4. **hasValueChanged**：只有当至少有一个参数还在变化时才返回true，全部结束后才停止播放

---

## 3. AE风格的参数化动画系统

### 3.1 14个可配置参数

`AECameraAnimationScriptableObject`是动画配置文件，包含14组参数：


| 参数类型                                          | 控制内容      | 对应节点                     |
| --------------------------------------------- | --------- | ------------------------ |
| `fieldOfView`                                 | FOV角度     | Main Camera              |
| `orthographicSize`                            | 正交模式尺寸    | Main Camera              |
| `horizontalRotation`                          | 水平旋转      | CameraRoot.rotation.y    |
| `tiltAngle`                                   | 倾斜角度      | CameraRoot.rotation.x    |
| `lensPushPull`                                | 推拉距离      | Main Camera.position.z   |
| `lensOffsetX/Y`                               | 镜头左右/上下偏移 | Main Camera.position.x/y |
| `verticalSway/horizontalSway`                 | 相机自身摇摆    | Main Camera.rotation     |
| `verticalMove/horizontalMove/forbackwardMove` | 整体位移      | CameraRoot.position      |
| `horizontalLensShift/verticalLensShift`       | 画面平移      | Main Camera.lensShift    |


### 3.2 核心设计思路

以上4点（多Clip串联、时间偏移、14组并行、hasValueChanged）确保了动画系统能够完整还原AE中的多关键帧、多曲线、依次执行的复杂相机运动效果。

---

## 4. 数据流全景

```
档位/车速变化
    ↓
CameraStateController.状态判断
    ↓
CameraAnimationManager.Play("Park"/"General"/"PdcOverlook"...)
    ↓
CameraAnimationPlayer.LateUpdate()
    ├── 读取AECameraAnimationScriptableObject配置
    ├── 按时间应用各参数（delay/duration/curve）
    ├── 像素→Unity单位转换
    └── 写入Camera.transform / CameraRoot.transform
```

---

## 5. 总结

这套模块的本质是：**用AE的思维做Unity的相机动画**——让习惯AE操作、不熟悉Unity组件系统的美术设计师，也能独立完成符合预期的复杂相机运动设计。后续，还会再介绍特殊美术要求下的Curve生成工具。

