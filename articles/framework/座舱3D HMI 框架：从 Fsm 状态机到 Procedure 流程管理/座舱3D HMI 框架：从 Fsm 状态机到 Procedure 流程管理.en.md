---
title: "Cockpit 3D HMI Framework: From the Fsm State Machine to Procedure Flow Management"
lang: en
date: 2026-08-21
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> A state machine is something almost every 3D application development framework must have. Conceptually, our applications are function-aggregating and scene-paginated. That pattern naturally gives rise to the concept of states: we fill in and group related items by state, and abstract each collection into a state to be managed. They get lifecycles, transitions, and detailed management in between.

This article covers the framework's state machine `Fsm<T>` and the flow management system `Procedure` built on top of it.

The former solves: how states are defined, and how they're centrally driven and switched. The latter solves: using the state machine to orchestrate an application's global flow, from startup through its various business features.

---

# Overview

`Fsm<T>` is a generic class where `T` is the "owner" type. We never need an abstract state machine — there's always some business requirement attached; call it `T`, and let it be injected into a state machine to become its soul. For example `Fsm<IProcedureManager>`, `Fsm<SceneStateManager>`, `Fsm<CameraManager>`. Each time you specify a `T`, it's as if you used the `Fsm` state-machine mold to cast a concrete state machine.

So `Fsm` provides three capabilities — registering states, centralized driving, and switching — but which states it manages, when it jumps, and what it does after jumping depends entirely on who `T` is.

`Procedure` is one concrete product cast from this mold: a management tool for sub-business flows within a Scene/Map, broadly understood. The `ProcedureManager` maintains an `Fsm<IProcedureManager>` internally, and everything it does serves the specific business semantics of **"flow"**: `Initialize` (build the Fsm + subscribe to events), `StartProcedure` (start the entry procedure), `OnFsmChanged` (forward as `ProcedureChangedEventArgs`).

Illustrative code:

```csharp
public void Initialize(IFsmManager fsmManager, params ProcedureBase[] procedures)
{
    _fsmManager = fsmManager;
    // Cast a concrete procedure state machine from the mold
    _procedureFsm = _fsmManager.CreateFsm(this, procedures);
    _procedureFsm.OnFsmChanged += OnFsmChanged;   // convert Fsm switches into procedure-changed events
}
```

We should also add the `ProcedureBase` code here. It's a description of a state — essentially a mountable business component, itself an abstract class that can be implemented:

```csharp
public abstract class ProcedureBase : MonoBehaviour, IFsmState<IProcedureManager>
{
    public void Init(ProcedureOwner procedureOwner)
    {
        Owner = procedureOwner;
        OnInit();        // initialization hook
    }
    public virtual void OnInit() { }
    public virtual void OnEnter() { }
    public virtual void OnUpdate(float elapseSeconds, float realElapseSeconds) { }
    public virtual void OnLeave() { }
    public virtual void Clear() { }
}
```

> Of course, if you want to build a state machine for other business semantics — say, a camera animation state machine — you can create a `CameraAnimStateBase` (defining some interfaces like enter, update, and leave), then use a `CameraStateManager` to maintain an `Fsm<CameraAnimStateBase>` state machine. When the camera needs to drive an animation, just have the Fsm jump states, and each concrete class inheriting `CameraAnimStateBase` executes the specific operations needed for the previous camera state to exit and the next one to enter.

# UML Class Diagrams

## Fsm

![1](./1.png)

