---
title: "Intelligent Driving SR Development: A Layered Implementation of HMI Camera Interaction"
date: 2026-05-21
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> My previous article, [Cockpit 3D HMI Camera Orbit: Three Mechanisms for Nailing the Slide Feel](https://mp.weixin.qq.com/s/boJ5a-Looy4GV4aQkKzfNw), covered orbit viewing as a baseline capability. But in SR development, to fully satisfy user interaction needs across different SR viewpoints, product and design will most likely ask for more features—for example, orbiting around the car while driving, pulling back to see the entire route in overview mode, or panning the map when picking a floor or a parking spot.

So we need a more comprehensive module that drives camera animation through gestures, one that offers orbit rotation, distance zoom, single-finger pan, two-finger pan, and more, all at once.

---

## 1. Overview

The camera gesture control system uses an **event-driven + strategy pattern** design, realized through the cooperation of the following core components:

*[Figures omitted; see the original WeChat article]*

---

## 2. Capability List

`CamGestureCtrl` defines 5 gesture capabilities via an enum:


| Enum value | Capability | Input method | Applicable scenarios |
| ----------- | ---------- | ---- | ---------- |
| `Orbit` | Orbit rotation (trackball rotation) | Single-finger slide | SR mode, overview mode |
| `Zoom` | Distance zoom (push in / pull out) | Two-finger pinch | All modes |
| `SinglePan` | Single-finger pan | Single-finger slide | Ground overview / navigation selection |
| `DualPan` | Two-finger pan | Two-finger slide | AVP overview mode |


---

## 3. Implementation Details

### 3.1 Orbit Rotation

> **This article won't expand on the detailed implementation of orbit rotation.** The three-layer node structure of the orbit camera, the basic flow of touch input → angular velocity → RotateAround, and the principles and code behind the three feel mechanisms—inertia / upward-swipe damping / downward-swipe bounce-back—are fully described in [Cockpit 3D HMI Camera Orbit: Three Mechanisms for Nailing the Slide Feel](https://mp.weixin.qq.com/s/boJ5a-Looy4GV4aQkKzfNw). I won't repeat them here.

This section only adds what that article didn't cover—**how orbit rotation is integrated into this system in an event-driven way**.

#### 3.1.1 Event-Driven Integration

*[Figures omitted; see the original WeChat article]*

#### 3.1.2 Cooperation with the Animation System

*[Figures omitted; see the original WeChat article]*

### 3.2 Distance Zoom

#### 3.2.1 Logic

Zooming uses a two-finger pinch gesture to move the camera back and forth along its own Z axis, changing the distance between camera and target point. The distance is clamped to the `[minDist, maxDist]` range, and after the fingers lift, an inertia factor keeps it gliding.

#### 3.2.2 Key Code

```csharp
private void OnPinchEvt(object sender, BaseEventArgs args)
{
    var e = args as OnPinchEvt;
    // Convert the pixel delta to unit delta, then scale by 100 as the velocity
    _zoomVel = ScreenUtil.PixelsToUnits(e.ScaleDeltaDelta) * 100;
}

private void TickZoom()
{
    _zoomVel *= _zoomInertia;  // inertia decay
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

> **Note**: the camera's localZ is negative (it faces the target point), hence `-clampedDist`. The zoom direction's sign is determined by the sign of `ScaleDeltaDelta`.

---

### 3.3 Single-Finger Pan

#### 3.3.1 Logic

Single-finger pan converts the finger's on-screen slide delta into camera position offsets along its local X/Y axes. **The key is** that the pan amount is scaled according to the camera's current FOV and distance, so the pan speed feels consistent at different zoom levels.

#### 3.3.2 Key Code

```csharp
private void TickSinglePan()
{
    _singlePanVel *= _panInertia;
    var posX = _camTrans.localPosition.x;
    var posY = _camTrans.localPosition.y;

    // Core: compute the frustum height from FOV and distance, used as the pan scaling factor
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

> **Note**: single-finger pan does **not** update the look-at target, meaning the camera center drifts away from the original gaze point after panning. It's used only in view scenarios such as memory-parking map overview / navigation selection.

---

### 3.4 Two-Finger Pan

#### 3.4.1 Logic

Two-finger pan uses exactly the same displacement algorithm as single-finger pan (also FOV-scaled), but with one difference: **two-finger pan updates the** `_focusTarget` **position in sync**. This guarantees that in the memory-parking mapping-result overview mode, when you keep orbiting after panning, the rotation center stays correct.

#### 3.4.2 Key Code

```csharp
private void TickDualPan()
{
    _dualPanVel *= _panInertia;
    // ... displacement calculation same as SinglePan (omitted) ...

    // ★ Key difference: update the orbit target point in sync
    var worldPos = _camTrans.TransformPoint(
        new Vector3(0, 0, -_camTrans.localPosition.z));
    SetFocusPos(new Vector3(worldPos.x, 0, worldPos.z));
}

```

> **Re-targeting logic**: transform the camera's local coordinate `(0, 0, -localZ)` into world coordinates—that is, the world point "localZ away, directly in front of the camera"—then take its XZ components (Y zeroed) as the new `_focusTarget` position.

---

## 4. Scene-to-Gesture Mapping

Different driving/feature scenarios use different gesture capability sets and parameter combinations:


| Scenario mode | Gesture capabilities | Zoom range | Pan method | Auto reset |
| -------------------------------------------------------------- | ------------------ | ----- | ---- | ---- |
| **SR mode**: General, HighSpeed, CrossWait, PdcOverlook, Park, Neutral | Orbit rotation + two-finger zoom | 9~50 | None | Yes |
| **Memory-parking map overview** | Orbit rotation + two-finger zoom + two-finger pan | 40~dynamic | Two-finger | No |
| **Memory-parking single-floor ground overview** | Single-finger pan + two-finger zoom | 30~80 | Single-finger | No |


> The method **memory-parking AVP** uses to compute viewing parameters from the mapping results will be covered in detail in the next article.

---

## 5. Gesture Event Management

### 5.1 Event Diagrams

Overall relationship diagram:

*[Figures omitted; see the original WeChat article]*

Camera animation states:

*[Figures omitted; see the original WeChat article]*

### 5.2 Conflict and Priority Handling

Setting `_activeGestures` decides which capability executes first, so the same input can drive different behaviors in different modes.

```csharp
// Zoom and single-finger slide are allowed to execute simultaneously (a two-finger pinch may come with sliding)
_pinchGesture.AllowSimultaneousExecution(_singleSlideGesture);

// UI-layer interception: touches on UI-layer objects are not passed to the gesture system
FingerEngine.Instance.CaptureGestureHandler = OnCaptureHandler;
private bool? OnCaptureHandler(GameObject go)
{
    if (go.layer == LayerMask.NameToLayer("UI"))
        return true;  // intercepted, not handled
    return false;     // let it through
}

// Gesture priority: Tap(10) > SingleSlide(9) > Scale(8)
_tapGesture.Priority = 10;
_singleSlideGesture.Priority = 9;
_pinchGesture.Priority = 8;
```

---

## 6. Wrap-Up

This set of mechanisms doesn't depend on Cinemachine. Overall it uses a layered, event-driven architecture combined with a state strategy pattern; it's lightweight in itself and adapts well to the multi-gesture camera interaction needs of different intelligent-driving SR scenarios. For the current business scenarios, it's enough.



&nbsp;
