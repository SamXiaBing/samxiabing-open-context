---
title: "座舱3D HMI开发框架：FrameworkLinkedList，节点池化的链表"
date: 2026-08-03
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> 座舱 3D HMI 框架里，模块注册、事件订阅、实体与 UI 组的动态增删，都要往集合里频繁插拔元素。`.NET` 的 `LinkedList<T>` 双向链表、持节点引用插入，看起来正好。跑起来却发现：每次按值增删都会 `new` / 丢弃一个 `LinkedListNode<T>`。长期驻留、60 帧刷新时，这批小对象会变成可感知的 Gen0 压力。
>
> 本文是「开发框架基础类」第一篇。边界先说清：只讲容器节点怎么池化、链表区间怎么复用、遍历中怎么安全改集合；不讲业务对象池（那是下一篇 `ObjectCache`），也不承诺“无 GC”——只砍掉链表节点这一层分配。

---

做框架底层时，第一个集合选型几乎都会落到 `LinkedList<T>`：`AddFirst` / `AddLast` / `AddBefore(node)` / `Remove(node)` 是 O(1)，还能拿着 `LinkedListNode<T>` 做排序插入和游标。`List<T>` 中部插入、删除要搬数组，O(n)，模块按优先级插队、事件 Handler 插拔都不合适。

问题不在算法，在节点生命周期。`AddFirst(value)` 内部必 `new LinkedListNode<T>`，`Remove(node)` 后节点交给 GC。模块启动注册十几次还好；SR 切场景时成批订阅/注销 Handler、EntityGroup 里实体显隐，会在进程生命周期里反复打。需求因此定死：**保留链表的 O(1) 节点操作，同时让节点可复用。**

（补充一句严谨口径：`Remove(T value)` 仍要先 `Find`，是 O(n)；文中说的 O(1) 指已持有节点时的增删。）

---

## 第一刀：包一层，把 new 拦下来

`LinkedList<T>` 的 `AddFirst(T)` 在基类里直接分配，子类拦不住。只能组合：内部一个真链表，外加一个节点缓存。

```csharp
// Assets/Scripts/Core/DataStruct/FrameworkLinkedList.cs（示意）
public sealed class FrameworkLinkedList<T> : ICollection<T>, IEnumerable<T>
{
    private readonly LinkedList<T> m_LinkedList = new LinkedList<T>();
    private readonly Queue<LinkedListNode<T>> m_CachedNodes = new Queue<LinkedListNode<T>>();

    private LinkedListNode<T> AcquireNode(T value)
    {
        if (m_CachedNodes.Count > 0)
        {
            var node = m_CachedNodes.Dequeue();
            node.Value = value;
            return node;
        }
        return new LinkedListNode<T>(value);
    }

    private void ReleaseNode(LinkedListNode<T> node)
    {
        node.Value = default; // 引用类型解引用，避免池里挂着业务对象
        m_CachedNodes.Enqueue(node);
    }
}
```

所有 `Add*` 走 `AcquireNode`，所有 `Remove*` 走 `ReleaseNode`；`Clear` 先逐节点 `Release` 再清空链表。缓存用 `Queue` 做 FIFO，实现简单；节点是托管小对象，FIFO/LIFO 对局部性差别不大，不必过度解读。

枚举器直接代理 `LinkedList<T>.Enumerator`，本身是 struct。注意：只有通过具体类型 `GetEnumerator()` 的 `foreach` 才免装箱；走 `IEnumerable<T>` 仍会装箱。

节点池有上限心态：缓存只增不减，峰值≈历史最大并发节点数。框架里模块/Handler/组内成员都是几十到几百量级，可接受；别拿它做“突发一万再删光”的容器。类本身不加锁，线程安全由调用方保证（如 `EventPool` 在锁内入队、主线程派发）。

这一刀解决了“增删节点不分配”。马上遇到第二个问题。

---

## 第二刀：一个链表上要挂多组值

事件系统要的是：一个 `eventId` 对应多个 Handler。若每个 key 一个 `List`/`LinkedList`，集合对象本身又是一笔分配；还要在“按 key 遍历”和“全局结构简单”之间折中。

