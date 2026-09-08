---
title: "智能座舱3D HMI：服务化渲染架构剖析"
date: 2026-06-01
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 智能座舱的HMI的设计方案中，3D渲染的画面常常会作为各项应用的一部分，比如对于车模桌面，3D画面的定位是背景；对于车辆设置，3D画面可能是侧方的车辆示意动画。而系统的原生开发会承担平面UI和基础服务的职责。基于这个行业现状，将3D渲染作为独立服务输出能力，逐渐成为了智能座舱HMI的标配方案。

因此本文根据之前工作中所了解的内容，尝试去理解服务化渲染的技术方案，对于相关的技术背景做一个整理，尝试剖析**画面从产生到上屏的过程**。

## 一、流程总览

一帧3D画面从引擎渲染到最终显示，经历四个阶段：

*[配图见公众号原文]*

**① 引擎渲染**：引擎在Service进程中执行GPU渲染，输出一帧画面。传统模式下引擎渲染到Activity的Window Surface，服务化渲染中没有Activity，引擎必须渲染到客户端传来的Surface上。这个Surface的跨进程能力是整个方案的基石。

**② BufferQueue跨进程传递**：Surface底层是BufferQueue，引擎通过`queueBuffer`将渲染完的帧放入队列，客户端通过`acquireBuffer`取出。两个进程操作同一个BufferQueue，帧数据走共享内存零拷贝传输。

**③ 系统合成**：SurfaceFlinger作为Android的合成器，将各App的Surface Layer合成后输出。如果画面需要跨域到QNX仪表盘，SurfaceFlinger将帧合成到VirtualDisplay，经LVDS硬件链路传到QNX。

**④ 客户端View显示**：客户端View持有Surface的消费者端，收到帧后显示到屏幕。

---

## 二、渲染载体

### 2.1 Surface

服务化渲染中，引擎跑在独立Service进程，没有Activity，没有Window。**引擎必须渲染到一个不依赖Window的载体上**，然后把这个载体的画面送到客户端。这个载体就是**Surface** 且不是Activity Window自带的，而是客户端通过Binder传递过来的。

Surface不是一个进程内的对象，Android的Surface底层对应一个跨进程的BufferQueue，生产者端在Service进程（3D引擎写入帧数据），消费者端在客户端进程（App端读取帧数据）。两个进程操作的是同一个BufferQueue，帧数据通过共享内存传递，不需要拷贝像素数据。

引擎拿到客户端的Surface后，通过EGL在其上创建EGLSurface（`eglCreateWindowSurface`），然后正常渲染。对引擎来说，这个Surface和一个普通Window Surface没有本质区别，只是它不在本地进程的Window里。

### 2.2 BufferQueue

BufferQueue是Android图形系统的核心数据结构，管理一组图形缓冲区（GraphicBuffer）的轮转交换。每个Surface背后都有一个BufferQueue。

默认情况下，这个缓冲区有三段缓冲。三个缓冲区分别处于"引擎正在写"、"等待消费"、"客户端正在读"三种状态，确保生产者和消费者不会争抢同一个缓冲区。三段缓冲覆盖一帧的流水线，同时不会占用过多GPU内存。

### 2.3 跨进程零拷贝：Binder + 共享内存

BufferQueue的生产者接口`IGraphicBufferProducer`是一个Binder对象。客户端创建Surface时，同时创建了BufferQueue和其Producer端的Binder引用。客户端把这个Binder引用通过AIDL传给Service，Service端拿到的就是同一个BufferQueue的生产者端。后续所有帧数据通过共享内存传递。两个进程映射同一块物理内存，写入方渲染到这块内存，读取方从这块内存取帧。

---

## 三、3D引擎

引擎需要处理Surface的创建、销毁和切换，并做出相应的GPU状态重建。这是服务化渲染中引擎适配层最核心的接口。

### 3.1 Unity：displayChanged + nativeRecreateGfxState

Unity通过`UnityPlayer`暴露了`displayChanged`接口，允许外部切换渲染目标Surface：

