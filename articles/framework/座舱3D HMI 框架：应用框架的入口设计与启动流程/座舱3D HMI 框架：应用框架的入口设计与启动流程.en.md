---
title: "Cockpit 3D HMI Framework: Entry Point Design and the Startup Flow"
lang: en
date: 2026-09-04
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> Following up on the entry point mentioned at the end of the previous article, this article shares that entry point. Most of this software development framework's underlying layers are pure C# classes; to use them inside the engine, a script needs to take on the role of linking into the engine's lifecycle and driving the whole framework to begin initializing — that's exactly what this entry point design is about.

# What the Entry Point Must Consider

When wiring the application framework into a 3D engine runtime, the entry layer needs to solve some concrete problems:

**1. Lifecycle adaptation**

The framework modules are pure C# classes that don't inherit `MonoBehaviour`/`AActor`. Framework modules can't receive the engine's frame-loop callbacks (Update, etc.) directly. The entry layer must provide a lifecycle bridge that converts the engine's frame callbacks, load callbacks, and destruction callbacks into events or interface calls that framework modules can subscribe to, letting pure C# modules participate in the engine's main loop.

**2. Global survival**

Applications may switch scenes. If key modules are mounted on objects, they must not be destroyed when a scene unloads; if they are, the framework may enter a stalled/abnormal state. So the entry layer must place such components on a root node that survives across scenes, unaffected by scene loading and unloading.

**3. Convenient dependency access**

Business code needs to access public services everywhere — the event bus, the network module, UI managers, and so on. If dependencies are passed layer by layer as parameters or fetched from global services, coupling is high and testing is hard. The entry layer should provide a unified dependency-injection mechanism, so business code can get module references directly when needed, without manual passing or global lookups.

**4. Standardized startup flow**

The application startup phase includes common steps: version initialization, log configuration, tool registration, multilanguage loading, language settings, and so on. These steps are universal, but each application's specific configuration differs. The entry layer needs to standardize the common startup flow, allowing each application to inject its differentiated settings within the unified flow framework.

# The Design Roles

![1](./1.png)

- **Context (application context)**: an application's ID card within the framework. It holds the package name, holds the framework instance, and provides access interfaces to all components. It's also responsible for creating child contexts, achieving multi-application isolation.
- **ApplicationBase (application entry base class)**: solidifies how an application starts into template methods; business subclasses only override the points that differ.
- **AppRunner (engine heartbeat)**: a `MonoBehaviour` singleton, the framework's heartbeat source, handing each frame's time to the framework.

Usage on the business side:

```csharp
var app = new App();   // by the time construction completes, context, framework, and heartbeat are all in place
app.Launch();          // common startup flow + business differences
```

# Context

`Context` is the application's identity, and also the assembly of components. What it solves: **how multiple applications can be isolated yet still share**. It draws on Android's Context: package name, application context, creating sub-package contexts, plus a dozen-odd component accessors.

Once business code has a `Context`, it can access all public services through the context object's unified entry — convenient and testable. The boundary between sharing and isolation is visible in the constructor code:

```csharp
public abstract class Context : IDisposable
{
    public abstract Framework Framework { get; }      // framework instance
    public abstract string GetPackageName();           // package name
    public abstract Context GetApplicationContext();   // application context
    public abstract Context CreatePackageContext(string packageName);  // sub-package context

    public abstract UIComponent UI { get; }            // below are all component accessors
    public abstract EventComponent Event { get; }
    public abstract NetworkComponent Net { get; }
    // ... same for the remaining components
}
```

The concrete implementation class `ContextImpl` uses the package name for business isolation, managing the framework instance and the components. Business code depends only on the `Context` abstract class.

```csharp
private ContextImpl(ContextImpl container, string packageName)
{
    _packageName = packageName;

    if (container != null)
    {
        // Sub-package context: share everything from the parent, only the package name changes
        _framework = container.Framework;
        _event = container.Event;
        // ... all remaining components reference the parent's
        return;
    }

    // Application context: actually creates the framework and all components
    _framework = new Framework();
    _event = GetOrCreateManager<EventComponent>();
    _fsm = GetOrCreateManager<FsmComponent>();
    // ... same for the remaining components
}
```

The components themselves are `MonoBehaviour`s; at creation time they're uniformly mounted under the `[AppRunner]` node with `DontDestroyOnLoad` set.

# ApplicationBase

The entry base class needs `Context` and `AppRunner` at construction time. It solidifies how an application starts — for example, spinning up the components during construction and providing the Launch template method that leaves room for differences.

```csharp
public class ApplicationBase
{
    private AppRunner _runner = null;
    private int _mainThreadId;         // main thread ID, needed for cross-thread dispatching

    public ApplicationBase()
    {
        _mainThreadId = Thread.CurrentThread.ManagedThreadId;

        ContextImpl appContext = ContextImpl.CreateAppContext();  // build the context (which builds the framework inside)
        this.AttachContext(appContext);

        _runner = AppRunner.Create(appContext.Framework);  // the heartbeat is up as soon as construction completes
    }

    public void Launch()
    {
        InitVersionHelper();                    // version number helper
        LoadDefaultTextSettings();              // text font settings
        OnLauncher();                       // leaves room for differences; business subclasses override
    }

    protected virtual void OnLauncher() { }    // business differences
}
```

The business subclass `App` overrides `OnLauncher`, adding its own initialization: log level, tools, language settings, then registering events.

# AppRunner

The first two roles are pure C# classes; the engine's per-frame callbacks can't reach them directly. `AppRunner` exists to fill exactly that gap:

```csharp
// The following is illustrative code
[MonoSingletonPath("[AppRunner]")]                // specifies the node path
public class AppRunner : MonoSingleton<AppRunner>
{
    private Framework Framework { get; set; }

    private void Update()
    {
        Framework.OnUpdate(Time.deltaTime, Time.unscaledDeltaTime);
    }

    protected override void OnDestroy()
    {
        base.OnDestroy();
        Release();
    }

    private async void Release()
    {
        await Task.Yield();                       // let one frame pass before cleaning up
        Framework.Shutdown();
    }

    public static AppRunner Create(Framework framework)
    {
        AppRunner.Instance.Framework = framework;      // first access triggers singleton creation
        return AppRunner.Instance;
    }
}
```

On first access of `Instance`, it looks for the node at the path specified by `[MonoSingletonPath]`; if it isn't found, one is created and given `DontDestroyOnLoad`.

In `OnDestroy`'s `Release`, the framework's `Shutdown()` is only called after `await Task.Yield()` — yielding one frame, waiting for the engine to finish this round of destruction before doing the framework-level cleanup.

# Runtime Sequence

![2](./2.png)

Across the entire lifecycle, business code appears in only three places: `new App()`, `Launch()`, and the differentiated logic inside `OnLauncher`. Everything else is the framework hooking things up.

# Closing Thoughts

The essence of entry point design is building a reliable road between two lifecycles: the engine's and the framework's.

Looking back at this design, the complex part is the "who owns whom" relationships: `ApplicationBase` owns `Context` and the `Runner`; `Context` owns the `Framework` (actually creating the framework and the components); the `Runner` only references the `Framework` without owning it.

This achieves sub-packages sharing the `Framework` and the components, while not sharing the startup flow. During scene switches, `AppRunner` doesn't disappear — it keeps driving the `Framework` the whole time.
