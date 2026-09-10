---
title: "Cockpit 3D HMI Framework: Module Abstraction, Registration, and Scheduling"
date: 2026-08-28
series: framework
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> A module is the collection of core business capabilities in a framework. Modules in a software development framework reflect, in their design, the characteristics of the business the framework serves — and this ultimately shows up in the interface definitions.

An application has many features that need to run every frame: event dispatching, network communication, state machine driving, resource loading, UI, procedures... And crucially, there has to be an ordering among them: the event bus finishes dispatching first, the state machine transitions next, and only then can the procedure get its ready data.

Each module can't go its own way, managing its own `Update`. If the ordering gets messed up, things break. You need something unified to manage these features: define their interfaces, decide their order, and unify their lifecycles. That something is the framework's module system.


![](./image.png)


# IFrameworkModule: The Module Interface

The `IFrameworkModule` interface defines three properties/methods: priority, polling, and shutdown:

```csharp
public interface IFrameworkModule
{
    int Priority { get; }                              // priority; higher goes first
    void Update(float elapse, float realElapse);       // polled every frame
    void Shutdown();                                    // shutdown cleanup
}
```

- `Priority` determines the position in the module chain at registration, and the order in which modules are cleaned up at shutdown.
- `Update` is what happens every frame; `Shutdown` is the cleanup done when the application exits.

The framework's existing modules and their priorities are for reference:


| Module              | Priority | Responsibility          |
| ------------------- | -------- | ----------------------- |
| `EventManager`      | 7        | Event dispatching       |
| `ObjectPoolManager` | 6        | Object pool             |
| `FsmManager`        | 1        | State machine driving   |
| `NetworkManager`    | 0        | Network communication   |
| `ResourceManager`   | 0        | Resource loading        |
| `UIManager`         | 0        | UI management           |
| `ProcedureManager`  | -2       | Procedure orchestration |


Modules with higher priority register earlier, poll earlier, and shut down later. For example, `EventManager` (7) runs first, ensuring the event queue has been consumed before other modules use it; `ProcedureManager` (-2) sits further back, driving the procedures only after the other modules are ready.

# RegisterModule

The core logic of module registration lives in the framework entry's `RegisterModule` method. What it does: traverse the existing module chain, find the first node whose priority is lower than the new module's, and insert before it. If the whole traversal finds none, insert at the end of the chain.

```csharp
public void RegisterModule(IFrameworkModule module)
{
    LinkedListNode<IFrameworkModule> current = _frameworkModules.First;
    while (current != null)
    {
        if (module.Priority > current.Value.Priority)
            break;                          // found the spot, stop
        current = current.Next;
    }

    if (current != null)
        _frameworkModules.AddBefore(current, module);  // insert before it
    else
        _frameworkModules.AddLast(module);             // lowest priority, put at the end
}
```

# GetModule

The GetModule method uses a lazy-loading strategy: first search the chain for a module whose type matches; if found, return it directly; if not, create an instance via reflection, register it into the chain, and then return it.

```csharp
// The following is illustrative code
public TModule GetModule<TModule>() where TModule : IFrameworkModule
{
    var type = typeof(TModule);

    // Look for an already-registered one first
    foreach (var module in _frameworkModules)
    {
        if (module.GetType() == type)
            return (TModule)module;
    }

    // Not found; create via reflection and register
    TModule moduleImpl = (TModule)Activator.CreateInstance(type);
    RegisterModule(moduleImpl);
    return moduleImpl;
}
```

# OnUpdate: Forward Traversal

Each frame is just a traversal of the chain, calling `Update` one by one from head to tail — and head to tail means from high priority to low priority:

```csharp
// The following is illustrative code
public void OnUpdate(float elapseSeconds, float realElapseSeconds)
{
    for (var current = _frameworkModules.First; current != null; current = current.Next)
    {
        current.Value.Update(elapseSeconds, realElapseSeconds);
    }
}
```

# Shutdown: Reverse-Order Cleanup

At shutdown it's the reverse — traverse from the tail of the chain backward:

# AppRunner

The modules in the development framework are designed not to be coupled to the engine; they independently abstract the business shape. So they are all pure C# classes, inheriting neither `MonoBehaviour` nor `UActorComponent`. They have no `Update` mechanism of their own, so someone needs to call them every frame. In past projects, that someone was named `AppRunner` — a `Singleton` attached to a `GameObject`/`AActor` in the scene/level. Its `Update` is the heart of the whole framework, passing the engine's `Update`/`Loop` to the framework, which then drives all modules uniformly:

```csharp
// Illustrative code (Unity)
private void Update()
{
    Framework.OnUpdate(Time.deltaTime,
    Time.unscaledDeltaTime);
}
```

# The Complete Chain


![](./image.png)


# Closing Words

The mechanism of using **priority ordering** combined with a linked list to control module runtime ordering lets every module care only about its own interface implementation and registration call, without touching any existing code. This idea of **declaring intent and letting the mechanism orchestrate** applies anywhere an order needs to be settled.