```java
public boolean updateGLDisplay(int index, Surface surface) {
    return updateDisplayInternal(index, surface);
}

private boolean updateDisplayInternal(int index, Surface surface) {
    // 在Unity主线程上执行GPU状态重建
    if (surface == null) {
        m_MainThread.surfaceLost(runnable);  // 通知主线程Surface已丢失
    } else {
        m_MainThread.surfaceAcquired(runnable);  // 通知主线程Surface已就绪
    }
    // runnable 内部调用 UnityPlayer.this.nativeRecreateGfxState(index, surface);
}
```

*[配图见公众号原文]*

`nativeRecreateGfxState`是Unity的JNI native方法，它负责通知C++层重建GPU渲染状态。包括重新绑定渲染目标。这个过程在Unity的渲染线程上执行，有ANR_TIMEOUT保护。

`index`参数：Unity支持多Display（`Display.displays`），index=0是主Display。主Display的Surface切换必须在主线程上同步执行（surfaceLost/surfaceAcquired），非主Display可以直接在调用线程执行。

### 3.2 Unreal：NativeActivity + nativeSetWindowInfo

Unreal的Android入口是`GameActivity`，它继承自`NativeActivity`并实现`SurfaceHolder.Callback2`。Surface的生命周期管理走的是Android标准的`surfaceCreated/surfaceChanged/surfaceDestroyed`回调：

```java
// 示意代码，只用来理解关键行为
public class GameActivity extends NativeActivity 
    implements SurfaceHolder.Callback2, ... {

    private SurfaceView MySurfaceView;

    // 初始化时创建SurfaceView
    void initSurfaceView() {
        getWindow().takeSurface(null);
        MySurfaceView = new SurfaceView(this);
        MySurfaceView.getHolder().addCallback(this);
        containerLayout.addView(MySurfaceView);
    }

    // Surface尺寸变化时通知C++层
    public void surfaceChanged(SurfaceHolder holder, int fmt, int w, int h) {
        nativeSetSurfaceViewInfo(
            holder.getSurfaceFrame().width(),
            holder.getSurfaceFrame().height());
    }

    // 关键native方法
    public native void nativeSetWindowInfo(
        boolean bIsPortrait, int DepthBufferPreference, int PropagateAlpha);
    public native void nativeSetSurfaceViewInfo(int width, int height);
}
```

Unity的`displayChanged`是主动切换Surface的接口，可以由外部调用；

Unreal的Surface绑定是被动跟随Activity生命周期的，没有暴露主动切换Surface的Java层API。这意味着在Unreal上实现服务化渲染，需要在`surfaceChanged`回调中注入来自客户端的Surface，或者直接在C++层修改`FAndroidWindow`的NativeWindow来源。这一部分需要得到ASIS插件才能进一步解析。

*[配图见公众号原文]*

---

## 四、跨系统投屏

之前接触的基本都是高通的方案，座舱是一个双OS并存的环境：中控跑Android，仪表跑QNX。引擎Service跑在Android侧，但画面可能需要同时输出到Android的中控屏和QNX的仪表盘。Android和QNX是两个独立的操作系统，没有Binder、没有Screen Window的互通。

**实际架构**：在量产座舱中，Android是跑在QNX之上的虚拟机里。QNX 作为 Hypervisor管理所有硬件资源，包括GPU和显示输出。跨系统传输3D画面需要依赖**VirtualDisplay + LVDS硬件链路**

Android端通过`DisplayManager.createVirtualDisplay()`创建一个虚拟Display。这和手机录屏用的是同一个标准Framework API。关键标志位`VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY`确保只投应用内容，不投系统状态栏和导航栏。SurfaceFlinger将应用渲染的帧合成到这个VirtualDisplay上，Display HAL把帧路由到LVDS硬件链路。

**LVDS**（Low Voltage Differential Signaling，低压差分信号）是QNX为Android虚拟Display提供的物理显示通道。VirtualDisplay本身是纯软件抽象，但它的帧输出被Display HAL接到了LVDS这条硬件通道上。QNX Screen在应用侧读取LVDS传输的帧，与QNX原生Window（仪表盘、ADAS视图等）合成后输出到物理屏幕。

