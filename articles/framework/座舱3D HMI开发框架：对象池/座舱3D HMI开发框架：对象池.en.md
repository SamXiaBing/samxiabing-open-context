---
title: "Cockpit 3D HMI Development Framework: The Object Pool"
date: 2026-07-31
series: framework
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous post covered the reference pool — a pool mainly prepared for recyclable pure C# objects. But during development you may run into situations like: the same type needing two management strategies, different parameters when creating instances, a pool needing a cap on instance count, or a lifetime that must follow the business module using the instance. In these cases, ReferencePool isn't a great fit.

Taking the above factors into account, in past development I came across another one: `ObjectPool<T>`. This module is a far more flexible pool, using the strategy pattern to give different instance objects in the pool different lifetime behaviors.

---

## The Design

*[Figures omitted; see the original WeChat article]*

### The Interface Layer

`IPool<T>` — the object pool interface

It declares three methods: `Allocate` (check out), `Recycle` (return), `Spawn` (take out without cleaning up).

`IObjectFactory<T>` — the factory interface

It declares only one method, `Create`, responsible for making objects. It is the "strategy object" attached to the object pool.

```csharp
// Illustrative code
public interface IPool<T>
{
    T Allocate();
    bool Recycle(T obj);
    T Spawn();
}

public interface IObjectFactory<T>
{
    T Create();
}

```

`IPoolable` — the poolable interface

It mainly constrains reusable objects: `OnRecycled` is called on return, and `IsRecycled` is a flag to prevent double returns. It is used later in SafeObjectPool.

```csharp
// Illustrative code
public interface IPoolable
{
    void OnRecycled();
    bool IsRecycled { get; set; }
}

```

### The Pool Base Class: `Pool<T>`

1. Uses a Stack to manage object storage;
2. Implements the `Allocate` logic (if the stack is empty, ask the Factory to make one; otherwise Pop);
3. Leaves `Recycle` for subclasses to implement, since cleanup logic differs from case to case.
4. The base class also holds an `IObjectFactory<T>` reference, injected when the subclass is constructed — that is when the concrete object production method is decided.

```csharp
// Illustrative code
public abstract class Pool<T> : IPool<T>
{
    protected IObjectFactory<T> _factory;
    protected readonly Stack<T> _stack = new Stack<T>();
    protected int _maxCount = 12;

    public virtual T Allocate()
    {
        return _stack.Count == 0
            ? _factory.Create()
            : _stack.Pop();
    }

    public abstract bool Recycle(T obj);
}

```

### The Two Factories

1. `DefaultObjectFactory<T>` is the most basic implementation — the default strategy for creating objects. When T here has a public parameterless constructor, you can use this default one.
2. `CustomObjectFactory<T>` receives an externally injected `Func<T>`, provided for constructors with parameters, reading from configuration, and other such construction scenarios. When the same T needs multiple construction approaches, use this one.

```csharp
// Illustrative code

// Default factory: new T()
public class DefaultObjectFactory<T> : IObjectFactory<T> where T : new()
{
    public T Create() => new T();
}

// Custom factory: Func<T> injection
public class CustomObjectFactory<T> : IObjectFactory<T>
{
    private readonly Func<T> _factoryMethod;

    public CustomObjectFactory(Func<T> factoryMethod)
    {
        _factoryMethod = factoryMethod;
    }

    public T Create() => _factoryMethod();
}

```

### `SimpleObjectPool<T>`

It extends `Pool<T>`. At construction time, you need to pass in the factory's construction method plus the delegate for when cleanup is needed. The construction method is injected as a `Func<T>`, and the cleanup method as an `Action<T>`.

`Recycle` is there for the case where returning the object requires related cleanup logic. The approach: call resetMethod and then Push; if there is none, Push directly. The essence of pooling is reuse, but once an object has been used, its internal state may have been modified, assigned to, no longer in its initial state — to reuse it next time, it has to be cleaned/refreshed.

```csharp
// Illustrative code
public class SimpleObjectPool<T> : Pool<T>
{
    private readonly Action<T> _resetMethod;

    public SimpleObjectPool(Func<T> factoryMethod, Action<T> resetMethod = null, int initCount = 0)
    {
        _factory = new CustomObjectFactory<T>(factoryMethod);
        _resetMethod = resetMethod;

        for (int i = 0; i < initCount; i++)
            _stack.Push(_factory.Create());  // pre-warm at construction
    }

    public override bool Recycle(T obj)
    {
        _resetMethod?.Invoke(obj);   // clean up if there's a cleanup method
        _stack.Push(obj);
        return true;
    }
}

```

### `SafeObjectPool<T>`

It also extends `Pool<T>`, but compared with SimpleObjectPool it has three differences:

1. `IsRecycled` prevents double returns; when the pool is full, drop the object directly and return false;

2. On `Allocate`, set `IsRecycled` to false; on `Recycle`, set it to true and then call `OnRecycled`.

```csharp
// Illustrative code
public class SafeObjectPool<T> : Pool<T> where T : IPoolable, new()
{
    public int MaxCacheCount
    {
        get { return _maxCount; }
        set
        {
            _maxCount = value;
            if (_maxCount > 0 && _stack.Count > _maxCount)
            {
                int removeCount = _stack.Count - _maxCount;
                while (removeCount-- > 0)
                    _stack.Pop();
            }
        }
    }

    public void Init(int maxCount, int initCount)
    {
        MaxCacheCount = maxCount;
        if (maxCount > 0) initCount = Math.Min(maxCount, initCount);
        for (var i = _stack.Count; i < initCount; ++i) Recycle(new T());
    }

    public override T Allocate()
    {
        var result = base.Allocate();
        result.IsRecycled = false;   // mark as "in use"
        return result;
    }

    public override bool Recycle(T t)
    {
        if (t == null || t.IsRecycled) return false;       // prevent double return

        if (_maxCount > 0 && _stack.Count >= _maxCount)
        { t.OnRecycled(); return false; }                  // full, discard

        t.IsRecycled = true;
        t.OnRecycled();
        _stack.Push(t);
        return true;
    }
}

```

## A Usage Example

Take a fixed-size byte buffer as an example.

```csharp
public class ByteBlock   // no need to implement IPoolable
{
    public byte[] Buffer { get; }
    public int Length { get; set; }

    public ByteBlock(int size) => Buffer = new byte[size];

    public void Reset()
    {
        Length = 0;
        Array.Clear(Buffer, 0, Buffer.Length);
    }
}

// The module holds its own pool
private readonly SimpleObjectPool<ByteBlock> _blockPool =
    new SimpleObjectPool<ByteBlock>(
        () => new ByteBlock(4096),    // how to make one
        b => b.Reset(),               // how to clean one
        initCount: 4);                // pre-warm 4

// Usage
var block = _blockPool.Allocate();
// ... write to Buffer
_blockPool.Recycle(block);

// Module shutdown
// _blockPool's Stack is released with the module; no global management needed

```

If there is also a need for small packets (byte arrays), just `new` another `SimpleObjectPool` and swap in a different `Func<T>`.

The usage flow is the same as the reference pool: `Allocate` → use → `Recycle`.

---

## Closing Words

In real projects, it's most often seen in communication code, because that is the standard scenario of high-frequency object usage: for example, the perception object data received in SR scenarios can pre-allocate a set of ByteBlocks — large 4KB, small 256B, one pool each; for example, in communication with Android native, the communication module may support multiple channels at once (JNI, Socket, shared memory), so the data packet base class can use object pools for different constructions across the different channels.
