---
title: "Cockpit 3D HMI Stability: A Proactive ANR Detection Scheme (Part 2)"
lang: en
date: 2026-07-06
series: stability
no: 2
status: published
visibility: public
wechat_url: ""
---

> I previously wrote about a pure-Java proactive ANR detection scheme: [Cockpit 3D HMI Stability: A Proactive ANR Detection Scheme (Part 1)](https://mp.weixin.qq.com/s/g0JfostHEqEKmxbzw4b3lw). This article approaches the solution from the business layer of the 3D engine (Unity/TuanJie).

Unlike the previous method, this one leans more toward passive observation rather than actively posting probe tasks. But at heart, both are monitoring the engine's main thread.

---

# Detection principle

The core idea: the Unity main thread increments an atomic counter every frame, and a background thread periodically checks whether the counter has changed. If the counter stays unchanged for a long time, the main thread has stopped executing — judged as frozen — and JNI is then used to call a native-layer interface to dump the stack.

# Implementation

## The 3D engine side (Unity)

The heart of the implementation is a script that increments a heartbeat every frame, plus a background detection thread.

### The main thread monitor

The core fields of `MainThreadMonitor`:

```csharp
public class MainThreadMonitor : MonoBehaviour
{
    public float TimeoutSeconds = 5f;           // timeout threshold
    public float CheckIntervalSeconds = 1f;     // check interval

    private Thread _watchdog;
    private volatile bool _running = true;
    private volatile uint _heartbeat = 0;       // atomic counter
}
```

### Initialization logic

In `Awake`: set DontDestroyOnLoad to keep the component alive, initialize the native layer, and start the background detection thread:

```csharp
void Awake()
{
    DontDestroyOnLoad(gameObject);

    // Initialize the native layer, passing in the log directory
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

### Heartbeat increment logic

The `Update` method runs on the main thread every frame, incrementing the `_heartbeat` counter:

```csharp
void Update()
{
    // volatile increment: no lock contention
    _heartbeat++;

    // Set the main thread TID on the first run
    if (_heartbeat == 1)
    {
        int tid = NativeStackDumper.NativeStackDumper_GetTid();
        NativeStackDumper.NativeStackDumper_SetMainThreadTid(tid);
        Debug.Log($"[MainThreadMonitor] Unity main thread TID={tid}");
    }
}
```

### Background detection logic

The background thread `WatchdogLoop` checks once per second whether `_heartbeat` has changed. If the heartbeat hasn't changed, it enters the freeze-detection flow: it accumulates the check count, and once the threshold (5 seconds) is exceeded, calls the native interface to dump the stack, then waits for the main thread to recover.

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
            // Heartbeat unchanged: possible freeze; enter the accumulating check
            int stuckCount = 0;
            while (_running && _heartbeat == lastHeartbeat)
            {
                stuckCount++;
                Thread.Sleep((int)(CheckIntervalSeconds * 1000));

                if (stuckCount * CheckIntervalSeconds >= TimeoutSeconds)
                {
                    Debug.LogError($"[MainThreadMonitor] Main thread freeze detected, dumping stack...");
                    NativeStackDumper.NativeStackDumper_DumpMainThread();

                    // Wait for the main thread to recover
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

### Calling the Java interface to dump the stack

Use Unity's `AndroidJavaClass` and `AndroidJavaObject` to call the Java-layer stack dump methods.

```csharp
private void DumpMainThreadStack()
{
#if UNITY_ANDROID && !UNITY_EDITOR
    try
    {
        // Call the Java class's static method
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

## The native-layer implementation

The native layer provides four JNI interfaces, using a signal mechanism and thread management to implement system-level stack dumps.

### Native interface declarations

First, declare the four native-layer JNI interfaces on the Unity side — for initialization, setting the thread ID, dumping the stack, and getting the current thread ID.

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
     * Print the stack info of all threads
     * Called when: the Unity side has detected a main-thread freeze
     */
    public static void DumpAllThreads() {
        Log.w(TAG, "=== Stack Dump Started ===");

        // Method 1: use Thread.getAllStackTraces()
        DumpAllThreadStacks();

        // Method 2: send a SIGQUIT signal to trigger system-level stack printing
        SendSigQuitSignal();

        Log.w(TAG, "=== Stack Dump Ended ===");
    }
// Concrete Java method bodies omitted
```

## The detection flow

1. The Unity main thread increments the `_heartbeat` counter every frame (atomic operation, extremely low overhead)
2. The background detection thread checks once per second whether `_heartbeat` has changed
3. If `_heartbeat` stays unchanged for a long time (over 5 seconds), it's judged as frozen
4. Call `NativeStackDumper_DumpMainThread()` to dump the stack
5. The Java layer prints all thread stacks to logcat
6. Wait for the main thread to recover, then continue with the next detection round

# Closing thoughts

This scheme complements the previous one. It's more cumbersome to write: besides the engine business-logic code, it also needs Java-side code to cooperate. Its distinguishing feature is that it judges freezes from the business-logic main thread, which puts it much closer to the immediate situation of the 3D layer.
