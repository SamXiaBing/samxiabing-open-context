---
title: "Cockpit 3D HMI Development Framework: Design and Purpose of the Command Mechanism"
lang: en
date: 2026-09-18
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article gave a broad overview of how the MVC philosophy is implemented in this framework and which classes are involved. Starting with this one, I'll try to walk through the key classes one by one to fill in the details. This article targets the Command.

---

# Where Command Fits

Earlier articles described the framework as five parts: engine bridging, the framework main class, the module layer, the business layer, and the foundation layer.

Command is not in the module layer. As the name suggests, you use it to issue a command, and whoever should execute it, executes it. It is a one-shot object created by the business code. It sits at the boundary between the business layer and the framework: the business instantiates it, the MVC module executes it, and in the end the reference pool reclaims it — use it and move on. It deserves an article of its own because write operations are the most frequent and the most easily-out-of-control part of business code.

# Purpose

When we change a piece of business state, a chain of changes usually follows. For example, switching into the parking state does not just change the camera view; it also has to hide the UI of the previous state, and finally fire an event to notify other modules. That logic ends up scattered across button callbacks, coroutines, and utility classes. The moment a requirement asks to add an effect during the switch, we have to search every place that changes the view and patch them all.

If we package this whole set of actions into one Command class, all callers go through the same entry point. You only ever change that one place, and the operation is no longer a scattering of fragments.

# What About Events?

Writing this far, a question comes up. If gathering all behavior into one place for centralized handling is our design philosophy, why do we still need an event module?

After all, events do exactly the opposite: they broadcast a piece of news, whoever cares subscribes, and the more spread out the better. Aren't these two completely opposite design approaches?

In my understanding, commands and events are for different scenarios. A command leans toward management: I clearly know that a data change is the entry point, and I have a fairly clear idea of which things it should cascade to. It is the beginning of a whole piece of work, an intent. An event, on the other hand, is more like the past tense: by the time it fires, the data change has already happened. It needs to notify other parties one-to-many, and it does not clearly know how many receivers there are.

---

# Interface Design

The interface the framework defines for Command covers these capabilities: reading models, sending events, sending further commands, sending queries, and using the reference pool.

```csharp
public interface ICommand :
    IBelongToArchitecture,   // Which module it belongs to
    ICanGetModel,            // Can read Model data
    ICanSendEvent,           // Can send events
    ICanSendCommand,         // Can send further commands
    ICanSendQuery,           // Can send further queries
    IReference               // Can be returned to the reference pool
{
    void Execute();          // The action itself
}
```

Compare this with the query interface `IQuery` mentioned in the previous article: at the interface level it does not inherit the ability to send events or commands. It keeps only data reading, plus a `Do()`.

## Abstract Class Design

After inheriting ICommand, the abstract class implements `Execute` by calling `OnExecute`. Business subclasses then only need to implement `OnExecute`. If the command object stores execution parameters, `Clear` should be where they get nulled out.

```csharp
public abstract class AbstractCommand : ICommand, IReference
{
    void ICommand.Execute()
    {
        OnExecute();          // The action filled in by subclasses
    }

    protected abstract void OnExecute();

    public virtual void Clear()   // Cleanup before returning to the reference pool
    {
    }
}
```

## Dispatch Design

Once a command has been instantiated, it is dispatched through MVCArchitecture:

```csharp
public void SendCommand<T>(T command) where T : ICommand
{
    command.Execute();              // Execute
    ReferencePool.Release(command); // Return it to the reference pool
}
```

The module guarantees that a command is always returned to the pool once execution finishes; the business only cares about sending. As for whether the command itself was `new`ed up or `Acquire`d from the pool, the module does not interfere.

---

# The Lifecycle of a Command

Putting the three design points above together, here is the day/night mode toggle command as an example:

```csharp
// The following is illustrative code
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

On the business side, sending the command takes one line of code.

```csharp
this.SendCommand(new SwitchDayNightCommand());
```

Behind the send, an extension method hands the command to the module, the module calls `Execute()`, the command finishes updating the Model, and then it goes into the reference pool. Before anyone acquires a command of the same type next time, the pool first calls `Clear()` to wipe the old state clean.

*[Figures omitted; see the original WeChat article]*

---

# Usage in Business Code

Inherit the base class, fill in Execute, send. Just those three steps. What it buys you is the convenience of being able to send commands from anywhere. For example, if you build a signal simulation panel, every button click in it can be a signal-type command.

```csharp
public abstract class AbstractResponse : IPacketHandler, ICommand, IContextAttachable
{
    void ICommand.Execute()
    {
        _stopWatch.Restart();
        OnExecute();                    // Subclasses parse the data and update the Model
        _stopWatch.Stop();

        // Warn if command execution took more than 5 ms
        if (_stopWatch.ElapsedMilliseconds > 5)
        {
            Log.Warning($"response {Id}, cost : {_stopWatch.ElapsedMilliseconds}");
        }
    }

    public void Handle(object sender, Packet packet)
    {
        data = packet as SCPacketBase;
        Context.MVC.SendCommand(this);  // Packet received → send self into the module as a command
    }
}
```

When a server data packet arrives, `Handle` sends the object itself into the module, the module calls `Execute()`, and the subclass parses the data and updates the Model inside `OnExecute`. The whole chain looks like this.

*[Figures omitted; see the original WeChat article]*

---

# Closing Thoughts

Command is a standard pattern that can be rolled out across a whole class of application scenarios. Beyond the signal simulation logic in the signal simulation panel, we have made it a convention that all state writes must go through the Command entry point, combined with access-control constraints on the Model. This avoids the problems, common in team collaboration, of someone modifying a field directly — state changes become untraceable and side effects get scattered all over the place.
