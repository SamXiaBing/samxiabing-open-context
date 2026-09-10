---
title: "ADAS SR Development: SR Scene Styles and Theme Management"
date: 2026-07-30
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered how to use Layers in an SR scene to manage objects hierarchically, splitting lane lines, parking slots, and so on into per-object layers, with each layer managing its own lifecycle. When we later discussed object creation, I mentioned that a stylization mechanism would be embedded there, namely theme management. This article shares the StyleManager module—a skin-swapping mechanism for the SR scene.

![图1](./图1.png)

---

## 1. The Requirement

An object's visual appearance in an SR scene is influenced by multiple dimensions. These dimensions are not mutually exclusive—they act on the same object simultaneously, resolved through different mechanisms:

- **Environment dimension** (day/night mode): lane lines are white by day and gray at night. This dimension is global; all objects change together.
- **Functional dimension** (state changes): a parking slot is one color when available and another when selected. This dimension belongs to each individual object; different objects are in different states.

If every module listened to day/night changes on its own and loaded materials based on its own state, the code would be scattered everywhere. StyleCatalog's approach is to centralize all objects' appearance definitions in a single JSON config, using two dimensions to locate an object's specific look: **the theme (Theme) determines the environmental context, and the style name (Style Name) determines the object's own identity**. At runtime, theme plus style name look up "what this object should look like in the current environment."

## 2. Overall Architecture

The module consists of three core parts: `StyleManager` (the coordinator), `Theme` (the theme pack), and `Style` (an individual style).

### 2.1 Style: the Appearance Definition

A `Style` is the complete appearance description of an object under a given theme:

```csharp
public class Style
{
    public string Type;           // style type
    public string PrefabPath;     // prefab path
    public Color Color;           // primary color
    public Color Color2;          // secondary color 2
    public Color Color3;          // secondary color 3
    public Material Material;     // material (lazily loaded)
    public Texture Texture;       // texture (lazily loaded)
    public ShadowCastingMode CastShadowMode;
    public bool ReceiveShadow;
}

```

The material and texture storage inside `Style` could be replaced with a url form, loading through the asset-management module's LoadAsset only when needed.

### 2.2 Theme: the Theme Definition

A `Theme` corresponds to one theme (for example, a day theme, a night theme, a Spring Festival theme). Internally it mainly maintains a Style dictionary:

```csharp
public class Theme
{
    public string ThemeName { get; }
    private Dictionary<string, Style> _styles;

    public bool InitStyle(Dictionary<string, StyleThemeJson> raw);
    public Style GetStyle(string styleName);
}

```

### 2.3 StyleManager: the Theme Manager

`StyleManager` is responsible for loading the JSON config, managing the current theme, and providing style queries.

```csharp
public class StyleManager : IStyleManager
{
    public void Init(string configPath);              // load the JSON config
    public bool UpdateTheme(string themeName);        // switch to the specified theme
    public Style GetStyle(string styleName);          // query styles under the current theme
}

```

Initialization flow, sketch code:

```csharp
_styleManager = new StyleManager(this);
_styleManager.Init("Configs/StyleConfig");   // load the JSON
_styleManager.UpdateTheme("Day");             // day theme by default

```

---

## 3. The JSON Config File

All style definitions are concentrated in a single JSON file:

```json
{
  "style": {
    "Theme.Day": {
      "config": {
        "StopLineMat": {
          "material": "Materials/StopLineMat_Day",
          "color": "#FFFFFFFF"
        },
        "ParkingSlot_Available": {
          "prefab_path": "Prefabs/Slot_Available",
          "color": "#4CAF50FF"
        },
        "ParkingSlot_Selected": {
          "prefab_path": "Prefabs/Slot_Selected",
          "color": "#2196F3FF"
        }
      }
    },
    "Theme.Night": {
      "config": {
        "StopLineMat": {
          "material": "Materials/StopLineMat_Night",
          "color": "#808080FF"
        }
      }
    }
  }
}

```

