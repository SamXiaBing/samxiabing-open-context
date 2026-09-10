---
title: "Cockpit 3D HMI Framework: The EventPool Event Dispatching Mechanism"
date: 2026-08-14
series: framework
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In application development, every instantiated service and controller needs to send messages to other objects, or receive messages from them. So an event mechanism is standard equipment in almost every development framework.

The point of using an event mechanism is to decouple the different business modules as much as possible. Be a broadcaster at a radio station, letting anyone who wants the information tune in by themselves — not a postman delivering telegrams door to door.

The most typical scenario: once the day/night mode changes, many things are affected — the UI needs to swap images, the car model needs to swap materials, the scene needs to swap post-processing effects. If all of this had to be managed centrally by the day/night mode manager, then every newly added item needing to change would have to be declared and coded inside the manager — not easy at all.

This article covers `EventPool<T>` in the framework — a bus that "only cares about events". Event sources just send; interested parties just listen; neither side references the other directly.

# Data Flow

![](./image.png)

# UML Class Diagram

![](./image.png)

- Other business modules only touch `EventBus`, a static entry point that forwards `Register / Send` to `EventManager`.
- `EventManager` implements the `IEventManager` interface and internally holds an `EventPool<BaseEventArgs>`.
- `EventPool` manages the event queue and the Handler chains.
- `Event` is a poolable event node.

# EventBus

Business modules use the event system through the static class `EventBus`. It exposes four methods:

```csharp
// The following is illustrative code
public static class EventBus
{
    public static void Register(int id, EventHandler<BaseEventArgs> handler);
    public static void UnRegister(int id, EventHandler<BaseEventArgs> handler);
    public static void Send(object sender, BaseEventArgs e);     // thread-safe, deferred dispatch
    public static void SendNow(object sender, BaseEventArgs e);   // immediate dispatch, not thread-safe
}
```
- `Register` subscribes to an event, `UnRegister` unsubscribes, `Send` sends an event (deferred, dispatched next frame), `SendNow` sends an event (dispatched immediately).
- `EventBus` forwards all calls to `EventManager`.

# EventManager

`EventManager` is the implementation of `IEventManager`, maintaining an `EventPool<BaseEventArgs>`

```csharp
// The following is illustrative code
internal sealed class EventManager : IEventManager
{
    private readonly EventPool<BaseEventArgs> _eventPool;

    public EventManager()
    {
        _eventPool = new EventPool<BaseEventArgs>(
            EventPoolMode.AllowNoHandler | EventPoolMode.AllowMultiHandler);
    }

    public void Update(float elapse, float realElapse)
    {
        _eventPool.Update(elapse, realElapse);   // consume the event queue every frame
    }
}
```
- `EventManager` creates the `EventPool` instance and specifies the mode at construction; on each Update frame it delegates to `EventPool` to consume the queue. On `Shutdown` it cleans up all Handlers and events.

> EventPoolMode is the enum of event modes: exactly one Handler required; no Handler allowed; multiple Handlers for one ID allowed; duplicate Handlers allowed.

# EventPool

`EventPool<T>` is the core of the event system. Its responsibility is solving three main problems: how to store Handlers, how to send events, and how to iterate over Handlers to run callbacks.

```
- public sealed class EventPool<T> where T : BaseEventArgs
{
    private readonly Dictionary<int, EventHandler<T>> _eventHandlers;  // handler chains stored by id
    private readonly Queue<Event> _events;                                  // queue of deferred-dispatch events
    private readonly EventPoolMode _eventPoolMode;                          // behavior mode
}
```

## Subscribing

Depending on the event mode, it performs Add operations against the dictionary:

```csharp
// The following is illustrative code
public void Subscribe(int id, EventHandler<T> handler)
{
    if (!_eventHandlers.Contains(id))
        _eventHandlers.Add(id, handler);                          // first time: create a new chain
    else if ((_eventPoolMode & EventPoolMode.AllowDuplicateHandler) == 0
             && Check(id, handler))
        throw new Exception("not allow duplicate handler");       // duplicate check
    else if ((_eventPoolMode & EventPoolMode.AllowMultiHandler) == 0)
        throw new Exception("not allow multi handler");           // multi check
    else
        _eventHandlers.Add(id, handler);                          // append
}
```

