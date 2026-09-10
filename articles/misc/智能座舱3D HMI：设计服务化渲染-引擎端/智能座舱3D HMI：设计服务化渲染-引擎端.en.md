---
title: "Smart Cockpit 3D HMI: Service-Based Rendering — The Engine Side"
lang: en
date: 2026-06-04
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article covered the design of service-based rendering and its basic framework on the Android side, with `EngineBridge` as the unified interface of the engine adaptation layer. But the story was incomplete: if the engine gives you Surface registration and switching APIs, service-based rendering is more than half won — if it doesn't, `EngineBridge.registerSurface` has no real implementation on the engine side.

Starting from **EngineBridge and going down**, this article attempts to describe the engine native-layer adaptation logic as I understand it: the ready-made call chains in Unity / Tuanjie Engine, a service-based rendering plugin implemented for Unreal, and my still-immature understanding of Godot.

---

## 1. Unity / Tuanjie

Tuanjie Engine's built-in URAS capability looks, from the source code, like an extension built on top of UnityPlayer; but once you get close to the native layer, everything goes through the `updateDisplayInternal` → `nativeRecreateGfxState` flow.

### 1.1 The Common Part: updateDisplayInternal → nativeRecreateGfxState

Whether U or T, both have to go through GPU state reconstruction:

```
updateDisplayInternal(displayIndex, surface)     ← main/secondary display branch
  └→ nativeRecreateGfxState(displayIndex, surface)   ← native method, GPU state reconstruction
```

`updateDisplayInternal`: the threading strategy differs between the main display and non-main displays. Non-main displays execute directly on the calling thread; the main display must be posted to the engine's main thread (`m_MainThread`), because GPU state reconstruction touches engine-internal state and isn't thread-safe.

`nativeRecreateGfxState`: a native method that destroys the old EGLSurface / framebuffer and creates render targets pointing at the new Surface. Main display or not, everything ends up here — the real GPU reconstruction happens inside this single native call.

### 1.2 Unity: the displayChanged Path

In standard Unity, the entry point for Surface switching is `displayChanged` — a public method on `UnityPlayer`:

```
registerSurface(displayIndex, surface)          ← called by EngineBridge
  └→ UnityPlayer.displayChanged(displayIndex, surface)    ← public Java method
       └→ updateDisplayInternal(displayIndex, surface)    ← main/secondary display branch
            └→ nativeRecreateGfxState(displayIndex, surface)   ← GPU state reconstruction
```

### 1.3 Tuanjie (URAS): the updateUrasGLDisplay Path

Tuanjie extends `UnityPlayer` with a private method `updateUrasGLDisplay`, which doesn't exist in the global version of Unity's `UnityPlayer.java`. This is Tuanjie's dedicated entry point for rendering service-ization:

```
registerSurface(displayIndex, surface)          ← called by EngineBridge
  └→ TuanjieViewManager → UnityPlayer.updateUrasGLDisplay(displayIndex, surface)  ← Tuanjie private extension
       └→ updateDisplayInternal(displayIndex, surface)    ← main/secondary display branch
            └→ nativeRecreateGfxState(displayIndex, surface)   ← GPU state reconstruction
```

### 1.4 EngineBridge Adaptation

**Global Unity adaptation:**


| EngineBridge method                                | Unity API                                                       |
| ---------------------------------------------- | --------------------------------------------------------------- |
| `registerSurface(displayIndex, surface, w, h)` | `displayChanged(displayIndex, surface)`                         |
| `unregisterSurface(displayIndex)`              | `displayChanged(displayIndex, null)`                            |
| `updateSurfaceSize(displayIndex, w, h)`        | `displayChanged(displayIndex, surface)` + `nativeSetResolution` |
| `sendMessage(obj, method, str)`                | `UnityPlayer.UnitySendMessage(obj, method, str)`                |
| `pauseEngine()`                                | `UnityPlayer.pause()`                                           |
| `resumeEngine()`                               | `UnityPlayer.resume()`                                          |


> For Tuanjie there's no need to adapt it — you can just use URAS directly.

---

## 2. Unreal 5

Service-based rendering on Unreal, when you have to implement it yourself, is more complicated than on Unity.

Unity exposes methods like nativeRecreateGfxState that take a Surface and a DisplayIndex; I couldn't find anything equivalent in Unreal's Java code. So you need to do some modification yourself.

> Epic Games China's technical support service packages can include the AndroidSingleInstanceService plugin.

For service-based rendering on Unreal, what I did before was Surface injection for the **main camera** (MainView) + **scene capture** for the other camera positions.


| displayIndex | Scenario   | Approach                                  |
| ------------ | ---- | ----------------------------------- |
| `0`          | Main camera | Modify the engine's window-fetch entry so the RHI draws directly to the Client Surface |
| `>0`         | Other cameras | `ARASCapturer` capture + GPU blit thread     |


### 2.1 Main Camera

The goal is to modify `GAndroidWindowOverride` so the RHI draws to the client-registered Surface.

In Unreal's Android code, on every rendered frame the Android platform layer calls `FAndroidWindow::GetHardwareWindow_EventThread()` to get the `ANativeWindow` corresponding to the `SurfaceView` *inside* the Activity, and the RHI then does its EGL handling on it. In other words, whatever `GetHardwareWindow` returns is what the image appears on.

#### The Modification

Add globals in the engine's `AndroidWindow.cpp` and add a check where the window is fetched:

