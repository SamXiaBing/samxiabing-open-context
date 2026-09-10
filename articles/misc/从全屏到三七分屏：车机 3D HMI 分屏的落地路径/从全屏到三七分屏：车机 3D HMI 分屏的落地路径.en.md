---
title: "From Full Screen to 30/70 Split Screen: A Practical Path for Split-Screen in IVI 3D HMI"
lang: en
date: 2026-06-18
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> Up to and through 2022, HMI design mockups showed plenty of card-style design elements. As 3D HMI gradually entered the design concepts, card-based layouts and small-window modes were progressively tried out in 3D HMI applications as well. Today, service-based rendering has satisfied almost all card-based and region-based usage needs, so this article starts from the split-screen requirement built on top of that, and sorts out how the system window layer and the 3D rendering layer cooperate.

One current HMI home-screen design philosophy is: **the center display no longer runs just one full-screen app**. Launcher cards, the map, media, and the 3D car model / smart-driving view dynamically divide the width of the same physical screen. For the user it is **one screen, many uses**; for 3D development it means the rendering area changes resolution at runtime.

## 1. Split-Screen Modes

In practice there are usually three layout modes:


| **Mode**                       | **Width-ratio threshold** | **Example resolutions** |
| ------------------------------ | ------------------------- | ----------------------- |
| Full screen                    | > 0.9                     | 1920×1200               |
| ~70% split (not a strict 2/3)  | > 0.5                     | 1272×1200               |
| ~30% split                     | ≤ 0.5                     | 642×1200                |


Across the three resolutions, we cannot share the same set of camera FOV, camera push/pull, or UI alignment — even gesture sensitivity differs. **In business terms, split-screen is not merely a UI layout change; it is an integration problem spanning rendering, camera, gestures, and environmental effects.**

---

## 2. The 3D-Side Implementation

### 2.1 Signal Trigger

Nothing special here: when the Android app detects that the 3D container window is being resized, it passes the new `width` / `height` over JNI/Socket. The 3D side receives it, computes the width ratio, and drives the graphics module to refresh:

```csharp
// Illustrative code
void OnHostWindowSizeChanged(int newWidth, int newHeight)
{
    int physicalWidth = _graphicsConfig.PhysicalScreenWidth;
    float widthRatio = (float)newWidth / physicalWidth;

    _graphicsConfig.ApplyViewportScale(widthRatio, 1f);
}
```

> `physicalWidth` is the physical screen width.
>
> `widthRatio` is what later derives full screen / ~70% split / ~30% split.

### 2.2 Refreshing Resolution and Firing Events

Create a graphics configuration module (`ViewportConfig`) responsible for three things:

1. Updating the internal resolution and scale ratio;
2. **Broadcasting an event: the layout has changed**, so subscribers such as the camera manager, UI manager, and gesture manager update in sync;
3. **Deferring the `Screen.SetResolution` call by one frame**, to avoid same-frame conflicts with the Android Surface resize.

> Within the same frame there is a race between the Android Surface size change and a possible Unity RenderTexture rebuild; if business code reads `Screen.width` immediately, it may still get the old value. Firing the event first and calling `SetResolution` on the next frame lets the camera/UI adjust their logic to the new ratio first, and only then change the pixel size.

A code listing adds nothing here; a step diagram serves better:

![Figure 1](./图1.png)

### 2.3 Layout Modes and Region Position

**Converting the width ratio into a mode enum:** the camera manager (`CameraManager`) converts the ratio into an enum


| Width-ratio threshold | Layout mode | Camera dolly offset                |
| --------------------- | ----------- | ---------------------------------- |
| > 0.9                 | Full screen | 0                                  |
| > 0.5                 | ~70% split  | 0                                  |
| ≤ 0.5                 | ~30% split  | -30 (dolly compensation in narrow windows) |


**Getting the 3D region position (left / right / full screen)** is learned via signals from the Android side:

```csharp
// 0 = full screen, 1 = 3D on the left, 2 = 3D on the right
int region = _hostBridge.QueryLayoutRegion();
_sceneState.LayoutRegion = (LayoutRegion)region;
```

### 2.4 Triggering Business Coordination


| Submodule              | What it does                                                                                                                                                                                                                                                                                 |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Car model camera       | 1. Adjust the dolly/truck/pan/boom camera parameters according to the split mode and split position. 2. Drive the post-split camera animation.                                                                                                                                                |
| Gesture zoom/rotate    | 1. Narrow the zoom range on narrow screens. 2. Attenuate the swipe rate by 1/3 or 1/7. 3. Recompute `PixelsPerInch` after resolution changes.                                                                                                                                                 |
| UI layout              | 1. Modify the Canvas's `CanvasScaler`. 2. Manually adjust key nodes of UI that cannot be simply scaled, to match appropriate offsets/sizes.                                                                                                                                                   |
| Environment rendering  | 1. Disable reflections in the ~30% split, since enabling them yields almost no perceptible benefit. 2. Switch to MSAA in the ~30% split and TAA otherwise, same reasoning. 3. Enable some post-effects several frames late; these post-effects need a stable frame image to guarantee no flicker after processing. |
| Scene transitions      | For some scenes, transitions need a full-screen mask; otherwise you get glitched frames.                                                                                                                                                                                                      |


