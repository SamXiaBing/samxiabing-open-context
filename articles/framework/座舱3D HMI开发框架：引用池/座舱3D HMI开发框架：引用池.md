---
title: "座舱3D HMI开发框架：引用池"
date: 2026-07-24
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> 开发中常见的是：预先实例化一些对象（GameObject），等到要用的时候再从对象池列表中激活。因此被叫做对象池，但对象并不局限于引擎的预制体，也可以是纯 C# 引用对象。

本文分享开发框架里的引用池`ReferencePool`，专门来池化 C# 引用类型对象。

引用池的设计目的，也是为了内存利用效率，规避频繁的GC。它主要针对的对象是各种临时的数据结构，这些数据对象有着生命周期短、体量小、分配频率高的特点。

*[配图见公众号原文]*

总的来说，它的诞生是为了**给所有"可回收的纯 C# 对象"一个统一入口，按类型自动分类，调用方不用关心实例管理策略。**

---

## 设计实现

*[配图见公众号原文]*

###  `ReferencePool`

设计一个全局静态的类，维护一个字典，这个字典把不同的 `Type` 和 引用集合 `ReferenceCollection` 对应起来。使用者只需要知道需要一个类的对象的时候去 Acquire，用完了就 Release。

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
        // Framework Shutdown 时一把清掉所有桶
    }
}
```

### `IReference`

引用池所支持的 `Type` 需要继承 `IReference` 接口，该接口只约定了需要实现归还后的 Clear 动作。目的是保证 Release 的时候一定调 Clear 。

```csharp
// 源码路径：Assets/Scripts/Core/ReferencePool/IReference.cs
// 以下为示意代码，已与工程逻辑对齐但非拷贝
public interface IReference
{
    void Clear();
}
```

### `ReferenceCollection`

引用集合使用队列 Queue 实现了具体的计数，存储，分配和销毁过程：

Acquire 流程：计数递增 → 加锁检查 Queue → 有则 Dequeue 复用 → 无则 new T() 分配。

Release 流程：先调 reference.Clear() 清字段，再 Enqueue 入队。

如果重复释放，可以选择抛不抛异常。

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
        return new T();   // 池空才分配；峰值过后复用
    }

    public void Release(IReference reference)
    {
        reference.Clear();   // 先清，再入队，顺序不能反
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

### 预分配

`ReferencePool` 还实现了两个额外能力：

```csharp
// 预分配：批量创建一批对象塞进池里，适合启动时预热
ReferencePool.Add<EventNode>(50);

// 缩容：从池里移除指定数量的闲置对象，适合峰值后清理
ReferencePool.Remove<EventNode>(30);
```

`Add` 在启动阶段有用，比如知道某个模块最多同时处理 50 个事件，就可以考虑提前把对象造好。

---

## 使用案例

引用池的用法一般是：

1. `Acquire` 
2. 填字段 / Initialize 
3. 使用 
4. `Release`（内部 Clear）。

比如 **事件**

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

1. Event 节点使用引用池：通过 Create 静态方法从池里获取，用完后由外部调用 ReferencePool.Release(node) 归还
2. 归还时 Clear() 自动执行，把 Sender 和 EventArgs 引用置空
3. 调用方（业务代码）只需要调 Event.Create(sender, args) 拿到节点，不用关心池的存在

*[配图见公众号原文]*

---

## 结语

引用池目前主要是在框架层内部使用，开发范围是可控的，所以设计得比较单纯：一个 Type 只对应一个引用集合且默认不限容量。

但是到了更复杂的业务层面，比如同一个类，需要不同的管理集合；或者是同一个类，在不同业务场景下的创建和清理的手段不同。此时，ReferencePool 的灵活性是不够的，所以还会有一套 ObjectPool 将在之后分享。