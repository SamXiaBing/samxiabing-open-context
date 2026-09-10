---
title: "Doing Unity Camera Animation with an Adobe After Effects Mindset: A Camera Motion Module in 3D HMI Practice"
date: 2026-05-18
series: misc
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> When you develop HMI applications with a 3D engine, you inevitably have to think about the design of a camera motion module. After all, there is both the need to show different viewpoints for different driving states, and the need to change viewpoints through touch interaction. This article only covers the former, describing one design approach — an approach that has certain advantages in collaboration cost and in how faithfully it reproduces the intended visuals.

3D engines generally come with their own camera management tools/plugins, such as Unity's Cinemachine. I've also taken part in a production vehicle project that used Cinemachine to implement camera animations. Cinemachine is powerful, but in engineering practice you can run into two problems:

1. **The professional background of our artist colleagues**: not every 3D artist we work with has spent years deep in the game industry. They are not TAs (technical artists) who have long been used to tweaking effects inside the engine — they are artists more familiar with tools like Adobe After Effects or Premiere. You run into this fairly often at automotive companies. So it's hard to get artist colleagues to accept and become proficient with Cinemachine/Sequencer.
2. **The result doesn't match expectations**: in a previous job, I ran into a case where Cinemachine could not reproduce the desired shot-transition effect. Of course, I can't rule out that my own insufficient familiarity with Cinemachine contributed: when switching from one viewpoint to another, the camera had to look comfortable, and the artists' requirement was that the camera should always follow an orbiting trajectory, changing distance, angle, and so on along the expected curves while orbiting. However, Cinemachine sometimes produced sudden trajectory/orientation jumps mid-motion, and it doesn't support adjusting the change curve of each fine-grained parameter individually.

So, targeting the "push/pull/pan/track" shot language that artist colleagues are familiar with, we **wrote our own camera module that simulates AE parameters**. Artists configure animations in the mindset they know best — how much FOV, how much push/pull, how much left/right offset — and tune them in their own development tools. On the development side, we simply copy the parameters over.

---

## 1. Camera Node Hierarchy

### 1.1 Three-Layer Node Design

```
Center (at the ego vehicle's center — the focal point of the observed subject)
└── Root (handles horizontal rotation + tilt + overall displacement, similar to Unreal's spring arm)
    └── Main Camera (handles push/pull + offset + the camera's own rotation; the main camera body)
```

This is the original three-layer structure of the camera system, where each layer handles only its own business:


| Node              | Controlled Parameters                              | Corresponding AE Parameters |
| ----------------- | -------------------------------------------------- | --------------------------- |
| **Root**          | Horizontal rotation, tilt angle, overall displacement | Camera displacement      |
| **Main Camera**   | Push/pull, left-right/up-down offset, camera's own rotation | Lens parameters    |


### 1.2 Design Benefits

- Rotating CameraRoot does **not** affect Main Camera's localPosition
- Main Camera's push/pull is a simple Z-axis translation, with clear physical meaning

---

## 2. Camera Script Design

*[Figures omitted; see the original WeChat article]*

### 2.1 Scripts Included

```
CameraStateController              → State machine: decides the current viewpoint based on gear/speed
CameraAnimationManager             → Animation manager: plays animations from ScriptableObjects
CameraAnimationPlayer              → Animation driver: applies animation parameters to the camera every frame
AECameraAnimationScriptableObject  → The animation config itself: a list of Clips for the 14 parameter groups
AECameraParamClip                  → Parameter clip base class: contains delay/duration/curve/endValue
AECameraPositionClip               → Position clip: AE pixels → Unity meters conversion
AECameraRotationClip               → Rotation clip: supports shortest-path angle interpolation
AECameraFOVClip / AECameraSizeClip → FOV / orthographic size clips
AECameraLensShiftClip              → Lens shift clip
```

### 2.2 CameraStateController: The State Machine

The core of CameraStateController is automatically switching viewpoints based on **vehicle state**. The following is illustrative code.

