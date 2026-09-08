---
title: "智能座舱3D HMI：设计服务化渲染-引擎端"
date: 2026-06-04
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇文章讲过了服务化渲染在设计上，在 Android 端的基本框架，其中`EngineBridge` 作为引擎适配层的统一接口。但是写到这里是不完整的，因为引擎如果给你Surface的注册和切换接口，那服务化渲染就成功大半，但是如果引擎不给你， `EngineBridge.registerSurface` 这一调用在引擎端就没有真实实现了。

本文从 **EngineBridge 往下**，尝试介绍我所了解的引擎native层适配逻辑：包括 Unity / 团结引擎 现成的调用链，为 Unreal 实现的服务化渲染插件，以及我对 Godot 的不成熟理解。

---

## 一、Unity / 团结

团结引擎自带的URAS能力，从源码上看，应该是在UnityPlayer的基础上做了扩展，但最终到接近native层后，走的都是 `updateDisplayInternal`→`nativeRecreateGfxState` 流程。

### 1.1 共同的：updateDisplayInternal → nativeRecreateGfxState

无论是U还是T，都得走 GPU 状态重建逻辑：

```
updateDisplayInternal(displayIndex, surface)     ← 主屏/副屏分支
  └→ nativeRecreateGfxState(displayIndex, surface)   ← native 方法，GPU 状态重建
```

`updateDisplayInternal`：主屏和非主屏的线程策略不同。非主屏直接在调用线程执行；主屏必须投递到引擎主线程执行（`m_MainThread`），因为 GPU 状态重建涉及引擎内部状态，线程不安全。

`nativeRecreateGfxState`：native 方法，销毁旧 EGLSurface / Framebuffer，创建指向新 Surface 的渲染目标。无论主屏还是非主屏，最终都走到这里，真正的 GPU 重建发生在这一个 native 调用里。

### 1.2 Unity：displayChanged 路径

标准 Unity 的 Surface 切换入口是 `displayChanged`——`UnityPlayer` 的公开方法：

```
registerSurface(displayIndex, surface)          ← EngineBridge 调用
  └→ UnityPlayer.displayChanged(displayIndex, surface)    ← Java 公开方法
       └→ updateDisplayInternal(displayIndex, surface)    ← 主屏/副屏分支
            └→ nativeRecreateGfxState(displayIndex, surface)   ← GPU 状态重建
```

### 1.3 团结（URAS）：updateUrasGLDisplay 路径

团结在 `UnityPlayer` 上扩展了一个私有方法 `updateUrasGLDisplay`，而这个在Global版本的 Unity 的 `UnityPlayer.java` 中不存在。这是团结面向渲染服务化的专用入口：

```
registerSurface(displayIndex, surface)          ← EngineBridge 调用
  └→ TuanjieViewManager → UnityPlayer.updateUrasGLDisplay(displayIndex, surface)  ← Tuanjie 私有扩展
       └→ updateDisplayInternal(displayIndex, surface)    ← 主屏/副屏分支
            └→ nativeRecreateGfxState(displayIndex, surface)   ← GPU 状态重建
```

### 1.4 EngineBridge 适配

**global版本的Unity 适配：**


| EngineBridge 方法                                | Unity API                                                       |
| ---------------------------------------------- | --------------------------------------------------------------- |
| `registerSurface(displayIndex, surface, w, h)` | `displayChanged(displayIndex, surface)`                         |
| `unregisterSurface(displayIndex)`              | `displayChanged(displayIndex, null)`                            |
| `updateSurfaceSize(displayIndex, w, h)`        | `displayChanged(displayIndex, surface)` + `nativeSetResolution` |
| `sendMessage(obj, method, str)`                | `UnityPlayer.UnitySendMessage(obj, method, str)`                |
| `pauseEngine()`                                | `UnityPlayer.pause()`                                           |
| `resumeEngine()`                               | `UnityPlayer.resume()`                                          |


> Tuanjie就没必要接了，可以直接用URAS

---

## 二、Unreal 5

服务化渲染如果遇到了Unreal，且需要自己实现，会比 Unity 复杂。

因为Unity 有 nativeRecreateGfxState 这种暴露 Surface 和 DisplayIndex 的方法；Unreal 的java代码中，我没看到有。所以需要自己做一些改造。

> Unreal 中国 提供的技术支持服务包可以附带 AndroidSingleInstanceService插件。

在 Unreal 上实现服务化渲染，我之前做的是 **主相机**（MainView）的 Surface 注入 + **其他机位** 做场景截图实现的。


| displayIndex | 场景   | 做法                                  |
| ------------ | ---- | ----------------------------------- |
| `0`          | 主摄像机 | 改引擎取窗口的入口，让 RHI 直接画到 Client Surface |
| `>0`         | 其他相机 | `ARASCapturer` 捕获 + GPU Blit 线程     |


### 2.1 主相机

目的就是改 `GAndroidWindowOverride`，让 RHI 画到客户端注册的 Surface。

Unreal的Android部分，引擎每一帧渲染时，Android 平台层会调用 `FAndroidWindow::GetHardwareWindow_EventThread()`，拿到 Activity *里* `SurfaceView` *对应的* `ANativeWindow` ，RHI 再对它做 EGL 处理。也就是说`GetHardwareWindow` 返回什么，画面就出现在什么上面。

#### 修改

在引擎 `AndroidWindow.cpp` 里增加全局量，并在取窗口处加一层判断：

```cpp
// AndroidWindow.cpp — 引擎补丁新增
void* GAndroidWindowOverride = nullptr;
int GSurfaceViewWidth = -1;
int GSurfaceViewHeight = -1;

void* FAndroidWindow::GetHardwareWindow_EventThread() {
    if (GAndroidWindowOverride != nullptr) {
        return GAndroidWindowOverride;
    }
    return NativeWindow;  // 未覆盖时，行为与原版一致
}
```

