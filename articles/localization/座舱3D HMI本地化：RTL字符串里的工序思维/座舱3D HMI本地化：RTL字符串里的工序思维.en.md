---
title: "Cockpit 3D HMI Localization: The Pipeline Mindset in RTL String Processing"
lang: en
date: 2026-06-11
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> RTL (Right-to-Left) text layout is a rather special beast in the localization of smart-cockpit 3D HMI. If the HMI application we're developing has to serve Middle East markets, chances are we need to handle right-to-left languages like Arabic and Hebrew.

When I first took on the Arabic requirement, I tried writing the right-to-left handling logic myself: if the Locale is RTL, call `Reverse()`. Short plain-Arabic strings looked fine — until text mixing brackets + English + numbers showed up. I found I couldn't handle RTL and LTR segments separately, nor complex requirements like full-string reversal. After a flurry of fixes, I was ultimately defeated by diacritics and glyph joining.

Later I did find a plugin that handles RTL, and I could have quit while I was ahead. But this acrobatic string manipulation fascinated me — I wanted to see what exactly made it impossible for me. That's where this article comes from.

## 1. Basic information

### 1.1 Languages


| Language | Locale | Region |
| ---- | ------ | ------------ |
| Arabic | ar | Middle East, North Africa; ~400 million speakers |
| Hebrew | he-IL | Israel |
| Persian | fa | Iran |
| Urdu | ur | Pakistan |
| Pashto | ps | Afghanistan |


These are the RTL languages. The last three all borrow the Arabic script, though their joining rules and numeral forms differ. For new energy vehicles going overseas to the Middle East, Arabic is a must; add Hebrew for the Israeli market and Persian for the Iranian market. I've handled `ar` and `he-IL` before.

### 1.2 Unity: RTLTMPro

TextMeshPro itself doesn't handle RTL. RTLTMPro is the most common community solution. Usage:

```csharp
_tmpComponent.isRightToLeftText = true;
RTLSupport.FixRTL(input, output);
output.Reverse();
_tmpComponent.text = output.ToString();
```

- `FixRTL` performs glyph correction and bidirectional reordering.
- `Reverse` converts logical order into the visual order TMP expects.
- Checking/setting `isRightToLeftText` makes TMP lay out from right to left.

### 1.3 Unreal: HarfBuzz + ICU

Unreal takes the built-in engine route. The Slate text rendering layer integrates:

- **ICU** handles the BiDi (Bidirectional Algorithm) — deciding which characters in a piece of text run left-to-right and which run right-to-left, then computing the correct display order.
- **HarfBuzz** handles Shaping — deciding which form each character should take based on context, such as the joined forms and ligatures of Arabic letters.

Working together, you hand `STextBlock` an `FText`, set the Culture, and in theory the engine automatically completes bidirectional ordering + glyph selection, with no manual pipeline tuning required. But there can be issues with brackets, numeral direction, and rich text, so in practice one option is the Arabic Support plugin on the Marketplace.

---

## 2. The headaches of RTL

First, a quick introduction to the core characteristics of RTL text, because everything that follows exists to deal with them.

### 2.1 Logical order vs. visual order

The Unicode standard specifies that text is stored in **logical order**, i.e., input order. Although Arabic reads right to left, you still type it letter by letter in reading order — so the storage order simply puts the first-typed letter first.

**In the translation Excel, the Arabic "looks" right — right to left, properly joined. That's because Excel's rendering layer does glyph correction and direction reordering. The string actually copied into the StringTable is in logical order: letters arranged left to right, as isolated characters.**

Assign the logical-order string to a text component and even with reversal enabled the result is wrong. Merely laying characters out right-to-left isn't enough — there's plenty of special handling to do.

### 2.2 Glyph joining

The shape of an Arabic letter depends on its position within the word. Take ب (Beh) for example:


| Positional form | Example | Meaning |
| -------- | --- | ----------- |
| Isolated | ب | Stands alone; connects to neither side |
| Final | ـب | End of word; joins the previous letter |
| Initial | بـ | Start of word; joins the following letter |
| Medial | ـبـ | Middle of word; joins on both sides |


Not joining at all is just as wrong as joining incorrectly — either way, it's a misspelled character.

### 2.3 Ligatures

لا (Lam-Alef) is the most common ligature: ل (Lam) + ا (Alef) merge into one glyph occupying one character slot instead of two. After the ligature, the original two character slots become one glyph + one placeholder, and the placeholder is skipped during rendering.

### 2.4 Bidirectional text

This is the trickiest part. English words and numbers embedded in RTL text remain LTR and must not be flipped along with everything else.

