---
title: "座舱3D HMI本地化：换语种不只是换文本"
date: 2026-06-10
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> 当文言表已经准备就绪，我们也拿到了语种信息准备要做UI切换了，那么自然而然需要考虑的就是我们具体需要切换什么？。

本文分享文言表里的文本怎么变成屏幕上正确的字。一条 Locale 切换信号收到之后，UI 需要面对以下三类作为：

- **换字体**：不同语种需要不同的字体资产，比如阿拉伯语、泰语用的字体文件不同，与中文也不同。
- **翻译文本**：查 文言表拿到当前 Locale 的翻译，并根据需求进行字符串拼接、右序排版等。
- **布局适配**：翻译后文本长度变化，超出容器时的溢出处理：换行、截断、或跑马灯滚动

---

## 一、映射表

为了要同时具备换文本和换字体的能力，在使用unity开发的时候，我选择在Localization中创建两张表，一张给文本翻译（`StringTableCollection`），一张给字体（`AssetTableCollection`）。


| 表名    | 类型                      | 内容                                              |
| ----- | ----------------------- | ----------------------------------------------- |
| 文本翻译表 | `StringTableCollection` | 每 Locale 一张 `StringTable`，存储翻译文本                |
| 字体表   | `AssetTableCollection`  | 每 Locale 一张 `AssetTable`，存储字体资产 `TMP_FontAsset` |
| 其他资产表 | `AssetTableCollection`  | 见下文分析                                           |


> 之前有思考，是不是有必要创建更多的**语言和资产的映射表**。用来在不同语种切换之后，更换UI管理器下需要调整的UI预置体，比如：
>
> - 首页的卡片布局会因为语言切换而需要加载不同的设计的预置体。
> - 右序语言时，从左到右排布的按钮，需要改成从右往左排布。
> - 某些语言国家，表达“宠物”这个概念要用猫而非狗，导致要换图和模型。

对于上述这种语种不同，素材、整体布局就不同的情况，是有必要再根据业务去配置更多的语种-资产映射表的。但是在过往项目中，我没有这么做。

主要原因是：在平台化开发框架下，**车型+应用**是一个元项目，所以一个元项目下可以直接配置好所需要的设计效果。比如这个车型是国版的，不需要翻译；那个车型是右舵的，那么就只用配卡片右对齐的预置体；亦或是车型是卖欧洲的，设计方案上只要求显示猫，不要求根据欧洲十国做区分，那么我就直接在这个车型项目中部署对即可。

所以我想，如果有一个车型，它的HMI表现差异细到了它所服务的每一个国家。且这些差异还很有计划性（比如语种和字体的关系），只靠switch或if只会更难维护的时候。这**第三类语种-资产映射表**就会有必要去设置了。

## 二、换字体

不同语种需要不同的字体资产，因为不同的字体资产包含的目标字符和语种有匹配关系，用错了字体，显示出来就是方块或者空白。

### 2.1 字体切换的触发链路

![图1](./图1.png)

由 Unity Localization 的 `LocalizedAssetBehaviour` 事件机制自动驱动。`LocalizationText` 继承自 `LocalizedAssetEvent<TMP_FontAsset, LocalizedTmpFont, UnityEvent<TMP_FontAsset>>`，在Awake的时候，`LocalizationText` 会通过 `AssetReference.SetReference("TMPFontAssetTable", "Font")`绑定好所挂载的UI需要匹配的字体。当 `SelectedLocale` 变化时，框架从字体表中加载当前 Locale 的 `"Font"` 条目，触发 `AssetChanged` 事件，回调 `UpdateAsset`。

```csharp
// 以下为示意代码。
protected override void UpdateAsset(TMP_FontAsset localizedAsset)
{
    if (localizedAsset)
        Debug.Log($"字体变更 {name} font={localizedAsset.name}");
    else
        Debug.LogWarning($"丢失字体 Local:{transform.name} Root:{transform.root.name}");

    _tmpComponent.font = localizedAsset;  // 换字体
    SetDirty();                           // 刷新文本（换字体后必须重新生成 mesh）
}
```

