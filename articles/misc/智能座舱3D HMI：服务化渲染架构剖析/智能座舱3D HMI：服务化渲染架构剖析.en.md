---
title: "Smart-Cockpit 3D HMI: Dissecting the Service-Based Rendering Architecture"
lang: en
date: 2026-06-01
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> In smart-cockpit HMI designs, 3D-rendered visuals often serve as part of individual applications — for the car-model desktop, the 3D view is the background; for vehicle settings, the 3D view might be a side-view animation of the car. Meanwhile, the system's native development handles the flat UI and the basic services. Given this industry situation, exposing 3D rendering as an independent service has gradually become the standard approach for smart-cockpit HMI.

Based on what I learned in previous work, this post tries to understand the technical design of service-based rendering, organize the relevant technical background, and dissect **how a frame travels from generation to on-screen display**.

## 1. Process Overview

A 3D frame goes through four stages from engine rendering to final display:

*[Figures omitted; see the original WeChat article]*

**① Engine rendering**: The engine performs GPU rendering in a Service process and outputs a frame. In the traditional model, the engine renders to the Activity's Window Surface; in service-based rendering there is no Activity, so the engine must render onto a Surface passed in by the client. That Surface's cross-process capability is the cornerstone of the whole design.

**② Cross-process transfer via BufferQueue**: Beneath the Surface sits a BufferQueue. The engine puts finished frames into the queue via `queueBuffer`, and the client takes them out via `acquireBuffer`. Both processes operate on the same BufferQueue, and frame data travels over shared memory with zero copies.

**③ System compositing**: SurfaceFlinger, Android's compositor, combines the Surface Layers of the various apps and outputs the result. If the frames need to cross domains to the QNX instrument cluster, SurfaceFlinger composites them into a VirtualDisplay, and they travel over the LVDS hardware link to QNX.

**④ Client View display**: The client View holds the consumer side of the Surface and displays each received frame on screen.

---

## 2. The Rendering Target

### 2.1 Surface

In service-based rendering, the engine runs in a separate Service process with no Activity and no Window. **The engine must render onto a target that does not depend on a Window**, then deliver that target's frames to the client. That target is a **Surface** — not the one bundled with an Activity Window, but one passed over from the client via Binder.

A Surface is not an in-process object. Android's Surface maps to a cross-process BufferQueue underneath: the producer side lives in the Service process (the 3D engine writes frame data), and the consumer side lives in the client process (the app reads frame data). Both processes operate on the same BufferQueue; frame data is passed through shared memory, with no pixel copies needed.

After obtaining the client's Surface, the engine creates an EGLSurface on it via EGL (`eglCreateWindowSurface`) and renders normally. To the engine, this Surface is fundamentally no different from an ordinary Window Surface — it just doesn't live in a Window of the local process.

### 2.2 BufferQueue

BufferQueue is the core data structure of the Android graphics system, managing the rotating exchange of a set of graphic buffers (GraphicBuffers). Every Surface has a BufferQueue behind it.

By default there are three buffers. The three buffers sit in three states — "engine writing", "waiting to be consumed", "client reading" — ensuring the producer and the consumer never fight over the same buffer. Triple buffering covers the pipeline of one frame while keeping GPU memory usage modest.

### 2.3 Cross-Process Zero-Copy: Binder + Shared Memory

The producer interface of BufferQueue, `IGraphicBufferProducer`, is a Binder object. When the client creates a Surface, it also creates the BufferQueue and a Binder reference to its producer side. The client passes that Binder reference to the Service via AIDL, so the Service ends up holding the producer side of the same BufferQueue. From then on, all frame data travels through shared memory. The two processes map the same physical memory: the writer renders into it, and the reader takes frames from it.

---

## 3. The 3D Engine

The engine must handle Surface creation, destruction, and switching, and perform the corresponding GPU state rebuild. This is the most critical interface of the engine adaptation layer in service-based rendering.

### 3.1 Unity: displayChanged + nativeRecreateGfxState

Unity exposes the `displayChanged` interface through `UnityPlayer`, allowing external code to switch the rendering target Surface:

