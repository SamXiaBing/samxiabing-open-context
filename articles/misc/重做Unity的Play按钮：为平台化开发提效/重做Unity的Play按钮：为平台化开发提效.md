---
title: "重做Unity的Play按钮：为平台化开发提效"
date: 2026-05-25
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> 一个平台化的3D HMI工程，为了满足不同车型、不同应用多合一的兼容能力。我们往往会因为考虑到启动阶段的严苛的性能环境和快速启动的要求，而去设计一个“空场景”作为在引擎完成加载之后的第一个业务场景。无论你后续真正要加载的业务场景是什么，总有那么一些模块是大家都需要的，就会放在这个场景里，比如日志服务模块、信号通讯模块、资源管理模块。

于是，在这个把‘空场景’作为 Bootstrap 场景的工程里，大多数人都会经历这样的调试循环：在另一个具体的业务场景里改完面板物体的参数 → 切回到 Bootstrap 场景 → 点 Play → 看完运行结果后停止 → 再切回原场景继续修改。五步动作反复做，一天下来光切场景就切了几十次，很麻烦。本文介绍一个小工具的做法，把这套循环压成一个按钮。

---

## 1. 工具职责

核心诉求：**在任意场景里，选好车型项目，一键从 Bootstrap 跑起来，跑完自动回到原场景**。

拆成三件事：

- **项目选择**：下拉框列出所有车型项目，选一个。
- **一键启动**：自动保存当前场景 → 打开 Bootstrap → 进入 Play 模式。
- **自动恢复**：退出 Play 时，自动重新打开之前在编辑的场景。

---

## 2. 做法

- 通过反射拿到 Unity 内置 Toolbar 的右侧区域，插入一个 IMGUI 容器渲染下拉框和按钮；
- 点击按钮时保存当前场景路径、打开 Bootstrap 场景并进入 Play 模式；
- 退出 Play 时从缓存路径恢复原场景。

### 2.1 按钮 — Toolbar注入

Unity 的 Toolbar 是内部类型，没有公开 API。但我们可以通过反射拿到它，然后往右侧区域插入自定义 UI，示意代码如下:

```csharp
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

[InitializeOnLoad]
public static class ProjectLauncherToolbar
{
    // Unity 内部 Toolbar 类型
    static readonly Type ToolbarType =
        typeof(Editor).Assembly.GetType("UnityEditor.Toolbar");

    static ScriptableObject _currentToolbar;

    static ProjectLauncherToolbar()
    {
        EditorApplication.update += OnUpdate;
    }

    static void OnUpdate()
    {
        if (_currentToolbar != null) return;

        // 反射查找 Toolbar 实例
        var toolbars = Resources.FindObjectsOfTypeAll(ToolbarType);
        _currentToolbar = toolbars.Length > 0
            ? (ScriptableObject)toolbars[0]
            : null;

        if (_currentToolbar == null) return;

        // 拿到 Toolbar 的 VisualElement 根节点
        var rootField = _currentToolbar.GetType()
            .GetField("m_Root",
                BindingFlags.NonPublic | BindingFlags.Instance);
        var concreteRoot = rootField.GetValue(_currentToolbar) as VisualElement;

        // 在右侧区域插入自定义容器
        var rightZone = concreteRoot.Q("ToolbarZoneRightAlign");
        var container = new VisualElement
        {
            style =
            {
                flexGrow = 1,
                flexDirection = FlexDirection.Row,
            }
        };
        var imgui = new IMGUIContainer();
        imgui.onGUIHandler += OnToolbarGUI;
        container.Add(imgui);
        rightZone.Add(container);
    }
}

```

- `[InitializeOnLoad]` 保证编辑器启动时就注册回调
- `EditorApplication.update` 每帧检查 Toolbar 是否已创建，保证注入时机正确
- `ToolbarZoneRightAlign` 是 Unity Toolbar 右侧区域的名字，插入后自定义 UI 自然靠右排列
- 用 `IMGUIContainer` 桥接 IMGUI 绘制到 UIElement 树里

### 2.2 下拉框 — 选择项目

平台化项目里，你可以选择一个方式去扫描出你希望能被选择的子项目/子应用。比如，你可以定向搜索某个文件夹的子文件夹，每个子文件夹都是子项目/子应用的资产；你也可以让每个应用都包含一个继承某个基类的脚本。工具扫描所有脚本，找到这些子类，就能自动列出项目清单，示意代码如下：

```csharp
static List<string> DiscoverProjects()
{
    var result = new List<string>();
    // 查找所有脚本资源
    var guids = AssetDatabase.FindAssets("t:Script");
    // 通过反射拿到项目基类
    Type baseType = Utility.Assembly.GetType("MyApp.Runtime.ProjectBase");
    if (baseType == null) return result;

    foreach (var guid in guids)
    {
        var path = AssetDatabase.GUIDToAssetPath(guid);
        var script = AssetDatabase.LoadAssetAtPath<MonoScript>(path);
        if (script?.GetClass() != null
            && script.GetClass().IsSubclassOf(baseType))
        {
            // 从路径提取项目名：Assets/Projects/<项目名>/Runtime/...
            var match = Regex.Match(path, @"Assets/Projects/(.*?)/Runtime");
            if (match.Success)
                result.Add(match.Groups[1].Value);
        }
    }
    result.Sort();
    return result;
}

```

