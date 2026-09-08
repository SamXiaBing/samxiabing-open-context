---
title: "座舱3D HMI性能：材质实例化与内存泄漏"
date: 2026-07-27
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇分享的是周期性掉帧的 GC 问题，这次说的是另一类：长时间运行后内存持续增长，场景切换后内存也不见回落。跑的时间越长，占的内存越多，最后 OOM 被系统杀进程。

# 问题表现

测试反馈：

> "行驻泊一体化桌面跑了十几分钟，内存从 400 多兆涨到 700 多兆。切换到任一全屏应用再回到桌面，内存也没降多少。多切换几次桌面的模式或者场景（场景模式、日夜、天气）大概率会崩溃。"

这种表现大概率是内存泄漏，表明一定有对象创建了但没被释放。

---

# Memory Profiler

内存泄漏的排查，可以采用**抓取两次快照做比对**的方法。可以在当前应用中，先抓一份 `.snap` ，然后在应用内进行功能的切换操作，几分钟后再取一份，对比哪些类型的对象只增不减。

打开 Memory Profiler 载入文件，在Unity Objects 视图中的 Description 下能看到 `Material` 类型的变化：


| 观察项            | 第一次快照                | 第二次快照    |
| -------------- | -------------------- | -------- |
| Material 实例数   | 30+                  | 80+      |
| 同名 Material 占比 | 大部分带 `(Instance)` 后缀 | 比例更高     |
| 总内存趋势          | —                    | 持续增长，无回落 |


Material 实例只增不减，而且大部分带 `(Instance)` 后缀。说明这些不是资源里预制的材质，而是运行时被克隆出来的。每次进不同的场景，场景内的物体就各创建一批实例化材质，退出场景时这些实例没有被销毁，就留在了内存里。

示意图：

*[配图见公众号原文]*

---

# renderer.material 

`material` 和 `sharedMaterial` 都是 `renderer` 的属性。`material` 的逻辑可以根据以下并非真实但是可以示意的代码来理解：

```csharp
public Material material {
    get {
        if (_sharedMaterial == _material) {
            return _material;
        }
        _material = new Material(_sharedMaterial);  // 克隆一份
        _sharedMaterial = _material;
        return _material;
    }
    set {
        _sharedMaterial = value;
        _material = new Material(_sharedMaterial);  // 又克隆一份
    }
}
```

访问 `renderer.material` 时，`new Material(_sharedMaterial)` 创建一份副本，赋给 `_material` 和 `_sharedMaterial`。之后再访问不会再克隆。但是：

1. **场景中众多物体的 Renderer 各自独立**。每个网格体都有自己的 `material` 属性，每次生成它们都会克隆一次，造成实例过多。
2. **场景切换不销毁**，通过 `renderer.material` 创建的实例，Unity 不会自动回收。GameObject 销毁时，Renderer 组件跟着销毁，但 Material 实例还挂在内存里。除非手动调 `Destroy(mat)`，或者等 `Resources.UnloadUnusedAssets` 触发清理。

---

# 代码分析

定位到车道线 piece 的渲染设置：

```csharp
// LaneLinePiece.cs
private void SetLineColor(Vector4 baseColor, Vector4 baseNightColor) {
    mr.material.SetColor("_BaseColor", baseColor);
    mr.material.SetColor("_NightBaseColor", baseNightColor);
}

private void ChangeOffset(float offset) {
    float normalized_offset = (offset / 9f) - MathF.Floor(offset / 9f);
    mr.material.SetFloat("_LaneLineAnimOffset", normalized_offset);
}
```

每段车道线要设置不同的颜色和动画 offset，代码用 `renderer.material` 来改属性。第一次访问 `mr.material` 时，就克隆了一份新材质。30 段就是 30 份克隆实例。再看看其他地方：

```csharp
// LaneEffect.cs
if (material == null) {
    MeshRenderer mr = body.GetComponent<MeshRenderer>();
    material = mr.material;  // 拿到克隆实例，缓存了但没有 Destroy
}
```

```csharp
// TrafficLightSymbolDisplay.cs
renderer.material = new Material(renderer.sharedMaterial);  // 显式 new，也没配对销毁
```

```csharp
// DrivableAreaRenderer.cs
return quadRenderer.material;  // 每次调用都克隆
```

工程里 `renderer.material` 的使用点不少。有的是隐式（`mr.material.SetColor`），有的是显式 `new Material`。

---

# 改法

1 如果实例的材质表现都是一样的，比如他车、路标等大多数感知物，那么就把 material 改成 sharedmaterial，因为每一类材质的所有实例的表现都一样。

2 如果同一个材质，实例之间可能表现不一样，可以考虑两个做法：  
（1）仍然使用 `renderer.material`，但是要确认和观察，使用它的地方是否会频繁触发，如果触发频率低，并非每秒都有几Hz或者十几Hz的，可以继续使用。

（2）仍然使用 `renderer.material`，无法确定是否频繁，但是可以知道什么时候要，什么时候不要，那就手动Destroy。示意代码：

```
// DrivableAreaRenderer.cs — 用完主动释放
private void CleanupMaterial() {
    if (material != null && drivableAreaShader != null) {
        Destroy(material);
        material = null;
    }
}
```

（3）用 `MaterialPropertyBlock`，这样的话，材质还是共享的，但是如果要改具体某个实例的表现，就new这个材质属性块。示意代码：

```csharp
// 示意代码
private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
private static readonly int NightBaseColorId = Shader.PropertyToID("_NightBaseColor");
private static readonly int AnimOffsetId = Shader.PropertyToID("_LaneLineAnimOffset");

private MaterialPropertyBlock mpb = new MaterialPropertyBlock();

private void SetLineColor(Vector4 baseColor, Vector4 baseNightColor) {
    mr.GetPropertyBlock(mpb);
    mpb.SetColor(BaseColorId, baseColor);
    mpb.SetColor(NightBaseColorId, baseNightColor);
    mr.SetPropertyBlock(mpb);
}

private void ChangeOffset(float offset) {
    float normalized_offset = (offset / 9f) - MathF.Floor(offset / 9f);
    mr.GetPropertyBlock(mpb);
    mpb.SetFloat(AnimOffsetId, normalized_offset);
    mr.SetPropertyBlock(mpb);
}
```

---

# 结语

材质实例化是比较常见的情况，日常开发的时候，应该有这块意识，去避免频繁实例化的隐患出现。