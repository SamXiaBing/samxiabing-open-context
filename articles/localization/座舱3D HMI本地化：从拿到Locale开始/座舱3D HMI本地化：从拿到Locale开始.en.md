---
title: "Cockpit 3D HMI Localization: It Starts with Getting the Locale"
lang: en
date: 2026-06-08
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> Localization, or multi-language support, is a feature that cockpit HMI development has to consider when shipping to multiple markets. Since it is a must in game development, the solutions are already fairly mature: either the engine ships a ready-made localization module/plugin, or the project team has its own localization framework.

This article discusses only one small point first: acquiring the language identifier and wiring it up. I still remember that when I first got into this area, I knew nothing about language identifiers; now that I have built up some understanding, I want to start pulling on the localization thread from its very beginning.

Content-wise, the discussion is split into two steps: **how to acquire the language identifier**, and **how to map it once you have it**. I'll try to cover both Unity and Unreal.

---

## 1. What Is a Language Identifier

The industry-standard language identifier today is BCP 47 (IETF's Tags for Identifying Languages). A tag consists of several hyphen-separated subtags, structured as:

```
language[-Script][-REGION][-variant]
```


| String       | Required | Length rules                    | Distinguishes       | Examples                                                              |
| ------------ | -------- | ------------------------------- | ------------------- | --------------------------------------------------------------------- |
| **language** | Yes      | 2 or 3 lowercase letters        | The base **language** | `zh` (Chinese), `en` (English), `pt` (Portuguese)                     |
| **Script**   | No       | 4 letters, first one capitalized | The **writing** system | `Hans` (Simplified), `Hant` (Traditional), `Cyrl` (Cyrillic)          |
| **REGION**   | No       | 2 uppercase letters or 3 digits | The **regional** variant | `CN` (Mainland China), `HK` (Hong Kong), `BR` (Brazil), `IL` (Israel) |


Examples:

- `zh-Hans`: Simplified Chinese, language + Script; the writing-system subtag distinguishes Simplified from Traditional.
- `zh-Hant-HK`: Traditional Chinese, Hong Kong, language + Script + REGION — though I have rarely seen all three subtags provided.
- `nb-NO`: Norwegian Bokmål, Norway, language + REGION, distinguishing Bokmål from Nynorsk. Worth mentioning here: for Chinese, what I have actually seen most often is this structure — a bare `zh` followed by a `CN` or `HK`.

---

## 2. Acquiring the Language Identifier

### 2.1 Three Ways to Get It in Unity

**Option 1:** `Application.systemLanguage`

A Unity-provided enum-based API that returns a `SystemLanguage` enum value.

The problem is that this enum is a flat structure:

- It only has `ChineseSimplified` / `ChineseTraditional` — **no way to distinguish zh-HK from zh-TW**
- Only `Norwegian` — **no way to distinguish nb-NO from nn-NO**;
- Only `Portuguese` — **no way to distinguish pt-BR from pt-PT**;
- Some languages are not in the enum and return `Unknown`.

So at the start of development, we could not use this enum to verify the protocol against the three-part variables from the Android side; and when requirement comparison revealed something to change or add, it was not convenient to adjust.

**Option 2: the Unity Localization plugin's System Locale**

At the time I was still on `com.unity.localization` (1.3.2). The plugin introduces a `Locale` / `LocaleIdentifier` system based on BCP 47 tags, supporting fine-grained identifiers such as `zh-Hans`, `zh-HK`, and `he-IL`. In that version, the acquisition logic tried `Application.systemLanguage` first, then fell back to `CultureInfo` (which often fails on IL2CPP/Android), so I did not use it back then.

In newer versions (1.5.3), the implementation chain of `SystemLocaleSelector.GetStartupLocale()` on Android is: **first, call** `java.util.Locale.getDefault().toLanguageTag()` **via JNI** — directly getting the system language in BCP 47 format. If that fails, **fall back to** `CultureInfo.CurrentUICulture`, with `Application.systemLanguage` as the **final safety net**.

Seen this way, using the Localization package to acquire the language is viable.

**Option 3: passing through the Android native layer (the current solution)**

The vehicle's Android system centrally controls language settings. Following the principle that the 3D application plays only a rendering role and does not actively call native methods at the system layer, we went with a **"be notified"** approach.

**How the Android side gets the language identifier**:

```java
// Option A: toString() — outputs Java Locale format (underscore-separated)
Locale.getDefault().toString()  // → "zh_CN", "he_IL", "en_US"

// Option B: toLanguageTag() — outputs BCP 47 format (hyphen-separated) ✅
Locale.getDefault().toLanguageTag()  // → "zh-Hans", "he-IL", "en-US"
```

The data transfer method depends on the current communication channel between Android and the 3D side.

### 2.2 How Unreal Gets It

Unreal Engine gets the OS default language via `FInternationalization::GetDefaultLanguage()`; the official documentation explicitly states that the return value is in **IETF language tag format** (e.g., `"zh-Hans-CN"`):

- `FInternationalization` is a singleton of the engine's Core module with three dimensions: Language / Locale / Culture, where Culture = Language + Locale. Language determines the language and writing system; Locale determines the region.
- Each platform has a corresponding `FPlatformInternationalization` implementation; the Android implementation obtains `Locale.getDefault().toLanguageTag()` through JNI, directly yielding the BCP 47 format.
- The tag returned by `GetDefaultLanguage()` can be passed straight into `SetCurrentLanguageAndLocale()` with no extra mapping.

Unreal's language identifier acquisition is done in one stroke.

---

## 3. How to Map It to Concrete Behavior

### 3.1 Unity: A Mapping Flow Driven by the Localization Package

**My approach**: after the 3D side receives the language string from Android, it converts it into a `LocaleIdentifier` via a mapping table, then sets `LocalizationSettings.SelectedLocale`, and the Unity Localization Package drives the subsequent string-table switching, font switching, and so on (the concrete driven behaviors are planned for the next article). Sketch of the code:

```csharp
// Step 1: receive the language string sent from Android
public void OnLanguageChanged(string languageTag)
{
    // Step 2: look up the mapping table and convert to a LocaleIdentifier
    if (!_androidToLocaleMap.TryGetValue(languageTag, out var localeCode))
    {
        // fallback: try matching by language subtag
        localeCode = FallbackToLanguageSubtag(languageTag);
        if (localeCode == null) return;
    }

    // Step 3: find the registered Locale via the LocaleIdentifier
    Locale locale = LocalizationSettings.AvailableLocales
        .GetLocale(new LocaleIdentifier(localeCode));
    if (locale == null) return;

    // Step 4: set SelectedLocale → Localization automatically drives the UI refresh
    LocalizationSettings.SelectedLocale = locale;
}
```

**Why manual code mapping is needed**:

> Here I have to mention something that still puzzles me: when we first defined the protocol for this part, my intention was that whatever the Android side sent in, I would simply configure my Locale settings to match. So I asked the Android engineer for a list of **all language identifier data the vehicle settings might send**. But my colleague said he **could not provide one**, and that he had no way to determine what would be sent — **for just Simplified Chinese, it might send zh, or zh_CN, or zh_Hans.**

In Unity-related projects I have worked on before, the language identifier data we received could not be confirmed: the output of Android Java Locale's `toString()` does not necessarily map one-to-one to a Unity `LocaleIdentifier`.

Conversions like `zh_CN`→`zh-Hans` (a REGION→Script semantic conversion) require a mapping table to handle, because Unity Localization registers the Chinese Locale as `zh-Hans` (script tag) rather than `zh-CN` (region tag).

**Common mapping issues and how to handle them**:


| Issue                                  | Example                      | Handling                                                                                                                              |
| -------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Bare language code with no region info | Receive `zh`                 | Exact match first; on failure, search the registered Locales by language subtag; ultimately degrade to the project default Locale       |
| Legacy code compatibility              | Receive `iw_IL`              | Cover both `iw` → `he` in the mapping table                                                                                           |
| Mapping failure                        | Receive an unregistered Locale | Fall back to `LocalizationSettings.ProjectLocale` and log it                                                                        |


> Note: the vast majority of BCP 47 tags can be used directly as a `LocaleIdentifier`; only shorthand mappings like `zh-Hant-HK`→`zh-HK` (Script+REGION→REGION) need explicit handling.

### 3.2 The Unreal Way

Once the Unreal side receives the BCP 47 tag, it simply calls the `FInternationalization` API directly — no mapping table needed:

```cpp
// The following is illustrative code, aligned with the production logic but not copied verbatim.
FInternationalization& I18N = FInternationalization::Get();
I18N.SetCurrentLanguageAndLocale(TEXT("zh-Hans"));
```

`SetCurrentLanguageAndLocale()` sets both Language (the source of translated text) and Locale (date/number formats) in one step. After the call, the engine automatically fires the `OnCultureChanged` delegate, and all UI components using `FText` refresh automatically.

---

## Conclusion

Discussing only how to acquire the language at the technical level is not the whole story of technology selection. Real decisions involve more influencing factors:

**First, the capability of the localization components**

Language acquisition is just the entry point; what really matters is whether there is a ready-made set of localization components to carry all the presentation after a switch:

- After a language change, does the UI refresh automatically, or does every widget need to be driven manually?
- Is RTL (right-to-left languages) layout natively supported, or do you have to do the mirroring yourself?
- When text overflows, are there mature truncation, wrapping, and scaling solutions?

**It is on the basis of component capability that you decide how to plug in language acquisition.** Component capability determines the constraints of the integration approach.

**Second, experience needs**

> When an Android app switches languages, the default behavior is that **a Configuration Change triggers an Activity recreation** — the system first destroys the current Activity (onDestroy) and then rebuilds it with the new configuration (onCreate); this process has noticeable jank.

Language switching in the 3D rendering process does not depend on Activity recreation; upon receiving the message it refreshes UI resources directly, **switching faster than the Android side**. Because the switching speeds of the two sides are out of sync, without coordination the user would see a jarring state where the 3D UI has already finished switching while the Android layer is still rebuilding.

Some solutions introduce a loading screen: after the user switches the language, a loading screen appears first, with the expectation that by the time it disappears, all language presentation must have finished switching. This requires message-based control to make the Android side and the 3D side complete the switch in sync, rather than each doing its own thing.

**This is a case of the experience design dictating the technical implementation.**