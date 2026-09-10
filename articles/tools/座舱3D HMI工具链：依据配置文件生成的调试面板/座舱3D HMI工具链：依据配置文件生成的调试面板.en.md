---
title: "Cockpit 3D HMI Toolchain: A Debug Panel Generated from Configuration Files"
date: 2026-07-17
series: tools
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> Today's various 3D engines all offer some level of support for custom engine tool panels. When delivering 3D HMI software, we also need to simulate and test some signals inside the editor for development self-testing. As platform-based engineering progresses, this tool has to support more applications and more signals while also taking usage efficiency into account.

So the tool we built earlier maintains an independent panel inside the editor, where clicking a button simulates the corresponding signal being received. Developers only need to modify the text content of a Json file following a fixed protocol, and the corresponding buttons, progress bars, or radio buttons automatically show up in the editor. It also supports a different Json file per application, and supports searching to surface the test UI you need.

*[Figures omitted; see the original WeChat article]*

## 1. The Configuration

A JSON file describes the UI entries. The information includes which group an entry belongs to, what text the button shows, and what payload is attached when clicked.

```json
{
  "entries": [
    {
      "category": "Lights",
      "displayName": "DRL - On",
      "payload": "<opaque>"
    }
  ]
}

```

`payload`: the so-called payload here is just the string you want to send. You can construct the string's protocol according to your own project's communication protocol.

In the project, files are split by **App** — for example, seatsignals.json for the seats, avatarsignals.json for the virtual human.

*[Figures omitted; see the original WeChat article]*

---

## 2. The Panel

### 2.1 Multi-File Scanning

At startup, it scans all files under `StreamingAssets` ending with `signals.json`, and adds the scanned files' names to the Toolbar:

```csharp
// Illustrative code: names are unrelated to the project
private void CollectSignalFiles()
{
    _signalFiles.Clear();
    foreach (var path in Directory.GetFiles(StreamingAssetsPath))
    {
        if (path.EndsWith("signals.json", StringComparison.OrdinalIgnoreCase))
            _signalFiles.Add(Path.GetFileNameWithoutExtension(path));
    }
}

```

Add a new `XxxSignals.json`, and the panel top automatically gains one more tab.

> Later, because there were too many json files, this was optimized into a dropdown list, which works better.
>
> So wherever the text below mentions a Toolbar, readers can mentally substitute EditorGUILayout.Popup.

### 2.2 The Data Structure

```csharp
// Outer key = file name, inner key = category
Dictionary<string, Dictionary<string, List<PanelEntry>>> _fileToCategories;

class PanelEntry
{
    public string categoryName;
    public string displayName;
    public string payload;   // opaque; the panel doesn't interpret it
}

```

The UI hierarchy is therefore fixed as:

**Toolbar (files) → Foldout (categories) → button list**

### 2.3 UI Drawing

```csharp
void OnGUI()
{
    _toolbarIndex = GUILayout.Toolbar(_toolbarIndex, _signalFiles.ToArray());
    string fileKey = _signalFiles[_toolbarIndex];
    _fileToCategories.TryGetValue(fileKey, out var categoryDict);

    _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);
    foreach (var kv in categoryDict)
    {
        var state = GetOrAddCategoryState(kv.Key);
        state.IsOpen = EditorGUILayout.Foldout(state.IsOpen, kv.Key, _foldoutStyle);
        if (!state.IsOpen) continue;

        EditorGUILayout.BeginVertical(EditorStyles.inspectorDefaultMargins);
        DrawCategory(kv.Value);
        EditorGUILayout.EndVertical();
    }
    EditorGUILayout.EndScrollView();
}

```

The fold state is remembered with `CategoryState`, avoiding everything popping open or snapping shut on every `OnGUI` repaint.

### 2.4 The Search Box

Sometimes there are so many buttons that scrolling the mouse wheel for ages still doesn't land on the one you want — and if you scroll past it, it's even more infuriating!

So later there was a plan to add a search box: put an input field under the Toolbar, filter by `displayName` / `category`; when there's a search term, force-expand the matching categories, and hide empty ones outright.

```csharp
private string _searchText = "";

_searchText = EditorGUILayout.TextField("Search", _searchText);
if (GUILayout.Button("Clear", GUILayout.Width(40)))
    _searchText = "";

bool hasFilter = !string.IsNullOrWhiteSpace(_searchText);
string filter = _searchText.Trim().ToLower();

foreach (var kv in categoryDict)
{
    var matched = new List<PanelEntry>();
    foreach (var entry in kv.Value)
    {
        if (!hasFilter
            || entry.displayName.ToLower().Contains(filter)
            || kv.Key.ToLower().Contains(filter))
            matched.Add(entry);
    }
    if (hasFilter && matched.Count == 0) continue;

    var state = GetOrAddCategoryState(kv.Key);
    if (hasFilter)
    {
        EditorGUILayout.LabelField(kv.Key, EditorStyles.boldLabel);
        DrawCategory(matched);
    }
    else
    {
        state.IsOpen = EditorGUILayout.Foldout(state.IsOpen, kv.Key, _foldoutStyle);
        if (state.IsOpen) DrawCategory(matched);
    }
}

```

*[Figures omitted; see the original WeChat article]*

---

## 3. Simulating Signals

*[Figures omitted; see the original WeChat article]*

### UI Operations

When the JSON is loaded, each config entry becomes a `PanelEntry` (the `category` / `displayName` / `payload` above). At the same time, we prepare a click callback for it:

```csharp
// entry = the PanelEntry corresponding to this JSON config entry
Action onClick = () =>
{
    _injector.Inject(entry.payload);
};
```

Later, when drawing buttons, it's roughly:

```csharp
if (GUILayout.Button(entry.displayName))
{
    onClick();   // equivalent to _injector.Inject(entry.payload)
}
```

### ISignalInjector

`_injector` is an instance of a class implementing the ISignalInjector interface.

```csharp
public interface ISignalInjector
{
    // Receives a string, triggering one "simulated signal"
    void Inject(string payload);
}
```

In `OnEnable` (when the window opens/is enabled), the panel obtains a concrete injector instance and stores it in `_injector`:

```csharp
public class BenchDebugWindow : EditorWindow
{
    ISignalInjector _injector;

    void OnEnable()
    {
        // This decides which delivery method this debugging session uses
        _injector = SignalInjectorFactory.CreateDefault();
    }
}
```

The project side can prepare different implementations:

```csharp
// Scenario A: Play was pressed in the editor, so the signal takes effect locally
class EditorPlayInjector : ISignalInjector
{
    public void Inject(string payload)
    {
        // Hand it to the project's existing debug entry point
        RuntimeDebugEntry.Submit(payload);
    }
}

// Scenario B: when connected to a bench / real device, forward the same payload out
class DeviceRelayInjector : ISignalInjector
{
    public void Inject(string payload)
    {
        DeviceBridge.Send(payload);  
    }
}
```

---

## Closing Words

This tool is mainly aimed at developer self-testing. If you extend the signal-simulation Actions, it can also accommodate bench testing. Meanwhile, it can also be combined with a TestFramework for automated unit testing.

However, it does have limitations: simulating signals by clicking buttons makes it very hard to reproduce cases where a group of multiple signals with timing requirements must fire together. When you hit such a case, you should open up a new source beyond the JSON config file as the data source — for example, a dedicated DebugOption class, reflected into the panel as a button; clicking that button executes the Excute method integrated in this class, and that's when you can start throwing "combination punches".
