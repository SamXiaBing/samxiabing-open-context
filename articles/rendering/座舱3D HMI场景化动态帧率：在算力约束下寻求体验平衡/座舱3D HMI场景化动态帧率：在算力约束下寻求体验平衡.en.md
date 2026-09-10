---
title: "Scenario-Based Dynamic Frame Rate for Cockpit 3D HMI: Seeking the Experience Balance Under Compute Constraints"
date: 2026-06-22
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> Dynamic Frame Rate is the ability to adjust the rendering frame rate in real time according to the application's current state and interaction events. Simply put: "fast when it should be fast, slow when it should be slow." Keep a high frame rate in scenarios that need a fluid experience (dragging, animations, transitions), and proactively drop the frame rate in idle or low-priority scenarios (background, AVM enabled), instead of locking to one fixed frame rate cap.

Vehicle 3D HMI applications (such as the 3D car model launcher) stay resident in the system for long periods, sharing the compute of the same board with multiple other applications — other 3D apps or high-performance consumers like navigation and voice. From a performance-optimization standpoint, 3D applications are one of the fearsome performance-load beasts. If you keep letting them run at full frame rate, it is a huge waste of CPU and GPU resources, because much of the time a 3D application's view is not the interaction focus.

So the core purpose of dynamic frame rate is **saving performance**, and the benefits include:

- **Free up compute for other applications**: when SR rendering, map navigation, and voice recognition run simultaneously, if the 3D Launcher is in the background but still needs to keep its signal updates going, it should proactively drop its frame rate, avoiding mutual contention that would make the scenarios that truly need fluidity stutter instead.
- **A better perceived experience**: users only need a high frame rate during short windows like touch and camera animations. After a few seconds of stillness, the naked eye can barely tell 30 fps from 60. Spend the saved compute where users actually need it, and the overall experience actually improves.

---

## 1. Designing the Dynamic Frame Rate Module

### 1.1 Implementation

Controlling the frame rate itself is fairly simple:

In Unity, you set the target frame rate through the `Application.targetFrameRate` property.

In Unreal Engine, you can set it with `GEngine->SetMaxFPS(60);`.

A dynamic frame rate manager would typically consider designing the following interfaces:


| Interface              | Parameters         | Description                                                |
| ---------------------- | ------------------ | ---------------------------------------------------------- |
| `RequestHighFrameRate` | `string requester` | Request a high frame rate; pass in the requester's identifier |
| `ReleaseHighFrameRate` | `string requester` | Release the high frame rate request; the idle timer starts  |
| `SetFrameRateDirectly` | `int frameRate`    | Set the frame rate directly (for special scenarios like AVM) |
| `GetCurrentFrameRate`  | -                  | Get the current frame rate                                  |


Illustrative code:

```csharp
public class DynamicFrameRateManager : SingletonMono<DynamicFrameRateManager>
{
    // Configuration parameters
    [SerializeField] private int _highFrameRate = 60;      // high frame rate during interaction
    [SerializeField] private int _lowFrameRate = 30;       // low frame rate when idle
    [SerializeField] private float _idleThreshold = 5f;    // idle detection threshold (seconds)

    // State variables
    private float _idleTimer = 0f;
    private bool _isHighPriorityMode = false;

    // Core interfaces
    public void RequestHighFrameRate(string requester)
    {
        if (!_isHighPriorityMode)
        {
            _isHighPriorityMode = true;
            _idleTimer = 0f;
            Application.targetFrameRate = _highFrameRate;
        }
    }

    public void ReleaseHighFrameRate(string requester)
    {
        // Reset the timer, waiting to re-enter the idle state
        _idleTimer = 0f;
    }

    // Per-frame update
    private void Update()
    {
        if (_isHighPriorityMode)
        {
            _idleTimer += Time.deltaTime;
            if (_idleTimer >= _idleThreshold)
            {
                _isHighPriorityMode = false;
                Application.targetFrameRate = _lowFrameRate;
            }
        }
    }
}
```

---

## 2. Frame Rate Strategies per Scenario

During delivery, differentiated frame rate strategies are drawn up based on the characteristics of each business scenario and the results of performance testing. Here are some common scenarios I'd like to share:

### 2.1 Launcher 3D Car Model Desktop / Vehicle Control Scenario


| State          | Frame Rate | Trigger                  | Applicability Analysis                                |
| -------------- | ---------- | ------------------------ | ----------------------------------------------------- |
| **Interacting**| 45 or 50 fps | User touches the screen | The user is actively operating; needs a fluid response |
| **Idle**       | 25 or 30 fps | No touch for 5 seconds  | Viewing the car model at rest; at 30 fps there is no visible difference |


**Rationale**: the Launcher is the first screen users see after entering the system, and it mostly sits still displaying the car model. A 60/30 configuration strikes a balance between fluidity and power consumption.

### 2.2 SR Application + AVM (Surround View) Scenario


| State       | Frame Rate | Applicability Analysis                                                                     |
| ----------- | ---------- | ------------------------------------------------------------------------------------------ |
| **AVM on**  | 20 fps     | If AVM's stitching algorithm runs on the Android side, the pressure is heavy; 3D may need to give up part of its performance budget to guarantee basic fluidity |
| **AVM off** | 30 fps     | Revert to SR's default frame rate                                                           |


**Rationale**: when AVM pops up, it is a higher safety-critical view whose frame rate must be guaranteed. If the AVM is stitched within the application, the performance pressure is heavy, so SR needs to drop to around 20 fps to satisfy the fluidity of the surround view in parking scenarios.