做法是：`MultiDictionary` 里只放一条 `FrameworkLinkedList<TValue>`，再用 `Dictionary<TKey, LinkedListRange<TValue>>` 记每段区间。`LinkedListRange<T>` 是 struct，只存 `First` 与哨兵 `Terminal`（不含有效数据），遍历到 `Terminal` 即停——区间视图本身不分配集合。

```csharp
// Assets/Scripts/Core/DataStruct/MultiDictionary.cs（示意）
public void Add(TKey key, TValue value)
{
    if (m_Dictionary.TryGetValue(key, out var range))
    {
        m_LinkedList.AddBefore(range.Terminal, value);
        return;
    }
    var first = m_LinkedList.AddLast(value);
    var terminal = m_LinkedList.AddLast(default); // 哨兵
    m_Dictionary.Add(key, new LinkedListRange<TValue>(first, terminal));
}
```

同一 key 的值在链表上连续，新增插在 `Terminal` 前，删除在区间内摘节点并归还池。代价也要讲明：每个 key 多一个哨兵节点；空区间用 `First == Terminal` 表示非法，由约定保证“有 key 就有哨兵”。

节点不分配了，多 key 也不用 N 个集合了。第三个问题在运行时才爆出来。

---

## 第三刀：遍历时，回调改了链表

事件派发和实体 `OnUpdate` 里，回调经常订阅/注销自己，或实体“自杀”离组。直接 `foreach` 链表会断链或跳元素。

两条路径，按场景选：

**事件：先快照再调。** `EventPool` 把当前 `LinkedListRange` 里的委托拷到临时链表再执行。当前轮迭代集与原链表解耦，回调怎么改订阅都安全。代价是临时链表有分配——这里换的是正确性，不是零 GC；节点池管的是长期驻留的 Handler 链，不是这一次派发的临时结构。

**实体/UI 组：单游标。** `EntityGroup` / `UIGroup` 只多一个 `m_CachedNode`：进入回调前记下 `current.Next`；`RemoveEntity` 若删的正是游标，就改为 `Next`。不建临时集合，适合“偶发删当前/下一个”、不会在回调里批量打乱组的场景。

```csharp
// Assets/Scripts/Entity/EntityGroup.cs（示意）
public void Update(float elapse, float realElapse)
{
    var current = m_Entities.First;
    while (current != null)
    {
        m_CachedNode = current.Next;
        current.Value.OnUpdate(elapse, realElapse);
        current = m_CachedNode;
        m_CachedNode = null;
    }
}
```

节点引用在这里才真正值钱：`List<T>` 很难做这种“下一个下标可能被删”的轻量游标。

---

## 它在框架里各取所需

`AppFramework` 用 `FrameworkLinkedList<IModule>` 做优先级插入：遍历找到第一个优先级更低的节点，`AddBefore`。`Update` 正序（高优先级先跑，下游同帧能吃到事件），`Shutdown` 逆序（先拆下游）。模块增删很稀，这里池化收益小，要的是节点引用与双向遍历。

事件路径：`MultiDictionary` + `LinkedListRange` 管 Handler 段；派发用快照保安全。实体/UI：链表管成员，游标保遍历中删除。

和 `ObjectCache` 分层：`FrameworkLinkedList` 池的是 `LinkedListNode<T>`（容器骨架）；`ObjectCache` 池的是 `EventNode` 等业务对象。两者叠用，不互相替代。

---

## 什么时候用，什么时候别用

| 更合适 | 不合适 |
|--------|--------|
| 运行时高频按节点增删，且 GC 敏感 | 一次性填表、很少再改 |
| 需要 `LinkedListNode` 做插入/游标 | 只需 `foreach`，从不用节点 |
| 规模几十到几百 | 上千上万还频繁 `Find(value)`（仍是 O(n)） |

---

`FrameworkLinkedList` 做的事很窄：把标准链表的节点分配换成池。`LinkedListRange` 让一条链服务多个 key。遍历变异则按场景用快照或游标。三层问题，三层补丁，都落在“信号与模块调度之下的容器层”。

下一篇写 `IRecyclable` 与 `ObjectCache`——业务对象怎么复用，和本文的节点池化互补。
