---
title: "Cockpit 3D HMI Performance: The Symmetry of Object Pool Acquisition and Reclamation"
lang: en
date: 2026-09-14
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article covered potential loopholes in the reference pool. This one targets the object pool, sharing the memory-control problems it caused.

On the road to polishing SR performance, perceived targets are sometimes numerous, then suddenly sparse again after passing an intersection. In scenarios where the count of spawned objects swings violently, we put every spawned object in the business onto object pools to keep GC from firing as much. But two anomalies showed up one after another: memory climbing past 1 GB with no sign of coming back down, and perceived objects suddenly disappearing from the scene.

---

# 1. Memory Still Climbs

The SR application receives messages from the Android side over UDP at high frequency. After running for a few dozen minutes, memory climbs all the way up, and even in the steady state it sits at about 1 GB. That number is clearly not normal.

## Diagnosis

The message parsing entry point:

```csharp
switch (kind[0])
{
    case '1':
        // ❌ Every message news one up, then throws it to GC after use
        packet = new IntMessage();
        packet.Decode(json.ToString());
        break;
    // case '2' and '3' likewise new up DoubleMessage and StringMessage
}
```

Three message types, all directly `new`ed. A message arrives, a new object is created, and after use it is tossed to the GC.

## Root Cause

The mistake here was carelessness in message handling: objects were only created, and the object pool was never actually used. The correct approach for this kind of business code is:

```csharp
var msg = MessagePool.Get<SomeMessage>();
msg.Decode(reader);
```

In one project, two styles coexisted, and one of them was clearly wrong. With a message stream at a dozen or even dozens of Hz on this side, hundreds to thousands of temporary objects were produced every second, and memory kept climbing.

## The Fix

Add a `Create()` factory method to each of the three message classes, handing object acquisition over to the object pool:

```csharp
public static IntMessage Create()
{
    return MessagePool.Get<IntMessage>();
}
```

Then replace every `new` in the project. The parsing entry point:

```csharp
case '1':
    packet = IntMessage.Create();   // ✅ Taken from the pool
    packet.Decode(json.ToString());
    break;
```

Same for the sender side:

```csharp
var msg = StringMessage.Create();
msg.Kind = kind;
msg.Payload = payload;
sender.Send(msg);
```

So: whenever you create something, think of the object pool / reference pool. As long as a single `new` remains in the code, a hidden risk may linger.

---

# 2. Perceived Objects Suddenly Disappear

## Symptoms

The other reported problem was perceived objects suddenly not showing during road tests, with some stuttering also visible in the SR UI.

## Diagnosis

Going through the commit history, the problematic version was exactly the one that integrated the object pool. Checking the reclamation logic:

```csharp
public override void OnPut()
{
    foreach (var binder in _binders)
    {
        binder.Put(Data);
    }
    // New: on reclamation, return the GameObject to the factory
    if (_gameObject != null)
    {
        Context.GetPrefabPool().Dispose(_gameObject);
        _gameObject = null;
    }
    base.OnPut();
}
```

The intent was that a GameObject is a fairly heavy object, so we would return it while we were at it during reclamation. But we only did the returning — we made no arrangement whatsoever for the next rebuild.

## Root Cause

The `Rebuild` method carries a skip check:

```csharp
private void Rebuild()
{
    string prefabPath = Context.GetStyleSystem().GetStyle(StyleName).PrefabPath;

    // ❌ Skips if the path hasn't changed, without checking whether the object still exists
    if (_prefabPath == prefabPath)
    {
        return;
    }
    // ... Create the GameObject, attach the data binders
}
```

The object pool provides two lifecycle hooks, OnGet and OnPut. Rebuild does not belong to the pool's acquisition phase; the acquisition phase only writes the new target's name into the data object.

GameObject construction happens in the usage phase. When OnUpdate detects the need to build, it calls Rebuild to complete GameObject instantiation and hookup. In this mechanism, taking an object out of the pool only guarantees that the data object is usable; construction of the render entity depends on a later check condition to trigger.

Therefore, taking an object out of the pool does not mean the render entity is ready — a construction check sits between the two.

![1](./1.png)

## The Fix

When returning, every destroy must be paired with a rebuild flag, and the old path cleared while we are at it:

```csharp
public override void OnPut()
{
    foreach (var binder in _binders)
    {
        binder.Put(Data);
    }
    if (_gameObject != null)
    {
        Context.GetPrefabPool().Dispose(_gameObject);
        _gameObject = null;
    }
    NeedRebuild = true;    // ✅ Destroy paired with a rebuild flag
    _prefabPath = null;    // ✅ Clear the old path to prevent misjudgment on reuse
    base.OnPut();
}
```

On the reuse side, the skip condition is completed:

```csharp
// ✅ Only skip if the path is unchanged AND the object still exists
if (_prefabPath == prefabPath && _view != null)
{
    return;
}
```

Any destruction done on the return side must find its matching counterpart on the acquisition side and be compared against it.

---

# Closing Thoughts

An object pool's lifecycle must consider the get and return sides at the same time. When it comes to reuse conditions, you need to think not only about equality at the resource/asset level, but also about changes at the rendering and state levels.
