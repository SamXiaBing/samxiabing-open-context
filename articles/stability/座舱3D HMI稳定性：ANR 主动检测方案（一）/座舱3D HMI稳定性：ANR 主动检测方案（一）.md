---
title: "座舱3D HMI稳定性：ANR 主动检测方案（一）"
date: 2026-07-03
series: stability
no: 1
status: published
visibility: public
wechat_url: ""
---

> 3D HMI 交付的过程中，有的时候会遇到画面卡死的 bug 单。一般情况下，是因为 3D 引擎的主线程卡死。线程卡死会导致屏幕画面冻结、用户的交互失效。如果没有一套主动发现 ANR 的方法，咱们能得到的只有信息量不够的日志，或者是非问题发生时刻的一些日志。

系统自身的 ANR 机制无法准确捕获 3D 引擎内部的卡死情况，因此咱们需要一套专门的检测方案。本文聚焦**3D HMI场景下的主线程卡死检测**问题**，分享第一套纯通过 Java 脚本去针对 3D 线程的 ANR 检测方案。

---

# 检测原理

核心思路是通过一个独立监控线程，持续检测引擎主线程的响应能力。监控线程向主线程投递一个轻量任务，并等待任务执行完成。如果主线程在规定时间内没有完成任务，就判定为卡死。

这种方法的优势：

- 不依赖系统 ANR 机制，能准确捕获目标线程Handler内部卡死。
- 检测逻辑独立运行，不会因为主线程卡死而失效。
- 完全在 Java 侧实现，不依赖 3D 侧修改。

# 实现方案

监控类继承自 Thread，在独立线程中运行检测逻辑。它持有一个引擎主线程的 Handler 引用，用于投递检测任务。

```java
package com.engine.monitor;

import android.os.Handler;
import android.os.Process;
import android.util.Log;

public class ThreadMonitor extends Thread {

    private static final String TAG = "ThreadMonitor";
    //- 超时阈值，目标线程超过这个时间未响应就判定为卡死
    private static final int TIMEOUT = 8000;
    //- 检测间隔，每次检测完成后的等待时间
    private static final int INTERVAL = 1000;
    //- 最大重试次数，连续超时超过这个次数才会终止进程
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

## 检测流程

1. 监控线程记录开始时间
2. 向目标线程投递心跳任务，任务执行时释放同步锁
3. 监控线程等待锁释放
4. 如果目标线程正常执行，会释放锁，监控线程继续下一轮检测
5. 如果目标线程卡死，不会释放锁，监控线程超时后判定为 ANR
6. 第一次超时时输出线程堆栈，连续超时超过重试次数后终止进程

# 集成方式

监控类需要持有引擎主线程的 Handler 引用。因此需要在引擎主线程中集成。比如在 Unity 引擎中，应该在 UnityPlayer.java 的 UnityMainThread 的run中去创建这个看门狗

# 结语

这套 ANR 主动检测方案通过独立线程监控目标线程响应能力，能够及时发现 3D HMI 场景下的线程卡死问题。方案实现简单，但也因为只关注线程的外在反馈表现,不关注引擎内部或业务内部逻辑而显得不够全面，需要3D侧的心跳机制辅助。