---

## 二、翻译文本：LocalizationText

本工程的本地化文本组件只有一个：`LocalizationText`，挂在 `TextMeshProUGUI` 上（`[RequireComponent]`关系）。它同时负责**字体切换、文本查表、RTL 排版**三件事。

### 2.1 文本刷新的触发链路

![图2](./图2.png)

Locale 变化触发 `UpdateAsset`，换完字体后调 `SetDirty()`。`SetDirty()` 是文本刷新的核心——查表、回退、RTL 判断、设置文本，全部在这里完成：

```csharp
// 以下为示意代码
private void SetDirty()
{
    string content = "";
    for (int i = 0; i < Keys.Count; i++)
    {
        string translated = Keys[i].GetLocalizedString();
        if (translated.StartsWith("No translation found for"))
            translated = Keys[i].TableEntryReference.Key;  // 回退到 key（中文原文）
        content += $"{_lstPrefixString[i]}{translated}";
    }

    Locale locale = LocalizationSettings.SelectedLocale;
    bool isRTL = locale != null
        && (locale.Formatter.ToString() == "ar" || locale.Formatter.ToString() == "he-IL");
    _tmpComponent.isRightToLeftText = isRTL;
    _tmpComponent.text = isRTL ? GetFixedText(content) : content;

    OnUpdateString?.Invoke(content);
}
```

**回退策略**：翻译缺失时回退到 `TableEntryReference.Key`。因为 StringTable 的 key 就是中文文本本身（"中文即 key"），所以回退结果就是中文原文，用户看到的是中文而不是报错。

**初始化时的零配置**：如果 `Keys` 列表为空，`Awake()` 会自动以 TMP 当前显示的文本（通常是中文）作为 key。大多数单 key 场景下，开发者不需要手动配置，组件自己就能自动配key然后工作。

**多 key 拼接**：如果一个 Text 需要显示多个独立翻译条目的组合（比如"前部：开启"，那么在这里的"前部"和"开启"各自是独立条目），`Keys` 列表里就可以放多个 key，`_lstPrefixString` 里放每个 key 前的分隔符，`SetDirty()` 遍历时逐个查表、按 `prefix + translated` 拼接。

```csharp
locText.SetKeyStart();
locText.SetKeyAppend("前部");
locText.SetKeyAppend("开启", "：");  // 第二个 key 前加冒号
locText.SetKeyEnd();                  // 触发 SetDirty()
```

### 2.2 RTL 排版

阿拉伯语和希伯来语是从右向左书写（RTL）的语言，不能简单翻转字符串，需要处理字形连写、合字、双向文本三件事。本工程使用开源插件 RTLTMPro，其核心是 `RTLSupport.FixRTL()` ，在把文本交给 TMP 之前完成字形修正和方向重排。

关于有序处理流程的详细分析，准备另写文章介绍。

---

## 三、文本溢出与布局适配

翻译后文本长度的变化是本地化最头疼的问题之一。中文两个字能表达的，德语可能要四个单词，阿拉伯语可能要六个单词。

### 3.1 换行

换行是处理溢出的常见方案。Unity的TMP 提供两个独立维度：`enableWordWrapping`（是否换行）和 `overflowMode`（溢出、截断）。

### 3.2 截断

当 UI 不允许换行时，设 `overflowMode = Truncate`（直接截断）即可，这是 TMP 的标准选项。

### 3.3 动态字体大小

有些不那么重要的文本，比如一些按钮的tips简介，有可能设计会允许使用这种方式，做法就是TMP的Auto Size功能。

### 3.3 动态宽度

在一行有多个UI组合的情况下，可能会遇到从左到右水平排列的需求，设计需求上只约束 Item 之间的间距，不约束 Item 自身的宽度。翻译后"未关闭"变成"Not Closed"，Item 要变宽才能放下；"已关闭"变成"Closed"，Item 可以窄一些。

