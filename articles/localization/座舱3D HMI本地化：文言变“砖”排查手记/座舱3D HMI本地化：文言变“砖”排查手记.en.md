---
title: "Cockpit 3D HMI Localization: Debugging When Text Turns into 'Bricks'"
lang: en
date: 2026-06-12
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> The localization workflow — my earlier articles have basically covered the main processing steps. So I wanted to write about a memorable and rather painful problem I've hit in localization, and that's when I thought of the display of text itself.

Maybe you've run into this too: after switching the language, the translations on screen all look right, but some places show **tofu blocks**. You can't read those characters anyway, but you can't help wondering: surely no character could be such a perfectly square "口".

The string exists in the StringTable and is not tofu; checking the `LocalizationText` component shows the font was switched too, and the input text is correct. So the problem lies in the font asset: **TextMeshPro reads a FontAsset, and a FontAsset is an asset pre-baked from a TTF. Only characters baked into the FontAsset's atlas texture can be rendered. Characters not in the atlas come out as tofu.** So it's worth understanding font assets: starting from a single tofu block, let's see how a TTF becomes a FontAsset, what a FontAsset contains, and how a character gets rendered at runtime.

---

## 1. TTF → SDF FontAsset

### 1.1 Creating the Font Asset

TextMeshPro provides an Editor window: `Window → TextMeshPro → Font Asset Creator`.

The input is a `.ttf`/`.otf` source font file.

The output is a `.asset` file (the FontAsset).

The baking process has three steps:

1. **Sampling**: draw the font outlines into bitmaps at the specified point size — like taking a photo of each character.
2. **SDF encoding**: convert the bitmap into a distance field. Each pixel records "how far it is from the glyph's edge": positive inside the outline, negative outside, exactly zero at the edge, stored as a grayscale image. The point is that when scaling, the continuous distance value allows smooth transitions, so jagged aliasing is much less likely.
3. **Packing**: stitch all characters' distance fields into one texture atlas, while recording each character's position and size within the image.

### 1.2 Key Parameters

The most important parameters in the Font Asset Creator window:


| Parameter | Meaning | Impact |
| -------------------- | ---------- | -------------------------------------------------------------------- |
| **PointSize** (sampling point size) | The point size at which the source font is rasterized | Larger value → each character takes more pixels in the atlas → sharper rendering → but fewer characters fit in the same atlas |
| **Atlas Resolution** | The pixel dimensions of the atlas texture | Larger value fits more characters, but uses more GPU memory |
| **Padding** | Pixel spacing between glyphs | If too small, glyph edges may be contaminated by neighboring characters when rendered at large sizes: SDF stores the **distance to the nearest outline** — if two glyphs sit too close, a neighboring glyph's outline may be nearer and hijack the distance field. |
| **Character Set** | Which characters to bake | Determines the font asset's character coverage |
| **Render Mode** | The SDF rendering mode | SDFAA / SDF32, etc.; affects anti-aliasing quality |


- With a 1024×1024 atlas, the empirical PointSize depends on the character count: Latin/Arabic run a few dozen to a couple hundred characters — PointSize 90 is clear enough;
- For Thai, which has attached marks above and below, 90px goes blurry; 160 may be needed;
- Cramming 8000+ Chinese characters into a single 1024×1024 image leaves only a tiny area per character. The larger the PointSize, the more area each character takes. But the image is only so big and you can't drop characters, so PointSize has to be squeezed down to 45. It's purely about "fitting in".

> About the Atlas Population Mode you can see in Generation Settings after generating the font asset: the choices are Static and Dynamic. We generally pick **Dynamic**, mainly because languages like Chinese adopt a small initial set + runtime on-demand expansion strategy, and it reduces the re-bake cost after each translation change during development — not because HMI copy changes randomly at runtime.
>
> But if you want to squeeze out performance:
>
> 1. Write a script to scan all locales' entries in `LanguageTable`, collecting Unicode code points grouped by font
> 2. Add the fixed symbol set: `0-9`, `%`, `°`, punctuation, units, etc.
> 3. In the Font Asset Creator, set Character Set to Custom, then generate with those code points
>
> Be careful to configure Fallback properly, because the copy might change while you forget to re-run the bake.

