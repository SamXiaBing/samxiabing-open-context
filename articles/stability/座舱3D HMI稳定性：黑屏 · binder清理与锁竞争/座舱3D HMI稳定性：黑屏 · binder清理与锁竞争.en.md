---
title: "Cockpit 3D HMI Stability: Black Screens · Binder Cleanup and Lock Contention"
date: 2026-08-24
series: stability
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> Starting with this article, I'll share how I handled some stability problems — black screens, freezes, and the like.
>
> Since this content is already history, the solutions' effectiveness is bounded by the modified system, service architecture, and engine version of the time. Don't copy them blindly.

For 3D HMI, the most frequent and most annoying problem is the black screen — especially when it's intermittent.

# Symptoms

> "The 3D UI occasionally goes black. After it blacks out, the service-based rendering process gets restarted by the system; it comes back up and goes black again. After several rounds, the picture returns to normal."

---

# Background

This project used Tuanjie Engine 1.5.3 with a **service-based rendering architecture**. The 3D rendering runs in a separate process, while other system apps (desktop, air conditioning, etc.) deliver Surfaces and events to the rendering service across processes via binder.

![1](./1.png)

When each client registers, the rendering service's `TuanjieC2SMessenger`:

1. Stores the client's `ITuanjieS2CMessenger` reference in `mAllS2CMessenger`
2. Calls `linkToDeath` to register a death callback for that binder

When a client process dies unexpectedly (killed by the system, crashed, or killed as ANR), the binder driver calls back `binderDied()`. Upon receiving the callback, the rendering service must clean up that client's Surface, View, and connection state.

**The problem lies precisely in this "cleanup" step.**

---

# The Lock Trap

In the engine's bundled `TuanjieC2SMessenger.java`, the binder death callback looks like this:

```java
// Tuanjie 1.5.3 PlaybackEngines/HMIAndroidPlayer/Source/com/unity3d/renderservice/TuanjieC2SMessenger.java

@Override
public void binderDied() {
    synchronized (this) {           // ← Holds the lock
        cleanUpAllS2CMessenger(false);
    }
}

public void cleanUpAllS2CMessenger(boolean isForceRemove) {
    synchronized (this) {           // ← The same lock
        Iterator<Map.Entry<String, ITuanjieS2CMessenger>> iterator =
            mAllS2CMessenger.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<String, ITuanjieS2CMessenger> entry = iterator.next();
            try {
                IBinder binder = entry.getValue().asBinder();
                if (binder.isBinderAlive() && !isForceRemove)
                    continue;

                iterator.remove();
                // All 5 of the following steps execute inside the lock
                TuanjieViewManager.getInstance().cleanupViewWhenClientDied(entry.getKey());
                TuanjieViewManager.getInstance().onClientConnectionChange(entry.getKey(), false);
                TuanjieAppViewManager.getInstance().OnClientDisconnect(entry.getKey());
                notifyClientConnectStatus(false, entry.getKey());
                binder.unlinkToDeath(this, 0);
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}
```

Looks fine at first glance: the binder died, clean up while holding the lock, release the lock when done.

**But the "cleanup" can be a heavy task:**

- `cleanupViewWhenClientDied`: traverses the View tree, releases the Surface, recycles the Display
- `onClientConnectionChange`: notifies the engine of internal state changes, possibly triggering render reconstruction (uncertain)
- `OnClientDisconnect`: notifies of client disconnection
- `notifyClientConnectStatus`: broadcasts the connection state change to all listeners
- `unlinkToDeath`: removes the death listener

These 5 steps all execute synchronously inside `synchronized(this)`. The first one is obviously the heaviest — it can take several hundred milliseconds.

---

# Why It Black-Screens

The rendering service's `this` lock is contended by the following threads:

- The thread that polls data from the message queue every frame and iterates `mAllS2CMessenger.values()` to send to clients. That iteration also holds `synchronized(this)`.
- Operations like client registering/deregistering Surfaces go through `RemoteBinder`, which also holds `synchronized(this)`.

`binderDied()` is called back on a Binder thread. When the binder-death cleanup holds the `this` lock for several hundred milliseconds, the data-sending thread gets blocked → the rendering service can't push data to clients this frame → the client's Surface receives no new frame → black screen.

If the system restarts the client process, the new binder registration also comes to grab the `this` lock (`registerS2CMessenger` holds the lock too), but the cleanup hasn't finished yet → an even longer block → the black screen continues.

---

# The Fix

Lighten the workload inside the lock:

*[Figures omitted; see the original WeChat article]*

## 1. Inside the Lock

```java
    // stage1: inside the lock, only collect the targets to clean up; no heavy work
    synchronized (this) {
        Iterator<Map.Entry<String, ITuanjieS2CMessenger>> iterator =
            mAllS2CMessenger.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<String, ITuanjieS2CMessenger> entry = iterator.next();
            try {
                IBinder binder = entry.getValue().asBinder();
                if (binder.isBinderAlive() && !isForceRemove)
                    continue;
                iterator.remove();
                cleanupTargets.add(new Pair<>(entry.getKey(), binder));
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
```

Inside the lock: iterate, check `isBinderAlive`, `iterator.remove` + collect into a list. All three are lightweight operations, so the lock hold time is extremely short.

## 2. Outside the Lock

```java
    // stage2: clean up one by one outside the lock
    for (Pair<String, IBinder> target : cleanupTargets) {
        try {
            String pkgName = target.getFirst();
            IBinder binder = target.getSecond();

            TuanjieViewManager.getInstance().cleanupViewWhenClientDied(pkgName);
            TuanjieViewManager.getInstance().onClientConnectionChange(pkgName, false);
            TuanjieAppViewManager.getInstance().OnClientDisconnect(pkgName);
            notifyClientConnectStatus(false, pkgName);
            binder.unlinkToDeath(this, 0);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
```

The real heavy work — Surface recycling, View cleanup, state notifications — now executes outside the lock. **It no longer blocks other threads**. The data-sending thread and the IPC registration thread can acquire the `this` lock, and rendering is not interrupted.

> One further change worth making: the data-sending thread's list can be copied inside the lock and iterated outside, avoiding modification during iteration.

---

# Closing Thoughts

**This change modifies the engine's bundled Java source template**, not Unity C# scripts. After the change, you need to verify it won't be overwritten when upgrading the engine version.

The stability of 3D HMI depends not only on whether the business code has problems, but also on whether the thread handling on the engine's Android side is robust. And these problems tend to occur on the Android side — in territory that 3D developers aren't so familiar with.
