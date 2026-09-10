---
title: "Cockpit 3D HMI Toolchain: The Asset Import Rules Module"
lang: en
date: 2026-07-10
series: tools
no: 
status: published
visibility: public
wechat_url: ""
---

> For any software project involving many kinds of assets, the first instinct is usually the same: all assets need to be noticed, and their forms need to be standardized. 3D HMI projects are no different — maximum texture size, compression formats on the Android side, these are all typical objects that need unified constraints.

Cockpit 3D projects feature many asset types, large volumes, and development work that spans multiple collaborating parties (3D art design, UI design, technical art vendors). We can't have every party manually set asset parameters on import, nor can we hope that one asset-management spec document will govern every single import action. So an automated tool that enforces asset import rules is a must.

Built on Unity engine APIs and its Addressables asset management solution, the following sections cover this tool's three-layer delegation-based design architecture, the rule matching approach, writing the configuration files for the asset management solution, and more.

---

# The Code Design

The asset import tool's core structure has three layers: the processor layer (`AllAssetProcessor`) → the rule layer (`AbstractRule`) → the wrapper layer (`AssetImporterWrapper`), driven by the delegation pattern. The call chain is:

*[Figures omitted; see the original WeChat article]*

## The Processor Layer

The whole asset import tool's entry point is Unity's `AssetPostprocessor.OnPostprocessAllAssets` callback, which fires after assets are imported. But `AllAssetProcessor` **doesn't iterate over and process assets directly.** It hands the work over to `AssetProcessorSettings` via a delegate callback.

```csharp
// Unified entry point, delegates to Settings
class AllAssetProcessor : AssetPostprocessor
{
    // Bound at startup by [InitializeOnLoadMethod]
    public static System.Action<string[], string[], string[], string[]> OnPostProcess;

    static void OnPostprocessAllAssets(
        string[] importedAssets,
        string[] deletedAssets,
        string[] movedAssets,
        string[] movedFromAssetPaths)
    {
        // Executes only when the Handler is bound
        if (OnPostProcess != null)
        {
            OnPostProcess(importedAssets, deletedAssets, movedAssets, movedFromAssetPaths);
        }
    }
}
```

Here `OnPostProcess` is bound by `AssetProcessorSettings` in `[InitializeOnLoadMethod]`. AllAssetProcessor is only responsible for forwarding the event.

Illustrative code:

```
// `AssetProcessorSettings` 

[InitializeOnLoadMethod]
static void Initialize()
{
    if (s_Instance == null)
    {
        s_Instance = AssetDatabase.LoadAssetAtPath<AssetProcessorSettings>(path);
        if (s_Instance != null)
        {
            AllAssetProcessor.OnPostProcess = s_Instance.OnPostprocess;  // bind
        }
    }
}
```

## The Rule Layer

What this layer solves is which rule (processing approach) each different asset type should use**:**


```csharp
// Rule base class (simplified illustration)
abstract class AbstractRule : ScriptableObject
{
    // Path regex, filled in via the Inspector
    public string regexPattern;

    // Precheck: skip certain paths, path matching
    public abstract bool Precheck(string path);

    // Postprocess: apply the actual import settings to matched assets
    public abstract void Postprocess(string path, AssetImporter importer);
}
```

**Rule execution**: `AssetProcessorSettings` iterates in `_rules` list order


```
//AssetProcessorSettings

[SerializeField]
private List<AbstractRule> _rules;

private void OnPostprocess(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
{
    foreach (var path in importedAssets)
        Postprocess(path);
    foreach (var path in movedAssets)
        Postprocess(path);
}
private void Postprocess(string assetPath)
{
    if (_rules == null || _rules.Count == 0)
        return;   
    AssetImporterWrapper assetImporter = null;
    foreach (var rule in _rules)
    {
        if (!rule.Precheck(assetPath))
            continue;
        if (assetImporter == null)
            assetImporter = AssetImporterWrapper.GetAtPath(assetPath);
        rule.Postprocess(assetImporter);
        if (assetImporter.IsDirty)
            break;   // stop after the first rule that produces changes executes
    }
    assetImporter?.SaveAndReimport();
}

```


