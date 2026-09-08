---
title: "座舱3D HMI场景化动态帧率：在算力约束下寻求体验平衡"
date: 2026-06-22
series: rendering
no: 
status: published
visibility: public
wechat_url: ""
---

> 动态帧率（Dynamic Frame Rate）是说根据应用当前状态和交互事件，实时调整渲染帧率的能力。简单来说，就是"该快就快，该慢就慢"。在需要流畅体验的场景（如拖拽、动画、切换）保持高帧率，在静止或低优先级场景（如后台、AVM开启）主动降帧，而不是锁定在一个固定的帧率上限值。

车机 3D HMI的应用（如车模桌面）长期驻留在系统中，与其他3D应用或高性能消耗应用（如导航、语音）等多个应用共享同一块板子的算力。出于性能优化的角度考虑，3D 应用是性能负载的洪水猛兽之一，如果一直放任它们跑满帧，那绝对是对CPU和GPU资源的极大的浪费，因为很多时候 3D 应用的画面并非交互焦点。

所以动态帧率的核心目的就是**节省性能**，带来的好处包括：

- **释放算力给其他应用**：SR 渲染、地图导航、语音识别同时运行时，3D Launcher 如果在后台，且需要保持信号更新，那么就应该主动降帧，避免互相抢夺导致真正需要流畅的场景反而卡顿。
- **提升响应体验**：用户只在触摸、镜头动画等短时间窗口内需要高帧率，静止几秒后，肉眼几乎分不出 30 和 60 帧的差别。把省下来的算力用在用户真正需要的地方，整体体验反而更好。

---

## 一、动态帧率模块的设计

### 1.1 实现方式

控制帧率本身是比较简单：

在 Unity 中，可以通过 `Application.targetFrameRate` 属性设置目标帧率。

在 Unreal Engine 中，可以通过 `GEngine->SetMaxFPS(60);` 来设置。

一个动态帧率管理器通常会考虑设计以下接口：


| 接口                     | 参数                 | 说明                  |
| ---------------------- | ------------------ | ------------------- |
| `RequestHighFrameRate` | `string requester` | 请求高帧率，传入请求者标识       |
| `ReleaseHighFrameRate` | `string requester` | 释放高帧率请求，开始计时进入静止状态  |
| `SetFrameRateDirectly` | `int frameRate`    | 直接设置帧率（用于特殊场景如 AVM） |
| `GetCurrentFrameRate`  | -                  | 获取当前帧率              |


代码示意：

