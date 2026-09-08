---
title: "智驾 SR 开发：场景元素的 Layer 化分层管理"
date: 2026-07-23
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 在智驾SR开发中，场景里的元素种类繁多——车道线、路面、停止线、人行横道、泊车位、路面标识……如果所有物体都堆在一起管理，代码容易越改越乱而难以维护。

分层管理的理念，最早我是在3D导航类的应用中了解到的。因为3D导航要显示的地图，地图元素众多，所以有将世界中的物体进行分层创建、分层渲染的软件架构思路。

基于 Layer 的分层管理所说的 Layer 并不是像 Unity 引擎里面所说的物体的Layer，并不只是那个控制物体是否进入相机渲染的 cullingMask 概念。它是一种自定义的类：把同类型的场景元素归为一个“层”，由一个`Layer`类统一管理这层内所有物体的完整生命周期——数据接入、网格生成、对象复用、超时回收、主题切换、可见性控制。它管的是物体从生到死的全过程；需要时也可以在层内给节点挂上物理Layer，再与`cullingMask`配合——两者职责不同，可以并存，但不是同一套机制。

*[配图见公众号原文]*

---

# 框架整体结构

整个分层框架由三层继承关系组成：`SceneNode` → `ElementLayer` → 具体子类。由`ElementLayerManager`统一调度。

*[配图见公众号原文]*

## SceneNode：节点基类

`SceneNode`是整个场景渲染体系的基础节点，提供了所有场景节点共有的能力：

- **物体绑定**：首次`Update`时延迟创建并挂到父节点。
- **可见性**：把`Show`/`Hide`丢进队列，在下一次`Update`里统一执行。
- **生命周期**：初始化、每帧更新和销毁的基类方法。
- **任务队列**：`ConcurrentQueue<Action>`，包括改名、改父节点、改可见性等Action。

## ElementLayer：层基类

`ElementLayer`继承`SceneNode`，定义了"一层"的核心扩展点，包括资源的加载路径，加载方式，主题变化的处理方式以及销毁方式。

```csharp
public class ElementLayer : SceneNode
{
    protected GameObject DefaultPrefab;    // 该层物体的默认预制体

    // 赋值变化时自动触发 LoadDefaultPrefab
    protected string DefaultPrefabUrl
    {
        ...
    }
    // 加载预制体资源
    protected virtual void LoadDefaultPrefab() { ... }

    // 主题切换（昼夜/节日）
    public virtual void OnThemeChanged() { }

    // 可选，数据处理入口
    public virtual void FillData(IPayload packet) { }

    // 资源清理（场景关闭 / 暂停时由上层统一调用）
    public virtual void Clear() { }
}
```

## 具体子类

用`ElementLayerId`枚举声明层类型，以区分不同子类：

```csharp
private void CreateLayers()
{
    _layerList = new Dictionary<ElementLayerId, ElementLayer>
    {
        { ElementLayerId.LaneLine,     new LaneLineLayer(...) },     // 车道线
        { ElementLayerId.RoadMark,     new RoadMarkLayer(...) },     // 路面标识
        { ElementLayerId.StopLine,     new StopLineLayer(...) },     // 停止线
        { ElementLayerId.Crosswalk,    new CrosswalkLayer(...) },    // 人行横道
        { ElementLayerId.RoadMesh,     new RoadMeshLayer(...) },     // 道路面
        { ElementLayerId.FuncState,    new FuncStateLayer(...) },    // 功能状态
        { ElementLayerId.Common,       new CommonLayer(...) },       // 通用占位
        { ElementLayerId.Alert,        new AlertLayer(...) },        // 通知提示
        { ElementLayerId.ParkingSlot,  new ParkingSlotLayer(...) }   // 泊车位
    };
}
```

每个子类管理一类场景元素，职责清晰互不干扰。以`ParkingSlotLayer`为例，它管理泊车位对象列表的完整生命周期：

```csharp
public class ParkingSlotLayer : ElementLayer, IEventBinder
{
    private List<ParkingSlotObject> _objList = new(50); // 按索引复用的对象列表

    // 收到感知数据后
    private void OnParkingSlots(ParkingSlotsEvent e)
    {
        // 1. 复用已有对象：Reset + FillData + Visible=true
        // 2. 不足时新建对象加入列表
        // 3. 超时未刷新的对象 Dispose
    }
}
```