---

## 2. The FontAsset

### 2.1 The Atlas Texture

This is one of the two sub-assets you see under the FontAsset in the Inspector: a grayscale texture where each character's SDF data is laid out, densely packed tiny glyphs side by side. At runtime, this texture is sampled by TMP's shader to reconstruct the glyph outlines.

### 2.2 The Material

The other sub-asset. The FontAsset embeds a material that references the texture above, rendered with the TextMeshPro/Distance Field material.

> Note: you can adjust Softness and outline effects here. The former also affects how sharp the text looks.

### 2.3 Glyph Lookup Tables (Character Table + Glyph Table)

These two sections sit at the bottom of the FontAsset's parent panel, and the two tables work together:

- **Character Table**: the mapping from `Unicode code point → Glyph Index`. "I need to render U+0041 (A), so go find glyph #37."
- **Glyph Table**: the mapping from `Glyph Index → UV coordinates + metrics`. "Glyph #37 sits at (0.25, 0.5) in the atlas, 12px wide and 14px tall, bearingX=1, bearingY=12, xAdvance=11."

Rendering a character at runtime: from the code point → look up the Character Table → get the Glyph Index → look up the Glyph Table → get the UVs → sample the atlas. If the code point can't be found in the Character Table, and TMP's Fallback can't find it either, you get tofu.

```
Locale switch
  → TMPFontAssetTable loads the corresponding FontAsset per Locale
  → LocalizationText.UpdateAsset() swaps TMP.font
  → SetDirty() queries the StringTable for the translated text
  → TMP renders character by character:
      Code point → look up the Glyph Index in the Character Table
      Glyph Index → look up UV + metrics in the Glyph Table
      UV → sample SDF data from the Atlas
      SDF shader: distance > 0 → shade the pixel, distance < 0 → transparent
```

### 2.4 Face Info

This section is the first item on the FontAsset's parent panel and is normally not edited by hand. It contains the font's global metrics: Family Name, Point Size, Line Height, Ascent, Descent, Underline, and so on. This data determines typesetting behavior such as line spacing and baseline alignment.

### 2.5 Font Weights

If the rendered font weight doesn't match the Figma UI design, or some text isn't sharp enough, this section is useful — the ones to watch are Normal Weight and Bold Weight.

> About text looking **blurry, not sharp**
>
> Besides the material's Softness and the Font Weights above, there are these further optimizations — though I've rarely found them necessary, and the effect is not that noticeable:
>
>
> | Method | When to use | How |
> | ----------------------- | ------------------- | ---------------------------------------------- |
> | **Increase PointSize** | Languages with few characters (Thai, Arabic, Latin) | Raise PointSize in the Font Asset Creator and regenerate |
> | **Increase the Atlas** | Languages with many characters | 1024→2048, more room per character — but VRAM quadruples |
> | **Canvas Scale Factor** | World Space 3D text | Raise the Scale Factor so TMP renders at a larger point size, adjusting the Canvas spatial proportions accordingly |
> | **Padding** | Edges clipped at large sizes | Increase Padding to leave more room for SDF spread |
>

---

## 3. The Tofu

Taking Thai as an example.

### 3.1 See Tofu, Go Back to the Copy Table for the Original String

After switching to Thai, a string in the charging-related UI shows tofu. Open the key in Unity Localization's UI to find the corresponding entry.

The source text is:

> ชาร์จถึงขีดจำกัด

Visually, the tofu appears in the "ขีดจำกัด" part. Most of it is normal; only one stroke position is tofu. This kind of "localized tofu" usually means **one specific Unicode code point** is missing from the FontAsset.

