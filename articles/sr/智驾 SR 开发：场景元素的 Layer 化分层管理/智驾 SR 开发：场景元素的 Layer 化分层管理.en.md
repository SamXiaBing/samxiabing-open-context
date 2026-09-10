---
title: "Intelligent Driving SR Development: Layer-Based Hierarchical Management of Scene Elements"
date: 2026-07-23
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In intelligent driving SR development, the scene contains a great variety of elements—lane lines, road surface, stop lines, crosswalks, parking slots, road markings... If all objects are piled together and managed in one place, the code tends to get messier with every change and becomes hard to maintain.

I first came across the idea of layered management in 3D navigation apps. Because the maps a 3D navigation app displays contain numerous map elements, there emerged the software architecture idea of creating and rendering the world's objects in separate layers.

The Layer in Layer-based hierarchical management is not the object Layer in the Unity engine—it's not just the cullingMask concept that controls whether an object enters the camera's rendering. It is a custom class: it groups same-type scene elements into a "layer", and a `Layer` class manages the complete lifecycle of all objects within that layer—data ingestion, mesh generation, object reuse, timeout recycling, theme switching, and visibility control. It manages an object's entire process from birth to death; when needed, you can also attach a physics Layer to nodes within the layer and combine it with `cullingMask`—the two have different responsibilities and can coexist, but they are not the same mechanism.

*[Figures omitted; see the original WeChat article]*

---

# Overall Framework Structure

The whole layered framework consists of a three-level inheritance chain: `SceneNode` → `ElementLayer` → concrete subclasses. `ElementLayerManager` does the unified scheduling.

*[Figures omitted; see the original WeChat article]*

## SceneNode: The Node Base Class

`SceneNode` is the base node of the entire scene rendering system, providing the capabilities common to all scene nodes:

- **Object binding**: lazily created and attached to the parent node on the first `Update`.
- **Visibility**: `Show`/`Hide` calls are thrown into a queue and executed together in the next `Update`.
- **Lifecycle**: base-class methods for initialization, per-frame update, and destruction.
- **Task queue**: a `ConcurrentQueue<Action>`, holding actions like renaming, re-parenting, and visibility changes.

## ElementLayer: The Layer Base Class

`ElementLayer` inherits from `SceneNode` and defines the core extension points of "a layer", including the resource loading path, the loading method, how theme changes are handled, and how destruction works.

```csharp
public class ElementLayer : SceneNode
{
    protected GameObject DefaultPrefab;    // the default prefab for this layer's objects

    // automatically triggers LoadDefaultPrefab when the value changes
    protected string DefaultPrefabUrl
    {
        ...
    }
    // load the prefab resource
    protected virtual void LoadDefaultPrefab() { ... }

    // theme switching (day-night / festival)
    public virtual void OnThemeChanged() { }

    // optional, data entry point
    public virtual void FillData(IPayload packet) { }

    // resource cleanup (called by the upper layer on scene close / pause)
    public virtual void Clear() { }
}
```

## Concrete Subclasses

Declare the layer types with the `ElementLayerId` enum to distinguish the different subclasses:

```csharp
private void CreateLayers()
{
    _layerList = new Dictionary<ElementLayerId, ElementLayer>
    {
        { ElementLayerId.LaneLine,     new LaneLineLayer(...) },     // lane lines
        { ElementLayerId.RoadMark,     new RoadMarkLayer(...) },     // road markings
        { ElementLayerId.StopLine,     new StopLineLayer(...) },     // stop lines
        { ElementLayerId.Crosswalk,    new CrosswalkLayer(...) },    // crosswalks
        { ElementLayerId.RoadMesh,     new RoadMeshLayer(...) },     // road surface
        { ElementLayerId.FuncState,    new FuncStateLayer(...) },    // function states
        { ElementLayerId.Common,       new CommonLayer(...) },       // general-purpose placeholder
        { ElementLayerId.Alert,        new AlertLayer(...) },        // notifications
        { ElementLayerId.ParkingSlot,  new ParkingSlotLayer(...) }   // parking slots
    };
}
```

Each subclass manages one category of scene elements, with clear, non-interfering responsibilities. Take `ParkingSlotLayer` as an example: it manages the complete lifecycle of the parking-slot object list:

