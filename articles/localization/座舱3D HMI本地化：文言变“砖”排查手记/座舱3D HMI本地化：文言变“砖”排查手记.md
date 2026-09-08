---
title: "座舱3D HMI本地化：文言变“砖”排查手记"
date: 2026-06-12
series: localization
no: 
status: published
visibility: public
wechat_url: ""
---

> 本地化的工作流程，在主要的处理步骤上，之前的文章基本都覆盖了。于是就想写一点本地化中遇到过的印象深刻且处理得比较痛苦的问题，这才想到了文字的显示本身。

也许你也曾遇到过，当切换了语种之后，满屏的翻译看上去都对，但是却发现有些地方显示出了**方块，**虽然这些字咱也看不懂，但是心里会嘀咕：总不至于会有如此平整的“口”字吧。

文言表 StringTable 里有这一条且不是方块，看看组件`LocalizationText` 发现也换了字体，input text也是对的。那问题就出在字体资产了，**TextMeshPro 读的是 FontAsset，FontAsset 是一个从 TTF 预烘焙出来的资产。字符只有被烘焙进 FontAsset 的 atlas 纹理，才能渲染出来。不在 atlas 里的字符，就是方块。**所以有必要了解一下字体资产，就从一个方块出发，看看 TTF 怎么变成 FontAsset，FontAsset 里装了什么，运行时怎么把一个字渲染出来？

---

## 一、TTF → SDF FontAsset

### 1.1 创建字体资产

TextMeshPro 提供了 Editor 窗口：`Window → TextMeshPro → Font Asset Creator`。

输入是一个 `.ttf` / `.otf` 源字体文件

输出是一个 `.asset` 文件（FontAsset）。

烘焙过程有三步：

1. **采样**：把字体轮廓按指定字号画成位图，就像给每个字拍张照。
2. **SDF 编码**：把位图转成距离场。每个像素记下"离字的边缘有多远"，轮廓内为正、外为负、边缘刚好是零，存成灰度图。这么做，就是为了在缩放的时候，根据距离这个连续值，就可以平滑过渡，不容易出现锯齿。
3. **打包**：把所有字的距离场拼进一张纹理图集，同时记下每个字在图里的位置和尺寸信息。

### 1.2 关键参数

Font Asset Creator 窗口里最重要的几个参数：


| 参数                   | 含义         | 影响                                                                   |
| -------------------- | ---------- | -------------------------------------------------------------------- |
| **PointSize**（采样点大小） | 源字体栅格化时的字号 | 值越大→图集中每个字符占的像素越多→渲染越清晰→但同一张图集能放下的字符越少                               |
| **Atlas Resolution** | 图集纹理的像素尺寸  | 值越大，越能放下更多字符但 GPU 显存占用越大                                            |
| **Padding**          | 字形之间的像素间距  | 太小的话，大字号渲染时字形边缘可能被邻字污染SDF存的是 **到最近轮廓的距离，**如果两个字靠得太近，可能邻字轮廓更近，导致被拐跑。 |
| **Character Set**    | 要烘焙哪些字符    | 决定字体资产的字符覆盖范围                                                        |
| **Render Mode**      | SDF 的渲染模式  | SDFAA / SDF32 等，影响抗锯齿质量                                              |


- 在 1024×1024 的 atlas 下，PointSize 的经验值取决于字符数量：拉丁/阿拉伯语几十到两三百个字符，PointSize 给 90 就够清晰；
- 泰语这类有上下附加标记的，90px 会糊，到 160 可能才行；
- 8000多个汉字要塞进一张1024×1024的图里，每个字只能分到很小的面积。PointSize越大，每个字占的面积越大。但图就那么大，字又不能少放，所以PointSize只能压到45。纯是考虑"塞得下"。

