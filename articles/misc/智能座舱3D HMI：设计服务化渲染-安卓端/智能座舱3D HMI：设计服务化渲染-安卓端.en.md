---
title: "Smart Cockpit 3D HMI: Designing Service-Oriented Rendering — The Android Side"
date: 2026-06-03
series: misc
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In my earlier articles on service-oriented rendering, the first one covered how a Surface gets displayed across processes; the second covered how to enable, integrate, and deliver URAS. But what if you're still on the international build of Unity, or another 3D engine, and want to implement service-oriented rendering yourself? What does designing this architecture from scratch actually require?

This article focuses on **the design of the service-oriented rendering framework itself**: how the client holds a Surface, how the Service side registers views and drives the engine, where the Player/Engine boundary provided by the 3D engine vendor lies, and so on.

---

## Introduction

If you're designing your own RAS, you can start by breaking down the different roles based on your understanding of the service-oriented flow:


| Role | Responsibility | Notes |
| ----------- | ------------------------ | ---------------------- |
| **View** | Client-side UI container that produces the Surface | Doesn't run the engine, doesn't hold .so files |
| **Display** | Logical render target inside the engine (displayIndex) | Implemented inside the 3D engine |
| **Monitor** | Mapping from a logical Display to a physical output | This role is optional; decide based on how many clients run in parallel. |
| **Player** | A player wrapper packaged around the 3D engine | Usually provided by the engine's .so package |
| **Engine** | Native runtime (.so), the engine's actual body | The lowest layer |


---

## 1. Overall Topology

The process model of service-oriented rendering is: **one Service process runs the engine; multiple Client processes consume the frames**.

Whether Unity or Unreal, the Surface is the rendering vehicle passed across processes.

*[Figures omitted; see the original WeChat article]*

- The Client's `RASSurface` obtains the Surface 
-  passes it across processes via `RASClient` to the Service's `ViewRegistry` 
-  which registers it under some `Display` 
- `EngineBridge` calls the engine `Player` 
- and the `Engine` queueBuffers into the Surface.

---

## 2. Client Side

### 2.1 View and Surface

The engine's input/output is a **Surface**, and the Surface comes from the lifecycle callbacks of a `SurfaceView` or `TextureView`.


| Class | Responsibility |
| -------------- | ---------------------------------------------- |
| **RASView** | Container: picks SurfaceView / TextureView, manages layout and Display switching |
| **RASSurface** | Surface lifecycle: syncs creation/destruction/resizes to the Service |
| **RASClient** | Connects to the Service: bind, AIDL proxy, message caching, S2C callbacks |


**RASView** only holds `RASSurface` and responds to UI events.

**RASSurface** is only responsible for notifying the Service when the Surface becomes available, and unregistering when it becomes invalid.

### 2.2 RASView

Sample code:

```java
public class RASView extends FrameLayout {
    public enum ViewType { SurfaceView, TextureView }

    private RASSurface mSurface;
    private int mDisplayIndex = 1;
    private ViewType mViewType = ViewType.TextureView;

    public void init(RASClient client, int displayIndex, ViewType type) {
        mDisplayIndex = displayIndex;
        mViewType = type;
        mSurface = new RASSurface(client, displayIndex, this);
        recreateInnerView(type);
    }

    public void changeDisplay(int newDisplayIndex) {
        mSurface.unregisterFromService();
        mDisplayIndex = newDisplayIndex;
        mSurface.setDisplayIndex(newDisplayIndex);
        mSurface.syncToService();
    }

    public void recreateByType(ViewType type) {
        mSurface.unregisterFromService();
        removeAllViews();
        recreateInnerView(type);
        mSurface.reattachToNewHolder();
    }
}
```

- At the View layer, `displayIndex` is merely a declaration of "which logical engine Display I want to draw into"; the actual registration is completed on the Service side.
- When switching view types, you must `unregister` the old Surface first, then attach the new Holder. Otherwise the Service side holds a reference to an invalid Surface, which shows up as a black screen or an EGL bad surface error.

### 2.3 RASSurface

It implements `SurfaceHolder.Callback` (SurfaceView) or listens to `SurfaceTextureListener` (TextureView), and calls the Service inside the callbacks:

```java
public class RASSurface implements SurfaceHolder.Callback {
    private final RASClient mClient;
    private int mDisplayIndex;
    private int mViewToken;  // View instance identifier, corresponds to URAS's viewHashCode

    void syncToService() {
        Surface surface = obtainValidSurface();
        if (surface == null || !surface.isValid()) return;
        mClient.registerView(mViewToken, mDisplayIndex, surface, mFrameInterval);
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        mClient.unregisterView(mViewToken, mDisplayIndex);
        // Optional: trigger last-frame retention (PersistentSurface)
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int w, int h) {
        mClient.updateResolution(mViewToken, mDisplayIndex, w, h);
    }
}
```

**viewToken**: a single app may contain multiple RASViews (one on the home screen, one on the settings page, for example). The Service side distinguishes them by the combination of `(pkgName, viewToken, displayIndex)`.

### 2.4 RASClient

