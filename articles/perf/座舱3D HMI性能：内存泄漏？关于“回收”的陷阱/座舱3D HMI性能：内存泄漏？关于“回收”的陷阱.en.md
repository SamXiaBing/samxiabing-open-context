---
title: "Cockpit 3D HMI Performance: Memory Leak? The Trap of “Recycling”"
lang: en
date: 2026-09-07
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> The problem discovered in this article is steadily rising memory usage — no black screens, no crashes, memory just keeps climbing. On the surface it looks like a memory leak, but in this case the crux lies in the reference pool.

# Symptoms

Running monkey tests, the illustrative data is as follows:


| Process                | Observed behavior                                                 |
| ---------------------- | ----------------------------------------------------------------- |
| 3D car-model home screen | 1–1.5 G under normal operation; 2 G+ after 15 hours of monkey      |
| SR                     | Road test: linear growth to 4 G+ within 2 hours                    |


Characteristics:

1. **Progressive growth**: memory correlates with test duration; the longer monkey runs, the higher it goes.
2. **It hits different 3D apps alike**: both the car-model home screen and SR leak.

---

# Root Cause Analysis

Build a development package and rerun 1–2 hours of monkey testing / road testing. Capture profiler data before and after, look at the Memory section, or take a Memory Snapshot — you can see the ReferenceCollection/IReference-related classes in the type list growing noticeably in memory.

After spotting this suspicious object, I added printing of UsingReferenceCount and retested, finding that **the reference pool only grew, never shrank**: `ReferencePool`'s `UsingReferenceCount` kept rising, and calling `GC.Collect()` did nothing.

## The Reference Pool

I previously wrote an article on the reference pool: it is an object reference module built on the `IReference` interface, whose core idea is that objects are not destroyed after use but returned to the pool for reuse, avoiding high-frequency create/destroy.

```csharp
// Illustrative code
public static partial class ReferencePool
{
    // Global dictionary: one reference collection per type
    private static readonly Dictionary<Type, ReferenceCollection> s_ReferenceCollections
        = new Dictionary<Type, ReferenceCollection>();

    // Take from the pool; new one if none
    public static T Acquire<T>() where T : class, IReference, new()
    {
        return GetReferenceCollection(typeof(T)).Acquire<T>();
    }

    // Return to the pool
    public static void Release(IReference reference)
    {
        GetReferenceCollection(reference.GetType()).Release(reference);
    }

    // The only cleanup entry point
    public static void ClearAll()
    {
        foreach (var collection in s_ReferenceCollections.Values)
        {
            collection.RemoveAll();
        }
        s_ReferenceCollections.Clear();
    }
}
```

The code has two hidden hazards:

**First, Acquire and Release must be paired.** As long as a single Acquire is never followed by a Release, that object is occupied forever — strongly referenced by business code and unable to be reclaimed by the GC.

**Second, the pool itself has no periodic cleanup mechanism.** The whole reference-pool system has only one cleanup entry, `ClearAll()`, and it only clears the idle queues. Nothing in the previous code ever called it on a schedule; the result was a pileup of unused objects residing in memory forever — the pool's total only ever grew.

> The GC's reclamation logic performs reachability analysis starting from GC Roots; only unreachable objects get reclaimed. The reference pool itself hangs off a global static dictionary, and every object in the pool has a complete strong-reference chain. That's why `GC.Collect()` did nothing.
>
> The reference pool's design is fine in itself — but you can't expect to hand the entire reclamation duty to the GC.

# The Solution


| Layer            | Action                                              | Goal                                                          |
| ---------------- | --------------------------------------------------- | ------------------------------------------------------------- |
| Business layer   | Complete Acquire/Release pairing + log level downgrade | Eliminate the leak source and reduce GC pressure              |
| Framework layer  | **MemoryManager periodically cleans the reference pool** | Catch business omissions as a safety net and cap the pool |


**Periodic fallback cleanup is the simplest, least error-prone path.** Business-side Acquire/Release pairing is the first line of defense; MemoryManager is the second.

## The MemoryManager Implementation

What MemoryManager does is: when it is created, it starts a timer that periodically cleans the reference pool. It can be registered into the application's Context.

```csharp
// Illustrative code
namespace Engine.Runtime
{
    public class MemoryManager : MyService
    {
        protected override void OnCreate()
        {
            // Run the reference pool cleanup every 120 seconds
            InvokeRepeating(nameof(ClearReferencePool), 120f, 120f);
        }

        private void ClearReferencePool()
        {
            // ② Release unused engine-side resources (textures, meshes, etc.)
            Resources.UnloadUnusedAssets();
            // ③ Clear the reference pool's idle queues
            ReferencePool.ClearAll();
            // ④ Trigger a full GC
            GC.Collect();
        }
    }
}
```

## Other Findings

During the investigation, some object subclasses turned out to have empty `Clear()` implementations. When the object was returned to the pool, its internal string references were still attached; the strings kept occupying pool memory — treating the symptom, not the cause. The correct way:

```csharp
public virtual void Clear()
{
    MapObjectType = null;   // release the string reference
    StyleName = null;       // release the string reference
    // subclasses keep clearing their own fields
}
```

---

# Conclusion

This reference-pool bug is, at its core, a reminder to me that **an object pool's "recycling" may not truly be recycling — it may be "postponement".** If the pool has no cleanup mechanism, it merely postpones "recycling" to some far-off later time, which is no different from a leak.