>  关于生成了字体资产之后，可以在Generation Settings里面看到的 Atlas Population Mode，可选Static 和 Dynamic。我们一般选**Dynamic**，主要是因为中文等语言采用小初始集 + 运行时按需扩展策略，并在开发期减少每次改翻译后的重烘焙成本；并非因为 HMI 文言在运行时随机变化。
>
> 但如果要抠性能：
>
> 1. 写脚本扫描 `LanguageTable` 全部 locale 的条目，按字体分组收集 Unicode 码点
> 2. 加上固定符号集：`0-9`、`%`、`°`、标点、单位等
> 3. Font Asset Creator 下的 Character Set 选 Custom，然后用上面的码点去生成
>
> 要注意配好 Fallback，因为可能文言一变更，但忘了重跑烘焙。

---

## 二、FontAsset 

### 2.1 Atlas 纹理

这就是你看到 FontAsset 在 Inspector 里其下有两个子资产的其中一个，一张灰度纹理，每个字符的 SDF 数据排列在其中，密密麻麻的小字排在一起。这张纹理在运行时被 TMP 的 shader 采样，还原出字形轮廓。

### 2.2 材质

另一个子资产。FontAsset 内嵌一个材质，引用上面说的纹理，使用TextMeshPro/Distance Field材质来渲染。

> 注意，这里可以调整 Softness 还有描边效果。前者对字的清晰度也会有影响。

### 2.3 字形查找表（Character Table + Glyph Table）

这两个菜单，在 FontAsset 父物体的面板最下面，这两张表配合工作：

- **Character Table**：`Unicode 码点 → Glyph Index` 的映射。"我要渲染 U+0041（A），去找第 37 号字形"
- **Glyph Table**：`Glyph Index → UV 坐标 + 度量` 的映射。"第 37 号字形在 atlas 的 (0.25, 0.5) 处，宽 12px，高 14px，bearingX=1，bearingY=12，xAdvance=11"

运行时渲染一个字：通过码点 → 查Character Table → 得到Glyph Index → 查Glyph Table → 得到UV → 然后图集采样。如果码点在 Character Table 里找不到，TMP的Fallback也找不到，就是方块。

```
Locale 切换
  → TMPFontAssetTable 按 Locale 加载对应 FontAsset
  → LocalizationText.UpdateAsset() 替换 TMP.font
  → SetDirty() 查 StringTable 拿翻译文本
  → TMP 逐字符渲染：
      码点 → Character Table 查 Glyph Index
      Glyph Index → Glyph Table 查 UV + 度量
      UV → Atlas 采样 SDF 数据
      SDF shader：distance > 0 → 像素着色，distance < 0 → 透明
```

### 2.4 Face Info

这个菜单项是 FontAsset 父物体的面板第一项，一般不会手动修改的。它包含字体的全局度量：Family Name、Point Size、Line Height、Ascent、Descent、Underline 等。这些数据决定了行间距、基线对齐等排版行为。

### 2.5 Font Weights

如果字体渲染出来和 Figma UI 稿粗细不符，或者某些文字不够清晰，这个菜单项有用，值得关注的是 ：Normal Weight 和 Bold Weight。

> 关于字看上去**不清晰，有点糊**
>
> 除了上述材质的Softness和Font Weights，还有以下优化手段，只是这些手段我很少发现用得上，且效果并不明显：
>
>
> | 方法                      | 适用场景                | 做法                                             |
> | ----------------------- | ------------------- | ---------------------------------------------- |
> | **加大 PointSize**        | 字符数少的语言（泰语、阿拉伯语、拉丁） | Font Asset Creator 里调大 PointSize 重新生成          |
> | **加大 Atlas**            | 字符数多的语言             | 1024→2048，更多空间给每个字符——但显存翻 4 倍                  |
> | **Canvas Scale Factor** | World Space 3D 文字   | 调大 Scale Factor 让 TMP 用更大的字号渲染，Canvas 空间比例相应调整 |
> | **Padding**             | 大字号下边缘被截            | 增大 Padding 给 SDF 扩散留更多空间                       |
>

---

## 三、方块

以泰语为例。

### 3.1 看到方块，回到文言表找原句

切到泰语后，充电相关界面有一句文言出现方块。打开 Unity Localization 的界面上的 key 找到对应条目。

原文是：

> ชาร์จถึงขีดจำกัด

肉眼看，方块出现在「ขีดจำกัด」这块。大部分正常，只有某个笔画位置是方块。这种「局部方块」通常就是**某一个 Unicode 码点**没在 FontAsset 里。

