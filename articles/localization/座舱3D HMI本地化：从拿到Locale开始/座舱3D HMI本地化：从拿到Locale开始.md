---
title: "座舱3D HMI本地化：从拿到Locale开始"
date: 2026-06-08
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> 本地化（Localization）或说 多语言 是座舱HMI开发中多市场需求下要考虑的功能。由于在游戏开发领域这是必需的，所以相关的方案已经比较成熟，或是引擎有现成的本地化模块/插件，或是项目组内自有一套本地化框架。

本文先只聊一个很小的点：语言标识的获取与联动。因为我还记得当时我刚接触这一块的时候，对语言标识这块是丝毫不了解的，现在有了一些认识，就想从头上把本地化这根线牵出来。

内容上，拆成两步讨论：**怎么获取语言标识**，以及**获取了标识之后怎么做映射**。尝试覆盖 Unity 与 Unreal 两个引擎。

---

## 一、语言标识是什么

当前业界通用的语言标识标准是 BCP 47（IETF 发布的 Tags for Identifying Languages），一个标签由连字符分隔的若干子标签组成，结构为：

```
language[-Script][-REGION][-variant]
```


| 字符串          | 必选  | 长度规则            | 区分什么     | 示例                                     |
| ------------ | --- | --------------- | -------- | -------------------------------------- |
| **language** | 是   | 2 或 3 位小写       | 基础**语言** | `zh`（中文）、`en`（英语）、`pt`（葡萄牙语）           |
| **Script**   | 否   | 4 位，首字母大写       | **书写**系统 | `Hans`（简体）、`Hant`（繁体）、`Cyrl`（西里尔字母）    |
| **REGION**   | 否   | 2 位大写字母 或 3 位数字 | **地区**变体 | `CN`（中国大陆）、`HK`（香港）、`BR`（巴西）、`IL`（以色列） |


例子：

- `zh-Hans`：中文简体,language + Script，通过书写系统字符串区分简繁。
- `zh-Hant-HK`：中文繁体,香港,language + Script + REGION，但我很少会见到能给全三个的。
- `nb-NO`：挪威书面语（Bokmål），挪威，language + REGION，区分书面语和新挪威语。这里要提一下，对于中文，我其实常见的是这种结构，一个zh，跟一个 CN 或 HK。

---

## 二、获取语言标识

### 2.1 Unity 的三种获取方式

**方式一：**`Application.systemLanguage`

Unity 提供的枚举式 API，返回 `SystemLanguage` 枚举值。

问题在于该枚举是扁平结构：

- 只有 `ChineseSimplified` / `ChineseTraditional`，**无法区分 zh-HK 与 zh-TW**
- 只有 `Norwegian`，**无法区分 nb-NO 与 nn-NO**；
- 只有 `Portuguese`，**无法区分 pt-BR 与 pt-PT**；
- 某些语种不在枚举中，返回 `Unknown`。

所以在开发之初，我们没法拿这个枚举去和安卓的三维变量核对协议；需求比对时发现要改或新增，也不方便调整。

**方式二：Unity Localization插件的 System Locale**

我当时用的还是`com.unity.localization`（1.3.2），插件本身是引入了 `Locale` / `LocaleIdentifier` 体系，基于 BCP 47 标签，支持 `zh-Hans`、`zh-HK`、`he-IL` 等细粒度标识。当时的版本，获取的逻辑是先尝试`Application.systemLanguage`，再回退到 `CultureInfo`（在 IL2CPP/Android 上常失败），所以当时就没有用它。

在较新版本（1.5.3）中，Android 上的`SystemLocaleSelector.GetStartupLocale()`实现链路为：**优先通过 JNI 调用** `java.util.Locale.getDefault().toLanguageTag()`——直接获取 BCP 47 格式的系统语种。如果失败，**回退到** `CultureInfo.CurrentUICulture`，**最终兜底** `Application.systemLanguage`。

这么看来，用Localization的方法获取语种是可行的。

**方式三：通过 Android 原生层传递（当前方案）**

车载 Android 系统统一管控语言设置，本着3D 应用只作为渲染的角色，不主动去系统层调用原生方法的原则，使用了**“被通知”**的方式。

**Android 侧怎么获取语言标识**：

```java
// 方式 A：toString() —— 输出 Java Locale 格式（下划线分隔）
Locale.getDefault().toString()  // → "zh_CN", "he_IL", "en_US"

// 方式 B：toLanguageTag() —— 输出 BCP 47 格式（连字符分隔）✅
Locale.getDefault().toLanguageTag()  // → "zh-Hans", "he-IL", "en-US"
```

数据传输方式根据当前安卓和3D之前的通讯方式来定。

### 2.2 Unreal 的获取方式

Unreal Engine 通过 `FInternationalization::GetDefaultLanguage()` 获取操作系统默认语言，官方文档明确指出返回值是 **IETF 语言标签格式**（如 `"zh-Hans-CN"`）：

- `FInternationalization` 是引擎 Core 模块的单例，有Language / Locale / Culture 三个维度，Culture = Language + Locale。Language 定了语言和书写，Locale 定了地区。
- 各平台有对应的 `FPlatformInternationalization` 实现，Android 平台通过 JNI 获取 `Locale.getDefault().toLanguageTag()`，直接拿到 BCP 47 格式。
- `GetDefaultLanguage()` 返回的标签可直接传入 `SetCurrentLanguageAndLocale()` 使用，无需额外映射。