## 五、客户端View

前面讲的都是帧的生产和传输：引擎怎么渲染、BufferQueue怎么轮转、Surface怎么跨进程、跨域怎么走。然而，全链路的最后一环是**客户端View怎么把帧显示出来**。

Android上消费Surface帧的View有两种：SurfaceView和TextureView。

### 5.1 SurfaceView

SurfaceView在View树中挖了一个"洞"——它不参与App的View合成，而是创建一个独立的Window，拥有自己的Surface。SurfaceFlinger将这个Window的Surface与App的其他Layer独立合成。

```
SurfaceFlinger 合成：
├── App Window（标题栏、按钮等2D UI）
└── SurfaceView Window（3D渲染帧）  ← 独立Layer
```

**优势**：3D帧不需要经过App的Hardware Layer合成，SurfaceFlinger直接合成独立Layer。对于每帧都在变化的3D内容，这意味着不需要每帧触发App侧的重绘。

**代价**：不支持旋转、缩放、alpha变换。它在View树中的位置只是决定"洞"的位置和大小，3D画面本身无法参与View动画。

### 5.2 TextureView

TextureView通过内部的SurfaceTexture消费帧，SurfaceTexture将帧更新为一个GL纹理，然后作为App Hardware Layer的一部分参与合成。

```
SurfaceFlinger 合成：
└── App Window
    ├── 标题栏、按钮等2D UI
    └── TextureView（3D渲染帧作为Hardware Layer纹理）
```

**优势**：TextureView是普通View，支持旋转、缩放、alpha、圆角。如果3D画面需要嵌入到可滚动、可动画的UI布局中，TextureView是一种选择。

**代价**：每帧更新都触发Hardware Layer重绘。在复杂布局下，额外合成开销可能导致掉帧。性能上SurfaceTexture本身也增加了BufferQueue的一个处理步骤：引擎渲染帧到Surface → SurfaceTexture从BufferQueue取出帧 → 作为纹理更新到Hardware Layer → SurfaceFlinger合成。

### 5.3 选型

**座舱**开发中3D车模桌面和3D仪表通常是全屏或近全屏场景，SurfaceView的性能优势明显，且不需要View变换。如果需要圆角、缩放等效果，可以选择TextureView。

更实际的做法是服务化渲染的SDK同时支持两者，让客户端按场景选择。

---

## 六、结语

回到开头的四个阶段：

**① 引擎渲染**：引擎在Service进程中渲染到客户端传来的Surface上。Surface之所以能跨进程，是因为它底层对应BufferQueue，两个进程通过Binder引用和共享内存操作同一个队列。引擎通过`displayChanged`/`nativeRecreateGfxState`（Unity）或`surfaceChanged`/`nativeSetWindowInfo`（Unreal）感知Surface切换并重建GPU状态。

**② BufferQueue跨进程传递**：BufferQueue的生产者-消费者轮转机制驱动帧流转。默认三缓冲，生产者`dequeueBuffer`取空缓冲区、`queueBuffer`提交已渲染帧，消费者`acquireBuffer`取已就绪帧、`releaseBuffer`归还。跨进程零拷贝靠Binder传递引用 + 共享内存。

**③ 系统合成**：Android内走SurfaceFlinger标准路径。如果画面需要跨到QNX，SurfaceFlinger将帧合成到`createVirtualDisplay`创建的虚拟屏，Display HAL路由到LVDS硬件链路，QNX Screen读取后与原生Window合成输出。

**④ 客户端View显示**：客户端View持有Surface的消费者端，SurfaceFlinger合成完成后通知显示。Surface的生命周期由客户端Activity/View驱动，与引擎侧双向同步。客户端Surface创建/销毁时通过AIDL通知Service，引擎收到销毁通知后立即停止渲染。Surface切换期间有可能出现黑帧/黑屏，需要在消费端保留末帧纹理的副本，用来规避闪黑问题。

---

下一篇，我们瞄准URAS的工程实现，讨论URAS在座舱项目里，客户端怎么接入、数据怎么流转、SDK怎么封装。