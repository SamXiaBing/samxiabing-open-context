---
title: "座舱3D HMI工具链：依据配置文件生成的调试面板"
date: 2026-07-29
series: tools
no: 
status: published
visibility: public
wechat_url: ""
---

> 当前的各类3D引擎，都具备一定的自定义引擎工具面板的支持能力，我们在做 3D HMI软件交付的时候，也需要在编辑器内模拟测试一些信号，做开发自测。随着平台化工程的开展，这个工具在兼容更多应用，更多信号的同时，也要考虑工具使用效率。

所以我们之前所做的这套工具，就是在编辑器里维护一套独立的面板，点一个按钮就能模拟相应的信号被收到。开发者只需要按照固定的协议去修改 Json 文件的文本内容，就能在编辑器上自动看到相应的按钮、进度条或是单选框。还能支持不同应用配置不同的 Json 文件，支持搜索相应的测试UI呈现出来。

*[配图见公众号原文]*

## 一、配置信息

用 JSON 文件描述 UI 条目，信息包括它属于哪个分组、按钮写什么字、点击时带哪段载荷。

```json
{
  "entries": [
    {
      "category": "灯光",
      "displayName": "日行灯 - 开",
      "payload": "<opaque>"
    }
  ]
}

```

`payload` ：这里所谓载荷，其实就是你要发的字符串，你可以根据自己的项目的通讯协议，去构造这串字符串的协议。

工程里按**App**拆成多个 JSON 文件，比如座椅的seatsignals.json，虚拟人的avatarsignals.json。

*[配图见公众号原文]*

---

## 二、面板

### 2.1 多文件扫描

启动时扫描 `StreamingAssets` 下所有以 `signals.json` 结尾的文件，将扫描到的文件的文件名添加进 Toolbar：

```csharp
// 示意代码：名称与工程无关
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

新增一个 `XxxSignals.json`，面板顶部自动多一个标签。

> 后续由于json太多了，这里就优化成为了下拉列表，会更好用。
>
> 所以下文如果提到了 Toolbar的地方，读者可脑补可替换为 EditorGUILayout.Popup。

### 2.2 数据结构

```csharp
// 外层 key = 文件名，内层 key = category
Dictionary<string, Dictionary<string, List<PanelEntry>>> _fileToCategories;

class PanelEntry
{
    public string categoryName;
    public string displayName;
    public string payload;   // 不透明，面板不解读
}

```

界面层次因此固定为：

**Toolbar（文件）→ Foldout（分类）→ 按钮列表**

### 2.3 界面绘制

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

折叠状态用 `CategoryState` 记住，避免每次 `OnGUI` 重绘时全部弹开或全部合上。

### 2.4 搜索框

有时候按钮很多，鼠标滚轮划拉半天也翻不到，要是翻过了，就更气人！

所以之后有考虑加搜索框：在 Toolbar 下加输入框，按 `displayName` / `category` 过滤；有搜索词时强制展开匹配分类，空分类直接隐藏。

```csharp
private string _searchText = "";

_searchText = EditorGUILayout.TextField("搜索", _searchText);
if (GUILayout.Button("清除", GUILayout.Width(40)))
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

*[配图见公众号原文]*

---

## 三、模拟信号

*[配图见公众号原文]*

### UI操作

加载 JSON 时，每条配置会变成一个 `PanelEntry`（上面的 `category` / `displayName` / `payload`）。同时，我们为它准备好一个点击回调：

```csharp
// entry = 这一条 JSON 配置对应的 PanelEntry
Action onClick = () =>
{
    _injector.Inject(entry.payload);
};
```

之后画按钮时，大致就是：

```csharp
if (GUILayout.Button(entry.displayName))
{
    onClick();   // 等价于 _injector.Inject(entry.payload)
}
```

### ISignalInjector

 `_injector` 就是 ISignalInjector 接口的类的实例。
 
```csharp
public interface ISignalInjector
{
    // 收到一段字符串，触发一次「模拟信号」
    void Inject(string payload);
}
```

面板在 `OnEnable`（窗口打开/启用）里拿到一个具体的注入器实例，存到 `_injector`：

```csharp
public class BenchDebugWindow : EditorWindow
{
    ISignalInjector _injector;

    void OnEnable()
    {
        // 这里决定：这次调试用哪一种投递方式
        _injector = SignalInjectorFactory.CreateDefault();
    }
}
```

工程侧可以准备不同实现：

```csharp
// 场景 A：编辑器里点了 Play，信号在本地生效
class EditorPlayInjector : ISignalInjector
{
    public void Inject(string payload)
    {
        // 交给工程里已有的调试入口
        RuntimeDebugEntry.Submit(payload);
    }
}

// 场景 B：连着台架 / 真机时，把同一段 payload 转发出去
class DeviceRelayInjector : ISignalInjector
{
    public void Inject(string payload)
    {
        DeviceBridge.Send(payload);  
    }
}
```

---

## 结语

这套工具主要是面向开发者自测。如果扩展信号模拟的Action，也可以兼容台架的测试。同时，它还可以和 TestFramework 结合，用来做自动化的单元测试。

然而它也有局限，通过点击按你来模拟信号，很不容易模拟出有时序要求的多个信号组成的信号组的情况。遇到这种情况，应该在 JSON 配置文件这个数据源以外，开辟一个新的源头，比如特定的 DebugOption 类，反射出面板的按钮，点击按钮，就会去执行集成这个类的 Excute 方法，这时就可以打“组合拳”了。