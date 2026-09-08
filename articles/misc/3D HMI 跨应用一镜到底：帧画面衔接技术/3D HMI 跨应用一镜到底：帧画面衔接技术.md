---
title: "3D HMI 跨应用一镜到底：帧画面衔接技术"
date: 2026-06-16
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇[3D HMI 应用内一镜到底：从设计决策到技术落地](https://mp.weixin.qq.com/s/tewpLjb4j5wHd0abxQr4Hw) 将什么是一镜到底，什么是应用内还是应用外做过了分享。并且聚焦在**应用内**的情况展开了我的业务理解和技术方案内容。但正如之前所说，应用内是比较简单的，当今我们在HMI的设计方案中，大概率是要面对跨应用的一镜到底的需求。

当车模桌面、智驾SR、导航地图分属不同 Android APK，它们都是或都有全屏的形态，那么当在Dock栏点击它们进入画面转场切换的时候，怎么让画面"看起来"连贯？

---

## 一、背景知识

### 1.1 三个关键类

**Activity、Window、Surface** 这三个 Android 类的关系对后面设计一镜到底方案比较关键。

**Activity**：一个有画面的安卓APK内部至少有一个Activity，它管生命周期（onCreate/onResume/onPause/onDestroy）。但是一个 Activity "活着"不等于它的画面"可见"，比如暂停（paused）的 Activity 还在内存里，但画面可能已经被另一个 Activity 盖住了。

**Window**：Activity 创建时自动关联一个 Window，它是画面的视觉容器。Window 本身不渲染，它承载一个 View 树，由你写的布局填充。Window 由 `WindowManagerService` 统一管理 Z-order 和窗口叠放。

**Surface**：画面最终要画在 Surface 上。Surface 是一块像素缓冲区（底层是 BufferQueue），SurfaceFlinger 把所有 Window 的 Surface 合成后送到屏幕。**谁持有 Surface，谁才有画面输出能力。**

**关系图：**

![图1](./图1.png)

### 1.2 特别的Surface

**普通 View 共享 Window 的 Surface，SurfaceView 和 TextureView 拥有各自独立的 Surface。** 虽然"独立"，却也受生命周期控制，即Activity 销毁时 Window 销毁，SurfaceView 的 Surface 和 TextureView 的 SurfaceTexture 都跟着销毁。

- **SurfaceView**：独立 Surface 在 SurfaceFlinger 里拿自己的合成层，画面走完全分开的合成路径。好处是纯渲染性能好，代价是它无法做alpha 动画、缩放、旋转，也无法嵌入 View 层级做叠放控制。
- **TextureView**：独立 Surface 的内容被当作 OpenGL 纹理消费，再贴回到 Window 的渲染管线里。所以它表现得像普通 View。多了一步纹理上传的开销，你可以在 View 层面用 alpha 动画遮盖切换间隙，SurfaceTexture 的回调也让你精确控制 Surface 的创建和销毁时机。

### 1.3 让两个 Surface 同时活着？

一个自然的想法是：有了服务化渲染，App A 和 App B 都把 Surface 传给同一个 RenderService，切换时 Service 只是把渲染目标从 Surface A 换到 Surface B，不就无缝了吗？

**这个想法的问题在于，Surface的生命周期不受你控制。**

Surface 随 Activity 生死。App A 切到 App B 时，A 的 TextureView 随着 Window 被移走，SurfaceTexture 触发 `onSurfaceTextureDestroyed`Surface 就没了。B 的 TextureView 要等 Window 创建后才触发 `onSurfaceTextureAvailable`Surface 才有。这个间隙是 Android 框架强制的，应用层无法精确干预。

RenderService 一直活着，引擎一直在渲染，但渲染结果要写到 Surface 的 BufferQueue 里。Surface A 已经销毁，Surface B 还没创建，引擎渲染的那帧就中断显示了。

> 切换APK意味着切换不同的Activity。而 Activity 切换的本质是 Window 和 Surface 生命周期的断裂与重建。
>
> 所以我认为跨应用的一镜到底，讨论的重点是**切换时的画面怎么衔接**，即**帧画面衔接**。无论是有服务化渲染+多视图的能力还是没有。

---

## 二、方案一：无服务化渲染

两个独立 APK，只有一个 3D引擎实例或两个独立的3D引擎实例的，各自的 EGL 上下文完全隔离。这种条件下我认为不存在"像素级连续"的可能性。你能做的，只有**近似帧画面衔接**。

做法是应用 A 把视角拉高到某个远景，定格画面、截图；另一个应用拉起来之后，拿到这张截图做显示并逐渐淡出。这本质上不是那么真实的一镜到底，而是一个经过视觉设计的转场遮罩。

但它仍然有价值，因为这是没有服务化渲染支撑时的**可行方案**，而且在特定场景（双桌面：车模桌面↔导航桌面）下效果可以接受。

### 典型实现：双桌面切换

**3D 桌面→导航桌面**：

1. Android 侧对导航的 SurfaceView 截一张图（`SurfaceControl.captureLayers` 或 `PixelCopy`），拿到导航当前正在渲染的像素。
2. 把这张截图模糊化后，贴到过渡遮罩（`TransitionView`）上。此时导航在后台，截图扮演的是**目的地的模糊预告**。让用户感知"我要去的地方大概长什么样"。
3. 向3D运行时发送转场指令，3D端虚拟相机动画拉高到远景。
4. 过渡遮罩 alpha 0→1（约 700ms），逐渐覆盖 3D 画面。用户此时看到的效果是远景的场景和车变化成模糊的"导航影子"浮现出来。
5. 真实的导航 TaskView 切入，过渡遮罩 alpha 1→0 淡出。

**导航桌面→3D 桌面（animateTo3D）**：

1. 再次捕获导航 SurfaceView 当前帧。
2. 设置模糊截图到过渡遮罩，alpha 0→1。此时截图扮演的是**离场的模糊幕布**，模糊的导航画面盖住真实的导航，3D 在幕布后面切入（被拉起）
3. 向 3D 侧发送返回指令，3D的虚拟相机动画回到衔接视角。
4. 3D的 TaskView 切入，过渡遮罩 alpha 1→0 淡出

> 两个桌面以远程 Task 的形式嵌入宿主 `MainActivity`，通过 `SharedTaskView` 管理。切换时通过 `SurfaceControl.Transaction` 的 `reparent` 操作将 Task 的 Surface leash 从一个 View 移到另一个 View，配合 `setAlpha` 动画实现视觉过渡。在这里不停地“换父亲”的就是导航的那张截图，用这种方法切换容器也不黑屏。

这个方案的好处是对于一镜到底的视觉效果来说比较解耦，几乎是各管各的了，也不要求有多么精确的画面衔接。缺点也在这里，如果两边的画面内容差异太大，就维持不了这种镜头感，会割裂。

---

## 三、方案二：服务化渲染+多视图

在服务化渲染和多视图能力的支持下，App A一个画面，App B一个画面，还有一个独立维护的Window也是一个画面，每个画面都是在同一个渲染服务中的一个虚拟相机。

我们可以（也许也必须）在不同的场景/关卡中使用同一套相机管理配置，对于Unity来说，这两个Scene用的是同一套Cinemachine的VirtualCamera组合Prefab。因为这么做，可以保证在不同的应用使用的相机动画逻辑是一致的，进一步保证画面是真的可以衔接的。

1. **Unity 侧 RT** ：多屏（仪表屏，CSD屏等）场景下，先把当前画面渲染到 RenderTexture，各屏幕的 RawImage 显示这张 RT，下面要说的过渡相机在 RT 后面平滑运镜。这样 Activity 切换间隙里，虽然 Surface 断了，但 RT 还在，多屏画面不中断。
2. **过渡相机**：设置专门的虚拟相机，渲染结果输出到独立 Display，这个 Display 的 Surface 由 Android 侧遮罩 Window 持有。遮罩 Window 是个全屏独立窗口，Z-order 在所有应用之上，持有 TextureView 接收过渡相机的画面，覆盖 Activity 切换的间隙。
3. **时序配合**：切换开始时，Unity 冻结当前画面到 RT，相机开始运镜，Android 切换 Activity，新 Surface 连上后，相机已到目标机位，关闭 RT，新应用画面淡入。整个过程用户看到的是：当前画面冻结 → 3D 运镜动画始终可见 → 新应用画面淡入，真正的一镜到底。

![图2](./图2.png)

> 遮罩 Window 需要 SystemUI 配合，涉及系统签名权限和跨进程通信，不是普通应用能独立完成的。如果项目没有系统级合作能力，这个方案根本落不了地。

---

## 结语

通过写文章，可能没有办法把完整的做法交付出来，甚至会丢失其中很多的细节。最多能说是提供了一个思路和方向。在实现任何一套方案的过程中，经历过太多的调整，太多的bug处理。有的事情是亲身经历的，有的问题在无觉知的时候就被解决了。因此我会尝试去回忆一些我曾经遇到过的问题，去在下一篇文章中尽量弥补一些这方面内容的缺失。