```csharp
// Gear + driving state → viewpoint enum
switch (_carInfoModel.GearState.Value)
{
    case EnumData.GearState.D:
    case EnumData.GearState.R:
        switch (_carInfoModel.MoveStatus.Value)
        {
            case EnumData.MoveStatus.GENERAL:
                cameraStatus = CameraStatusEnum.General;  // driving viewpoint
                break;
            case EnumData.MoveStatus.HIGH_SPEED:
                cameraStatus = CameraStatusEnum.HighSpeed; // high-speed viewpoint
                break;
            case EnumData.MoveStatus.PDC:
                cameraStatus = CameraStatusEnum.Pdc; // PDC overhead view
                break;
            // ...
        }
        break;
    case EnumData.GearState.P:
        cameraStatus = CameraStatusEnum.Park; // parking viewpoint
        break;
}
CameraAnimationManager.Instance.Play(cameraStatus, false, allowGesture);
```

It is also responsible for **automatically resetting the viewpoint**: when the user hasn't interacted for a while, it slowly returns to the default viewpoint for the current gear.

### 2.3 CameraAnimationManager: The Animation Manager

A singleton that manages playback of all viewpoint animations. It supports switching between multiple **camera states**, both **interruptible animations** and **non-interruptible ones, and provides animation event listening**. The following is illustrative code.

```csharp
public void Play(string cameraStatusEnum, bool immediateComplete = false, bool allowGesture = false)
{
    // allowGesture=true means gestures may interrupt the animation while it is playing
    _allowGesture = allowGesture;
    CameraAnimationPlayer.Play(anim, immediateComplete);
}
```

### 2.4 CameraAnimationPlayer: The Animation Player

It manages the actual execution of the animations driven by AECameraAnimationScriptableObject, updating every frame in `LateUpdate`:

```csharp
private void LateUpdate()
{
    if (isPlaying && _curPlayingAnimation != null)
    {
        if (_curPlayingAnimation.UpdateCamera(_camera, _animTime))
            _animTime += Time.deltaTime;  // animation not finished yet, accumulate time
        else
        {
            isPlaying = false;
            OnCompleted?.Invoke();  // animation completed callback
        }
    }
}
```

### 2.5 AECameraAnimationScriptableObject: The Core Configuration Script

This is the **most critical** script — it stores the 14 groups of animation parameters in the form of a ScriptableObject, with each group composed of multiple Clips. The following is illustrative code.

```csharp
/// <summary>
/// The animation config itself: stores the Clip lists for the 14 parameter groups
/// </summary>
[CreateAssetMenu(menuName = "Camera/AECameraMotion")]
public class AECameraAnimationScriptableObject : ScriptableObject
{
    // 14 parameter groups, each a List<Clip>, supporting multi-segment animations

    // Lens FOV
    public List<AECameraFOVClip> fieldOfView;

    // Orthographic mode size
    public List<AECameraSizeClip> orthographicSize;

    // Horizontal rotation (Root.rotation.y)
    public List<AECameraRotationClip> horizontalRotation;

    // Tilt angle (Root.rotation.x)
    public List<AECameraRotationClip> tiltAngle;

    // Lens push/pull (MainCamera.position.z)
    public List<AECameraPositionClip> lensPushPull;

    // Lens left/right / up/down offset (MainCamera.position.x/y)
    public List<AECameraPositionClip> lensOffsetX;
    public List<AECameraPositionClip> lensOffsetY;

    // The camera's own sway (MainCamera.rotation)
    public List<AECameraRotationClip> verticalSway;
    public List<AECameraRotationClip> horizontalSway;

    // Overall displacement (Root.position)
    public List<AECameraPositionClip> verticalMove;
    public List<AECameraPositionClip> horizontalMove;
    public List<AECameraPositionClip> forbackwardMove;

    // Frame translation (MainCamera.lensShift)
    public List<AECameraLensShiftClip> horizontalLensShift;
    public List<AECameraLensShiftClip> verticalLensShift;
}
```

#### 2.5.1 Initialization and Parameter Reading

