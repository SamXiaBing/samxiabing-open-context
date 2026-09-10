---
title: "Cockpit 3D HMI Stability: Black Screen · False Kills Triggered by STR"
lang: en
date: 2026-08-31
series: stability
no: 
status: published
visibility: public
wechat_url: ""
---

> I previously wrote two articles on proactive ANR detection schemes, which can catch main-thread freezes in time and dump the stack. But there's one scenario that can throw this scheme's judgment off: the head unit entering STR.

## 1. The symptom

### 1.1 The phenomenon: 3D black screen after STR

After the user leaves the car, the system enters STR. When the user returns and operates the car again, the 3D car-model desktop interface shows a black screen, and only recovers after the engine cold-restarts.

Capturing logs revealed: the 3D rendering process was killed during STR — the kill signal came from the in-process ANR watchdog, not from the system.

### 1.2 How to reproduce

The problem has a few clear trigger conditions:

- The head unit enters STR (a few minutes after the user leaves the car)
- STR lasts longer than the ANR watchdog timeout threshold (over 10 seconds)
- The Java-side alive check is running

With all three conditions met, the false kill is nearly deterministic. It only looks "intermittent" because how long after ignition-off the system enters STR, and when the user operates the car again — these times are random.

### 1.3 Why it wasn't caught earlier

The ANR watchdog detection mechanism had only recently shipped (as of that time). The test cases never covered STR — who would have thought that normal behavior could trigger the watchdog?

## 2. Root cause analysis

STR is an Android Automotive power management state, short for Suspend To RAM. When the head unit is shut off or enters a low-power mode, the system suspends all processes to memory and the CPU stops executing. When the user operates the car again, the system resumes from RAM and the processes continue running. The whole point is its fast system recovery capability.

For the 3D side, it means trouble:

- The Unity main thread stops executing; `Update()` is no longer called
- The heartbeat counter stops incrementing
- JNI calls no longer happen
- The rendering pipeline is paused

### 2.1 The Java-side alive check false kill

This alive check mechanism was added by our own team at the engine service layer (the rendering service process) in the vehicle program of that time, running on Android's main-thread Handler:

```java
// TuanjieC2SMessenger.java
private static final int ALIVE_CHECK_INTERVAL = 3_000; // check every 3 seconds

private final Runnable aliveCheckRunnable = new Runnable() {
    @Override
    public void run() {
        if (App.Companion.isAliveCheckEnabled()) {
            int step = anrStep.get();
            int pid = android.os.Process.myPid();
            if (step == 0) {
                long now = SystemClock.elapsedRealtime();
                // 10-second timeout
                if (lastAliveTime.get() > 0 && now - lastAliveTime.get() > 10000) {
                    // dump the stack
                    var process = Runtime.getRuntime().exec("kill -3 " + pid);
                    anrStep.set(step + 1);
                }
            } else if (step >= 3) {
                // 3 consecutive timeouts: kill the process
                android.os.Process.killProcess(pid);
            } else {
                anrStep.set(step + 1);
            }
        }
        mainHandler.postDelayed(this, ALIVE_CHECK_INTERVAL);
    }
};
```

The watchdog logic: check every 3 seconds; if no heartbeat from the engine arrives within 10 seconds, dump the stack first; 3 consecutive timeouts and it kills the process.

The Java-side alive check runs in the system service process; whether that service gets suspended during STR depends on the power management policy. If the process hosting the alive check isn't fully suspended (or, after wake-up, the messages in the Handler queue are executed all at once), it computes the current time minus the `lastAliveTime` from before STR — and the difference can be minutes or even hours, far beyond the 10-second threshold.

> The heartbeat mechanism is the input end of the whole watchdog: every 2 seconds, the Unity side calls the Java-side onHeartBeat() via JNI, refreshing lastAliveTime to the current time; the alive check later uses that timestamp for the timeout decision — if the heartbeat stops, the engine is presumed dead.

That's the root cause of the false kill: the watchdog judges life and death by "time difference", but it knows nothing about STR.

> The Unity-side watchdog runs in the same process as the engine: when STR suspends everything, the detection thread freezes too, and after waking there's no time difference to measure — so it can't false-kill by nature. This contrasts sharply with the Java side's cross-layer detection.

## 3. The solution

Pause the watchdog during STR; after wake-up, reset its state and then resume.

So two things need doing:

1. Be able to sense STR state changes
2. On wake-up, zero out the watchdog state — don't keep computing with times from before STR

### 3.1 PowerManager

Listen to the system power state via `CarPowerManager`. Code omitted — this part was modified by the Android-side colleagues.

### 3.2 Pausing and resuming the alive check

Register the power mode listener in the constructor:

```java
// TuanjieC2SMessenger.java
if (supportCarPower) {
    OnPowerModeActiveListener powerModeActiveListener = isActive -> {
        if (isActive && is3DEngineReady.get()) {
            // Wake-up: reset the watchdog state, restart the alive check
            resetAliveCheckState();
            mainHandler.removeCallbacks(aliveCheckRunnable);
            mainHandler.postDelayed(aliveCheckRunnable, ALIVE_CHECK_INTERVAL);
        } else {
            // STR: pause the alive check
            mainHandler.removeCallbacks(aliveCheckRunnable);
        }
    };
}
```

1. On entering STR: `removeCallbacks(aliveCheckRunnable)` stops the alive check, preventing the false kill.
2. On wake-up: first `resetAliveCheckState()` zeroes `anrStep` and updates `lastAliveTime` to the current time, then the alive check is restarted.

## Closing thoughts

As I recall, STR-induced 3D black screens have more than one cause. The case described in this article is one of the clearer ones, whereas STR often brings far more baffling problems — say, a render thread sitting in the Runnable state yet never getting scheduled; or everything in the renderer seemingly running, but the display staying black. Troubleshooting those requires more field data and more lines of suspicion — don't let this article box in your thinking.