### 3.2 定位是哪一个字：拿到 Unicode

通过复制方块，或者根据文言表，找到会显示方块的那个字符，去浏览器上搜它的Unicode。或者写脚本去对 FontAsset 的 Character Table 和你的 文言表里所有出现过的字符做比对，列出所有潜在的缺字。比如会发现 ๆ（U+0E46）、๊（U+0E4A）、ญ（U+0E09）等，当时用的 FontAsset 里都没有。

### 3.3 在 FontAsset 里搜这个 Unicode

在 Project 里选中字体资产，Inspector 展开 **Character Table**，搜索框里输入，比如 `ั`，或搜十进制 `3638`、十六进制 `0E36`，会发现搜不到。

Character Table 标题旁显示当时只有 **74** 个字符（界面上大致是七十来个）。码点 U+0E36 不在表里，TMP 渲染到这一位就只能画方块。

### 3.4 TTF 明明有字，为什么还方块？

`ThaiLooped-Regular.ttf` 源文件体积不小。把同一句「ชาร์จถึงขีดจำกัด」贴到 Windows 记事本，字体选 Thai Looped 是**显示正常**的。说明：**TTF 里有这个字形**但是**FontAsset 里没烘焙**。

### 3.5 把丢失的字烘焙进去

缺字 **U+0E36** 落在泰语 Unicode 区块 **U+0E00–U+0E7F** 内。**查清这一语种的 Unicode 区间，重烘焙时直接把区间填进 Font Asset Creator。**

`Window → TextMeshPro → Font Asset Creator`（或选中旧 FontAsset → Inspector → **Update Atlas Texture**），参数如下：


| 参数                       | 值                                             |
| ------------------------ | --------------------------------------------- |
| Source Font File         | `NotoSansThai-Regular.ttf`                    |
| Point Size               | **160**（3D 场景下 90 太小，泰语上下标笔画会糊；Adjusted 由此得名） |
| Atlas Resolution         | 1024×1024                                     |
| Character Set            | **Unicode Range (Hex)**                       |
| Character Sequence (Hex) | `E00-E7F`                                     |
| Padding                  | 保持默认或略加大                                      |


点 **Generate Font Atlas** → **Save**，保存为 `Thai-Regular-Adjusted SDF.asset`。Creator 会遍历该区间内每个码点，**源 TTF 里有的字形才进 atlas**，最终工程烘焙结果 **87** 个字形，比 Looped 版 **74** 个多，缺的 ั、ๆ、๊ 等都在里面。

### 3.6 验证：Table 里有了，方块消失

重新打开 Adjusted 版 FontAsset 的 **Character Table**，搜 `ั`（U+0E36）——**能搜到了**。标题旁字符数从 Looped 版的 **74** 变成 Adjusted 版的 **87**。切回泰语，原来方块的「ชาร์จถึงขีดจำกัด」整句正常显示

---

## 结语

本文解决了**字变方块和字看不清**的问题，还有一个绕不开的事：**字体文件本身不小，会撑大 apk**。

- Android 原生默认**借系统公共字库，**可以做到不需要每个app复制一套字体文件。
- Unity 默认是字体资产要进包的，字体资产进包会增加 apk 大小这件事，首先需要让相关方有这个心理准备。

> 如果很敏感，比如3D应用数量众多，而且还都有文言显示能力，我想解决方案是做一个字体的bundle包，放在车机上指定位置（如 /vendor/unity_shared/fonts.bundle），所有3D应用需要通过 AB包加载此文件，并加载资产类型 TMP_FontAsset，然后赋给TMP的font属性。

所以如果只考虑单应用工程内，可以做成Static的模式，把需要翻译的文言都烘焙到 FontAsset 中，这样就可以不要把ttf文件放到Addressable里面了。

> 这里可以做一个扫表烘焙的工具，跟随开发框架的编译管线一起触发。

当然，如果因为吃不准而用了Dynamic，就必须带上ttf字体，此时能做的是尽量选择精简的字体 ttf 文件，比如不要Bold，就只留Normal。

