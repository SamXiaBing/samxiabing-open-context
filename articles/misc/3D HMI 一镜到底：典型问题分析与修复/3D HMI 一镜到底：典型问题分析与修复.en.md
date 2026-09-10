---
title: "3D HMI One-Take Transitions: Typical Problems and Fixes"
date: 2026-06-17
series: misc
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In cockpit 3D projects, a one-take transition is not just a camera animation — it also involves the Android window system, rendering service timing, and lifecycles. So there are always some nasty bugs that look utterly baffling at first glance. This article shares some of the problems that appeared in a previous solution.

This article focuses on the 3D rendering and Android adaptation part of the **center display**, assuming the approach of a **rendering service** + **Android mask Window** as described in the article [3D HMI Cross-App One-Take Transitions: Frame-to-Frame Visual Handoff](https://mp.weixin.qq.com/s/VBmmUXH0a2aartjLReozOA). Problems are grouped into five categories: black screens, stutter/frame jumps, performance, concurrency, and miscellany.

---

## 1. Black Screen Problems

A black screen is the most severe failure of a one-take transition. Whether or not it can recover, it gets top-priority handling as a bug. On the center display, one-take black screens are most likely the combination of two problems: **the mask was withdrawn too early, or the new rendering source hasn't produced its first frame yet**.

### Problem: Mask Window Withdrawn Too Early — Intermittent Black Screen from Desktop→SR

**Background**: as mentioned in the previous article, SystemUI prepares an **Android mask Window** to fill the gap during a switch. The normal sequence is: mask Window covers the screen first → the target SR rendering service completes its first frame → the Unity camera animation reaches its target → `TransitionComplete` notifies Android → the mask fades out. If any completion signal arrives before the visuals are ready, the user sees a black screen. The 3D side, as a fallback, prepares a **LoadingMask** (application layer) to guard against these black screens:

- The originating app's RT failed to be created, or its release ordering is wrong → frozen-frame black
- The mask window has faded out but the target app's first frame hasn't arrived → gap black
- The camera's targetTexture broke but the RawImage hasn't been closed yet → empty-texture black

**Symptom**: during a cross-app one-take from Desktop→SR, the center display **occasionally** goes black for about 200–800ms, then the SR visuals appear normally. The reproduction rate varies with the pacing of user operations; rapid consecutive switches make it more likely. It wasn't reproducible on demand, so for a while it was misdiagnosed as sporadic frame drops caused by high GPU load.

**Root cause**: the "transition is in handoff state" signal was triggered by **the camera animation on our own side ending**, not by **the counterpart's rendering service having committed its first Surface frame**.

After the desktop side's rendering service receives the one-take signal and starts, the camera first lerps to the intermediate-state camera position, and the completion is triggered the moment the animation ends:

```csharp
// SR camera manager — fires the completion callback as soon as the animation ends
srCameraTransitionCallback += (value) =>
{
  var msg = new TransitionCompleteMessage();
  msg.cameraType = CameraType.SurroundView;
  msg.isIntermediate = IsInIntermediateState();
  // ...
  SendToAndroidSide(bytes);  // Android withdraws the mask Window based on this
};
```

The problem: animation end ≠ the rendering service instance that SR belongs to has already drawn its first valid frame. On low-end chips, or when SR's rendering service has just been reclaimed by the system, getting SR's visuals ready again can take several hundred milliseconds. Once the mask is withdrawn, the desktop Surface is no longer visible on the center display and the SR Surface isn't ready yet — the gap in between is a black screen.

**Fix**: the completion callback adds a check for **the target rendering service being ready**. The camera animation ending only means the Unity-side state machine is in place; it does not mean it's OK to tell Android to withdraw the mask.

**The general pattern**: in cross-process one-take transitions, **animation completion and deliverable visuals are two independent events**. The Unity side can drive a camera animation to completion in a few hundred milliseconds, while the other side's Surface reconstruction and first-frame presentation run on a separate timeline. For every handoff point, deploy clear log prints — with logs you can pin down state changes precisely.

---

## 2. Stutter and Frame-Jump Problems

Stutter means the picture freezes; a frame jump means the picture suddenly changes. Stutter is usually lost callbacks or a deadlocked state; frame jumps are usually the transition's tail frame not being continuous with the target app's first frame.

### Problem: Transition Tail Frame Discontinuous with the Target's First Frame — Mask Fade-Out Too Early

**Symptom**: during a cross-app one-take, the camera animation finishes and the mask Window starts to fade out, revealing the target SR scene. But the first frame shows an obvious jump from the transition's tail frame (camera position, exposure, or scene object states inconsistent). It's more noticeable when performance debt is high.

**Root cause**: when the camera animation completes, the SR side's show/hide switches for scene objects and post-processing Volume switches may not yet have taken effect in the same frame. Once the mask fades out, what's revealed is a half-finished product where the camera has arrived but the scene isn't ready.

**Fix**:

1. Delay the visuals-ready callback until after **scene show/hide + post-processing** complete.
2. Make the mask fade out with a **gradient of ≥250ms**, leaving headroom for the first frame's compositing (the number comes from the median of Activity/Surface readiness delays gathered from logs).

**The general pattern**: cross-system callbacks need some time buffering.

---

## 3. Performance Problems

During a one-take transition, the CPU and GPU are doing scene switching, resource loading/unloading, and multi-screen output — the budget is tight.

### Problem: Full Rendering of the Intermediate State

**Symptom**: during a Desktop→SR one-take, as the camera passes through the intermediate-state position, frame rate plummets from 50fps to below 30fps.

**Root cause**: at the intermediate-state camera position, the weather rendering is complex — rain/snow particles, volumetric fog, ground environment. Meanwhile, the car-model desktop scene's various objects are still being rendered too.

**Fix**: add a transition-state effects configuration: switch the weather to a simplified clear-sky version, and hide the car-model desktop interactive objects.

**The general pattern**: the performance budget during a transition is usually insufficient. Look backward from the transition's perspective: what must be displayed, and what can be downgraded.

---

## 4. Concurrency Problems

Concurrency here means **concurrent requests to the state machine** — the user interrupts, switches back, or switches to a third state before the current switch has completed.

### Problem: Mid-Transition Interruption Across Apps

**Symptom**: a Desktop→SR one-take is in its intermediate state when the user triggers navigation (via soft/hard keys or voice). The camera finishes its transition into SR, but what the user actually wanted was navigation.

**Root cause**: there was already a mechanism designed for this: while the one-take lerps to the intermediate state, it waits 5 seconds for the target app's readiness signal. If the signal never arrives, it times out and falls back to the previous camera position.

```csharp
// Before the fix: on timeout, always fall back to the previous camera position
if (intermediateTime > 5f)
  ForceTransitionTo(lastCameraState);
```

But `lastCameraState` is the camera position from before entering the intermediate state (the desktop), not wherever the user actually wanted to go mid-way (navigation).

**Fix**: record the newly chosen target position as a pending state. If that position exists, jump directly to it.

**The general pattern**: signals from different channels can arrive "simultaneously." The state machine design must account for all kinds of possible conflicts. Both mid-process interruption as described above and possible multi-signal concurrency require the one-take manager to have a filtering and reconciliation mechanism.

---

## 5. Miscellaneous Problems

### Problem: DOTween Accidentally Killing the One-Take Animation

**Symptom**: mid-way through the one-take animation, the camera on the center display suddenly jumps to the wrong position. Reproducible 100% of the time via: enter scene mode → exit → trigger a one-take.

**Root cause**: both the camera return-home animation and the one-take animation are driven by DOTween. When multiple camera controller instances share the same camera reference, a Tweener ID conflict killed the one-take animation by mistake.

**Fix**: change the Tweener's ID to use the controller component's instance name:

### Problem: Pause Logic Freezing the Camera Animation

**Symptom**: after the head unit enters the charging screen, the one-take animation freezes; after exiting charging, the picture jumps straight to the target position. If the mask Window is still showing at that moment, what the user sees is a long still image, then a sudden black flash as it jumps to the destination.

**Root cause**: the charging screen sets `Time.timeScale` to 0, and DOTween and Cinemachine Brain are affected by timeScale by default.

**Fix**: set all camera-related animations and Brain components to ignore timeScale (`.SetUpdate(true)` / `Ignore Time Scale = true`).

**Key awareness**: a one-take transition is a system-level behavior; it shouldn't freeze just because time pauses.

---

## Closing Thoughts

One-take transitions are quite a pain during delivery — a module with a lot of problems. It's the kind of feature where the technical design always feels slightly imperfect, with gaps here and there; it merely met the delivery bar because this is a project, judged by the testing results at this time and place.