### 2.3 3D Application in the Background


| State                        | Frame Rate | Trigger                   | Applicability Analysis                                            |
| ---------------------------- | ---------- | ------------------------- | ----------------------------------------------------------------- |
| **App goes to background**   | 3 fps      | Android lifecycle onPause | Almost stops rendering, keeps signal handling alive, releases compute. |
| **App returns to foreground**| 45 or 50 fps | Android lifecycle onResume | Restore the frame rate to guarantee the experience              |


**Rationale**: 3 fps in the background is a "basically not occupying the GPU but still alive" configuration — it can respond to necessary state updates while consuming almost no compute. Note that without service-based rendering capability, this one may not be achievable: after OnStop, UnityPlayer completely enters a state with no Surface to render to and suspends the main thread and the render thread. When the app returns to the foreground, the Android side usually needs to use the last frame captured when it went to the background as a mask, giving 3D time to resume rendering and finish pulling and processing messages from the message thread.

---

## 3. Typical Bug Case Analysis

### 3.1 Bug #1: Returning to Foreground, Frame Rate Not Restored

**Symptom**:  
The user reported that after switching back from a navigation app to the 3D Launcher, sliding the car model clearly stuttered, and the frame rate stayed in single digits for several seconds before recovering. QA filed it as "screen stutter".

**Root cause**:  
When the app switches to the background, the Android side sends an "app has gone to background" signal, at which point the frame rate manager is set to an extremely low value to free GPU compute. But in the `OnApplicationPause(false)` callback, AndroidListener's restore handling is empty:

```csharp
// AndroidListener.cs — real code
void OnApplicationPause(bool pause)
{
    Debug.Log($"on application pause: {pause}");
    // only logs; does no frame rate restoration at all
}
```

Frame rate restoration relies entirely on `SetFrameRate`, called every frame in `LauncherScene.Update()`. But if the scene's Update was suspended while in the background (for example, rebuilding scene assets, or the framework-level state machine jump getting stuck), it can only recover on the first frame after returning to the foreground — and that time window is exactly where problems easily get caught.

**Solution**:  
Explicitly restore the frame rate in `OnApplicationPause(false)`, giving the scene's Update a clear starting point:

```csharp
void OnApplicationPause(bool pause)
{
    if (!pause)
    {
        // Back to foreground: restore the current scene's target frame rate
        // -1 means let the system choose automatically, until SetFrameRate in Update takes over
        Application.targetFrameRate = -1;
    }
}
```

`targetFrameRate = -1` makes Unity reset to its default frame rate strategy, and on the next frame `SetFrameRate` will set the correct value according to the state.

**Lesson learned**: **lifecycle events (going to background / returning to foreground / scene switches) also need fallback restoration**. Callbacks like `OnApplicationPause` are the last line of defense.

---

### 3.2 Bug #2: Frequent Frame Rate Switching Causes Stuttering

**Symptom**:  
When the integrated driving-parking desktop and AVM (surround view) coexist, the frame rate jumps rapidly (30 → 20 → 60 → 20 → 30), and the UI feels stuttery.

**Root cause**:  
The frame rate control logic had **no unified executor**. Two systems were each writing `Application.targetFrameRate` on their own:

- `LauncherScene.SetFrameRate()`: checks interaction every frame, flipping back and forth between 30/60
- `AndroidListener.AVMStatusChanged()`: directly sets 20 when AVM turns on, 30 when it turns off

The two control paths overwrite each other:

1. AVM turns on → `targetFrameRate = 20`
2. The Launcher's Update runs → `CheckForInteraction()` returns true → `targetFrameRate = 60`
3. AVM turns off → `targetFrameRate = 30`

**Frame rate jumping** — which can manifest as screen stutter.

**Solution**:  
Introduce a unified frame rate manager; all frame rate changes go through the same executor, and no business code writes `Application.targetFrameRate` directly:

```csharp
public class DynamicFrameRateManager : MonoBehaviour
{
    private int _pendingFrameRate = -1;
    private int _currentFrameRate = -1;

    public void RequestFrameRate(int target, string source, int priority)
    {
        // Record all requests, take the highest priority value
        _pendingFrameRate = CalculateHighestPriorityRate();

        // Debounce: don't re-apply when the difference is below the threshold
        if (Mathf.Abs(_currentFrameRate - _pendingFrameRate) < 2)
            return;

        _currentFrameRate = _pendingFrameRate;
        Application.targetFrameRate = _currentFrameRate;
    }
}
```

After the refactor, requests are sent through `DynamicFrameRateManager.RequestFrameRate()`. The manager handles deduplication, debouncing, and priority arbitration.

**Lesson learned**: `Application.targetFrameRate` is a global state, and nothing anywhere should write it directly. All frame rate changes must go through a unified executor; otherwise, multi-path concurrent overwrites are only a matter of time.

---

## Closing Words

Dynamic frame rate is the product of seeking balance under a triple constraint: limited compute, multiple coexisting applications, and short interaction windows. It replaces the global 60 fps scheme with "fast when fast is needed, slow when slow is enough". As vehicle hardware evolves, SoC compute will keep getting stronger, but the value of dynamic frame rate won't disappear. On the contrary, as features grow richer and applications multiply, the competition for compute may only get fiercer.

Future dynamic frame rate systems may evolve to become smarter — for example, dynamically adjusting the frame rate budget according to real-time load, hooking frame rate control into the whole system's scheduling system, negotiating based on data from multiple applications, and achieving a global optimum.