```csharp
/// <summary>
/// Animation initialization: records the camera parameters before playback as the start values
/// </summary>
/// <param name="camera">The current Unity Camera object</param>
public void InitCameraParam(Camera camera);

/// <summary>
/// Drives animation playback: updates the camera's parameters based on time
/// </summary>
/// <param name="camera">The current Unity Camera object</param>
/// <param name="time">The current animation time</param>
/// <returns>Whether the animation is still running</returns>
public bool UpdateCamera(Camera camera, float time);

/// <summary>
/// Gets the list of parameters where the animation finally settles
/// </summary>
/// <returns>A list of the 14 end values</returns>
public List<float> GetLastValue();

/// <summary>
/// Gets the camera Root's final rotation angles (XY)
/// </summary>
/// <returns>Vector2(final tilt angle, final horizontal rotation angle)</returns>
public Vector2 GetCameraRootEndEulerXY();
```

#### 2.5.2 Dynamically Modifying Animation End Points

```csharp
/// <summary>
/// Sets the end value of the push/pull distance (adjustable at runtime, for scenarios like AVP where the distance is computed dynamically)
/// </summary>
/// <param name="value">The push/pull value (Unity meters)</param>
public void SetLensPushPull(float value);

/// <summary>
/// Sets the end value of the tilt angle
/// </summary>
/// <param name="value">Root.rotation.x</param>
public void SetTiltAngle(float value);

/// <summary>
/// Sets the end value of the horizontal rotation
/// </summary>
/// <param name="value">Root.rotation.y</param>
public void SetHorizontalRotation(float value);

/// <summary>
/// Sets the end value of the vertical sway
/// </summary>
/// <param name="value">MainCamera.rotation.x</param>
public void SetVerticalSway(float value);

/// <summary>
/// Sets the end value of the horizontal sway
/// </summary>
/// <param name="value">MainCamera.rotation.y</param>
public void SetHorizontalSway(float value);

/// <summary>
/// Sets the end value of the lens shift X-axis offset
/// </summary>
/// <param name="offset">LensShift.x</param>
public void SetLensShiftOffsetX(float offset);

/// <summary>
/// Sets the end value of the lens shift Y-axis offset
/// </summary>
/// <param name="offset">LensShift.y</param>
public void SetLensShiftOffsetY(float offset);
```

#### 2.5.3 Writing the Configuration

```csharp
/// <summary>
/// Sets the animation end point from the current Unity camera state (used to "copy the current position into the animation config")
/// </summary>
/// <param name="camera">The current Unity Camera object</param>
public void SetView(Camera camera);

/// <summary>
/// Copies end values from another animation config (used to "reset to another viewpoint's end point")
/// </summary>
/// <param name="source">The source animation config</param>
public void SetView(AECameraAnimationScriptableObject source);

/// <summary>
/// Sets the animation end points parameter by parameter (the 14-parameter version)
/// </summary>
public void SetView(float fov, float size, float hRot, float tilt,
    float len, float lenX, float lenY,
    float vSway, float hSway,
    float vMove, float hMove, float fbMove,
    float hLensShift, float vLensShift);
```

### 2.6 AECameraParamClip: The Parameter Clip Base Class

Every animation parameter (FOV, position, rotation, etc.) is composed of multiple `Clips`, supporting the splicing of multi-segment animations. The following is illustrative code.

```csharp
/// <summary>
/// Parameter clip base class: defines the time behavior of a single animation clip
/// </summary>
[Serializable]
public class AECameraParamClip
{
    public float delay;           // how long to wait before starting (seconds)
    public float duration;        // duration (seconds)
    public AnimationCurve curve;  // easing curve
    public float endValue;        // end value (in AE pixel units)

    /// <summary>
    /// Gets the interpolated result at the current moment
    /// </summary>
    /// <param name="startValue">The start value (Unity units)</param>
    /// <param name="timePoint">The current animation time (seconds)</param>
    /// <param name="output">The current interpolation output</param>
    /// <returns>Whether the animation is still running</returns>
    public virtual bool GetValue(float startValue, float timePoint, ref float output)
    {
        if (timePoint <= delay)
            return true;  // still in the delay, not started
        else if (timePoint > (delay + duration))
        {
            output = GetUnityEndValue();  // finished, return the end value
            return false;
        }
        else
        {
            // Compute the time progress percentage
            float timePercentage = Mathf.Abs((timePoint - delay) / duration);
            // Use the AnimationCurve to compute the value progress percentage
            float valuePercentage = curve.Evaluate(timePercentage);
            // Start value + progress * (end - start)
            output = valuePercentage * (GetUnityEndValue() - startValue) + startValue;
            return true;
        }
    }

    /// <summary>Gets the end value (AE pixels)</summary>
    public virtual float GetEndValue() => endValue;

    /// <summary>Gets the end value in Unity units (may involve a pixels→meters conversion)</summary>
    public virtual float GetUnityEndValue() => endValue;

    /// <summary>Sets the end value (AE pixels)</summary>
    public virtual void SetEndValue(float value) => endValue = value;

    /// <summary>Sets the end value in Unity units (requires a reverse conversion to AE pixels)</summary>
    public virtual void SetUnityEndValue(float value) => endValue = value;
}
```

