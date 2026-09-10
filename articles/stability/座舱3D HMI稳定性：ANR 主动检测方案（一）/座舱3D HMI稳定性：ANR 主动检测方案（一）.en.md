---
title: "Cockpit 3D HMI Stability: A Proactive ANR Detection Solution (Part 1)"
date: 2026-07-03
series: stability
no: 1
status: published
visibility: public
wechat_url: ""
lang: en
---

> During 3D HMI delivery, you sometimes get bug tickets about the screen freezing. Usually, this is because the 3D engine's main thread is stuck. A stuck thread freezes the screen and kills user interaction. Without a proactive way to discover ANRs, all we get are logs with too little information, or logs from moments other than when the problem actually occurred.

The system's own ANR mechanism cannot accurately capture freezes inside the 3D engine, so we need a dedicated detection solution. This article focuses on the problem of **main-thread freeze detection in 3D HMI scenarios** and shares a first ANR detection solution targeting the 3D thread, implemented purely in Java.

---

# Detection Principle

The core idea is to use an independent monitoring thread to continuously probe the engine main thread's responsiveness. The monitor posts a lightweight task to the main thread and waits for the task to finish. If the main thread fails to complete the task within the allotted time, it is judged as frozen.

The advantages of this approach:

- It doesn't rely on the system ANR mechanism, and can accurately capture freezes inside the target thread's Handler.
- The detection logic runs independently, so it won't fail just because the main thread is stuck.
- It is implemented entirely on the Java side, with no dependency on changes on the 3D side.

# The Implementation

The monitor class extends Thread and runs the detection logic in its own independent thread. It holds a reference to the engine main thread's Handler, used to post the detection task.

```java
package com.engine.monitor;

import android.os.Handler;
import android.os.Process;
import android.util.Log;

public class ThreadMonitor extends Thread {

    private static final String TAG = "ThreadMonitor";
    //- Timeout threshold; if the target thread doesn't respond within this time, it's judged as frozen
    private static final int TIMEOUT = 8000;
    //- Detection interval; the wait time after each detection round completes
    private static final int INTERVAL = 1000;
    //- Max retries; the process is terminated only after consecutive timeouts exceed this count
    private static final int MAX_RETRY = 3;

    private final Handler targetHandler;
    private final Object lock = new Object();
    private int retryCount = 0;

    public ThreadMonitor(Handler handler) {
        targetHandler = handler;
        start();
    }

    @Override
    public void run() {
        while (!isInterrupted()) {
            long start = System.currentTimeMillis();
            
            synchronized (lock) {
                targetHandler.post(() -> {
                    synchronized (lock) {
                        lock.notify();
                    }
                });

                try {
                    lock.wait(TIMEOUT + 1000);
                } catch (InterruptedException e) {
                    return;
                }
            }

            if (System.currentTimeMillis() - start >= TIMEOUT) {
                if (++retryCount > MAX_RETRY) {
                    Log.e(TAG, "Terminating process");
                    Process.sendSignal(Process.myPid(), Process.SIGNAL_KILL);
                } else {
                    Log.e(TAG, "Dumping stack, retry: " + retryCount);
                    Process.sendSignal(Process.myPid(), Process.SIGNAL_QUIT);
                }
            } else {
                retryCount = 0;
            }

            try {
                Thread.sleep(INTERVAL);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    public void shutdown() {
        interrupt();
    }
}
```

## The Detection Flow

1. The monitoring thread records the start time
2. It posts a heartbeat task to the target thread; when the task executes, it releases the synchronization lock
3. The monitoring thread waits for the lock to be released
4. If the target thread executes normally, it releases the lock, and the monitoring thread continues to the next detection round
5. If the target thread is frozen, the lock is never released, and after timing out the monitoring thread declares an ANR
6. On the first timeout, it dumps the thread stacks; after consecutive timeouts exceed the retry limit, it terminates the process

# Integration

The monitor class needs to hold a reference to the engine main thread's Handler. Therefore the integration has to happen in the engine's main thread. For example, in the Unity engine, you should create this watchdog inside the run of UnityMainThread in UnityPlayer.java.

# Closing Words

This proactive ANR detection solution uses an independent thread to monitor the target thread's responsiveness, and can promptly discover thread freezes in 3D HMI scenarios. The solution is simple to implement, but precisely because it only watches the thread's external feedback and doesn't look at engine-internal or business-internal logic, it isn't comprehensive enough and needs a heartbeat mechanism on the 3D side as a complement.