```csharp
public class DynamicFrameRateManager : SingletonMono<DynamicFrameRateManager>
{
    // 配置参数
    [SerializeField] private int _highFrameRate = 60;      // 交互时的高帧率
    [SerializeField] private int _lowFrameRate = 30;       // 静止时的低帧率
    [SerializeField] private float _idleThreshold = 5f;    // 静止检测阈值（秒）

    // 状态变量
    private float _idleTimer = 0f;
    private bool _isHighPriorityMode = false;

    // 核心接口
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
        // 重置计时器，等待重新进入静止状态
        _idleTimer = 0f;
    }

    // 每帧更新
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

## 二、各场景的帧率策略

交付过程中根据不同业务场景的特性，以及性能测试的结果，会制定差异化的帧率策略。以下是一些常见场景的分享：

### 2.1 Launcher 3D 车模桌面车控场景


| 状态      | 帧率        | 触发条件        | 适用性分析              |
| ------- | --------- | ----------- | ------------------ |
| **交互中** | 45或50 fps | 用户触摸屏幕      | 用户正在操作，需要流畅响应      |
| **静止**  | 25或30 fps | 无触摸操作持续 5 秒 | 静止看车模，30 fps 肉眼无差别 |


**理由**：Launcher 是用户进入系统后的第一屏，大部分时间静止展示车模。60/30 的配置在流畅性和功耗之间取得平衡。

### 2.2 SR 应用 + AVM（全景影像）场景


| 状态         | 帧率     | 适用性分析                                          |
| ---------- | ------ | ---------------------------------------------- |
| **AVM 开启** | 20 fps | AVM 如果合成算法跑在安卓上，压力会很大，可能需要 3D 让出性能预算，去保证基本的流畅度 |
| **AVM 关闭** | 30 fps | 恢复 SR 默认帧率                                     |


**理由**：AVM 弹出的时候，属于安全等级较高的画面，需要保证其帧率。如果是应用内拼接画面拼出AVM的话，性能压力很大，所以SR 需要降低到 20 fps 左右去满足泊车等场景的全景影像的流畅度。

### 2.3 3D 应用在后台


| 状态          | 帧率        | 触发方式                  | 适用性分析                 |
| ----------- | --------- | --------------------- | --------------------- |
| **App 退后台** | 3 fps     | Android 生命周期 onPause  | 几乎停止渲染，保留信号处理能力，释放算力。 |
| **App 回前台** | 45或50 fps | Android 生命周期 onResume | 恢复帧率，保证体验             |


**理由**：后台 3 fps 是"基本不占 GPU 但活着"的配置，既能响应必要的状态更新，又几乎不消耗算力。注意，如果没有服务化渲染能力，这一条可能是实现不了的，会在OnStop之后，UnityPlayer完全进入无Surface可渲染的状态而暂停主线程和渲染线程。当App回到前台的时候，往往需要安卓侧通过之前退后台时截取的末帧图作为遮罩，给到 3D 时间去恢复渲染，并完成从消息线程里面提取处理消息。

---

## 三、典型 Bug 案例分析

### 3.1 Bug #1：退后台回前台，帧率未恢复

**现象**：  
用户反馈从导航应用切回 3D Launcher 后，车模滑动明显卡顿，帧率持续在个位数，需要等好几秒才恢复正常。测试报为"画面卡顿"。

**问题原因**：  
应用切换到后台时，Android 侧会发一个"应用已退到后台"的信号，这时候帧率管理器被设置为一个极低值来释放 GPU 算力。但在 `OnApplicationPause(false)` 回调里，AndroidListener 的恢复处理是空的：

```csharp
// AndroidListener.cs — 真实代码
void OnApplicationPause(bool pause)
{
    Debug.Log($"on application pause: {pause}");
    // 只打了日志，没有做任何帧率恢复
}
```

帧率恢复完全依赖 `LauncherScene.Update()` 里每帧调用的 `SetFrameRate`。但如果退到后台期间场景的 Update 被挂起（例如正在重建场景资源、或框架层跳转状态机卡住），回到前台后第一帧才能恢复，这个时间窗口就容易被抓到问题。

**解决方法**：  
在 `OnApplicationPause(false)` 中显式恢复帧率，给场景的 Update 一个明确的起点：

```csharp
void OnApplicationPause(bool pause)
{
    if (!pause)
    {
        // 回到前台：恢复当前场景的目标帧率
        // -1 表示让系统自动选择，等 Update 中的 SetFrameRate 接管
        Application.targetFrameRate = -1;
    }
}
```

`targetFrameRate = -1` 的效果是让 Unity 重置到默认帧率策略，下一帧 `SetFrameRate` 就会按 状态重新设成正确的值。

**经验总结**：**生命周期事件（退后台/回前台/场景切换）也需要兜底恢复**。`OnApplicationPause` 这种回调是最后的保障线。

---

### 3.2 Bug #2：帧率频繁切换导致画面卡顿

**现象**：  
在 行驻泊一体化桌面 和 AVM（全景影像）共存时，帧率出现快速跳变（30 → 20 → 60 → 20 → 30），界面出现卡顿感。

**问题原因**：  
帧率控制逻辑**没有统一的执行器**。两套系统各自在写 `Application.targetFrameRate`：

- `LauncherScene.SetFrameRate()`：每帧检查 interaction，在 30/60 之间来回切
- `AndroidListener.AVMStatusChanged()`：AVM 开启时直接设 20，关闭时设 30

两条控制路径互相覆盖：

1. AVM 开启 → `targetFrameRate = 20`
2. Launcher 的 Update 跑到了 → `CheckForInteraction()` 返回 true → `targetFrameRate = 60`
3. AVM 关闭 → `targetFrameRate = 30`

**帧率跳变**，可能表现出画面卡顿。

**解决方法**：  
引入统一帧率管理器，所有帧率变更走同一执行器，不直接在业务代码里写 `Application.targetFrameRate`：

```csharp
public class DynamicFrameRateManager : MonoBehaviour
{
    private int _pendingFrameRate = -1;
    private int _currentFrameRate = -1;

    public void RequestFrameRate(int target, string source, int priority)
    {
        // 记录所有请求，按优先级取最高值
        _pendingFrameRate = CalculateHighestPriorityRate();

        // 防抖：差值小于阈值时不重复设置
        if (Mathf.Abs(_currentFrameRate - _pendingFrameRate) < 2)
            return;

        _currentFrameRate = _pendingFrameRate;
        Application.targetFrameRate = _currentFrameRate;
    }
}
```

改造之后，通过 `DynamicFrameRateManager.RequestFrameRate()` 发请求。管理器负责去重、防抖和优先级裁定。

**经验总结**：`Application.targetFrameRate` 是一个全局状态，任何地方都不能直接写。所有帧率变更必须过统一执行器，否则多路径并发覆盖是迟早的事。

---

## 结语

动态帧率是在算力受限、多应用共存、交互窗口短的三重约束下去寻求平衡的产物，用"该快则快、该慢则慢"代替了全局 60 fps 的方案。随着车机硬件的发展，SoC 算力会越来越强，但动态帧率的价值不会消失。相反，随着功能越来越丰富、应用越来越多，算力竞争可能会更加激烈。

未来的动态帧率系统可能会演变地更智能一些，比如根据实时负载动态调整帧率预算，让帧率控制去对接整个系统的调度体系，根据多个应用的数据综合协商，实现全局最优。