---

# 驱动方式

## ElementLayerManager

`ElementLayerManager`是所有层的调度中心，核心职责是：创建层、每帧更新层、响应主题切换、统一清理。

```csharp
public class ElementLayerManager : SceneNode
{
    private Dictionary<ElementLayerId, ElementLayer> _layerList;

    protected override void OnUpdate()
    {
        foreach (ElementLayer layer in _layerList.Values)
        {
            if (layer.Visible)    // 不可见的层跳过本帧 Update
            {
                try { layer.Update(); }
                catch (Exception e) { RenderLog.Error(TAG, e); }
            }
        }
    }
}
```

`Visible=false`时，该层不会进入`Update`→`OnUpdate`，会停掉该层的所有逻辑，包括创建和物体复用。

*[配图见公众号原文]*

## 数据驱动

实现`IEventBinder`，通过事件系统接收数据：

```csharp
public class ParkingSlotLayer : ElementLayer, IEventBinder
{
    public IModuleHub GetArchitecture() => ModuleArchitecture.Interface;

    // OnAwake 时注册事件
    this.RegisterEvent<ParkingSlotsEvent>((sender, args) => {
        // 收到泊车位感知数据，更新对象列表
    });
}
```

事件驱动适合频率不固定、需要立即响应的数据源，比如泊车位检测结果、功能状态变化。

## 主题

昼夜主题切换通过对AppModel的值变化监听触发：

```csharp
// ElementLayerManager 构造时注册监听
AppModel.DayNightMode.RegisterOnValueChanged(OnDayNightChanged);

// 昼夜切换 → 遍历所有层 → 各层重写 OnThemeChanged
private void OnDayNightChanged(DayNightMode mode)
{
    foreach (var layer in _layerList.Values)
        layer.OnThemeChanged();
}
```

各子类的`OnThemeChanged()`去执行具体的材质属性修改。

---

# 层内的物体

## ElementObject

`ElementObject`继承`SceneNode`，它是具体的每根车道线、泊车位等物体的基类/基础单元，ElementObject就是可管理的生成物的最小单元。

```csharp
public abstract class ElementObject : SceneNode
{
    public abstract void FillData(IElementData data);
    public abstract void OnThemeChanged();
}
```

以`ParkingSlotObject`为例，在`ParkingSlotLayer`的控制下：

**创建**：当收到了泊车位数据的时候，列表里复用或新建物体，`FillData`写入数据并标记样式名，`Visible=true`

**更新**：每帧需要时，取Prefab路径和颜色/贴图进行销毁和重建。

**回收**：本帧数据不包含此ElementObject，设`Visible=false`，并且如果超过一定时间数据未刷新，则`Dispose()`

Layer 管数据与存活，Object 管自己的样式与重建。

```csharp
// Layer 侧：事件里复用或新建后灌数据
private void OnParkingSlots(ParkingSlotsEvent e)
{
    for (int i = 0; i < e.Slots.Count; i++)
    {
        var obj = i < _objList.Count ? _objList[i] : CreateNew();
        obj.FillData(e.Slots[i]);
        obj.Visible = true;
    }
    // 本帧未命中的：Visible=false；超时：Dispose()
}

// Object 侧：FillData 只记样式名，不立刻 Instantiate
public override void FillData(IElementData data)
{
    _data = (ParkingSlotData)data;
    StyleName = _data.StyleName;       // 标脏，等 OnUpdate 再刷
    ColorStyleName = _data.ColorStyle;
}

protected override void OnUpdate()
{
    if (_needUpdateStyle)
    {
        ApplyStyle();   // 从样式表取预制体+材质，重建或刷新
        _needUpdateStyle = false;
    }
}
```

---

## 结语

基于分层的场景管理，是为了把SR场景中杂乱的物体按类型管理。

每个`ElementLayer`既是一个渲染容器，又是一个生命周期管理器。

节日主题也可使用这套设计结构：

- 要在已有感知物上叠加装饰，可新建或按需挂载一个新的 layer 来适配；
- 若要在原有感知物上替换资源，则需在`ElementObject`侧做换皮。

换皮机制将在下一篇系列文章中分享。

