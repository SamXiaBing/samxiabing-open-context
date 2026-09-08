---
title: "座舱3D HMI性能：内存泄漏？关于“回收”的陷阱"
date: 2026-09-07
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> 本文发现的问题是内存占用持续上升，没有黑屏和崩溃，就是内存一直往上走，表面看是内存泄漏，但是这一例的症结在引用池。

# 问题表现

跑monkey测试，示意数据如下：


| 进程      | 实测情况                        |
| ------- | --------------------------- |
| 3D 车模桌面 | 正常操作1G-1.5G；monkey 15小时到2G+ |
| SR      | 路测2小时线性涨到4G+                |


特征：

1. **渐进式增长**：内存跟测试时长相关，monkey越跑越高。
2. **不同的3D应用都有**：车模桌面、SR都有泄漏。

---

# 根因分析

通过打development包，并重新进行1-2小时的monkey测试/路试。抓取前后的profiler数据，查看Memory部分，或通过Memory Snapshot，可以看到类型列表中的数据 ReferenceCollection/IReference 相关的类，在内存上有明显增长。

在发现这个可疑的对象之后，主动加入 UsingReferenceCount 的打印，复测发现**引用池只增不减**：`ReferencePool`的`UsingReferenceCount`持续涨，调`GC.Collect()`没用。

## 引用池

之前写过引用池的文章，介绍过它是一套基于`IReference`接口的对象引用模块，核心思路是对象用完不销毁，放回池里复用，避免高频创建销毁。

```csharp
// 示意代码
public static partial class ReferencePool
{
    // 全局字典：每种类型对应一个引用集合
    private static readonly Dictionary<Type, ReferenceCollection> s_ReferenceCollections
        = new Dictionary<Type, ReferenceCollection>();

    // 从池中取，没有就new
    public static T Acquire<T>() where T : class, IReference, new()
    {
        return GetReferenceCollection(typeof(T)).Acquire<T>();
    }

    // 放回池中
    public static void Release(IReference reference)
    {
        GetReferenceCollection(reference.GetType()).Release(reference);
    }

    // 唯一的清理入口
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

代码有两个隐患：

**一、Acquire和Release必须配对。** 只要有一次Acquire之后没人Release，这个对象就永远占着，业务代码强引用，无法GC回收。

**二、池子本身没有定期清理机制。** 整个引用池系统只有`ClearAll()`一个清理入口，还只清空闲队列。之前的代码里也没有任何地方定时调用它，结果就是攒了大量没人用的对象，永远驻留内存，池子总量只增不减。

> GC的回收逻辑是从GC Root出发做可达性分析，不可达的对象才回收。引用池本身挂在全局静态字典上，池里的每个对象都有一条完整的强引用链。所以`GC.Collect()`没用。
>
> 引用池的设计本身没问题，但不能指望把回收的职责全交给GC。

# 解决方案


| 层   | 动作                         | 目标              |
| --- | -------------------------- | --------------- |
| 业务层 | 补齐Acquire/Release配对 + 日志降级 | 消灭泄漏源，降低GC压力    |
| 框架层 | **MemoryManager定期清理引用池**   | 兜底处理业务遗漏，给池子加上限 |


**定时兜底清理是最简单、最不容易错的那条路。** 业务上的获取和释放的配对是第一道防线，MemoryManager是第二道防线。

## MemoryManager 部分的实现

MemoryManager 做的事情就是被创建的时候，启动一个定时器，定时去清理引用池。它可以注册到应用的Context中。

```csharp
// 示意代码
namespace Engine.Runtime
{
    public class MemoryManager : MyService
    {
        protected override void OnCreate()
        {
            // 每120秒执行一次引用池清理
            InvokeRepeating(nameof(ClearReferencePool), 120f, 120f);
        }

        private void ClearReferencePool()
        {
            // ② 释放引擎侧未使用的资源（贴图、网格等）
            Resources.UnloadUnusedAssets();
            // ③ 清空引用池空闲队列
            ReferencePool.ClearAll();
            // ④ 触发一次完整GC
            GC.Collect();
        }
    }
}
```

## 其他发现

排查中发现部分对象子类的`Clear()`是空实现。对象归还池子时，内部的字符串引用还挂着，字符串照样占着池子内存，治标不治本。正确写法：

```csharp
public virtual void Clear()
{
    MapObjectType = null;   // 释放字符串引用
    StyleName = null;       // 释放字符串引用
    // 子类继续清自己的字段
}
```

---

# 结语

引用池的这个bug，本质是在提醒我**对象池的"回收"也许不是真的回收，而是"拖延"。**如果池子没有清理机制，它就只是把"回收"推迟到很久以后，跟泄漏没有区别。