---
title: "座舱3D HMI稳定性：ANR 主动检测方案（二）"
date: 2026-07-06
series: stability
no: 2
status: published
visibility: public
wechat_url: ""
---

> 之前写了纯 Java 的 ANR 主动检测方案：[《座舱3D HMI稳定性：ANR 主动检测方案（一）》](https://mp.weixin.qq.com/s/g0JfostHEqEKmxbzw4b3lw)。这一篇写的是从 3D引擎（Unity/TuanJie）业务层出发去考虑解决方案。

与之前的方法不同，这个方法更偏被动观察，而非主动去Post任务做探测。但是本质上两者都是针对引擎的 mainthread 在做检测。

---

# 检测原理

核心思路是通过 Unity 主线程每帧递增一个原子计数器，后台线程定期检查计数器是否变化。如果计数器长时间不变，说明主线程停止执行，判定为卡死，然后通过 JNI 调用 Native 层接口 dump 堆栈。

# 实现方案

## 3D引擎侧(Unity)

实现的核心是通过脚本进行每帧心跳递增，并创建一个线程进行后台检测。

### 主线程检测器

`MainThreadMonitor` 的核心字段：

```csharp
public class MainThreadMonitor : MonoBehaviour
{
    public float TimeoutSeconds = 5f;           // 超时阈值
    public float CheckIntervalSeconds = 1f;     // 检测间隔

    private Thread _watchdog;
    private volatile bool _running = true;
    private volatile uint _heartbeat = 0;       // 原子计数器
}
```

### 初始化逻辑

在 `Awake` 中：设置 DontDestroyOnLoad 确保组件不被销毁、初始化 Native 层、启动后台检测线程：

```csharp
void Awake()
{
    DontDestroyOnLoad(gameObject);

    // 初始化 Native 层，传入日志目录
    string logDir = Application.persistentDataPath;
    NativeStackDumper.NativeStackDumper_Init(logDir);
    Debug.Log($"[MainThreadMonitor] Native initialized, logDir={logDir}");

#if UNITY_ANDROID && !UNITY_EDITOR
    _watchdog = new Thread(WatchdogLoop)
    {
        IsBackground = true,
        Name = "MainThreadMonitor"
    };
    _watchdog.Start();
#endif
}
```

### 心跳递增逻辑

`Update` 方法在主线程每帧调用，递增 `_heartbeat` 计数器。：

```csharp
void Update()
{
    // volatile 递增：无锁竞争
    _heartbeat++;

    // 首次运行时设置主线程 TID
    if (_heartbeat == 1)
    {
        int tid = NativeStackDumper.NativeStackDumper_GetTid();
        NativeStackDumper.NativeStackDumper_SetMainThreadTid(tid);
        Debug.Log($"[MainThreadMonitor] Unity main thread TID={tid}");
    }
}
```

### 后台检测逻辑

后台线程 `WatchdogLoop` 每秒检查一次 `_heartbeat` 是否变化。如果发现心跳未变化，进入卡死检测流程：累计检测次数，超过阈值（5 秒）后调用 Native 接口 dump 堆栈，然后等待主线程恢复。

```csharp
private void WatchdogLoop()
{
    uint lastHeartbeat = _heartbeat;

    while (_running)
    {
        Thread.Sleep((int)(CheckIntervalSeconds * 1000));

        uint current = _heartbeat;

        if (current == lastHeartbeat)
        {
            // 心跳未变化：可能卡死，进入累计检测
            int stuckCount = 0;
            while (_running && _heartbeat == lastHeartbeat)
            {
                stuckCount++;
                Thread.Sleep((int)(CheckIntervalSeconds * 1000));

                if (stuckCount * CheckIntervalSeconds >= TimeoutSeconds)
                {
                    Debug.LogError($"[MainThreadMonitor] Main thread freeze detected, dumping stack...");
                    NativeStackDumper.NativeStackDumper_DumpMainThread();

                    // 等待主线程恢复
                    while (_running && _heartbeat == lastHeartbeat)
                    {
                        Thread.Sleep(500);
                    }
                    break;
                }
            }
        }

        lastHeartbeat = _heartbeat;
    }
}
```

### 调用 Java 接口 dump 堆栈

使用 Unity 的 `AndroidJavaClass` 和 `AndroidJavaObject` 调用 Java 层的堆栈 dump 方法。

```csharp
private void DumpMainThreadStack()
{
#if UNITY_ANDROID && !UNITY_EDITOR
    try
    {
        // 调用 Java 类的静态方法
        AndroidJavaClass stackDumperClass = new AndroidJavaClass("com.example.engine.StackDumper");
        stackDumperClass.CallStatic("DumpAllThreads");

        Debug.Log("[MainThreadMonitor] Stack dump triggered successfully");
    }
    catch (System.Exception e)
    {
        Debug.LogError($"[MainThreadMonitor] Failed to dump stack: {e.Message}");
    }
#endif
}
```

## Native 层实现

Native 层提供四个 JNI 接口，通过信号机制和线程管理实现系统级堆栈 dump。

### Native 接口声明

首先在 Unity 侧声明 Native 层的四个 JNI 接口，分别用于初始化、设置线程 ID、dump 堆栈和获取当前线程 ID。

```java
package com.example.engine;

import android.util.Log;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Map;

public class StackDumper {
    private static final String TAG = "StackDumper";

    /**
     * 打印所有线程的堆栈信息
     * 调用时机：Unity 侧检测到主线程卡死时
     */
    public static void DumpAllThreads() {
        Log.w(TAG, "=== Stack Dump Started ===");

        // 方法1：使用 Thread.getAllStackTraces()
        DumpAllThreadStacks();

        // 方法2：发送 SIGQUIT 信号触发系统级堆栈打印
        SendSigQuitSignal();

        Log.w(TAG, "=== Stack Dump Ended ===");
    }
// Java的具体方法略
```

## 检测流程

1. Unity 主线程每帧递增 `_heartbeat` 计数器（原子操作，极低开销）
2. 后台检测线程每秒检查 `_heartbeat` 是否变化
3. 如果 `_heartbeat` 长时间不变（超过 5 秒），判定为卡死
4. 调用 `NativeStackDumper_DumpMainThread()` dump 堆栈
5. Java 层打印所有线程堆栈到 logcat
6. 等待主线程恢复，继续下一轮检测

# 结语

这套方案可以和之前的方案形成互补，写法上更麻烦一些，不仅有引擎业务逻辑代码的部分，而且还需要java侧的代码进行配合。这个做法的特点就是从业务逻辑主线程出发去评判是否卡死，更加贴近3D层的即时情况。