The client side doesn't need to know about Player and Engine. Its responsibilities are:

1. `ensureStarted()` — start and bind the foreground Service  
2. `registerS2CCallback()` — register the Service→Client callbacks  
3. Forward `RASSurface` register/unregister/update calls as AIDL calls  
4. Cache during disconnects and reconnect

```
/**
 * Client-side bus: binds the Service, holds the C2S proxy, registers S2C, forwards Surface operations.
 * URAS counterpart: TuanjieRenderService
 */
public final class RASClient implements ServiceConnection {
//....
      @Override
    public void onServiceConnected(ComponentName name, IBinder binder) {
        mC2S = IC2SMessenger.Stub.asInterface(binder);
        mC2S.c2sRegisterS2CMessenger(mClientPkg, mS2CStub);  // ① register S2C
        flushPendingCalls();                                // ② flush the cache
        notifyCallbacksConnected();                         // ③ notify RASView it can sync
    }
    public void registerView(int viewToken, int displayIndex, Surface surface, int interval) {
        if (mC2S == null) { enqueue(/* c2sRegisterViewToDisplay */); return; }
        mC2S.c2sRegisterViewToDisplay(mClientPkg, viewToken, displayIndex, surface, interval);
    }
}
```

---

## 3. Service Side

### 3.1 Display


| Concept | Meaning | Created by |
| ------------------- | --------------------------------------- | ---------------------------------------------- |
| **Engine Display** | A logical render target inside the engine; multi-camera rendering is indexed by `displayIndex` | Display 0 (main target) exists when the engine starts; Client registration starts at index ≥ 1 |
| **Android Display** | A physical screen or a VirtualDisplay | System `DisplayManager` |
| **RAS DisplaySlot** | The Service-side registration entry tracking who currently occupies an engine Display | Your `DisplayRegistry` |


 Sketch code for the **DisplaySlot** of this logical Display we create:

```java
/** Service-side state of one logical Display inside the engine */
public class DisplaySlot {
    public final int displayIndex;
    public String ownerPkg;
    public int ownerViewToken;
    public Surface boundSurface;      // may be null (nobody consuming)
    public int frameInterval = 1;
    public IS2CCallback ownerCallback;
}
```

**Relationship between View and Display**:

- A **RASView** (client) declares "I want the picture of displayIndex = 2".
- On receiving the register call, the server-side **ViewRegistry** finds `DisplaySlot(2)` in the **DisplayRegistry** and writes `ownerPkg / ownerViewToken / boundSurface` into it.
- A `displayIndex` has only one owner at any given moment; the rule is that later registration overrides earlier registration, and the earlier owner must be notified.

*[Figures omitted; see the original WeChat article]*

### 3.2 ViewRegistry

`ViewRegistry` is the most core business class on the Service side. Its responsibilities:


| Responsibility | Description |
| ------- | ---------------------------------------------------- |
| Register / unregister | Maintains `(pkg, viewToken, displayIndex) → Surface` |
| Preemption handling | A new registration on the same displayIndex replaces the old owner and sends an S2C notification |
| Death cleanup | `DeathRecipient`: when a Client process crashes, release the DisplaySlot it occupies |
| Serialized entry point | All methods are dispatched by `IPCGateway` to run on the Service's single thread |
| Drive the engine | After a successful registration, call `EngineBridge.registerSurface(...)` |


```java
public class ViewRegistry {
    private final DisplayRegistry mDisplays;
    private final EngineBridge mEngine;

    void registerView(String pkg, int viewToken, int displayIndex,
                      Surface surface, int frameInterval, IS2CCallback s2c) {
        DisplaySlot slot = mDisplays.slotFor(displayIndex);

        if (slot.hasOwner() && !slot.isOwner(pkg, viewToken)) {
            notifyDisplayTakenOver(slot, pkg, viewToken);
        }

        slot.bind(pkg, viewToken, surface, frameInterval, s2c);
        mEngine.registerSurface(displayIndex, surface, /* w, h from slot */);

        s2c.onStartRenderView(viewToken, displayIndex);
    }

    void unregisterView(String pkg, int viewToken, int displayIndex) {
        DisplaySlot slot = mDisplays.slotFor(displayIndex);
        if (!slot.isOwner(pkg, viewToken)) return;

        slot.unbind();
        mEngine.unregisterSurface(displayIndex);
        // Key: detach does NOT pause the engine (see §3.5)
    }
}
```

### 3.3 Monitor

**Monitor isn't mandatory. Scenarios that need a Monitor**: an engine Display must be cast to the passenger screen, the rear screen, or another physical display. In that case, the Monitor maintains the information of that physical screen link.

```java
/** Physical output abstraction—not an engine concept, an HMI deployment concept */
public enum MonitorId {
    MAIN,           // embedded in the center-stack Activity
    COPILOT,        // passenger android.view.Display
    REAR,           // rear seats
    CLUSTER_BRIDGE  // via VirtualDisplay / LVDS to the instrument cluster (§4 of the series' first article)
}

public class MonitorRegistry {
    /** displayIndex → default Monitor; can be overridden by AppView / Presentation */
    void bindDisplayToMonitor(int displayIndex, MonitorId monitor, int androidDisplayId) { ... }
}
```