### 3.2 Identify Which Character: Get the Unicode

By copying the tofu, or from the copy table, find the character that renders as tofu and search for its Unicode in a browser. Alternatively, write a script to compare the FontAsset's Character Table against every character that appears in your copy table, and list all potentially missing characters. You might discover, for example, that ๆ (U+0E46), ๊ (U+0E4A), ญ (U+0E09) and others are all absent from the FontAsset that was in use at the time.

### 3.3 Search for This Unicode in the FontAsset

Select the font asset in the Project window, expand **Character Table** in the Inspector, and type into the search box, e.g. `ั`, or search the decimal `3638` or the hex `0E36` — you'll find nothing.

The header next to Character Table showed only **74** characters at the time (roughly seventy-odd in the UI). The code point U+0E36 is not in the table, so when TMP renders that position it can only draw tofu.

### 3.4 The TTF Clearly Has the Glyph — Why Still Tofu?

The `ThaiLooped-Regular.ttf` source file is not small. Paste the same sentence "ชาร์จถึงขีดจำกัด" into Windows Notepad and select Thai Looped as the font — it **displays fine**. That tells us: **the TTF has this glyph**, but **it was never baked into the FontAsset**.

### 3.5 Bake the Missing Characters In

The missing **U+0E36** falls within the Thai Unicode block **U+0E00–U+0E7F**. **Look up the Unicode range for the language, and fill that range directly into the Font Asset Creator when re-baking.**

`Window → TextMeshPro → Font Asset Creator` (or select the old FontAsset → Inspector → **Update Atlas Texture**), with these parameters:


| Parameter | Value |
| ------------------------ | --------------------------------------------- |
| Source Font File | `NotoSansThai-Regular.ttf` |
| Point Size | **160** (90 is too small in a 3D scene — Thai's above/below marks go blurry; hence the name Adjusted) |
| Atlas Resolution | 1024×1024 |
| Character Set | **Unicode Range (Hex)** |
| Character Sequence (Hex) | `E00-E7F` |
| Padding | Keep the default or slightly larger |


Click **Generate Font Atlas** → **Save**, and save it as `Thai-Regular-Adjusted SDF.asset`. The Creator iterates over every code point in that range, and **only glyphs present in the source TTF make it into the atlas**. The final bake in the project produced **87** glyphs, more than the Looped version's **74**, and the missing ั, ๆ, ๊ and the like are all in there.

### 3.6 Verify: It's in the Table and the Tofu Is Gone

Reopen the Adjusted FontAsset's **Character Table** and search for `ั` (U+0E36) — **it can be found now**. The character count next to the header goes from the Looped version's **74** to the Adjusted version's **87**. Switch back to Thai, and the previously tofu'd "ชาร์จถึงขีดจำกัด" displays correctly in full.

---

## Closing

This post solved the problems of **characters turning into tofu and characters looking blurry**. There's still one unavoidable matter: **font files themselves aren't small, and they inflate the apk**.

- Android natively **borrows the system's shared font library** by default, so each app doesn't need its own copy of the font files.
- Unity by default bundles font assets into the package. The fact that font assets in the package increase apk size is something stakeholders need to be mentally prepared for up front.

> If size is very sensitive — say there are many 3D apps, and all of them have text display capability — I think the solution is to make a font bundle placed at a fixed location on the head unit (e.g. /vendor/unity_shared/fonts.bundle). All 3D apps load this file via an AssetBundle, load the asset of type TMP_FontAsset, and assign it to TMP's font property.

So if you only consider a single-app project, you can use Static mode and bake all the copy that needs translating into the FontAsset — that way you no longer need to put the ttf file into Addressables.

> Here you could build a scan-the-table-and-bake tool that triggers along with the development framework's build pipeline.

Of course, if you went with Dynamic because you couldn't be sure, you must ship the ttf font; in that case, what you can do is pick the leanest ttf file possible — for instance, skip Bold and keep only Normal.