```cpp
// AndroidWindow.cpp — added by the engine patch
void* GAndroidWindowOverride = nullptr;
int GSurfaceViewWidth = -1;
int GSurfaceViewHeight = -1;

void* FAndroidWindow::GetHardwareWindow_EventThread() {
    if (GAndroidWindowOverride != nullptr) {
        return GAndroidWindowOverride;
    }
    return NativeWindow;  // when not overridden, behavior matches the original
}
```

When the client registers the main camera's Surface, our code converts the `Surface` into an `ANativeWindow*` and writes it into `GAndroidWindowOverride`; from the next frame on, `GetHardwareWindow` returns the client's window — the same purpose as Unity's `displayChanged`: swapping the Surface.

```cpp
// The following is illustrative code.
JNI_METHOD void nativeSetSurfaceOverride(
    JNIEnv* env, jclass, jobject surface, jint width, jint height)
{
    ANativeWindow* newWindow = surface
        ? ANativeWindow_fromSurface(env, surface) : nullptr;
    ANativeWindow* oldWindow = (ANativeWindow*)GAndroidWindowOverride;

    GAndroidWindowOverride = newWindow;
    GSurfaceViewWidth = width;
    GSurfaceViewHeight = height;

    // The old window may still be in use by the render thread; release is deferred to a render command
    if (oldWindow && oldWindow != newWindow) {
        ANativeWindow_acquire(oldWindow);
        ENQUEUE_RENDER_COMMAND(ReleasePrev)(
            [oldWindow](FRHICommandListImmediate&) {
                ANativeWindow_release(oldWindow);
            });
    }

    // Secondary-display blits need to share textures with the main EGL context; cache the main context here
    ENQUEUE_RENDER_COMMAND(CacheEGL)([](FRHICommandListImmediate&) {
        RASCapturer_CacheEGLShareContextFromRenderThread();
    });

    FAppEventManager::GetInstance()->EnqueueAppEvent(
        APP_EVENT_STATE_WINDOW_CHANGED);
}
```

### 2.2 Multi-View: `ARASCapturer`

There's only one `GAndroidWindowOverride`, and the main RHI has only one swap target per frame. The other cameras in a multi-view setup are usually *another* `Camera` *in the scene*, which needs to output to a different Client Surface at the same time.

My solution is to run ARASCapturer as an Actor in the level, one instance per `cameraId` (corresponding to `displayIndex > 0`). Core components:

- `USceneCaptureComponent2D`: binds to a specified Camera in the scene and renders the scene to a texture every frame.
- `UTextureRenderTarget2D`: an off-screen texture on the GPU, written by the main render thread.

On one end, via ENQUEUE_RENDER_COMMAND, the captured texture is blit-copied to the current ANativeWindow.

On the other end, via the newly added `nativeBindCamera(cameraId, surface)`: when the Java side calls this native JNI method, the engine's game thread finds the corresponding Capturer, converts the client's `Surface` into an `ANativeWindow`, and hands it to the `FEGLBlitState` inside the Capturer to manage.

I can't show illustrative code here, so take this as a way of thinking about it: **the render thread captures the scene into an RT; the blit thread copies the RT onto the Client Surface and swaps.**

*[Figures omitted; see the original WeChat article]*

### 2.3 EngineBridge Adaptation Summary


| EngineBridge method                      | Unreal ASIS equivalent                                                                |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| `registerSurface(0, surface, w, h)`  | `nativeSetSurfaceOverride` + `nativeAppCommand(INIT_WINDOW)`                  |
| `registerSurface(>0, surface, w, h)` | `nativeBindCamera(cameraId, surface)`                                         |
| `unregisterSurface(0)`               | Cache EGL + `nativeSetSurfaceOverride(null, 0, 0)`                               |
| `unregisterSurface(>0)`              | `nativeUnBindCamera(cameraId)`                                                |
| `updateSurfaceSize(idx, w, h)`       | MainView: call `nativeSetSurfaceOverride` again / MultiView: `Capturer.SetWindowSize` |
| `pauseEngine()`                      | `nativeAppCommand(APP_CMD_PAUSE)`                                             |
| `resumeEngine()`                     | `nativeAppCommand(RESUME)` + `INIT_WINDOW`                                    |


---

## 3. Godot

This is still at the design-exploration stage; I've never landed it in an actual project. All of the following design ideas are based purely on theoretical understanding:

- The core RenderingServer module provides low-level rendering APIs fully independent of the scene tree. Developers can drive the entire rendering flow with pure code, without binding to fixed scene nodes — it might be usable for service-based rendering;
- viewport_create() combined with viewport_set_use_own_render_target() can create an independent off-screen Viewport, supporting rendering the scene into a render target that isn't displayed directly — this should be the core prerequisite for RAS-style multi-output;
- Meanwhile, Godot also provides an undocumented JNI method, GodotLib.newcontext(Surface), which supports replacing the rendering Surface at runtime and could serve as the switching entry point.

Current assessment: what still needs to be added is off-screen rendering capability, externally injected windows, and multi-view output.

---

## Closing Thoughts

Implementing service-based rendering yourself not only deepens our understanding of 3D-to-system adaptation; it also serves the most important goal: **getting ready to make the engine a platform**.

> That said, engine platform-ization isn't a mainstream need today. In most cases, once a dev team has picked an engine, it's very hard to switch as vehicle models iterate.

Ideally, rendering service-ization itself could be cross-OS-platform and cross-engine: on top of one 3D service-based rendering management service, you'd implement a set of standard `EngineBridge` interfaces to accommodate different 3D engines; meanwhile, the service itself supports casting the picture across systems — whether it's the instrument cluster, the CSD, or other screens within the same DHU, it can all be managed centrally for rendering.

Ahh~~~ just thinking about it feels great.