First check whether this ID already has a duplicate handler, then see whether multiple handlers are allowed, and only then append to the chain.

Unsubscribing simply removes the corresponding handler from the chain by id.

## Sending Events

The event system provides two dispatch methods, differing in **whether they go through the queue and whether they're thread-safe**:

```csharp
// The following is illustrative code
public void Send(object sender, T e)
{
    var node = Event.Create(sender, e);
    lock (_events) { _events.Enqueue(node); }   // enqueue, non-blocking
}

public void SendNow(object sender, T e)
{
    HandleEvent(sender, e);                     // dispatch immediately
}
```

`Send()` is thread-safe. No matter which thread calls it, it only creates the event as an Event node and enqueues it; the main thread's `Update` then consumes everything uniformly.

`SendNow()` bypasses the queue and dispatches directly; it is not thread-safe, and the caller must be on the main thread.

`Update` runs on the main thread each frame, `Dequeue`-ing the nodes in the queue one by one, then calling `HandleEvent`, and finally releasing and returning the Event. This way, an event submitted in this frame is fully dispatched by the next frame.

## HandleEvent

The goal is to trigger every EventHandler in the chain once, while guarding against changes to the original chain and also against being affected by temporary modifications to it. So first **copy all** the handler delegate references from the original chain into a temporary chain, then iterate the temporary chain to execute. That way, no matter how the callbacks add to or remove from the original chain, the current traversal is unaffected.

```csharp
// The following is illustrative code
private void HandleEvent(object sender, T e)
{
    if (!_eventHandlers.TryGetValue(e.Id, out var range)) return;

    // Step 1: copy all the handler delegate references from the original chain into a temporary chain
    var cache = new LinkedList<EventHandler<T>>();
    var current = range.First;
    while (current != null && current != range.Terminal)
    {
        _cachedNodes[e] = current.Next != range.Terminal ? current.Next : null;
        cache.AddLast(current.Value);
        current = _cachedNodes[e];
    }

    // Step 2: iterate the temporary chain and run the callbacks
    foreach (var handler in cache)
        handler(sender, e);

    cache.Clear();
    _cachedNodes.Remove(e);
}
```

---

# Event

`Event` is a private class inside `EventPool`, containing two fields: `Sender` and `EventArgs`. It achieves creation by borrowing an Event object from the reference pool:

```csharp
// The following is illustrative code
private sealed class Event : IReference
{
    public object Sender;
    public T EventArgs;

    public static Event Create(object sender, T e)
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

On `Send`, `Create` checks it out; after `Update` finishes dispatching, `Release` returns it. What gets reused here is exactly the `IReference` discussed in the earlier reference pool post.

---

# How to Use It

The complete usage flow has three steps. Step one: define the event args class:

```csharp
// The following is illustrative code
public class DayNightModeChangedEvent : BaseEventArgs
{
    public DayNightMode Mode;

    public static DayNightModeChangedEvent Create(DayNightMode m)
    {
        var e = ReferencePool.Acquire<DayNightModeChangedEvent>();
        e.Mode = m; 
        return e;
    }
}
```

Step two: the sender raises the event: `EventBus.Send(this, DayNightModeChangedEvent.Create(DayNightMode.Night))` (use `SendNow` if it must take effect immediately).

Step three: the receiver registers: `EventBus.Register(OnDayNightModeChanged.Id, OnDayNightModeChanged)`; in the callback, use `as` to cast back to the concrete event type to read the data; on destruction, call `EventBus.UnRegister(OnDayNightModeChanged.Id, OnDayNightModeChanged)` to unsubscribe and prevent memory leaks.

---

# Closing Words

This event mechanism was written with reference to several development frameworks, and was later used in project deliveries. However, the event subscription mechanism isn't always that convenient. As more people and more projects get involved, it can get somewhat out of control.

For example: different colleagues hooked up the same signal and therefore created identical events, causing redundant event code and confusion/ambiguity in the logic code. Or: someone who wasn't the event's original author, upon finding an overlap in logical purpose, proactively fires that event — but he has no idea what all of that event's receivers do, resulting in inappropriately triggering an event he doesn't sufficiently understand.

So when using the event mechanism in delivery, my suggestion is to keep all BaseEventArgs derived classes managed uniformly under one path, with regular reviews. And event responses should have clear log feedback, making it easy to find out how many things a single event triggered.
