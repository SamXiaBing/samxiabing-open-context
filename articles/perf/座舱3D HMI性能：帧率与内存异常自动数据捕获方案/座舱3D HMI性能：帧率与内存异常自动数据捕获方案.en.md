---
title: "Cockpit 3D HMI Performance: Auto-Capturing Data on Frame Rate and Memory Anomalies"
date: 2026-07-13
series: perf
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> When delivering 3D HMI software projects, one class of performance-stability problems goes like this: mid-run, the frame rate suddenly drops, and interaction feels laggy or janky. If testers aren't bound by any reporting discipline, all we developers get to see at that moment is the logcat log. And logcat alone almost certainly leaves you "guessing" at the cause.

So we want to proactively capture more "engine-friendly" performance data at the exact moment the performance drop happens. The scheme in this article: **when the frame rate is detected to be below a threshold, automatically trigger the Unity Profiler API, capturing both the** `.raw` **frame data and the** `.snap` **memory snapshot**. With this mechanism and tooling in place, you can go straight back to the Editor and analyze such problems with the relevant Performance tools — with the precondition that you're in Development mode/stage.

---

# Scheme Overview

![Figure 1](./图1.png)

Core idea: **poll at low cost during normal operation, and drop the evidence all at once when the frame rate goes abnormal**.

---

# Implementation

## 1. Detection

- Create a `PerformanceMonitor` class, instantiated at startup in debug mode, with these default parameters:


| Parameter      | Default | Meaning                                            |
| -------------- | ------- | -------------------------------------------------- |
| `fpsThreshold` | 24      | Trigger capture when average FPS falls below this value |
| `interval`     | 2       | Frame rate check interval, in seconds              |
| `cooldown`     | 10      | Minimum interval between two captures, in seconds  |


Illustrative code:

```csharp
void CheckPerformance()
{
    if (averageFps < fpsThreshold)
    {
        string reason = $"Low frame rate={Mathf.RoundToInt(averageFps)}fps";
        CapturePData(reason);
    }
}
```

- I also recommend adding a **memory-over-threshold** check as an auxiliary trigger condition.

```
// Get current memory usage (MB)
#if !UNITY_EDITOR
        float currentMemory = Android JNI instance.GetCurrentAppMemoryMB();
#else
        float currentMemory = UnityEngine.Profiling.Profiler.GetTotalAllocatedMemoryLong() / (1024f * 1024f);
#endif

if (currentMemory > memoryThresholdMB)
{
    string reason = $"Memory too high={Mathf.RoundToInt(currentMemory)}MB";
    CapturePData(reason);
}
```

## 2. Capture

When the frame rate/memory goes abnormal, **start both captures simultaneously**.

```csharp
public void CapturePData(string reason = "Performance anomaly")
{
#if DEVELOPMENT_BUILD
    maxFrames = 300; // Capture 300 frames
    captureFrameIndex = 0;
    isCapturing = true;

    // Enable Profiler areas
    Profiler.SetAreaEnabled(ProfilerArea.CPU, true);
    Profiler.SetAreaEnabled(ProfilerArea.GPU, true);
    Profiler.SetAreaEnabled(ProfilerArea.Memory, true);
    Profiler.SetAreaEnabled(ProfilerArea.Rendering, true);
    Profiler.SetAreaEnabled(ProfilerArea.Audio, true);
    Profiler.SetAreaEnabled(ProfilerArea.Video, true);
    Profiler.SetAreaEnabled(ProfilerArea.Physics, true);
    Profiler.SetAreaEnabled(ProfilerArea.Physics2D, true);
    Profiler.SetAreaEnabled(ProfilerArea.NetworkMessages, true);
    Profiler.SetAreaEnabled(ProfilerArea.NetworkOperations, true);

    // Set up the log file
    string fileName = $"profiler_{DateTime.Now:yyyyMMdd_HHmmss}.raw";
    string fullPath = Path.Combine(profilerFilePath, fileName);
    
    Profiler.logFile = fullPath;
    Profiler.enableBinaryLog = true;
    Profiler.enableAllocationCallstacks = true;
    Profiler.enabled = true;

    Debug.Log($"Started capturing performance data: {fullPath}");

    //-------------------------- Memory -----------------------------//
    string fileName = $"memory_{DateTime.Now:yyyyMMdd_HHmmss}.snap";
    string fullPath = Path.Combine(memoryFilePath, fileName);

    try
    {
        // Capture the memory snapshot, including all data types
        MemoryProfiler.TakeSnapshot(
            fullPath,
            OnMemorySnapshotFinished,
            OnMemorySnapshotProgress,
            CaptureFlags.ManagedObjects | 
            CaptureFlags.NativeObjects | 
            CaptureFlags.NativeAllocations | 
            CaptureFlags.NativeAllocationSites | 
            CaptureFlags.NativeStackTraces
        );
        
        Debug.Log($"Started capturing memory: {fullPath}");
    }
    catch (Exception e)
    {
        Debug.LogError($"Memory snapshot capture failed: {e.Message}");
    }
#endif
}
```

### Stopping the Capture

Capture stops automatically once the frame count reaches its limit.

```csharp
    void Update()
    {
        // Handle Profiler frame capture
        if (isCapturing)
        {
            captureFrameCount++;
            if (captureFrameCount >= maxCaptureFrames)
            {
                StopProfilerCapture();
            }
        }
    }
```

---

# Analyzing Back in the Editor

The two generated files can be inspected in the Editor:

- `.raw` corresponds to Unity's Window → Analysis → Profiler → Load. Use it to find which frame was slow, which function dragged performance down, and how often GC ran.
- `.snap` corresponds to Window → Analysis → Memory Profiler → Import, for seeing which objects occupy memory.

I plan to add the detailed analysis walkthrough next Monday.

---

# Caveats

**When to enable it:** in actual use, this tool works like this — after you've reproduced the performance-problem scenario, you use the control panel to turn on the auto-record feature, which then automatically triggers the performance data capture.

> The main reason is the scheme's current weakness: frame rate jitter, or passive frame drops below the threshold during certain app switches, can cause false triggers.

---

# Closing Thoughts

Analyzing performance-stability problems depends on tooling and data. That's exactly why this class of problems takes so long to resolve: the runtime lacks a complete data-capture capability matched to these problems. And even that capability needs to be embedded into the testing workflow — otherwise you end up having to capture everything yourself.