**Special handling in derived classes**:


| Derived Class           | Special Handling                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------- |
| `AECameraPositionClip`  | Pixels→meters conversion (debugging pinned the factor at 378); overrides `GetUnityEndValue`/`SetUnityEndValue` |
| `AECameraRotationClip`  | Shortest-path angle interpolation; overrides `GetValue` to solve the 0°/360° boundary problem |
| `AECameraFOVClip`       | No special handling; uses Unity values directly                                              |
| `AECameraSizeClip`      | No special handling; uses Unity values directly                                              |
| `AECameraLensShiftClip` | No special handling; uses Unity values directly                                              |


### 2.7 The Complete Execution Logic of UpdateCamera

`UpdateCamera` is the core of the driver. It iterates over the 14 parameter groups, calls `UpdateAnimationList` for each group to compute the current value, and finally writes everything into the camera's Transform. The following is illustrative code.

```csharp
/// <summary>
/// Drives animation playback: updates the camera's parameters based on time
/// </summary>
/// <param name="camera">The current Unity Camera object</param>
/// <param name="time">The current animation time</param>
/// <returns>Whether the animation is still running</returns>
public bool UpdateCamera(Camera camera, float time)
{
    bool hasValueChanged = false;

    // 1. Update FOV
    if (UpdateAnimationList(fieldOfView, time, _cameraFOVStart, ref _cameraFOV))
        hasValueChanged = true;
    camera.fieldOfView = _cameraFOV;

    // 2. Update orthographic size
    if (UpdateAnimationList(orthographicSize, time, _cameraSizeStart, ref _cameraSize))
        hasValueChanged = true;
    camera.orthographicSize = _cameraSize;

    // 3. Update CameraRoot rotation (horizontal + tilt)
    if (UpdateAnimationList(horizontalRotation, time, _cameraRootRotYStart, ref _cameraRootRotY))
        hasValueChanged = true;
    if (UpdateAnimationList(tiltAngle, time, _cameraRootRotXStart, ref _cameraRootRotX))
        hasValueChanged = true;

    // 4. Update MainCamera position (push/pull + offset)
    if (UpdateAnimationList(lensPushPull, time, _cameraPosZStart, ref _cameraPosZ))
        hasValueChanged = true;
    if (UpdateAnimationList(lensOffsetX, time, _cameraPosXStart, ref _cameraPosX))
        hasValueChanged = true;
    if (UpdateAnimationList(lensOffsetY, time, _cameraPosYStart, ref _cameraPosY))
        hasValueChanged = true;

    // 5. Update MainCamera rotation (vertical sway + horizontal sway)
    if (UpdateAnimationList(verticalSway, time, _cameraRotXStart, ref _cameraRotX))
        hasValueChanged = true;
    if (UpdateAnimationList(horizontalSway, time, _cameraRotYStart, ref _cameraRotY))
        hasValueChanged = true;

    // 6. Update CameraRoot position (overall displacement)
    if (UpdateAnimationList(verticalMove, time, _cameraRootPosYStart, ref _cameraRootPosY))
        hasValueChanged = true;
    if (UpdateAnimationList(horizontalMove, time, _cameraRootPosXStart, ref _cameraRootPosX))
        hasValueChanged = true;
    if (UpdateAnimationList(forbackwardMove, time, _cameraRootPosZStart, ref _cameraRootPosZ))
        hasValueChanged = true;

    // 7. Update lens shift
    if (UpdateAnimationList(horizontalLensShift, time, _cameraLensShiftXStart, ref _cameraLensShiftX))
        hasValueChanged = true;
    if (UpdateAnimationList(verticalLensShift, time, _cameraLensShiftYStart, ref _cameraLensShiftY))
        hasValueChanged = true;

    // 8. Write into the camera Transform
    UpdateCameraRootLocalEuler(_cameraRootRotX, _cameraRootRotY, 0);
    UpdateCameraRootTransLocalPos(_cameraRootPosX, _cameraRootPosY, _cameraRootPosZ);
    UpdateCameraMainLocalEuler(_cameraRotX, _cameraRotY, 0);
    UpdateCameraMainTransLocalPos(_cameraPosX, _cameraPosY, _cameraPosZ);

    return hasValueChanged;
}

/// <summary>
/// Updates a single parameter list (supports chaining multiple Clips)
/// </summary>
private bool UpdateAnimationList<T>(List<T> list, float time, float start, ref float value)
    where T : AECameraParamClip
{
    if (list.Count == 0)
        return false;

    for (int i = 0; i < list.Count; i++)
    {
        // Each Clip's start value is the previous Clip's end (chained animation)
        float clipStart = i == 0 ? start : list[i - 1].GetUnityEndValue();
        // The Clip's local time = total time - the total duration of the preceding Clips
        float clipTime = time - (i > 0 ? list[i - 1].delay + list[i - 1].duration : 0);

        if (list[i].GetValue(clipStart, clipTime, ref value))
        {
            return true;  // animation still in progress
        }
    }
    return false;  // all Clips have finished
}
```

