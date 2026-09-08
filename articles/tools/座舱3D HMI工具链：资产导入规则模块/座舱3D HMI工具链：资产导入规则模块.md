---
title: "座舱3D HMI工具链：资产导入规则模块"
date: 2026-07-10
series: tools
no: 
status: published
visibility: public
wechat_url: ""
---

> 对于一个涉及到较多种类资源的软件工程，首先咱们都会有一个意识：各种资源需要能被觉察并规范资源形态。对于3D HMI项目也是如此，比如纹理的最大尺寸，在安卓端的压缩格式，这些都是很典型的需要考虑如何去统一约束的对象。

面对座舱 3D 工程资产类型多、体量大、开发工作涉及多方（3D美术设计、UI设计、技术美术供应商）团队协作的特点，咱们不可能让各方导入资源时，都由其手动设置资源参数，或者寄希望于一份工程美术资产管理规范文档可以控制每一次资产导入动作。所以资产导入规则的自动实施工具是必需的。

基于 Unity 引擎的API及其Addressable的资源管理方案，下文将依次介绍这套工具的三层委托模式设计架构、规则匹配方式，资源管理方案的配置文件写入等。

---

# 代码的设计

资产导入工具的核心结构是三层：处理器层（`AllAssetProcessor`）→ 规则层（`AbstractRule`）→ 包装层（`AssetImporterWrapper`），委托模式驱动。调用链如下：

*[配图见公众号原文]*

## 处理器层

整个资源导入工具的入口是 Unity 的 `AssetPostprocessor.OnPostprocessAllAssets` 回调，这个回调是发生在资源导入后，但是`AllAssetProcessor` **不直接遍历处理资产。**它通过委托回调把工作交给 `AssetProcessorSettings`。

```csharp
// 统一入口，委托给 Settings
class AllAssetProcessor : AssetPostprocessor
{
    // 由 [InitializeOnLoadMethod] 在启动时绑定
    public static System.Action<string[], string[], string[], string[]> OnPostProcess;

    static void OnPostprocessAllAssets(
        string[] importedAssets,
        string[] deletedAssets,
        string[] movedAssets,
        string[] movedFromAssetPaths)
    {
        // 仅当 Handler 已绑定时执行
        if (OnPostProcess != null)
        {
            OnPostProcess(importedAssets, deletedAssets, movedAssets, movedFromAssetPaths);
        }
    }
}
```

这里的`OnPostProcess` 由 `AssetProcessorSettings` 在 `[InitializeOnLoadMethod]` 中绑定。AllAssetProcessor 只负责把事件转交出去。

示意代码：

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
            AllAssetProcessor.OnPostProcess = s_Instance.OnPostprocess;  // 绑定
        }
    }
}
```

## 规则层

这里解决的问题是不同的资源类型应该使用什么规则（处理方式）**：**

```csharp
// 规则基类（简化示意）
abstract class AbstractRule : ScriptableObject
{
    // 路径正则，在 Inspector 中填写
    public string regexPattern;

    // 前置检查：部分路径需要跳过、路径匹配
    public abstract bool Precheck(string path);

    // 后处理：对命中的资产执行实际导入设置
    public abstract void Postprocess(string path, AssetImporter importer);
}
```

**规则执行**：`AssetProcessorSettings` 按 `_rules` 列表顺序遍历

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
            break;   // 首个产生变更的规则执行后停止
    }
    assetImporter?.SaveAndReimport();
}

```

### 规则设计


| 规则                | 作用                                                |
| ----------------- | ------------------------------------------------- |
| `TextureRule`     | Android 平台 ASTC 压缩                                |
| `SpriteRule`      | Sprite 类型设置、关 Mipmap。也可以根据开发者手动标记的 Label 进行特殊处理。 |
| `AddressableRule` | 解析路径，自动创建/迁移 Addressable 分组、地址、标签                 |
| `SceneRule`       | 按平台化框架要求，重新设置 Addressable 中的路径和名字                 |


#### TextureRule 

考虑到篇幅不能太长，这里只展示贴图的导入规则，主要就是做压缩：自动设 Android 平台 ASTC 压缩格式。

```
// 判断 assetPath 是否属于 png jpg  tif exr
protected override bool OnPrecheck(string assetPath)
{
  //...
}

// Postprocess
protected override void OnPostprocess(AssetImporterWrapper importer)
{
    var tex = importer as TextureImporterWrapper;
    var android = tex.GetPlatformTextureSettings("Android");
    // EXR 用 4x4，其余用 6x6
    bool isExr = Path.GetExtension(importer.AssetPath) == ".exr";
    android.format = isExr ? ASTC_4x4 : ASTC_6x6;
    android.overridden = true;
    tex.SetPlatformTextureSettings(android);
}
```

---

## 包装层

包装层就是把各种资产类型的importer进行封装，这个“包一层”的主要目的，一方面是管理属性的修改，另一方面是为了延迟写入，即，设置isDirty，全部属性修改之后再统一 SaveAndReimport：

```csharp
// 包装器基类
class AssetImporterWrapper
{
    protected AssetImporter _mImporter;
    public bool IsDirty { get; private set; }

    // 通过反射创建对应类型的 Wrapper 实例
    // 命名约定：{ImporterType}Wrapper，如 TextureImporterWrapper
    public static AssetImporterWrapper Create(string path)
    {
        var importer = AssetImporter.GetAtPath(path);
        var wrapperType = Type.GetType($"AssetProcessors.Wrappers.{importer.GetType().Name}Wrapper");
        return (AssetImporterWrapper)Activator.CreateInstance(wrapperType, importer);
    }

    // 统一保存：仅当有变更时才调用 SaveAndReimport
    public void SaveAndReimport()
    {
        if (IsDirty)
        {
            _mImporter.SaveAndReimport();
        }
    }
}
```

任何一个资产类型的包装器内的一个属性，又被属性包装器所包装。

```
// ① 每个属性背后都有一个 PropertyWrapper
class PropertyWrapper<TImporter, TValue> : IWrapper
{
    TValue _modifiedValue;       // 暂存新值
    bool _hasModified;           // 是否被 set 过
    TValue OriginalValue;        // 创建时从 Unity Importer 读出的原值

    // set 时：不碰 Unity 对象，只记下来
    public TValue Value
    {
        set
        {
            if (Equals(value, OriginalValue)) return;  
            _modifiedValue = value;
            _hasModified = true;
        }
    }
  
    // 最后提交：把暂存值写回 Unity Importer
    public bool Apply()
    {
        if (!IsChanged) return false;
        // 反射写回 importer.textureType / mipmapEnabled 等
        return true;
    }
}
```

---

## 结语

这套工具可以让资产的管理有统一的入口，不至于需要到零散的提交记录中或是编辑器内去一批批资产检索校验。同时，也省去对这块开发规范的宣讲。由于它可以通过每一个资产的路径来判断它是否需要加入 Addressable Group，加入哪个Group，没有这个Group如何创建，所以它也是资源管理模块，自动化构建管线模块的支撑。