---
title: "Cockpit 3D HMI Development Framework: Putting the MVC Architecture into Practice"
date: 2026-09-11
series: framework
no: 
status: published
visibility: public
lang: en
wechat_url: ""
---

> I've shared quite a bit of the lower-level design of the business framework already. Setting aside the Components that exist to serve specific business requirements, the big remaining modules should be the MVC-related ones. So over the next three posts, I'll cover how our development framework applied the architectural ideas of MVC and implemented them within its own architecture.

All too often, by the middle of a project, the business code of a software application quickly grows complex enough: coupling risks rise and clarity drops. At that point you may discover that the click logic of a button is written inside the script of the related UI, and then, because the value of some business data changed, the UI-related code of several screens all needs to be modified in sync. Similar pieces of code end up scattered across a handful of files, and developers start getting the feeling of losing control.

The MVC architectural idea can help us solve exactly this kind of problem: the Model manages data, the View manages display, and the Controller manages orchestration. It splits apart the tangled web of business dispatch, and the layers interact with one another through bindings and events rather than direct references.

# Where MVC Fits

We've touched on this area in previous articles. For example, the typical representative of the M layer is the `BindableProperty` family of reactive atoms. What this article wants to describe is the concrete design of the C layer.

*[Figures omitted; see the original WeChat article]*

MVC is a business module on the framework's dispatch chain. Looking at the whole picture, the framework is organized into these layers of concepts:

- Engine bridge layer: AppRunner and ApplicationBase manage the startup flow, and Context manages component access; they translate the engine's lifecycle for the framework.
- Framework main class: Framework holds a List of modules and polls each one to trigger OnUpdate; it is the dispatcher of all modules.
- Module layer: modules such as events, object pool, state machine, MVC, UI, network, resources, and procedures are arranged by priority.
- Business layer: Controllers initiate operations, Commands/Queries carry actions, Models store data, and Views receive events and refresh — business code lives in this layer.
- Foundation layer: reference pool, pooled linked lists, event pool, property — pure C# implementations shared by all the layers above.

You could say its positioning is the mandatory gateway through which business enters and exits the framework: all business logic has to go through it to reach the framework's internal events, data, and dispatch mechanisms.

# What MVC Is Made Of

Taken apart on its own, the class composition looks like this:

*[Figures omitted; see the original WeChat article]*

## The Module Itself: MVCArchitecture

An inner class that implements `IFrameworkModule`, so it can enter the module list and run along with the Framework's frame loop.

It exposes three methods to the outside:

- `RegisterModel` — registers a Model
- `SendCommand` — executes a command
- `SendQuery` — executes a query

Internally there is a `Container` (a dictionary) that registers Models by type, calling `Init` on registration and `Dispose` on unregistration.

## The Interfaces of the Four Roles


| Interface     | Role      | Description                                                                       |
| ------------- | --------- | --------------------------------------------------------------------------------- |
| `ICommand`    | Write     | Can send events, and can send further commands                                    |
| `IQuery`      | Read      | Can only read data                                                                |
| `IModel`      | Data      | The data facade                                                                   |
| `IController` | Dispatch  | A bundle of capabilities: send commands, send queries, receive events, read data models. |


## Composable Capabilities

The module defines a group of interfaces prefixed with `ICan`:

- `ICanSendCommand` — can send commands
- `ICanSendQuery` — can send queries
- `ICanGetModel` — can read models
- `ICanSendEvent` — can send events
- `ICanRegisterEvent` — can receive events
- `IBelongToArchitecture` — can access the framework

Whoever wants a capability just inherits the corresponding interfaces.

## Base Classes for the Business Side

The framework provides base classes that already implement the common logic in those interfaces. Business code doesn't need to implement the interfaces from scratch — just inherit the base class and fill in the designated methods with your business.

- To write a command, inherit `AbstractCommand` and put the business logic in the `OnExecute` method. Framework flows such as command registration, execution, and recycling are already handled by the base class.
- To write a data class, inherit `AbstractModel`, write initialization in `OnInit` and cleanup in `OnDispose`. Model registration and lifecycle management are handled by the base class as well.

---

# Collaboration Sequence

Using one complete command as an example, let's walk through how things happen under the current MVC framework design:

*[Figures omitted; see the original WeChat article]*

---

# Closing Thoughts

This is the first of the three MVC posts. It introduces the overall design; the follow-up posts will write out the design of each class mentioned here, one at a time. From some of the interface designs, you can also see the shadow of QFramework in this architecture, so if you want to dig deeper, feel free to check out the related material.
