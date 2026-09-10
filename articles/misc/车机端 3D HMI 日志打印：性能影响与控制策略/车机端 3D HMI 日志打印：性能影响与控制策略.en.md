---
title: "3D HMI Logging on In-Vehicle Units: Performance Costs and Control Strategies"
date: 2026-06-19
series: misc
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> Writing logs is something every software engineer does. In the development of 3D HMI for smart cockpits, we all need to print logs—to visualize data, record states, or diagnose exceptions. Logging is necessary, especially after a version has shipped: analyzing field issues depends entirely on logs, since there is no way to preserve the scene. So we need to think about what should be printed and what can be left out.

An in-vehicle system is highly sensitive to performance load. It cannot support high-frequency log output, and under heavy load the system itself will drop large amounts of logs. System engineers usually impose a constraint on how much logging the whole system may emit per minute, refined down to per-application limits—say, 300 lines/minute.

Since there is such a rate ceiling on the logs our applications may output, I think we can explore the topic in this order:

1. What performance load does printing one log line actually generate?
2. How should we decide whether a given business log should be printed or not?
3. What engineering means do we have to control log verbosity in bulk?

---

# 1. What Does Logging Consume?

## 1.1 CPU

A log is not just the `Debug.Log(...)` line it appears to be. On the main thread, it triggers the following stages:

### **String construction**

Every call allocates a new string, triggering GC.

```
_log.Info(string.Format("WriteValue {0} = {1}", key, value));
// or with interpolation syntax
_log.Info($"WriteValue {key} = {value}");
```

### **Locking in FormatString**

Our development framework inevitably has a logging module, and that module prefixes every log line to identify which module—or even which method—the log came from.

Because a lock protects the StringBuilder, there is also a risk of lock contention blocking threads here.

```
// Pseudocode inside the logging framework
lock (_lock)  // lock to protect the StringBuilder
{
    _sb.Append($"[{moduleName}] ");
    _sb.Append(message);
    finalString = _sb.ToString();
}
```

### **Engine-internal call overhead**

For example in Unity, from Debug.Log to a call into the Native layer, and from there to the Android Logcat output.

### **StackTrace capture**

If stack tracing is enabled, the overhead multiplies.

## 1.2 Disk I/O

Disk I/O refers to the speed and frequency of reading and writing storage devices (e.g., log files under /data/log/, system buffers), whereas the I/O metric we usually see in adb top expresses a process's share of I/O wait time. For instance, %iowait is the share of CPU time spent waiting for I/O to complete.

An in-vehicle app's logs mostly end up in **Android logcat**, which is consumed simultaneously by the system log service, capture tools, remote diagnostics, and other consumers—all of them competing for I/O resources.

So this is how printing logs consumes I/O:


| Stage                          | What happens           | Where the I/O goes    |
| --------------------------- | --------------- | --------- |
| JNI call                      | Unity → Android | Data copies      |
| logcat buffer                  | Writing into the system buffer         | Lock contention, memory copies  |
| FileLogger, **the business-defined file logging system** | Writing files + Flush     | Synchronous disk flush (the most lethal) |
| Multi-consumer reading                      | System / capture / remote diagnostics      | Bandwidth contention      |


## 1.3 Memory

Every log line creates new string objects. As described in 1.1, string allocations and StringBuilder resizes, when triggered at high frequency, create large numbers of temporary strings that eat memory, and StringBuilder growth allocates new memory too.

---

# 2. Should This Log Be Printed?

> **What follows is a subjective operational scheme derived from my personal project experience. A principle is only a principle.**
>
> **When you lack confidence in some area, or a certain class of bug keeps haunting you, add more logs to help predict or locate the problem.**

## 2.1 Should Not Print

**High frequency**: anything called more than once per second is off by default. If you log inside Update(), that's 60 times a second—obviously not acceptable.

> - Configuration writes triggered by interaction events: for example the current vehicle model camera view or the car paint color. Fine to print while investigating an issue, but not advisable afterwards.
> - Printing during dynamic frame-rate adjustments: may fire in bursts over a short period when the frame rate changes.
> - Message handling: when a signal arrives, printing its message header is fine, and printing which type of handler it was dispatched to is fine too. But going further down that path gets risky.

**High cost**: complex string concatenation, StackTrace attached, or serializing large objects—such logs deserve caution even at low frequency. For example logs with rich text: some developers like seeing colored logs in the Editor, so they use color-tagged Debug output. If those tags ship in the release build too, they burn resources.

> Let me highlight StackTrace here. As a developer, of course I want StackTrace information in my logs, because it shows how execution step-by-step arrived at the problem.
>
> But for a release build, for the sake of performance—and even from the perspective of overall human efficiency when analyzing logs—this is definitely not the way. The purpose StackTrace serves can be partly met, within the performance budget, by the prefixes our logging module attaches; the rest comes down to our own familiarity and understanding of the code.