```java
public boolean updateGLDisplay(int index, Surface surface) {
    return updateDisplayInternal(index, surface);
}

private boolean updateDisplayInternal(int index, Surface surface) {
    // Rebuild the GPU state on Unity's main thread
    if (surface == null) {
        m_MainThread.surfaceLost(runnable);  // Notify the main thread that the Surface is lost
    } else {
        m_MainThread.surfaceAcquired(runnable);  // Notify the main thread that the Surface is ready
    }
    // Internally, runnable calls UnityPlayer.this.nativeRecreateGfxState(index, surface);
}
```

*[Figures omitted; see the original WeChat article]*

`nativeRecreateGfxState` is Unity's JNI native method; it notifies the C++ layer to rebuild the GPU rendering state, including rebinding the render target. The process runs on Unity's render thread, protected by ANR_TIMEOUT.

The `index` parameter: Unity supports multiple displays (`Display.displays`), where index=0 is the main display. Surface switching for the main display must execute synchronously on the main thread (surfaceLost/surfaceAcquired); non-main displays can execute directly on the calling thread.

### 3.2 Unreal: NativeActivity + nativeSetWindowInfo

Unreal's Android entry point is `GameActivity`, which extends `NativeActivity` and implements `SurfaceHolder.Callback2`. Surface lifecycle management follows Android's standard `surfaceCreated/surfaceChanged/surfaceDestroyed` callbacks:

```java
// Sketch code, only for understanding the key behaviors
public class GameActivity extends NativeActivity 
    implements SurfaceHolder.Callback2, ... {

    private SurfaceView MySurfaceView;

    // Creates the SurfaceView at init time
    void initSurfaceView() {
        getWindow().takeSurface(null);
        MySurfaceView = new SurfaceView(this);
        MySurfaceView.getHolder().addCallback(this);
        containerLayout.addView(MySurfaceView);
    }

    // Notifies the C++ layer when the Surface size changes
    public void surfaceChanged(SurfaceHolder holder, int fmt, int w, int h) {
        nativeSetSurfaceViewInfo(
            holder.getSurfaceFrame().width(),
            holder.getSurfaceFrame().height());
    }

    // Key native methods
    public native void nativeSetWindowInfo(
        boolean bIsPortrait, int DepthBufferPreference, int PropagateAlpha);
    public native void nativeSetSurfaceViewInfo(int width, int height);
}
```

Unity's `displayChanged` is a proactive interface for switching the Surface, callable from outside;

Unreal's Surface binding passively follows the Activity lifecycle, with no Java-level API exposed for proactively switching the Surface. This means implementing service-based rendering on Unreal requires injecting the client's Surface inside the `surfaceChanged` callback, or modifying the NativeWindow source of `FAndroidWindow` directly at the C++ layer. Analyzing this further requires access to the ASIS plugin.

*[Figures omitted; see the original WeChat article]*

---

## 4. Cross-OS Display Output

What I've worked with is mostly Qualcomm-based solutions. The cockpit is a dual-OS environment: the center stack runs Android, and the instrument cluster runs QNX. The engine Service runs on the Android side, but the frames may need to be output simultaneously to the Android center-stack screen and to the QNX instrument cluster. Android and QNX are two independent operating systems — there is no Binder, and no interop between Screen windows.

**Actual architecture**: In mass-production cockpits, Android runs inside a virtual machine on top of QNX. QNX acts as the Hypervisor, managing all hardware resources including the GPU and the display outputs. Cross-OS transfer of 3D frames relies on **VirtualDisplay + the LVDS hardware link**.

On the Android side, a virtual display is created via `DisplayManager.createVirtualDisplay()` — the same standard Framework API used by phone screen recording. The key flag `VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY` ensures only app content is cast, not the system status bar or the navigation bar. SurfaceFlinger composites the app-rendered frames onto this VirtualDisplay, and the Display HAL routes the frames to the LVDS hardware link.

**LVDS** (Low Voltage Differential Signaling) is the physical display channel QNX provides for the Android virtual display. A VirtualDisplay is purely a software abstraction, but its frame output is wired by the Display HAL to the LVDS hardware channel. QNX Screen reads the frames delivered over LVDS on the application side, composites them with QNX-native windows (instrument cluster, ADAS views, etc.), and outputs the result to the physical screen.

