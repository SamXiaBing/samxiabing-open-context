---
title: "座舱3D HMI稳定性：黑屏 · STR引发的误杀"
date: 2026-08-31
series: stability
no: 
status: published
visibility: public
wechat_url: ""
---

> 之前写了两篇 ANR 主动检测方案，能在主线程卡死时及时发现并 dump 堆栈。但有一个场景可能会让这套方案的判断出问题：车机进入 STR 状态。

## 一、问题表现

### 1.1 现象：STR后3D黑屏

用户离车后，进入STR，再次上车操作，3D 车模桌面界面黑屏，需要等待引擎重新冷启动才能恢复。

抓日志发现：3D 渲染进程在 STR 期间被 kill 了，kill 信号来自进程内部的 ANR 看门狗，不是系统。

### 1.2 复现方式

这个问题有几个明确的触发条件：

- 车机进入 STR 状态（离车后若干分钟）
- STR 持续时间超过ANR看门狗超时阈值（10秒以上）
- Java 侧的 alive check 在运行

满足这三个条件，误杀几乎是必现的。之所以看起来"偶现"，是因为用户熄火后多久进入 STR、什么时候再次操作，这些时间是随机的。

### 1.3 为什么之前没发现

ANR 看门狗检测机制是（对于当时来说的）近期上线的，测试案例没有测过STR，谁能想到正常行为也会触发看门狗。

## 二、根因分析

STR 是 Android Automotive 的电源管理状态，全称 Suspend To RAM。车机在熄火或进入低功耗模式时，系统会把所有进程挂起到内存中，CPU 停止执行。等用户再次操作时，系统从 RAM 恢复，进程继续运行。要的就是它的系统快速恢复能力。

对3D来说，它意味着麻烦：

- Unity 主线程停止执行，`Update()` 不再调用
- 心跳计数器停止递增
- JNI 调用不再发生
- 渲染管线暂停

### 2.1 Java 侧 alive check 误杀

这套 alive check 机制是当时车型项目中自己在引擎服务层（渲染服务进程）加的，运行在 Android 的主线程 Handler 上：

```java
// TuanjieC2SMessenger.java
private static final int ALIVE_CHECK_INTERVAL = 3_000; // 3秒检查一次

private final Runnable aliveCheckRunnable = new Runnable() {
    @Override
    public void run() {
        if (App.Companion.isAliveCheckEnabled()) {
            int step = anrStep.get();
            int pid = android.os.Process.myPid();
            if (step == 0) {
                long now = SystemClock.elapsedRealtime();
                // 10秒超时
                if (lastAliveTime.get() > 0 && now - lastAliveTime.get() > 10000) {
                    // dump 堆栈
                    var process = Runtime.getRuntime().exec("kill -3 " + pid);
                    anrStep.set(step + 1);
                }
            } else if (step >= 3) {
                // 连续3次超时，杀进程
                android.os.Process.killProcess(pid);
            } else {
                anrStep.set(step + 1);
            }
        }
        mainHandler.postDelayed(this, ALIVE_CHECK_INTERVAL);
    }
};
```

这个看门狗的逻辑是：3 秒检查一次，如果 10 秒内没收到引擎的心跳，先 dump 堆栈；连续 3 次超时就杀进程。

Java 侧的 alive check 跑在系统服务进程里，STR 期间系统服务是否挂起取决于电源管理策略。如果 alive check 所在的进程没有被完全挂起（或者唤醒后 Handler 队列里的消息被一次性执行），它就会拿当前时间去减 STR 之前的 `lastAliveTime`，结果就是差值可能是几分钟甚至几小时，远远超过 10 秒阈值。

> 心跳机制是整个看门狗的输入端：Unity 侧每 2 秒通过 JNI 调用一次 Java 侧的 onHeartBeat()，把 lastAliveTime 刷新为当前时间，后面 alive check 拿这个时间戳做超时判断，心跳断了就认为引擎挂了。

这就是误杀的根因：看门狗用"时间差"判断死活，但它对 STR 是无知的。

> Unity 侧看门狗跑在引擎同进程里，STR 挂起时检测线程也一起冻住，醒后拿不到时间差，天然不会误杀。这跟 Java 侧跨层检测的误杀形成鲜明对照。

## 三、解决方案

STR 期间暂停看门狗，唤醒后重置状态再恢复。

所以要做两件事：

1. 能感知到 STR 状态变化
2. 唤醒时要把看门狗状态清零，不能拿 STR 之前的时间继续算

### 3.1 PowerManager

通过 `CarPowerManager` 监听系统电源状态，代码略，这部分由安卓侧同事修改。

### 3.2 alive check 的暂停与恢复

在构造函数中注册 power mode 监听：

```java
// TuanjieC2SMessenger.java
if (supportCarPower) {
    OnPowerModeActiveListener powerModeActiveListener = isActive -> {
        if (isActive && is3DEngineReady.get()) {
            // 唤醒：重置看门狗状态，重新启动 alive check
            resetAliveCheckState();
            mainHandler.removeCallbacks(aliveCheckRunnable);
            mainHandler.postDelayed(aliveCheckRunnable, ALIVE_CHECK_INTERVAL);
        } else {
            // STR：暂停 alive check
            mainHandler.removeCallbacks(aliveCheckRunnable);
        }
    };
}
```

1. 进入 STR 时：`removeCallbacks(aliveCheckRunnable)`，停掉 alive check，避免误杀
2. 唤醒时：先 `resetAliveCheckState()` 把 `anrStep` 清零、`lastAliveTime` 更新为当前时间，再重新启动 alive check

## 结语

印象中，STR 引发的 3D 黑屏的原因不止一种。本文所说的还算是比较清晰的情况，而往往 STR 可能带来很多莫名其妙的，比如渲染线程进入了 Runnable 的状态却不调度；或是渲染的一切看上去都在跑，但是上屏就是黑的。此时排查这些问题会需要更多的现场数据和怀疑的方向，思路不应被本文禁锢。