### 3.4 IPCGateway

`IPCGateway` only does routing, not rendering business:

```java
public class IPCGateway extends IC2S.Stub {
    private final Handler mServiceThread;
    private final ViewRegistry mViews;

    @Override
    public void c2sRegisterViewToDisplay(...) {
        runOrdered(() -> mViews.registerView(...));
    }

    private void runOrdered(Runnable task) {
        if (Looper.myLooper() == mServiceThread.getLooper()) {
            task.run();
        } else {
            mServiceThread.post(task);
        }
    }
}
```

**Serialized calls**: register/unregister, `binderDied`, engine pause/resume—otherwise you may get black flashes.

### 3.5 Lifecycle

> **Surface attach/detach is window rebinding, not the app going to the background.**


| Event | Wrong approach | Correct approach |
| ------------------------- | ---------------- | -------------------------------------- |
| Client unregisters Surface | `Engine.pause()` | Only `unregisterSurface(displayIndex)` |
| Last Client unbinds | Depends on configuration | Pause the engine only when `autoPause=true` |
| Client Activity onPause | Map to engine pause | **Don't map it** (the URAS SDK does nothing on Activity pause) |


In `ViewRegistry.unregisterView`, **don't** pause the entire engine just because one Client switched away—otherwise the other Clients' Displays will stop rendering too.

---

## 4. Player and Engine

*[Figures omitted; see the original WeChat article]*

### 4.1 Understanding the Class Names


| | Player | Engine |
| ------- | ------------------------------------------- | --------------------------------------- |
| **What it is** | The Java/JNI shell provided by the engine vendor | The native runtime (`libunity.so` / `libUnreal.so` etc.) |
| **Maintained as** | The engine JAR (`unity-classes.jar`, UE GameActivity) | The engine SO + your game/scene SOs |


The Player is the engine's Android front desk; the Engine is the render workshop that actually does the work.

### 4.2 EngineBridge

`EngineBridge` is the engine adaptation layer—the seam between the RAS framework and a specific engine.

```java
public interface EngineBridge {
    /** On Service start: engine init requires a Surface; a 1×1 placeholder Surface works */
    void ensureEngineStarted(Surface placeholderSurface);

    /** A Client Surface registered to a given displayIndex */
    void registerSurface(int displayIndex, Surface surface, int width, int height);

    /** A Client Surface unregistered */
    void unregisterSurface(int displayIndex);

    /** Resolution / frame-interval changes */
    void updateSurfaceSize(int displayIndex, int width, int height);
    void setFrameInterval(int displayIndex, int interval);

    /** Business message forwarding (optional) */
    void sendMessage(String objectName, String methodName, String payload);

    /** Global pause/resume (when no Clients exist, or on explicit calls) */
    void pauseEngine();
    void resumeEngine();

    boolean isEngineReady();
}
```

### 4.3 RenderService

`RenderService` is the Service itself on the server side, managing IPCGateway, ViewRegistry, and EngineBridge:

```java
public class RenderService extends Service {
    private IPCGateway mGateway;
    private ViewRegistry mViewRegistry;
    private EngineBridge mEngine;

    @Override
    public void onCreate() {
        startForeground(/* per the head unit's process-kill policy */);
        mEngine = EngineBridgeFactory.create(this);
        mViewRegistry = new ViewRegistry(new DisplayRegistry(), mEngine);
        mGateway = new IPCGateway(mViewRegistry, mEngine);

        Surface placeholder = createPlaceholderSurface(); // 1×1 SurfaceTexture
        mEngine.ensureEngineStarted(placeholder);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return mGateway;
    }
}
```

---

## 5. Project Deployment

Mapped onto concrete project files, the recommended deployment is:

```
your-ras/
├── render-service/          → packaged as engine-service.aar (or a full Service APK)
│   ├── RenderService / IPCGateway / ViewRegistry / EngineBridge
│   ├── Player + lib*.so (engine artifacts)
│   └── AndroidManifest: foreground Service declaration
│
├── render-client-sdk/       → packaged as render-client.aar
│   ├── RASClient / RASView / RASSurface
│   └── AIDL interfaces (sharing the same .aidl files as the Service)
│
└── launcher/                → optional Demo APK
    └── verify bind + single-screen rendering
```

**Deployment modes**:


| Mode | Service | Client |
| ----------- | ---------------------------------------------- | ------------------------------------------------------ |
| **Cross-process (production)** | Standalone APK (e.g. `com.oem.render3d`), system UID or priv-app | The business app depends only on `render-client.aar`; `init(ctx, servicePkg)` |
| **Same-process (debugging)** | Same APK as the app | `render-client` + `render-service` in the same module; |


---

## Closing Thoughts

This article doesn't cover the engine-side part of hooking up the Surface, because different engines currently have different capabilities in their Android code: Unity ships native methods for registering a Surface and a displayIndex, while Unreal has no such interface. As for Godot, I haven't looked into it yet. I plan to write a dedicated article later on the engine side of self-built service-oriented rendering.

