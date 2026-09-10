---
title: "Rethinking Unity's Play Button: Boosting Efficiency for Platform-Based Development"
date: 2026-05-25
series: misc
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> In a platform-based 3D HMI project, to support compatibility across different vehicle models and multiple apps running as one, we often have to account for the harsh performance environment at startup and the requirement for fast boot. That's why we typically design an "empty scene" as the first business scene the engine loads after startup. No matter what business scene you load later, there are always some modules everyone needs, so they go into this scene — for example, the logging service module, the signal communication module, and the resource management module.

So in a project like this, where the "empty scene" serves as the Bootstrap scene, most people go through this debugging loop: tweak the parameters of panel objects in some concrete business scene → switch back to the Bootstrap scene → hit Play → watch the result, stop → switch back to the original scene to keep editing. Five steps, over and over. By the end of the day you've switched scenes dozens of times. It's a pain. This article covers a small tool that compresses this whole loop into a single button.

---

## 1. What the Tool Does

The core requirement: **from any scene, pick a vehicle-model project, launch from Bootstrap with one click, and automatically return to the original scene when done**.

It breaks down into three things:

- **Project selection**: a dropdown listing all vehicle-model projects; pick one.
- **One-click launch**: automatically save the current scene → open Bootstrap → enter Play mode.
- **Automatic restore**: when exiting Play, automatically reopen the scene you were editing.

---

## 2. How It's Built

- Use reflection to get the right-side zone of Unity's built-in Toolbar, and insert an IMGUI container to render the dropdown and button;
- When the button is clicked, save the current scene path, open the Bootstrap scene, and enter Play mode;
- When exiting Play, restore the original scene from the cached path.

### 2.1 The Button — Toolbar Injection

Unity's Toolbar is an internal type with no public API. But we can get it through reflection and then insert custom UI into the right-side zone. Here's the illustrative code:

```csharp
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

[InitializeOnLoad]
public static class ProjectLauncherToolbar
{
    // Unity's internal Toolbar type
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

        // Find the Toolbar instance via reflection
        var toolbars = Resources.FindObjectsOfTypeAll(ToolbarType);
        _currentToolbar = toolbars.Length > 0
            ? (ScriptableObject)toolbars[0]
            : null;

        if (_currentToolbar == null) return;

        // Get the Toolbar's VisualElement root
        var rootField = _currentToolbar.GetType()
            .GetField("m_Root",
                BindingFlags.NonPublic | BindingFlags.Instance);
        var concreteRoot = rootField.GetValue(_currentToolbar) as VisualElement;

        // Insert a custom container into the right-side zone
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

- `[InitializeOnLoad]` ensures the callback is registered as soon as the editor starts
- `EditorApplication.update` checks every frame whether the Toolbar has been created, ensuring injection happens at the right moment
- `ToolbarZoneRightAlign` is the name of the right-side zone of Unity's Toolbar; once inserted, the custom UI naturally aligns to the right
- `IMGUIContainer` bridges IMGUI drawing into the UIElements tree

### 2.2 The Dropdown — Selecting a Project

In a platform-based project, you can pick a way to scan out the sub-projects/sub-apps you want to be selectable. For example, you can search a specific folder's subfolders, where each subfolder holds the assets of one sub-project/sub-app. Or you can require every app to include a script inheriting from some base class. The tool scans all scripts, finds these subclasses, and automatically builds the project list. Here's the illustrative code:

```csharp
static List<string> DiscoverProjects()
{
    var result = new List<string>();
    // Find all script assets
    var guids = AssetDatabase.FindAssets("t:Script");
    // Get the project base class via reflection
    Type baseType = Utility.Assembly.GetType("MyApp.Runtime.ProjectBase");
    if (baseType == null) return result;

    foreach (var guid in guids)
    {
        var path = AssetDatabase.GUIDToAssetPath(guid);
        var script = AssetDatabase.LoadAssetAtPath<MonoScript>(path);
        if (script?.GetClass() != null
            && script.GetClass().IsSubclassOf(baseType))
        {
            // Extract the project name from the path: Assets/Projects/<ProjectName>/Runtime/...
            var match = Regex.Match(path, @"Assets/Projects/(.*?)/Runtime");
            if (match.Success)
                result.Add(match.Groups[1].Value);
        }
    }
    result.Sort();
    return result;
}

```

When a new project/app is added, as long as it follows the directory convention (placed under `Assets/Projects/<ProjectName>/Runtime/`), it automatically shows up in the dropdown — zero changes to the tool's code.

### 2.3 One-Click Launch

When the Start button is clicked, three things need to happen: save the currently open scene path, open the Bootstrap scene, and enter Play mode. It automatically restores on exiting Play. Here's the illustrative code:

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
    /// Start Play mode from the specified scene
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
        // Wait for the editor to be idle
        if (_pendingSceneName == null
            || EditorApplication.isPlaying
            || EditorApplication.isCompiling)
            return;

        EditorApplication.update -= OpenAndPlay;

        // Save current scene modifications first
        if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
        {
            _pendingSceneName = null;
            return;
        }

        // Cache the current scene paths, restore on exit
        SaveCurrentScenePaths();

        // Find the scene by name and open it
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
        // Restore the previous scenes when exiting Play
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

The flow, step by step:

1. The user clicks Start → `StartFromScene("Bootstrap")` is called
2. If already in Play mode, stop first
3. Wait for the editor to be idle (not compiling, not mid Play-mode transition)
4. Prompt to save current modifications
5. Cache all currently open scene paths with `EditorPrefs`
6. Use `AssetDatabase.FindAssets` to locate the Bootstrap scene by name
7. `OpenScene` opens it, `isPlaying = true` enters Play
8. On exiting Play, the `playModeStateChanged` callback fires, reads the paths back from `EditorPrefs`, and restores them one by one

### 2.4 Wiring the Dropdown and Button Together

Render a dropdown and a button on the Toolbar. Here's the illustrative code:

```csharp
static List<string> _projects;
static int _selectedIndex;
const string LastSelectKey = "ProjectLauncher_LastSelect";

static void OnToolbarGUI()
{
    GUILayout.BeginHorizontal();

    // Project dropdown
    int newIndex = EditorGUILayout.Popup(
        _selectedIndex,
        _projects.ToArray(),
        GUILayout.Width(200));

    if (newIndex != _selectedIndex)
    {
        _selectedIndex = newIndex;
        EditorPrefs.SetString(LastSelectKey, _projects[newIndex]);
        // Update the current project identifier for the Bootstrap runtime to read
        EditorPrefs.SetString("CurrentProjectName",
            ExtractProjectName(_projects[newIndex]));
    }

    // One-click launch button
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

Switching projects also triggers two **auxiliary operations**:

- **Quality settings switch**: some platform hardware has lower performance; selecting the corresponding project automatically lowers the `QualitySettings` level.
- **Game window resolution switch**: different apps run at different runtime window resolutions; switching projects automatically adjusts the Game view window size.

> The details of how Bootstrap parses and loads things based on the project name will be covered in the launcher part of the development framework series.

---

## 3. Closing Thoughts

The tool itself is not much code, but the debugging time it saves is enormous. The core idea of tooling is exactly this: automate scenarios of the form "repeated operations → one click and done."