## 5. The Client View

Everything above covered frame production and transport: how the engine renders, how the BufferQueue rotates, how the Surface crosses processes, and how cross-domain delivery works. But the last link of the whole chain is **how the client View displays the frames**.

On Android, two kinds of Views consume Surface frames: SurfaceView and TextureView.

### 5.1 SurfaceView

SurfaceView punches a "hole" in the View tree — it does not participate in the app's View compositing; instead it creates an independent Window with its own Surface. SurfaceFlinger composites this Window's Surface independently of the app's other Layers.

```
SurfaceFlinger compositing:
├── App Window (title bar, buttons, and other 2D UI)
└── SurfaceView Window (3D rendered frames)  ← independent Layer
```

**Advantage**: 3D frames don't go through the app's Hardware Layer compositing; SurfaceFlinger composites the independent Layer directly. For 3D content that changes every frame, this means no app-side redraws are triggered per frame.

**Cost**: No support for rotation, scaling, or alpha transforms. Its position in the View tree only determines the position and size of the "hole"; the 3D view itself cannot participate in View animations.

### 5.2 TextureView

TextureView consumes frames through an internal SurfaceTexture, which updates each frame into a GL texture; the texture then participates in compositing as part of the app's Hardware Layer.

```
SurfaceFlinger compositing:
└── App Window
    ├── Title bar, buttons, and other 2D UI
    └── TextureView (3D rendered frames as a Hardware Layer texture)
```

**Advantage**: TextureView is an ordinary View and supports rotation, scaling, alpha, and rounded corners. If the 3D view needs to be embedded in a scrollable, animatable UI layout, TextureView is one option.

**Cost**: Every frame update triggers a Hardware Layer redraw. In complex layouts, the extra compositing overhead can cause frame drops. Performance-wise, SurfaceTexture itself also adds one more processing step to the BufferQueue pipeline: the engine renders a frame to the Surface → SurfaceTexture takes the frame from the BufferQueue → the frame is updated into the Hardware Layer as a texture → SurfaceFlinger composites.

### 5.3 Choosing Between Them

In **cockpit** development, the 3D car-model desktop and the 3D instrument cluster are usually full-screen or near-full-screen scenarios, where SurfaceView's performance advantage is obvious and no View transforms are needed. If you need rounded corners, scaling, and similar effects, TextureView is an option.

The more practical approach is for the service-based rendering SDK to support both, letting the client choose per scenario.

---

## 6. Closing

Back to the four stages from the beginning:

**① Engine rendering**: The engine renders in a Service process onto the Surface passed in by the client. The Surface can cross processes because it maps to a BufferQueue underneath; the two processes operate on the same queue through a Binder reference and shared memory. The engine perceives Surface switches and rebuilds GPU state via `displayChanged`/`nativeRecreateGfxState` (Unity) or `surfaceChanged`/`nativeSetWindowInfo` (Unreal).

**② Cross-process transfer via BufferQueue**: BufferQueue's producer-consumer rotation drives the frame flow. Triple buffering by default: the producer takes a free buffer via `dequeueBuffer` and submits the rendered frame via `queueBuffer`; the consumer takes a ready frame via `acquireBuffer` and returns it via `releaseBuffer`. Cross-process zero-copy relies on Binder-passed references + shared memory.

**③ System compositing**: Within Android, the standard SurfaceFlinger path is used. If the frames need to cross to QNX, SurfaceFlinger composites them onto the virtual display created by `createVirtualDisplay`; the Display HAL routes them to the LVDS hardware link; QNX Screen reads them and composites them with native windows for output.

**④ Client View display**: The client View holds the consumer side of the Surface, and display happens after SurfaceFlinger finishes compositing. The Surface's lifecycle is driven by the client Activity/View and synchronized both ways with the engine side. When the client Surface is created/destroyed, the Service is notified via AIDL; upon receiving a destruction notice, the engine stops rendering immediately. Black frames/black screens can occur during Surface switching, so the consumer side should keep a copy of the last frame's texture to avoid the flash-to-black problem.

---

In the next post, we'll target the engineering implementation of URAS: how the client integrates, how data flows, and how the SDK is packaged in a cockpit project.