For example, "شحن (AC) 220V". The Arabic runs right to left, but "(AC) 220V" runs left to right. If you reversed the whole string, "AC" would become "CA" and "220" would become "022".

### 2.5 Bracket mirroring

In left-to-right text, the opening bracket `(` is on the left and the closing bracket `)` is on the right. In an RTL context:

- If a bracket **directly touches** an RTL character (no space in between), the bracket's opening direction must be flipped visually. `(AC)` displays visually as `)AC(`, opening toward the right. What Unicode stores is still `(` and `)`.
- But if there are spaces separating the brackets on both sides (as in `الشّحن (AC) 220V`), `(AC)` is an LTR fragment: the brackets wrap English read left to right, so it still displays visually as `(AC)` and doesn't flip.

### 2.6 Diacritics

Arabic diacritics (Tashkeel) are marked above consonants: Fatha (َ), Damma (ُ), Kasra (ِ), Shadda (ّ), and so on. They don't occupy their own character slot; they attach to consonants.

Shadda (ّ) marks a doubled consonant. When it combines with another diacritic, Unicode has dedicated ligature code points for the pair.

Tashkeel interferes with glyph-joining decisions: if a Tashkeel sits between two letters, the "can the previous letter connect" check goes wrong. - -!

### 2.7 Telling RTL characters from LTR characters

**Check the Unicode code point ranges.**

RTLTMPro's `TextUtils` maintains a set of code point ranges:

- Arabic letters fall in `0x0600`–`0x06FF` (Arabic Base Block).
- `0xFB50`–`0xFDFF` (Presentation Forms-A): pre-composed code points for the various complex Arabic joining combinations and vowel-marked forms, each with its own dedicated code point.
- `0xFE70`–`0xFEFF` (Presentation Forms-B) contains the four basic positional forms of every Arabic letter (isolated, initial, medial, final).
- Hebrew letters fall in `0x0591`–`0x05F4`.
- English letters fall in `0x41`–`0x5A` and `0x61`–`0x7A`.

At every step of the RTL string pipeline, whenever you pick up a character, just check which range its code point falls into, and you know whether it's an RTL character, an LTR character, or a diacritic.

---

## 3. The complete processing pipeline

**Example**: a charging status line of text roughly meaning "Charging (AC) 220V — 80%". The line contains: Arabic letters, a Shadda diacritic, the English abbreviations AC and V, brackets, three groups of digits, an em dash, and a percent sign. Fairly thorny (downright nasty).


| Step | Stage | String |
| --- | ---------- | ------------------------ |
| ① | Excel rendering | `(AC) 220V — 80% الشّحن` |
| ② | What the code receives | `الشّحن (AC) 220V — 80%` |
| ③ | After FixRTL | `80% — 220V (AC) ﻦﺤّﺸﻟﺍ` |
| ④ | After Reverse | `ﺍﻟﺸّﺤﻦ )CA( V022 — %08` |
| ⑤ | Shown in the UI | `(AC) 220V — 80% الشّحن` |


> How does step 4 turn into step 5?
>
> - **Drawing the Arabic**: TMP receives `ﺍﻟﺸّﺤﻦ` and draws right to left. It draws `ﺍ` at the far right, then `ﻟ` to its left... The visual result is exactly the correctly-ordered `الشّحن`!
> - **Drawing the English**: Next, TMP receives `)CA(` and keeps drawing right to left. It draws `)` at the far right, then `C`, then `A`, and finally `(` at the far left. Looked at as a whole, doesn't it visually become a perfect `(AC)` again?
> - **Drawing the digits**: Same idea — `V022` drawn right to left becomes, visually, `220V` again.

Below is how RTLTMPro's six-stage `RTLSupport.FixRTL()` pipeline processes it, stage by stage.

### Stage 1: Strip diacritics (RemoveTashkeel)

The Shadda (`0x0651`) on ش is stripped off, with its position recorded.


| | String |
| --- | --------------------------------------- |
| Before | الشحن (AC) 220V — 80% (isolated forms, Shadda wedged in between) |
| After | الشحن (AC) 220V — 80% (pure consonants, Shadda stripped) |


The ّ is removed, leaving only pure consonant letters. Subsequent joining decisions won't be interrupted by diacritics.

### Stage 2: Glyph joining correction (GlyphFixer.Fix)

For each Arabic letter, determine its positional form from the surrounding letters, then offset the code point from the isolated form in the Arabic Base Block to the joined-form code point in the **Presentation Forms-B** block.

