---
title: "Cockpit 3D HMI Development Framework: The Reference Pool"
lang: en
date: 2026-07-24
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> What's common in development: pre-instantiate some objects (GameObjects) and activate them from the object-pool list when they're needed. Hence the name object pool. But the objects aren't limited to engine prefabs — they can also be pure C# reference objects.

This article shares the framework's reference pool, `ReferencePool`, which is dedicated to pooling C# reference-type objects.

The reference pool is likewise designed for memory utilization efficiency, avoiding frequent GC. It mainly targets temporary data structures — data objects that are short-lived, small, and allocated at high frequency.

*[Figures omitted; see the original WeChat article]*

In short, it exists to **give all "recyclable pure C# objects" one unified entry point, auto-sorted by type, so callers never need to care about instance management policy.**

---

## Design and Implementation

*[Figures omitted; see the original WeChat article]*

###  `ReferencePool`

Design a global static class that maintains a dictionary mapping different `Type`s to reference collections (`ReferenceCollection`). All the user needs to know: when you need an object of a class, Acquire it; when you're done, Release it.

```csharp
public static partial class ReferencePool
{
    private static readonly Dictionary<Type, ReferenceCollection> s_Collections
        = new Dictionary<Type, ReferenceCollection>();

    public static T Acquire<T>() where T : class, IReference, new()
    {
        return GetCollection(typeof(T)).Acquire<T>();
    }

    public static void Release(IReference reference)
    {
        if (reference == null) throw new Exception("Reference is invalid.");
        GetCollection(reference.GetType()).Release(reference);
    }

    public static void ClearAll()
    {
        // Wipe out all buckets in one go on framework shutdown
    }
}
```

### `IReference`

Types supported by the reference pool must implement the `IReference` interface, which only stipulates implementing the Clear action to be performed when the object is returned. The goal is to guarantee that Clear is definitely called on Release.

```csharp
// Source path: Assets/Scripts/Core/ReferencePool/IReference.cs
// The following is illustrative code — aligned with the production logic but not a verbatim copy
public interface IReference
{
    void Clear();
}
```

### `ReferenceCollection`

The reference collection uses a Queue to implement the concrete counting, storage, allocation, and recycling:

Acquire flow: increment counters → lock and check the Queue → if one exists, Dequeue and reuse → otherwise allocate with new T().

Release flow: first call reference.Clear() to clear the fields, then Enqueue back into the queue.

For double releases, you can choose whether or not to throw.

```csharp
private sealed class ReferenceCollection
{
    private readonly Queue<IReference> m_References;
    private readonly Type m_ReferenceType;
    private int m_UsingReferenceCount;
    private int m_AcquireReferenceCount;
    private int m_ReleaseReferenceCount;

    public T Acquire<T>() where T : class, IReference, new()
    {
        m_UsingReferenceCount++;
        m_AcquireReferenceCount++;
        lock (m_References)
        {
            if (m_References.Count > 0)
                return (T)m_References.Dequeue();
        }
        return new T();   // allocate only when the pool is empty; reuse after the peak
    }

    public void Release(IReference reference)
    {
        reference.Clear();   // clear first, then enqueue — the order must not be reversed
        lock (m_References)
        {
            if (m_EnableStrictCheck && m_References.Contains(reference))
                throw new Exception("The reference has been released.");
            m_References.Enqueue(reference);
        }
        m_ReleaseReferenceCount++;
        m_UsingReferenceCount--;
    }
}
```

### Preallocation

`ReferencePool` also implements two extra capabilities:

```csharp
// Preallocation: batch-create a batch of objects and stuff them into the pool, good for warm-up at startup
ReferencePool.Add<EventNode>(50);

// Shrinking: remove a given number of idle objects from the pool, good for cleanup after a peak
ReferencePool.Remove<EventNode>(30);
```

`Add` is useful during the startup phase: for example, if you know a module handles at most 50 events concurrently, you can consider building those objects ahead of time.

---

## Usage Example

The usual usage pattern for the reference pool:

1. `Acquire`
2. Fill fields / Initialize
3. Use
4. `Release` (Clear happens inside).

For example, **events**:

```csharp
private sealed class Event : IReference
{
    public object Sender;
    public BaseEventArgs EventArgs;

    public static Event Create(object sender, BaseEventArgs e)
    {
        var node = ReferencePool.Acquire<Event>();
        node.Sender = sender;
        node.EventArgs = e;
        return node;
    }

    public void Clear()
    {
        Sender = null;
        EventArgs = null;
    }
}
```

1. The Event node uses the reference pool: it's obtained from the pool via the static Create method, and after use the outside caller returns it via ReferencePool.Release(node).
2. On return, Clear() executes automatically, nulling out the Sender and EventArgs references.
3. The caller (business code) only needs to call Event.Create(sender, args) to get a node, without ever caring that the pool exists.

*[Figures omitted; see the original WeChat article]*

---

## Closing Thoughts

The reference pool is currently used mainly inside the framework layer, where the scope of development is controllable, so the design stays fairly simple: one Type maps to exactly one reference collection, with unlimited capacity by default.

But at more complex business levels — say, the same class needs different managing collections; or the same class gets created and cleaned up through different means in different business scenarios — ReferencePool's flexibility isn't enough. So there's also an ObjectPool, which I'll share in a later article.