### Rule Design



| Rule                | Purpose                                                |
| ----------------- | ------------------------------------------------- |
| `TextureRule`     | ASTC compression for the Android platform                                |
| `SpriteRule`      | Sprite type settings, disabling Mipmap. Can also apply special handling based on Labels manually tagged by developers. |
| `AddressableRule` | Parses paths; automatically creates/migrates Addressable groups, addresses, and labels                 |
| `SceneRule`       | Per the platform-ization framework's requirements, resets paths and names in Addressables                 |


#### TextureRule

To keep the length manageable, only the texture import rule is shown here. Its main job is compression: automatically setting the Android platform's ASTC compression format.

```
// Determine whether assetPath is a png, jpg, tif, or exr
protected override bool OnPrecheck(string assetPath)
{
  //...
}

// Postprocess
protected override void OnPostprocess(AssetImporterWrapper importer)
{
    var tex = importer as TextureImporterWrapper;
    var android = tex.GetPlatformTextureSettings("Android");
    // EXR uses 4x4, everything else uses 6x6
    bool isExr = Path.GetExtension(importer.AssetPath) == ".exr";
    android.format = isExr ? ASTC_4x4 : ASTC_6x6;
    android.overridden = true;
    tex.SetPlatformTextureSettings(android);
}
```

---

## The Wrapper Layer

The wrapper layer encapsulates the importers of the various asset types. The main purposes of this "wrapping" are, on one hand, managing property modifications, and on the other, deferring writes — that is, setting isDirty, then doing one unified SaveAndReimport after all properties have been modified:

```csharp
// Wrapper base class
class AssetImporterWrapper
{
    protected AssetImporter _mImporter;
    public bool IsDirty { get; private set; }

    // Creates the corresponding Wrapper instance via reflection
    // Naming convention: {ImporterType}Wrapper, e.g. TextureImporterWrapper
    public static AssetImporterWrapper Create(string path)
    {
        var importer = AssetImporter.GetAtPath(path);
        var wrapperType = Type.GetType($"AssetProcessors.Wrappers.{importer.GetType().Name}Wrapper");
        return (AssetImporterWrapper)Activator.CreateInstance(wrapperType, importer);
    }

    // Unified save: only calls SaveAndReimport when there are changes
    public void SaveAndReimport()
    {
        if (IsDirty)
        {
            _mImporter.SaveAndReimport();
        }
    }
}
```

Any property inside any asset type's wrapper is itself wrapped by a property wrapper.

```
// (1) Behind every property there's a PropertyWrapper
class PropertyWrapper<TImporter, TValue> : IWrapper
{
    TValue _modifiedValue;       // stashes the new value
    bool _hasModified;           // whether it has been set
    TValue OriginalValue;        // the original value read from the Unity Importer at creation

    // On set: don't touch the Unity object, just record it
    public TValue Value
    {
        set
        {
            if (Equals(value, OriginalValue)) return;  
            _modifiedValue = value;
            _hasModified = true;
        }
    }
  
    // Final commit: write the stashed value back to the Unity Importer
    public bool Apply()
    {
        if (!IsChanged) return false;
        // Writes back via reflection: importer.textureType / mipmapEnabled, etc.
        return true;
    }
}
```

---

## Closing Thoughts

This tool gives asset management a unified entry point, so you no longer need to dig through scattered commit records or search the editor batch by batch to verify assets. It also removes the need to keep evangelizing the development conventions for this area. And because it can tell, from each asset's path, whether the asset needs to join an Addressable Group, which Group it should join, and how to create the Group if it doesn't exist, it also underpins the resource management module and the automated build pipeline module.