```csharp
public class ParkingSlotLayer : ElementLayer, IEventBinder
{
    private List<ParkingSlotObject> _objList = new(50); // object list reused by index

    // after perception data arrives
    private void OnParkingSlots(ParkingSlotsEvent e)
    {
        // 1. Reuse existing objects: Reset + FillData + Visible=true
        // 2. When insufficient, create new objects and add them to the list
        // 3. Dispose objects not refreshed within the timeout
    }
}
```

---

# Driving Mechanisms

## ElementLayerManager

`ElementLayerManager` is the scheduling hub of all layers. Its core responsibilities: create layers, update layers every frame, respond to theme switches, and perform unified cleanup.

```csharp
public class ElementLayerManager : SceneNode
{
    private Dictionary<ElementLayerId, ElementLayer> _layerList;

    protected override void OnUpdate()
    {
        foreach (ElementLayer layer in _layerList.Values)
        {
            if (layer.Visible)    // invisible layers skip this frame's Update
            {
                try { layer.Update(); }
                catch (Exception e) { RenderLog.Error(TAG, e); }
            }
        }
    }
}
```

When `Visible=false`, the layer never enters `Update`→`OnUpdate`, which stops all of the layer's logic, including creation and object reuse.

*[Figures omitted; see the original WeChat article]*

## Data-Driven

Implement `IEventBinder` and receive data through the event system:

```csharp
public class ParkingSlotLayer : ElementLayer, IEventBinder
{
    public IModuleHub GetArchitecture() => ModuleArchitecture.Interface;

    // register events in OnAwake
    this.RegisterEvent<ParkingSlotsEvent>((sender, args) => {
        // parking-slot perception data received; update the object list
    });
}
```

The event-driven approach suits data sources with irregular frequency that need immediate response, such as parking-slot detection results and function state changes.

## Themes

Day-night theme switching is triggered by listening for value changes on AppModel:

```csharp
// register the listener when ElementLayerManager is constructed
AppModel.DayNightMode.RegisterOnValueChanged(OnDayNightChanged);

// day-night switch → iterate all layers → each layer overrides OnThemeChanged
private void OnDayNightChanged(DayNightMode mode)
{
    foreach (var layer in _layerList.Values)
        layer.OnThemeChanged();
}
```

Each subclass's `OnThemeChanged()` performs the specific material property modifications.

---

# Objects Within a Layer

## ElementObject

`ElementObject` inherits from `SceneNode`. It is the base class / basic unit of each concrete object—each lane line, each parking slot, and so on. ElementObject is the smallest manageable unit of spawned output.

Take `ParkingSlotObject` as an example, under `ParkingSlotLayer`'s control:

**Creation**: when parking-slot data arrives, reuse or create an object in the list; `FillData` writes the data and marks the style name; `Visible=true`

**Update**: each frame when needed, take the prefab path and color/texture to destroy and rebuild.

**Recycling**: this frame's data doesn't contain this ElementObject, so set `Visible=false`; and if the data hasn't refreshed within a certain time, call `Dispose()`

The Layer manages data and survival; the Object manages its own style and rebuilding.

```csharp
// Layer side: after reusing or creating in the event, pour in the data
private void OnParkingSlots(ParkingSlotsEvent e)
{
    for (int i = 0; i < e.Slots.Count; i++)
    {
        var obj = i < _objList.Count ? _objList[i] : CreateNew();
        obj.FillData(e.Slots[i]);
        obj.Visible = true;
    }
    // Not hit this frame: Visible=false; timeout: Dispose()
}

// Object side: FillData only records the style name, doesn't Instantiate right away
public override void FillData(IElementData data)
{
    _data = (ParkingSlotData)data;
    StyleName = _data.StyleName;       // mark dirty, refresh later in OnUpdate
    ColorStyleName = _data.ColorStyle;
}

protected override void OnUpdate()
{
    if (_needUpdateStyle)
    {
        ApplyStyle();   // take prefab + material from the style sheet, rebuild or refresh
        _needUpdateStyle = false;
    }
}
```

---

## Closing Thoughts

Layer-based scene management exists to manage the messy objects in the SR scene by type.

Each `ElementLayer` is both a rendering container and a lifecycle manager.

Festival themes can also use this design structure:

- To overlay decorations on existing perceived objects, create a new layer or mount one on demand to adapt;
- To replace resources on the original perceived objects, you need to do reskinning on the `ElementObject` side.

The reskinning mechanism will be shared in the next article of the series.