Presentation Forms-B (`0xFE70`–`0xFEFF`) is the Unicode block reserved specifically for Arabic, storing joined-form code points. A letter has only one code point in the Base Block, but up to four consecutive code points in Forms-B (Isolated, Final, Initial, Medial), laid out in that order. So once you know the isolated-form code point and the positional form, a single additive offset does the job: +0 is Isolated, +1 is Final, +2 is Initial, +3 is Medial.

In "الشحن":

- ا (Alef): nothing before it to join → Isolated (+0)
- ل (Lam): Alef doesn't join forward, so Lam has nothing before it; ش follows → Initial (+2)
- ش (Shin): ل before it, ح after → Medial (+3)
- ح (Hah): ش before it, ن after → Medial (+3)
- ن (Noon): ح before it, nothing after → Final (+1)


| | String |
| --- | ----------------------------------------------------- |
| Before | الشحن (AC) 220V — 80% (Arabic Base Block isolated-form code points) |
| After | ٱلـشـحـن (AC) 220V — 80% (Presentation Forms-B joined-form code points) |


### Stage 3: Restore diacritics (RestoreTashkeel)

Insert the Shadda stripped in stage 1 back in:


| | String |
| --- | ------------------------- |
| Before | ٱلـشـحـن (AC) 220V — 80% |
| After | ٱلـشّـحـن (AC) 220V — 80% |


The Shadda sits above the Shin; its position is relative to the consonant and unaffected by the joining correction.

### Stage 4: Shadda ligatures (FixShaddaCombinations)

In this example, the Shadda (ّ) doesn't combine with any other diacritic, so nothing changes.

But if the input were `Shadda + Fatha`, the two characters would be replaced by a single ligature code point, for example:


| | String | Description |
| --- | ---------- | -------------------------------------------- |
| Before | ...شَّن... | Two separate code points: `0x0651` (Shadda) + `0x064E` (Fatha) |
| After | ...شﱟن... | One ligature code point: `0xFC93` (ShaddaWithFathaIsolatedForm) |


### Stage 5: Bidirectional reordering (LigatureFixer.Fix)

Walk the string from the end toward the start, reassembling it by directional property. This is the step where the string changes the most:

- RTL characters (Arabic letters): appended directly to the output.
- LTR fragments ("AC", "220V", "80%"): buffered first; when an RTL character or the string boundary is hit, the buffer is reversed and then appended — so LTR fragments keep their left-to-right reading order in the output.
- Bracket mirroring: swap `(` ↔ `)` only when at least one side of the bracket **directly touches** an RTL character. In this example, `(AC)` is separated from the Arabic by spaces on both sides; it's an LTR fragment and doesn't trigger mirroring.


| | String |
| --- | ------------------------- |
| Before | ٱلـشّـحـن (AC) 220V — 80% |
| After | 80% — 220V (AC) ﻦﺤّﺸﻟﺍ |


Because of the buffered reversal, the LTR content — "80%", "220V", "(AC)" — regains its character order as collected during the end-to-start traversal, while the Arabic part, now reversed, has moved to the tail.

### Stage 6: Rich text tag correction (RichTextFixer.Fix)

No rich text tags in this example, so nothing changes.

But if there were — say `<color=red>الشّحن</color> (AC)` — then during stage 5's scan of the entire string, all tags of the `<...>` form are found and the character order inside them gets reversed, turning them into `>der=roloc<` and `>roloc<`. `نحّشلا` isn't inside a tag, so it stays untouched.

### Reverse: logical order → visual order

`FixRTL` outputs logical order. With `isRightToLeftText = true`, TMP expects visual order, where the first character should appear at the far right. So we reverse the whole thing once:


| | String |
| --- | ---------------------------- |
| Before | 80% — 220V (AC) ﻦﺤّﺸﻟﺍ (logical order) |
| After | ﺍﻟﺸّﺤﻦ )CA( V022 — %08 (visual order) |


After the reversal, the character order inside each LTR fragment is flipped as well: `(AC)` → `)CA(`, `220V` → `V022`, `80%` → `%08`. It all looks backwards — but this is exactly what TMP wants. See the quoted block above Stage 1 for the details.

---

## 4. Closing thoughts

When I originally tried to handle RTL, my approach was also a character-by-character sweep: at each character, run through the case analysis, hoping that by the time I'd processed the last character, the result would be roughly right.

But RTLTMPro's approach made me realize: engineering is about the sequence of operations. Some things can't be settled in a single pass, no matter how carefully you deal with each item one by one.

It's like assigning tasks to stakeholders and spelling out the requirements — that doesn't mean things will run on rails. Surprises like "diacritics", "joining", and "ligatures" always pop up, forcing you to add another step to the pipeline and comb through everything again.