Client 注册主相机的 Surface 时，我们的代码中把`Surface` 转成 `ANativeWindow*` 写进 `GAndroidWindowOverride`；从下一帧起`GetHardwareWindow` 返回的就是 Client 的窗口，和 Unity `displayChanged` 的目的一样，换掉Surface。

```cpp
// 以下为示意代码。
JNI_METHOD void nativeSetSurfaceOverride(
    JNIEnv* env, jclass, jobject surface, jint width, jint height)
{
    ANativeWindow* newWindow = surface
        ? ANativeWindow_fromSurface(env, surface) : nullptr;
    ANativeWindow* oldWindow = (ANativeWindow*)GAndroidWindowOverride;

    GAndroidWindowOverride = newWindow;
    GSurfaceViewWidth = width;
    GSurfaceViewHeight = height;

    // 旧窗口可能仍被渲染线程使用，延迟到 RenderCommand 里 release
    if (oldWindow && oldWindow != newWindow) {
        ANativeWindow_acquire(oldWindow);
        ENQUEUE_RENDER_COMMAND(ReleasePrev)(
            [oldWindow](FRHICommandListImmediate&) {
                ANativeWindow_release(oldWindow);
            });
    }

    // 副屏 Blit 需要与主 EGL Context 共享纹理，此处缓存主 Context
    ENQUEUE_RENDER_COMMAND(CacheEGL)([](FRHICommandListImmediate&) {
        RASCapturer_CacheEGLShareContextFromRenderThread();
    });

    FAppEventManager::GetInstance()->EnqueueAppEvent(
        APP_EVENT_STATE_WINDOW_CHANGED);
}
```

### 2.2 多视图：`ARASCapturer` 

`GAndroidWindowOverride` 全局只有一份，主 RHI 每帧只有一个 swap 目标*。*多视图的其他相机往往是场景里的*另一台* `Camera`*，*需要同时输出到另一块** Client Surface。

我的方案是让 ARASCapturer 作为一个 Actor 跑在关卡中，每个 `cameraId`（对应 `displayIndex > 0`）一个实例。核心组件：

- `USceneCaptureComponent2D`：绑定场景里指定 Camera，每帧把场景渲染到纹理。
- `UTextureRenderTarget2D`：GPU 上的离屏纹理，主渲染线程写入。

一头通过ENQUEUE_RENDER_COMMAND，将捕获的纹理，通过Blit拷贝到当前的 ANativeWindow。

另一头通过新增`nativeBindCamera(cameraId, surface)` 当java端调用这个native jni方法的时候，在引擎的游戏线程这边会找到*对应的 Capturer，把 Client 的* `Surface` *转成* `ANativeWindow`交给 `Capturer` 内部的`FEGLBlitState` 管理。

在这里无法展示示意代码，权当了解一个思路：**渲染线程把场景截图进 RT；Blit 线程把 RT 抄到 Client Surface 并 swap。**

*[配图见公众号原文]*

### 2.3 EngineBridge 适配一览


| EngineBridge 方法                      | Unreal ASIS 对应                                                                |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| `registerSurface(0, surface, w, h)`  | `nativeSetSurfaceOverride` + `nativeAppCommand(INIT_WINDOW)`                  |
| `registerSurface(>0, surface, w, h)` | `nativeBindCamera(cameraId, surface)`                                         |
| `unregisterSurface(0)`               | 缓存 EGL + `nativeSetSurfaceOverride(null, 0, 0)`                               |
| `unregisterSurface(>0)`              | `nativeUnBindCamera(cameraId)`                                                |
| `updateSurfaceSize(idx, w, h)`       | MainView: 再次 `nativeSetSurfaceOverride` / MultiView: `Capturer.SetWindowSize` |
| `pauseEngine()`                      | `nativeAppCommand(APP_CMD_PAUSE)`                                             |
| `resumeEngine()`                     | `nativeAppCommand(RESUME)` + `INIT_WINDOW`                                    |


---

## 三、Godot

目前还处于方案推演阶段，没有在实际项目中落地实施过，以下所有设计思路都只是基于理论层面的了解：

- 核心模块RenderingServer提供了完全独立于场景树的底层渲染API，开发者可以用纯代码驱动整个渲染流程，不需要绑定固定的场景节点，可能可以用来做服务化渲染；
- viewport_create()搭配viewport_set_use_own_render_target()可以创建独立的离屏Viewport，支持把场景渲染到不直接显示的渲染目标中，这应该会是RAS实现多路输出的核心前提；
- 同时Godot也提供了非公开JNI方法GodotLib.newcontext(Surface)，支持运行时替换渲染Surface，可用作切换入口。

目前评估需要补充的是离屏渲染的能力、外部注入窗口以及多视图输出。

---

## 结语

服务化渲染自行实现，除了可以帮助我们加深 3D 与系统适配的理解，还有最重要的目标：**为实现引擎的平台化做好准备**。

> 当然，引擎的平台化目前并不是主流的需求，大多数情况下，一个研发团队选定了一款引擎，随着车型迭代就很难再换。

理想中，渲染服务化本身是可以跨系统平台、跨引擎工具的：在实现了一套 3D 服务化渲染管理服务的基础上，实现 `EngineBridge` 的一些标准接口来兼容不同的 3D 引擎，同时，服务化本身又支持将画面进行跨系统投射，无论是仪表，还是CSD，或是同DHU内的其他屏幕，它都能够集中化地进行渲染管理。

em~~~ 想想就很优秀。