- `IFsmBase` is the non-generic base interface (for `FsmManager`'s unified management); `IFsm<T>` inherits it generically and adds business semantics.
- `Fsm<T>` implements both `IFsm<T>` and `IReference` (poolable), and internally aggregates a set of `IFsmState<T>`.
- `FsmManager` manages a dictionary of `IFsmBase`, responsible for creation and centralized driving.

## Procedure

![2](./2.png)

- `ProcedureBase` implements `IFsmState<IProcedureManager>` — a procedure is essentially a state.
- `ProcedureManager` aggregates `IFsm<IProcedureManager>` — the manager holds a state machine internally.
- `IProcedureManager` inherits `IFrameworkModule`; understand it as being used as a framework module that gets loaded and unloaded.

# Usage Flow

![3](./3.png)

- The initialization phase runs from `Setup` to `StartProcedure`, completing registration and startup.
- After that, every frame `Framework.OnUpdate` drives `FsmManager`, which in turn drives the concrete `Fsm` and its current state.
- On state switches, `DoTransfer` executes the enter/leave lifecycle callbacks and broadcasts the event.

# Fsm

## States

States are defined through the `IFsmState<T>` interface, which clearly declares the lifecycle functions:

```csharp
public interface IFsmState<T> where T : class
{
    public string Name { get; }                        // the state's name
    public void Init(IFsm<T> fsm);                     // initialized once when registered into the Fsm
    public IFsm<T> Owner { get; set; }                 // back-reference to the state machine
    public void OnEnter();                             // enter the state
    public void OnUpdate(float elapse, float realElapse); // polled every frame
    public void OnLeave();                             // leave the state
    public void Clear();                               // cleanup when the Fsm is destroyed
}
```

- `Init` runs only once, at creation.
- `OnEnter/OnUpdate/OnLeave` are the runtime loop of repeated enter/exit cycles.

## Centralized Driving

The state machine engine uses **centralized driving**. Each frame, `FsmManager` calls `fsm.Update` on every registered Fsm one by one; inside `Fsm.Update`, the current state's `OnUpdate` gets called. Outside business code doesn't need to care about any of the details.

```csharp
public void Update(float elapseSeconds, float realElapseSeconds)
{
    m_TempFsms.Clear();
    foreach (var fsm in m_Fsms) m_TempFsms.Add(fsm.Value);  // copy first to avoid modifying during iteration

    foreach (IFsmBase fsm in m_TempFsms)
    {
        if (fsm.IsDestroyed) continue;
        fsm.Update(elapseSeconds, realElapseSeconds);       // drive uniformly
    }
}
```

## Switching and Pooling

Switching is the Fsm's core action, performed by the illustrative function `DoTransfer`. Its main duties: record the previous state, hook up the new state, then the old state's `OnLeave` and the new state's `OnEnter`, and finally broadcast an `FsmChanged` event.

```csharp
private void DoTransfer(IFsmState<T> from, IFsmState<T> to)
{
    _lastState = from;
    _currentState = to;

    if (from != null) from.OnLeave();   // the old state exits
    to.OnEnter();                       // the new state enters

    if (_onFsmChanged != null && from != null)
    {
        var args = FsmChangedEventArgs.Create(from.Name, to.Name);
        _onFsmChanged(this, args);      // broadcast the switch
        args.Release();                 // return the event args to the reference pool
    }
}
```

`Fsm<T>` can use the reference pool at creation time — it implements `IReference`:

```csharp
// The following is illustrative code
public static Fsm<T> Create(string name, T owner, params IFsmState<T>[] states)
{
    Fsm<T> fsm = ReferencePool.Acquire<Fsm<T>>();  // borrow
    // ... register states, bind the Owner
    return fsm;
}

public void Shutdown()
{
    ReferencePool.Release(this);  // return
}
```

# Procedure

For the Procedure part I won't show code — there's too much of it, and it's tiring to read anyway. Based on the UML above, here's a quick sketch of the relationships:

`ProcedureManager` is a module inside the framework, designed as a pure C# class rather than a `MonoBehaviour`. Business code doesn't use it directly; instead, you need a class that, in the scene, helps collect `ProcedureBase[]` and hands it to the framework-level `ProcedureManager`.

Hence the component called `ProcedureComponent`: a `MonoBehaviour` mounted in the scene, acting as the bridge between the business layer and `ProcedureManager`.

`ProcedureComponent` exposes a `Setup` method; the business side calls this method to complete procedure registration and startup.

Step one of `Setup` calls `Initialize`, passing a set of `ProcedureBase` to `ProcedureManager`, which internally uses `FsmManager.CreateFsm` to build a procedure state machine; step two calls `StartProcedure`, specifying the entry procedure and starting it.

> To summarize this: `ProcedureManager` is the chef doing the cooking; `ProcedureComponent` is the waiter.

`ProcedureManager` also subscribes to the underlying Fsm's `OnFsmChanged` event and broadcasts it on every state machine switch. That way, what the business layer perceives is "the procedure changed", not the low-level "the Fsm switched" — much closer to how the business layer thinks.

# Closing Thoughts

I first encountered finite state machine design in UnityGameFramework. Later, during cockpit HMI project deliveries, my colleagues adopted it as an important module. Back then, the 3D car-model launcher app would have a loading state, a vehicle-control state, a charging state, scene-mode states × N. Every state involved managing the show/hide and animation of objects in the scene.

The next article plans to share the framework's Module concept — how modules like `FsmManager` and `ProcedureManager` are abstracted, organized, and driven.