**Key design points to understand**:

1. **Chained multi-Clip**: the same parameter group can hold multiple Clips; the second Clip's start value equals the first Clip's end value, enabling complex multi-segment animations
2. **Time offset**: each Clip has its own independent delay and duration; when chained, the later Clip's time must subtract the total duration of the preceding Clips
3. **14 parameter groups in parallel**: all parameters are computed simultaneously within the same frame without interfering with each other, and are written to the Transform together at the end
4. **hasValueChanged**: it returns true only while at least one parameter is still changing; playback stops only after everything has finished

---

## 3. An AE-Style Parameterized Animation System

### 3.1 The 14 Configurable Parameters

`AECameraAnimationScriptableObject` is the animation configuration file, containing 14 parameter groups:


| Parameter                                     | Controlled Content                        | Corresponding Node       |
| --------------------------------------------- | ----------------------------------------- | ------------------------ |
| `fieldOfView`                                 | FOV angle                                 | Main Camera              |
| `orthographicSize`                            | Orthographic mode size                    | Main Camera              |
| `horizontalRotation`                          | Horizontal rotation                       | CameraRoot.rotation.y    |
| `tiltAngle`                                   | Tilt angle                                | CameraRoot.rotation.x    |
| `lensPushPull`                                | Push/pull distance                        | Main Camera.position.z   |
| `lensOffsetX/Y`                               | Lens left/right / up/down offset          | Main Camera.position.x/y |
| `verticalSway/horizontalSway`                 | The camera's own sway                     | Main Camera.rotation     |
| `verticalMove/horizontalMove/forbackwardMove` | Overall displacement                      | CameraRoot.position      |
| `horizontalLensShift/verticalLensShift`       | Frame translation                         | Main Camera.lensShift    |


### 3.2 The Core Design Ideas

These four points (chained multi-Clips, time offsets, 14 groups in parallel, hasValueChanged) ensure that the animation system can fully reproduce the complex camera motion effects from AE — multiple keyframes, multiple curves, executed in sequence.

---

## 4. The Data Flow at a Glance

```
Gear / speed change
    ↓
CameraStateController. State decision
    ↓
CameraAnimationManager.Play("Park"/"General"/"PdcOverlook"...)
    ↓
CameraAnimationPlayer.LateUpdate()
    ├── Reads the AECameraAnimationScriptableObject config
    ├── Applies each parameter over time (delay/duration/curve)
    ├── Converts pixels → Unity units
    └── Writes into Camera.transform / CameraRoot.transform
```

---

## 5. Summary

The essence of this module is: **doing Unity camera animation with an AE mindset** — it lets art designers who are used to AE and unfamiliar with Unity's component system independently complete complex camera motion designs that match expectations. In a follow-up post, I'll also introduce the Curve generation tool built for special art requirements.
