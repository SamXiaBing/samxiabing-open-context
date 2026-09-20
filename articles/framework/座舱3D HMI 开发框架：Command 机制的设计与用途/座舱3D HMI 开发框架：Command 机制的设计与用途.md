---
title: "座舱3D HMI 开发框架：Command 机制的设计与用途"
date: 2026-09-18
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇把 MVC 的理念在这套框架里面的落实的大体情况做了交代，讲到了有哪些类。从本篇开始就尝试一个个关键的类进行分享，试图把这些细节补全。本文瞄准的是 Command 命令。

---

# 定位

框架之前说分五块：引擎桥接、框架主类、模块层、业务层，基础层。

Command 不在模块里，顾名思义，使用它就是为了发出一个命令，谁该执行谁执行。它是业务造出来的一次性对象。它的位置在业务层与框架的交界处，业务把它实例化出来，MVC 模块去执行它，最后引用池回收它，用完即走。它值得单独写一篇，是因为写操作是业务里最高频、也最容易失控的部分。

# 目的

我们改一个业务状态，后面往往关联着一串变化。比如切个泊车的状态，不仅是改变视角，而且要隐藏掉上一个状态的UI，最后还要发事件通知其他模块。这些逻辑散落在按钮回调、协程、工具类里各处。一旦需求说要在切换的时候加入一个效果，我们就得搜所有改视角的地方，多处进行缝补。

如果把这一整套动作打包成一个 Command 类，所有调用方都走同一个入口。只改这么一个地方，操作就不再是散落的碎片。

# 事件？

写到这，有个问题。既然所有行为都集合起来处理才是我们的设计理念，那我们还要事件模块干嘛呢？

毕竟，事件干的恰好相反，它把一件事广播出去，谁关心谁订阅，越散越好。这不是两种完全相反的设计思路吗？

命令和事件我理解用在不同的场景，命令更偏向于管理：我明确知道一个数据变化作为入口，且比较清晰地知道它意味着要联动哪些东西的变化。它是一整件事情起的那个头，一个意图。而事件就更像是个过去时，它发生之前，数据的变化已经发生了，它需要一对多地通知其他方面，且它并不清晰知道有多少接收人。

---

# 接口设计

框架给 Command 定的接口，在能力上包括：能读模型、能发事件、能再发命令、查询、使用引用池。

```csharp
public interface ICommand :
    IBelongToArchitecture,   // 归属哪个模块
    ICanGetModel,            // 能读 Model 数据
    ICanSendEvent,           // 能发事件
    ICanSendCommand,         // 能再发命令
    ICanSendQuery,           // 能再发查询
    IReference               // 可归还引用池
{
    void Execute();          // 动作本体
}
```

对比来看上一篇提到的查询接口 `IQuery` ，它在接口上不继承发事件和发命令的能力，只留读数据，以及一个`Do()` 。

## 抽象类设计

继承ICommand之后，抽象类去实现调用`OnExecute`。继而，业务子类只需要去实现 `OnExecute`就可以了，如果命令对象存了执行参数，Clear下面应该去做置空的动作。

```csharp
public abstract class AbstractCommand : ICommand, IReference
{
    void ICommand.Execute()
    {
        OnExecute();          // 子类填的动作
    }

    protected abstract void OnExecute();

    public virtual void Clear()   // 归还引用池前的清理
    {
    }
}
```

## 触发设计

命令被实例化出来，通过MVCArchitecture，将命令触发：

```csharp
public void SendCommand<T>(T command) where T : ICommand
{
    command.Execute();              // 执行
    ReferencePool.Release(command); // 归还引用池
}
```

模块保证执行完必定归还，业务只管发送。至于命令本身是 `new` 出来还是从池里 `Acquire` 的，模块不干涉。

---

# 一条 Command 的过程

综合上述三个设计项，以日夜模式切换的命令为例子：

```csharp
// 以下为示意代码
public class SwitchDayNightCommand : AbstractCommand
{
    protected override void OnExecute()
    {
        var model = this.GetModel<AppModel>();
        model.DayNightMode.Value =
            model.DayNightMode.Value == DayNightMode.Day
                ? DayNightMode.Night
                : DayNightMode.Day;
    }
}
```

业务侧发送命令，一行代码搞定。

```csharp
this.SendCommand(new SwitchDayNightCommand());
```

发送的背后逻辑是扩展方法把命令交给模块，模块调 `Execute()`，命令改完 Model，进引用池。下一次有人取用同类命令前，池子会先调 `Clear()` 把旧状态清干净。

*[配图见公众号原文]*

---

# 业务用法

继承基类、填充Execute、发送。就这三步，它可以带来的是处处都可以发命令的方便，比如你制作一个信号模拟面板，里面每一次按钮的点击，都可以是一个信号类的command。

```csharp
public abstract class AbstractResponse : IPacketHandler, ICommand, IContextAttachable
{
    void ICommand.Execute()
    {
        _stopWatch.Restart();
        OnExecute();                    // 子类解析数据、更新 Model
        _stopWatch.Stop();

        // 命令执行超过 5ms，告警
        if (_stopWatch.ElapsedMilliseconds > 5)
        {
            Log.Warning($"response {Id}, cost : {_stopWatch.ElapsedMilliseconds}");
        }
    }

    public void Handle(object sender, Packet packet)
    {
        data = packet as SCPacketBase;
        Context.MVC.SendCommand(this);  // 收到包 → 自己作为命令进模块
    }
}
```

服务器数据包到达，`Handle` 把自己送进模块，模块调 `Execute()`，子类在 `OnExecute` 里解析数据、更新 Model。整条链是这样的。

*[配图见公众号原文]*

---

# 结语

Command 是一套可以铺开到一类应用场景的标准用法。除了信号模拟面板中的信号模拟逻辑，我们约定所有状态写入都必须走 Command 入口，配合 Model 的访问控制约束，避免团队协作中有人直接修改字段导致的状态变更不可追溯、副作用散落各处的问题。