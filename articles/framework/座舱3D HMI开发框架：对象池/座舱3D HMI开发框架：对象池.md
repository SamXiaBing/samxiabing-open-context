---
title: "座舱3D HMI开发框架：对象池"
date: 2026-07-31
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇写了引用池，它主要是作为可回收的纯 C# 对象而准备的一个池子。但开发过程中可能会碰到：同一种类型要两套管理策略、创建实例的时候参数不同、池子要有实例数量上限、生命周期要跟着使用这个实例的业务模块变化。这些情况下 ReferencePool 就不大适用。

出于以上因素的考虑，之前开发过程中，有接触过另一套：`ObjectPool<T>`，这个模块就是更加灵活多变的池子，使用策略模式来让池子里不同的实例对象有不同的生命周期行为。

---

## 设计实现

*[配图见公众号原文]*

### 接口层

`IPool<T>` 对象池的接口

声明了3个方法：`Allocate` 借出、`Recycle` 归还、`Spawn` 取出但不清理。

`IObjectFactory<T>` 工厂的接口

只有一个 `Create`方法的声明，负责造对象。它是挂在对象池上的“策略对象”。

```csharp
// 示意代码
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

`IPoolable` 可池化的接口

主要用来约束可循环利用的对象，`OnRecycled` 在归还时调用，`IsRecycled` 标记防重复归还。它在之后用在SafeObjectPool 中。

```csharp
// 示意代码
public interface IPoolable
{
    void OnRecycled();
    bool IsRecycled { get; set; }
}

```

### 对象池基类：`Pool<T>`

1. 用Stack来管理对象的存储；
2. 实现了`Allocate` 的逻辑（栈空了就找 Factory 造，有就 Pop）；
3. `Recycle` 留给子类实现，因为清理逻辑各有不同。
4. 基类还持有一个 `IObjectFactory<T>` 引用，子类构造时注入，此时才决定具体的对象的生产方法。

```csharp
// 示意代码
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

### 两种工厂

1. `DefaultObjectFactory<T>` 就是最基本的一种实现，是默认创造对象的一个策略，当这里的 T 有public的无参构造函数时，就可以用这个默认的
2. `CustomObjectFactory<T>` 接收一个由外部注入的 `Func<T>`，是提供给带参构造，或者从配置读等多种场景的构造方法的。同一种 T 要多种构造方式就用这个。

```csharp
// 示意代码

// 默认工厂：new T()
public class DefaultObjectFactory<T> : IObjectFactory<T> where T : new()
{
    public T Create() => new T();
}

// 自定义工厂：Func<T> 注入
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

继承 `Pool<T>`，在构造的时候，就需要传入工厂的构造方法以及当需要清理的时候的委托。其中构造方法由 `Func<T>` 类型注入，清理的方法由 `Action<T>` 注入。

`Recycle` 是针对如果这个对象归还的时候，需要有相关的清理逻辑的，可以使用。做法是调 resetMethod 再 Push，没有则直接 Push。池化的本质是要复用，但是一个对象用过了，它的内部状态可能是改过的，被赋值过的，非初始态的，下次要再利用，那就得清理/刷新。

```csharp
// 示意代码
public class SimpleObjectPool<T> : Pool<T>
{
    private readonly Action<T> _resetMethod;

    public SimpleObjectPool(Func<T> factoryMethod, Action<T> resetMethod = null, int initCount = 0)
    {
        _factory = new CustomObjectFactory<T>(factoryMethod);
        _resetMethod = resetMethod;

        for (int i = 0; i < initCount; i++)
            _stack.Push(_factory.Create());  // 构造时预热
    }

    public override bool Recycle(T obj)
    {
        _resetMethod?.Invoke(obj);   // 有清理就清
        _stack.Push(obj);
        return true;
    }
}

```

### `SafeObjectPool<T>`

也是继承 `Pool<T>`，但相比 SimpleObjectPool 有三个不同：

1，`IsRecycled` 防重复归还，满了直接丢弃并返回 false；

2，`Allocate` 时把 `IsRecycled` 置 false，`Recycle` 时置 true 再调 `OnRecycled`。

```csharp
// 示意代码
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
        result.IsRecycled = false;   // 标记为「在用」
        return result;
    }

    public override bool Recycle(T t)
    {
        if (t == null || t.IsRecycled) return false;       // 防重复归还

        if (_maxCount > 0 && _stack.Count >= _maxCount)
        { t.OnRecycled(); return false; }                  // 满了丢弃

        t.IsRecycled = true;
        t.OnRecycled();
        _stack.Push(t);
        return true;
    }
}

```

## 使用案例

以固定大小的字节缓冲为例。

```csharp
public class ByteBlock   // 不必实现 IPoolable
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

// 模块内持有自己的池
private readonly SimpleObjectPool<ByteBlock> _blockPool =
    new SimpleObjectPool<ByteBlock>(
        () => new ByteBlock(4096),    // 造法
        b => b.Reset(),               // 清法
        initCount: 4);                // 预热 4 个

// 使用
var block = _blockPool.Allocate();
// ... 写 Buffer
_blockPool.Recycle(block);

// 模块关闭
// _blockPool 的 Stack 随模块释放，不用管全局

```

如果同时还有小包（字节数组）的需求。就再 `new` 一个 `SimpleObjectPool`，换一个 `Func<T>` 就行。

使用流程和引用池一样：`Allocate` → 用 → `Recycle`。

---

## 结语

实际项目应用时，多见于通讯代码中，因为这是个标准的高频使用对象的场景：比如SR 场景收到的感知物数据，可以预分配一组 ByteBlock，大的 4KB 小的 256B，各自一个池；比如与安卓原生的通讯中，通讯模块可能同时会支持多种通道（JNI，Socket，共享内存），那数据包的基类，在不同的通道中，就可以使用对象池进行不同的构造。