新增项目/应用时，只要遵循目录约定（放在 `Assets/Projects/<项目名>/Runtime/` 下），下拉框自动出现新条目，工具代码零修改。

### 2.3 一键启动能力

点击 Start 按钮时，需要做三件事：保存当前打开的场景路径、打开 Bootstrap 场景、进入 Play 模式。退出 Play 时自动恢复，示意代码如下：

```csharp
static class ScenePlayHelper
{
    const string SavedScenePathsKey = "ScenePlayHelper_SavedPaths";
    static string _pendingSceneName;

    static ScenePlayHelper()
    {
        EditorApplication.playModeStateChanged += OnPlayModeChanged;
    }

    /// <summary>
    /// 从指定场景启动 Play 模式
    /// </summary>
    public static void StartFromScene(string sceneName)
    {
        if (EditorApplication.isPlaying)
            EditorApplication.isPlaying = false;

        _pendingSceneName = sceneName;
        EditorApplication.update += OpenAndPlay;
    }

    static void OpenAndPlay()
    {
        // 等待编辑器空闲
        if (_pendingSceneName == null
            || EditorApplication.isPlaying
            || EditorApplication.isCompiling)
            return;

        EditorApplication.update -= OpenAndPlay;

        // 先保存当前场景修改
        if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
        {
            _pendingSceneName = null;
            return;
        }

        // 缓存当前场景路径，退出时恢复
        SaveCurrentScenePaths();

        // 按名称查找场景并打开
        var guids = AssetDatabase.FindAssets("t:scene " + _pendingSceneName);
        if (guids.Length > 0)
        {
            var path = AssetDatabase.GUIDToAssetPath(guids[0]);
            EditorSceneManager.OpenScene(path);
            EditorApplication.isPlaying = true;
        }
        _pendingSceneName = null;
    }

    static void OnPlayModeChanged(PlayModeStateChange state)
    {
        // 退出 Play 时恢复之前的场景
        if (state != PlayModeStateChange.EnteredEditMode) return;

        var saved = EditorPrefs.GetString(SavedScenePathsKey);
        if (string.IsNullOrEmpty(saved)) return;

        var paths = saved.Split(';',
            StringSplitOptions.RemoveEmptyEntries);
        for (int i = 0; i < paths.Length; i++)
        {
            if (i == 0)
                EditorSceneManager.OpenScene(paths[0], OpenSceneMode.Single);
            else
                EditorSceneManager.OpenScene(paths[i], OpenSceneMode.Additive);
        }
        EditorPrefs.SetString(SavedScenePathsKey, string.Empty);
    }

    static void SaveCurrentScenePaths()
    {
        var sb = new StringBuilder();
        for (int i = 0; i < EditorSceneManager.loadedSceneCount; i++)
        {
            var scene = EditorSceneManager.GetSceneAt(i);
            sb.Append(scene.path + ";");
        }
        EditorPrefs.SetString(SavedScenePathsKey, sb.ToString());
    }
}

```

流程时序：

1. 用户点击 Start → `StartFromScene("Bootstrap")` 被调用
2. 如果正在 Play，先停掉
3. 等编辑器空闲（不在编译、不在 Play 切换中）
4. 弹窗提示保存当前修改
5. 用 `EditorPrefs` 缓存当前打开的所有场景路径
6. 用 `AssetDatabase.FindAssets` 按名称找到 Bootstrap 场景
7. `OpenScene` 打开它，`isPlaying = true` 进入 Play
8. 退出 Play 时，`playModeStateChanged` 回调触发，从 `EditorPrefs` 读回路径，逐一恢复

### 2.4 串接下拉框和按钮

在 Toolbar 上渲染一个下拉框和一个按钮，示意代码如下：

```csharp
static List<string> _projects;
static int _selectedIndex;
const string LastSelectKey = "ProjectLauncher_LastSelect";

static void OnToolbarGUI()
{
    GUILayout.BeginHorizontal();

    // 项目下拉框
    int newIndex = EditorGUILayout.Popup(
        _selectedIndex,
        _projects.ToArray(),
        GUILayout.Width(200));

    if (newIndex != _selectedIndex)
    {
        _selectedIndex = newIndex;
        EditorPrefs.SetString(LastSelectKey, _projects[newIndex]);
        // 更新当前项目标识，供 Bootstrap 运行时读取
        EditorPrefs.SetString("CurrentProjectName",
            ExtractProjectName(_projects[newIndex]));
    }

    // 一键启动按钮
    if (GUILayout.Button(
        new GUIContent("Start",
            EditorGUIUtility.FindTexture("PlayButton")),
        GUILayout.Width(60)))
    {
        ScenePlayHelper.StartFromScene("Bootstrap");
    }

    GUILayout.EndHorizontal();
}

```

项目切换时还会做两件**辅助操作**：

- **画面质量切换**：某些平台硬件性能较低，选择对应项目时自动调低 `QualitySettings` 等级。
- **Game窗口分辨率切换**：不同应用的运行时窗口分辨率不同，切换项目时自动调整 Game视图窗口的尺寸。

> 关于Bootstrap根据项目名进行解析和载入的流程，放到开发框架讲述启动器的部分撰写。

---

## 3. 结尾

工具本身的代码量不大，但省下的调试时间是巨大的。做工具的核心思路，就是把这类‘重复操作 → 一键搞定’的场景自动化。