> Design trait: decoupled from Android's actual pixels via ratio thresholds (0.9 / 0.5); the enum and event design means later business changes only need to care about the abstractions.

---

## 3. The Android Side

### 3.1 Window / Fragment Structure

Unity is typically embedded in the Android app's Fragment: **a FrameLayout container + SurfaceView**. When the Android app changes the split-screen layout, it changes the container's size and position; Unity learns the new width/height through JNI messages.

```java
// Illustration: the Unity container Fragment
public class RenderHostFragment extends Fragment {
    private SurfaceView mRenderSurface;
    private FrameLayout mContainer;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup parent, Bundle state) {
        mContainer = (FrameLayout) inflater.inflate(R.layout.render_host, parent, false);
        mRenderSurface = new SurfaceView(getActivity());
        mContainer.addView(mRenderSurface);
        mRenderSurface.getHolder().setFormat(PixelFormat.TRANSLUCENT);
        return mContainer;
    }
}
```

### 3.2 SurfaceView Characteristics and the Cost of Split-Screen


| Dimension  | SurfaceView (the common choice for in-vehicle 3D)         |
| ---------- | --------------------------------------------------------- |
| Compositing | A separate Surface, layered below ordinary Views          |
| Size change | Buffers often need rebuilding; prone to flicker/black frames |
| Transparency | Can be set TRANSLUCENT, still constrained by the Surface mechanism |


The cost of choosing SurfaceView: a split-screen resize must be accompanied by a mask transition, because buffer rebuilding cannot be made imperceptible. The core flow is: show the mask → resize/reposition the 3D container View → wait for Unity's first valid frame → remove the mask. The mask can be a Bitmap/View matching the home-screen background, or a blurred image related to the 3D app, to reduce the sense of discontinuity.

### 3.3 Can the Window Stay Alive During Resize?

I once saw an official demo at Unite: when a finger dragged a split-screen window to resize it, the 3D view stayed continuous — alive. Since I have never shipped that myself, the following is my speculation about the approach:

- It relies on the URAS service-based rendering capability.
- For the Android app side, what matters is the TextureView's changes — and the system natively supports TextureView scaling in real time following Matrix transforms.
- For the 3D side, there are possibly two ways to handle it:
  - If the interaction allows the rendered view to stay unchanged, keep the original fixed resolution handed to the Android View.
  - If the interaction requires cropping to follow the window, dynamically change the camera's viewport while keeping the resolution unchanged.
  - After the window drag ends, I would probably still add a step based on the current window: reset the resolution. But this step needs testing for black flashes — supposedly TextureView does not have that problem.

---

## 4. A Typical Problem: Black Window During Split-Screen

> On Android, Unity **always** has a `Display.displays[0]` (i.e., `Display.main`); in this project — a car-model home screen with only one SurfaceView — only index=0 is used.
>
> On Android, Unity splits size into two layers:
>
> `systemWidth/Height` is the system size bound to the Surface
>
> `renderingWidth/Height` is the framebuffer size the GPU actually renders
>
> `Screen.SetResolution` mainly updates `Screen.*` and some upper-layer state
>
> `Display.SetRenderingResolution` is the one used on mobile — the path that directly changes the GPU rendering resolution.

### Symptom

Switching from full screen into the ~70% split, the rendering area goes **completely black**.

### Investigation

Logs showed: `Screen.SetResolution` had been called, but `Display.main.renderingWidth/Height` was **not updated**.

### **Root Cause**

In the Android embedded scenario, `Screen.SetResolution` and `Display.renderingWidth/Height` **take two different paths**.

Calling only the former is not enough; you must also call `Display.SetRenderingResolution(0, w, h)` to sync the GPU rendering target (index=0 is the main Display and cannot be omitted on Android).

### Fix

When refreshing the rendering target, **Screen and Display should be used together** (illustrative code):

```csharp
IEnumerator ApplyResolutionNextFrame()
{
    yield return null;

    int w = (int)(_baseWidth * _viewportScaleX);
    int h = (int)(_baseHeight * _viewportScaleY);

    Screen.SetResolution(w, h, true);
    ApplyDisplayRenderSize(0, w, h);  // index=0, main Display; cannot be omitted on Android

    _eventHub.Publish(new ViewportChangedEvent(w, h));
}

void ApplyDisplayRenderSize(int displayIndex, int width, int height)
{
    var display = Display.displays[displayIndex];
    display.Activate();
    display.SetRenderingResolution(width, height);

    Debug.Log($"rendering={display.renderingWidth}x{display.renderingHeight}, " +
              $"system={display.systemWidth}x{display.systemHeight}");
}
```

---

## Conclusion

On Android, Unity's `Screen.SetResolution` and `Display.SetRenderingResolution` have similar names; but this kind of API similarity — with subtly hidden differences — is sometimes a black hole for engineering time. One black-screen bug costs you logging, analysis, and repeated verification, only to find it was just an API misuse or an omission. That time should have been spent on more valuable things.