Unity 的做法是 `ContentSizeFitter` + `HorizontalLayoutGroup` 组合：

- `ContentSizeFitter`：`HorizontalFit` 设为 `PreferredSize`，让文本多长，RectTransform 就多宽
- `HorizontalLayoutGroup`：只设 `spacing`，不勾 `Control Child Size` 的宽度，这样每个子 Item 的宽度由自身的 `ContentSizeFitter` 决定，Layout Group 只负责按间距水平排列。

这种模式下，Locale 切换后文本长度变化，`ContentSizeFitter` 自动撑开/收缩宽度，Layout Group 自动重新排列。

### 3.4 跑马灯滚动

当文本不能换行、又不能截断（用户必须看到完整内容）时，跑马灯滚动是最后手段。本工程用 `TextMeshProScroll` 组件实现，挂在带 `LocalizationText` + `TextMeshProUGUI` 的 Text 节点上，配合父节点的 Mask 做可视区域裁剪。

![图3](./图3.png)

**核心设计**：每帧改自身 `anchoredPosition`以固定速度向左平移，到达边界后跳回起点，形成循环滚动。

**滚动检查**：`Start()` 函数中比较 `TextMeshProUGUI.preferredWidth`与父容器 `rect.width`，文本更宽才启用。

**每帧滚动**：`Update()` 函数中按 `speed`（比如40 px/s）移动 `anchoredPosition`。LTR 向左移，RTL 向右移，RTL 文本的阅读起点在右侧，滚动方向也反过来。

```csharp
// 以下为示意代码
void Update()
{
    if (!_isScroll) return;

    if (_isRightOrder == false)  // LTR：向左滚动
    {
        m_Rect.anchoredPosition += Vector2.left * speed * Time.deltaTime;
        if (m_Rect.anchoredPosition.x < _fDestiX)       // 到达左边界
            m_Rect.anchoredPosition = new Vector2(       // 跳回右侧
                m_StartX + _fMaxX, m_Rect.anchoredPosition.y);
    }
    else  // RTL：向右滚动
    {
        m_Rect.anchoredPosition -= Vector2.left * speed * Time.deltaTime;
        if (m_Rect.anchoredPosition.x > _fMaxX)          // 到达右边界
            m_Rect.anchoredPosition = new Vector2(       // 跳回左侧
                m_StartX - _fMaxX, m_Rect.anchoredPosition.y);
    }
}
```

---

## 四、刷新链路总结

![图4](./图4.png)

---

## 五、Unreal的做法

由于我只在Unity上做过本地化的交付，所以没有讲到Unreal的部分。以下Unreal的处理方式仅停留在尝试阶段：

**换字体**：Unreal 把所有语种的字体塞进一个 **Composite Font**，按字符的 Unicode 范围和Culture 过滤器逐字符路由。引擎自己就能跨字体，代价是配置比较烦。

**翻译文本**： .locres 就是 Unreal 的翻译资源文件，每个 Culture 一个文件夹，里面包含 .locres 文件，一个文言`FText` 的内部是 Namespace + Key + Source String 三元组数据，当切换 Culture 时，引擎加载对应 Culture 的 .locres 文件，`FText` 内部存储的`FTextHistory` 拿着 Namespace + Key 去新加载的 .locres 里查翻译。

**布局适配**：Unreal 的 UMG 比较简陋，不考虑插件的话，远没有 Unity 的 UGUI 的 TMP 那么全面了，之前所说到的效果要么靠面板的嵌套，要么需要自己手搓逻辑。

---

## 结语

本地化是一件蛮繁琐的事情。有时 Weblate 更新了翻译，开发跟进差了一个 Daily 版本，测试就提 bug 单；有时 UI 比较复杂，很难考虑全所有适配场景，导致文言异常重叠、超出显示范围、字体变小。这些琐碎的问题都需要花时间去沟通和处理，**所以方案上能帮上一些就帮一些，能省一步就尽量省一步。**



&nbsp;