Each style under each theme has one or more properties; which property fields exist is configured according to what the object needs. The day theme defines the material and color of `StopLineMat`, while the night theme may only change the material.

Note the division of labor between the two dimensions here: **the theme corresponds to the environment dimension, the style name to the functional dimension**. A parking slot in the "available" state by day queries ParkingSlot_Available under Theme.Day; after switching to night, the same style name under Theme.Night points to another set of textures. Environment changes are handled uniformly by theme switching; state changes are addressed precisely by style name.

### Hierarchical Design of Style Names

In real projects, the variants under one semantic are far more than two. Take parking slots: they split into mechanical slots and regular slots, each further split into multiple states such as Default, Disable, CanSelect, Checking, ParkingHead, ParkingRear, plus narrow and non-narrow slots. There are many variants, and writing `prefab_path` repeatedly for every variant would be rather unintelligent.

StyleCatalog's approach: **style names are separated by** `.` **and automatically inherit from the parent style by hierarchy**.

```csharp
private Style CreateStyle(string styleName, Dictionary<string, StyleElementConfigJson> elementsJson)
{
    int index = styleName.IndexOf('.');
    Style ret = null;
    Style parent = null;
    if (index > 0) {
        // recursively create the parent style
        string parentStyle = styleName.Substring(0, index);
        parent = CreateStyle(parentStyle, elementsJson);
    }

    if (!_styles.TryGetValue(styleName, out ret)) {
        ret = new Style(parent);   // clone all of the parent style's properties
        _styles.Add(styleName, ret);
    }

    if (elementsJson.TryGetValue(styleName, out StyleElementConfigJson elementJson)) {
        ret.LoadJson(elementJson); // load its own config, overriding properties inherited from the parent
    }
    return ret;
}

```

---

## 4. The Theme-Switching Chain

![图2](./图2.png)

Understanding it as a whole: StyleManager is responsible for updating the data, and LayerManager consumes it.

### What the Layer Does

Once a Layer's `OnThemeChanged()` fires, it can **update materials directly**: the Layer re-fetches the material itself and iterates over its subordinate objects to update them.

```csharp
// CrossWalkLaye
public override void OnThemeChanged()
{
    m_CrossWalkMaterial = Context.GetStyleSystem().GetStyle("CrossWalkMat").Material;
    foreach (var obj in activeObjects)
    {
        obj.GetComponent<Renderer>().material = m_CrossWalkMaterial;
    }
}

```

Or it can **forward to the Objects under the Layer**: the Layer doesn't process anything directly and lets each Object decide how to swap itself.

### What the Object Does

This is where the core of skin-swapping happens. After an Object receives the theme-switch notification, it re-queries the style, assigns the style's values, and marks itself as needing an update.

```csharp
public override void FillData(IMapData data)
{
    _data = (ParkingSlotData)data;
    // only record the style name, mark dirty, don't touch assets
    StyleName = _data.StyleName;
    ColorStyleName = _data.ColorStyle;
}

protected override void OnUpdate()
{
    if (_needUpdateStyle)
    {
        UpdateStyle();
        _needUpdateStyle = false;
    }
}

public override void OnThemeChanged()
{
    UpdateStyle();  // the theme changed; force a refresh against the current Catalog
}

private void UpdateStyle()
{
    Style style = StyleCatalog.GetStyle(StyleName);
    if (style == null) return;

    // only trigger Rebuild when the path changed; on change, destroy the old GO and rebuild with the new prefab
    PrefabPath = style.PrefabPath;

    // color and texture are changed in place, no rebuild needed
    Style colorStyle = StyleCatalog.GetStyle(ColorStyleName);
    if (colorStyle.Texture != null)
        _slotController.Material.SetTexture(ShaderProperty.BaseMap, colorStyle.Texture);
    _slotController.RefreshParkBackgroundColor(colorStyle.Color);
}
```

---

## Closing

Combined with the layered framework, this style design strips appearance definitions out of the code. It makes the boundary between designers and developers clearer here, and the collaboration more direct.