**Main thread**: typically, a framework's logging module maintains a message queue on the main thread. The main thread only throws the content to be printed into the queue, while the log thread managed by the module pulls messages from the queue and then performs the expensive work: formatting, prefix concatenation, writing to logcat or to files. So avoid printing logs on the main thread—even if it's not every frame, it can stall the main thread at the worst possible moment.

## **2.2 Should Print**

**Message handling**, e.g. messages sent over from Android. For command-type messages: at minimum print the command type and its main parameters. For ADAS serialized data that's relatively long (e.g., perception data): keep the log to printing the data count. The actual data should be recorded to disk files through the SR's own replay-tool mechanism.

**Application lifecycle events**, such as app startup, version number printing, and each module's Init completion. These happen only once; use Info level, print once, and they help quickly locate initialization-phase problems.

**Scene/state transition events**, such as SR Show/Hide, entering/exiting APA mode. These events are low-frequency (users don't switch scenes every second), so either Debug or Info works; they let you trace scene flow.

**Errors and exceptions**, such as communication initialization failures, protocol parsing exceptions, and critical resource loading failures. Every developer knows to expose these at Error level.

**Stability analysis**, e.g., a response taking more than 5ms to execute, with alerts based on a project-specific ANR-like detection mechanism. This kind of log is very valuable for analyzing black screens and freezes.

---

# 3. Log Control Strategies

## 3.1 Editor Mode

Editor mode achieves debugging through conditional compilation and stack-trace configuration:

- **Conditional compilation to isolate debug logs**: wrap debug output that's only needed in the Editor with `#if UNITY_EDITOR`; these logs never reach the release build.
- **Tiered stack-trace control**: set `StackTraceLogType.ScriptOnly` in the Editor environment to keep the script call stack for debugging; set `StackTraceLogType.None` on real hardware to avoid the per-log overhead of capturing the call stack.

## 3.2 Log Configuration After Release

- Inject the **global log level via configuration** at app startup:

```csharp
private void InitLogHelper()
{
    s_Log.Debug("InitLogHelper");
    var appConfig = AppConfig.Instance;
    Log.SetLevel((LogLevel)appConfig.logLevel);
}
```

Level definitions (lower value = more permissive):

- `All = 0` → `Verbose` → `Debug` → `Info` → `Warn` → `Error` → `Off = 6`

Recommended configurations per environment:

- **Unity Editor**: Debug (2), stack trace ScriptOnly
- **Bench / field testing**: Info (3) or Warn (4), stack trace None
- **Mass production / OTA Release**: Warn (4) or Error (5), stack trace None
- **Performance testing / executive demo vehicles**: Off (6) or a runtime master switch

> There is one more configuration here, tied to what the framework's logging module can do:
>
> - **Modular loggers**: create separate logger instances per module via `Log.GetLogger("SRManager")` and similar calls. On top of the print-level restrictions, this adds a finer-grained restriction by functional module. It basically came into being for the SR side.

## 3.3 Ways to Switch Log Levels

We can configure log levels through the following means:

- **Configuration file switching**: modify the `app config class .logLevel` value, and the new log level is injected at app startup. This suits version builds for different environments—it's exactly the capability the 3D automated build pipeline needs.
- **Runtime master switch**: once the app is installed on a bench and I want to change the log level, besides planting a backdoor for enabling Debug logs (e.g., placing a file at a fixed path), we can also use the bench debugging tool panel to toggle `UnityEngine.Debug.unityLogger.logEnabled` in real time over a Socket link, temporarily disabling logs during performance testing.
- **Conditional compilation**: wrap debug logs with `#if UNITY_EDITOR` to isolate development-only logs at the code level, ensuring the release build contains none of this output—already covered above.

> What we've discussed so far is controlling log levels from the 3D side. But we know that when a log is printed, it ultimately goes through JNI into the Java layer, which uses native methods to complete the print.
>
> So 3D can have its own control methods, but the Android app layer can also, through configuration, control the overall log level for both the Android side and the 3D side—and that is beyond the 3D side's control.

---

## Closing

Given all the above, there's no need to repeat the usual tips for optimizing logging, because they're already woven into the discussion.

Let me share a bug ticket I once saw: when swiping the vehicle model on the car-model desktop, memory would spike from around 700 MB to over 800 MB. By digging through the logs we found that during this phase, coordinate changes were being printed at high frequency, and in the gaps between swipes the vehicle model's current pose was also being recorded and written to file.

The fix was simply to comment out the overly frequent logs, keeping the log output volume within limits while swiping the vehicle model. It was from this issue onward that I realized logging isn't just a debugging feature—it's also a performance-sensitive source of hidden risk.