Unreal 的语言标识获取是一气呵成的。

---

## 三、怎么映射到具体行为

### 3.1 Unity：使用 Localization 插件驱动的映射流程

**我的做法**：3D 端收到 Android 传来的语种字符串后，通过映射表转为 `LocaleIdentifier`，再设置 `LocalizationSettings.SelectedLocale`，由 Unity Localization Package 驱动后续的字符串表切换、字体切换等（驱动的具体行为计划在下一篇文章中分享）。代码示意：

```csharp
// 步骤 1：收到 Android 传来的语种字符串
public void OnLanguageChanged(string languageTag)
{
    // 步骤 2：查映射表，转为 LocaleIdentifier
    if (!_androidToLocaleMap.TryGetValue(languageTag, out var localeCode))
    {
        // fallback：尝试语言子标签匹配
        localeCode = FallbackToLanguageSubtag(languageTag);
        if (localeCode == null) return;
    }

    // 步骤 3：用 LocaleIdentifier 查找已注册的 Locale
    Locale locale = LocalizationSettings.AvailableLocales
        .GetLocale(new LocaleIdentifier(localeCode));
    if (locale == null) return;

    // 步骤 4：设置 SelectedLocale → Localization 自动驱动 UI 刷新
    LocalizationSettings.SelectedLocale = locale;
}
```

**为什么需要手动代码映射**：

> 这里要说一件我仍困惑的事：最初在定这块的协议的时候，我的本意是安卓端送什么进来，我直接对应地去配我的Locale配置文件就好了。所以我就向安卓工程师要一份**车辆设置上可能发送的所有语言标识数据**。但是我的同事说他**给不了**，而且他没有办法确定会发什么，**就一个中文简体，可能发zh，可能发zh_CN，也可能发zh_Hans。**

在之前实施的unity相关的项目中，我们收到的语言标识数据没法确认，Android Java Locale 的 `toString()` 输出与 Unity `LocaleIdentifier` 之间不一定一一对应。

比如 `zh_CN`→`zh-Hans`（REGION→Script 的语义转换）这种转换的，就需要映射表来处理。因为 Unity Localization 的中文 Locale 注册的是 `zh-Hans`（脚本标签）而非 `zh-CN`（地区标签）。

**映射上的常见问题及处理**：


| 问题        | 示例              | 处理方式                                            |
| --------- | --------------- | ----------------------------------------------- |
| 裸语言码无地区信息 | 收到 `zh`         | 先精确匹配，失败则按语言子标签在已注册 Locale 中搜索，最终降级到项目默认 Locale |
| 旧代码兼容     | 收到 `iw_IL`      | 映射表中同时覆盖 `iw` → `he`                            |
| 映射失败      | 收到项目未注册的 Locale | 降级到 `LocalizationSettings.ProjectLocale`，并输出日志  |


> 注：绝大多数 BCP 47 标签可以直接用于 `LocaleIdentifier`，只有 `zh-Hant-HK`→`zh-HK` 这类 Script+REGION→REGION 的简写映射需要显式处理。

### 3.2 Unreal驱动方式

Unreal 端收到 BCP 47 标签后，直接调用 `FInternationalization` API 即可，无需映射表：

```cpp
// 以下为示意代码，已与工程逻辑对齐但非拷贝。
FInternationalization& I18N = FInternationalization::Get();
I18N.SetCurrentLanguageAndLocale(TEXT("zh-Hans"));
```

`SetCurrentLanguageAndLocale()` 同时设置 Language（翻译文本来源）和 Locale（日期/数字格式），一步到位。调用后引擎自动触发 `OnCultureChanged` 委托，所有使用 `FText` 的 UI 组件自动刷新。

---

## 结语

仅讨论技术层面如何获取语种，并不是选型的全部。实际决策还有更多的影响因素：

**一、本地化组件能力**

语种获取只是入口，真正关心的是有没有一套现成的本地化组件来承接切换后的所有表现：

- 语言变化后 UI 是否自动刷新，还是需要手动驱动每个控件？
- RTL（右序语言）布局是否原生支持，还是需要自己镜像处理？
- 文本超长时有没有成熟的截断、换行、缩放方案？

**基于组件能力，才去决定语种获取怎么接入。** 组件能力决定了接入方式的约束。

**二、体验需要**

> Android 应用切换语言时，默认行为是 **Configuration Change 触发 Activity 重建**——系统先销毁当前 Activity（onDestroy），再以新配置重建（onCreate）这个过程有明显的卡顿。

3D 渲染进程的语种切换不依赖 Activity 重建，收到消息后直接刷新 UI 资源，**切换速度比 Android 侧更快**。由于两侧切换速度不同步，如果不做协调，用户会看到 3D 界面已经切完、Android 层还在重建的割裂状态。

有的方案中会引入一个 loading 画面：用户切语言后先出 loading，预期是 loading 消失时所有语言表现必须切换完毕。这就需要通过消息控制让 Android 侧和 3D 侧同步完成切换，而不是各做各的。

**这是为体验方案决定技术实现方式的情况。**

