---
title: "车机端生成式 UI 实践：A2UI 协议的 Unity UI Toolkit 原生渲染方案"
date: 2026-09-05
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> **本文要点**
>
> - 仓库地址：[https://github.com/SamXiaBing/a2ui-unity-toolkit](https://github.com/SamXiaBing/a2ui-unity-toolkit)
>
> - 车机端 GenUI 的技术路线对比，以及原生组件映射的取舍。
> - A2UI 渲染流水线的流程设计。
> - 从 Figma 设计稿到 USS 主题的自动化管线。
> - 开源仓库包含的测试回归能力。

## 为什么需要一个 A2UI 的 Unity 渲染器？

生成式 UI（GenUI）是由 AI Agent 以自然语言描述界面结构，客户端实时完成渲染。Google 提出的 A2UI 协议以 JSONL 为消息格式，定义了组件描述、层级关系、数据绑定与动作回调的标准规范，官方渲染器覆盖 Angular、Flutter、Lit 等 Web 与移动端框架，社区另有 Compose 渲染器。

车机端座舱3D HMI开发中，界面运行于 3D引擎环境（比如 Tuanjie），渲染层为引擎自身的UI画布系统（比如 UI Toolkit），现有 A2UI 生态缺乏对应实现。

本文介绍的实现，是将 A2UI 协议直接映射到 Unity UI Toolkit 原生组件的部署。Agent 输出的 JSONL 报文经校验、转化与映射后，以原生组件形式渲染，不经过 HTML、WebView 或像素流。

该项目支持协议 v0.8 与 v0.9 双栈、主题切换、Figma 设计稿自动转主题，以及全主题 × 全样例的自动化回归测试。开源资料包含代码 23 个 C# 文件，工具链 18 个 Python 脚本， 21 种组件、3 套内置主题、56 份样例。仓库以 MIT 协议开源。

## 技术路线的思考

实现 AI 驱动的座舱 GenUI，有这么几条可比较的技术路线。

### **WebView 插件路线**

以 Web 技术栈渲染界面，Agent 输出 HTML 或类 Web 描述。优势是实现成本低、生态成熟。但 Unity 本身不能直接渲染 HTML/CSS，必须依赖 Vuplex 3D WebView 这类第三方插件，走离屏纹理路径和 3D 内容融合，每帧多一次像素拷贝，性能代价显著。同时在车机 3D HMI项目中适配成本并不低。

### **Compose 桥接路线**

将 Android Compose 的绘制指令传递至 Unity 做API级别的映射并最终完成渲染。优势是可复用 Android 生态，声明式范式与 GenUI 结构描述天然契合。但需要修改 Android Framework相关代码，风险和难度有点高，且绑定 Compose 之后，3D端的技术范围受限。

### **原生组件（UITK）映射路线**

将模型输出视为结构协议，直接映射到 Unity 原生 UI Toolkit 组件。UI Toolkit 的声明式样式体系和 Web 设计体系在语义层面是对齐的：它有 Flex 排版能力，USS 的属性命名、选择器机制、变量体系都和 CSS 高度相似。这意味着设计侧的 Figma 设计系统、前端侧的样式，都可以通过自动化管线直接转换成 USS 主题，而不是从零开始重写一套视觉资产。在此基础上性能完全可控。代价是需要自己实现协议到组件的映射层。

## 核心挑战

采用原生组件映射路线，需解决三个方向上的技术问题。

**渲染宿主与协议的适配。** UI Toolkit 的布局、样式系统、组件集与 Web/Android 生态存在差异。flex 布局的行为、滚动的机制、变换属性等方面存在不一致，需要在映射层逐一适配，确保协议描述的界面语义在3D引擎端正确呈现。

**多版本协议兼容。** A2UI 协议 v0.8 与 v0.9 在报文结构上存在差异：v0.8 为嵌套式组件描述，类型以嵌套 key 表示；v0.9 为平铺式组件数组，children 直接引用 ID。兼容要求内部有一个数据层，提供 JSONL 转换的中间模型，与版本解耦，做到协议升级时映射层无需改动。

**视觉资产的工程化。** 生成式 UI 的视觉质量取决于主题系统而非模型输出。如何建立可扩展、可验证、可从设计稿自动转换的主题管线，是决定系统可用性的关键因素，而非架构本身。

## 系统架构

JSONL 报文处理流程七个阶段：

*[配图见公众号原文]*



### 数据驱动模式

用户操作不直接修改界面，而是经动作路由进入车机服务，服务回写数据后界面随数据自动更新：

![2](./2.png)

### 协议兼容

**v0.8 报文**（嵌套式）：

```
{
  "surfaceId": "demo",
  "column": {
    "children": [
      {
        "text": {
          "text": "有点热，调到 22 度",
          "variant": "h4"
        }
      },
      {
        "button": {
          "text": "确认",
          "action": "confirm"
        }
      }
    ]
  }
}
```

**v0.9 报文**（平铺式）：

```
{"version":"v0.9","createSurface":{"surfaceId":"demo","catalogId":".../standard_catalog_definition.json"}}
{"version":"v0.9","updateComponents":{"surfaceId":"demo","components":[
  {"id":"root","component":"Column","children":["title","b1"]},
  {"id":"title","component":"Text","text":"有点热，调到 22 度","variant":"h4"},
  {"id":"b1","component":"Button","text":"确认","action":"confirm"}
]}}
```

v0.8 的组件类型嵌在 key 里，结构是递归树；

v0.9 的组件类型在 component 字段里，结构是扁平数组 + children 引用 ID，需要额外还原出树。

归一化后的内部数据模型（两种版本收敛为同一种）：

```
{
  "surfaceId": "demo",
  "rootId": "root",
  "components": {
    "root":  { "type": "Column", "children": ["title", "b1"], "props": {} },
    "title": { "type": "Text",   "children": [],             "props": { "text": "有点热，调到 22 度", "variant": "h4" } },
    "b1":    { "type": "Button", "children": [],             "props": { "text": "确认", "action": "confirm" } }
  }
}
```

1. 类型统一：key 和 component 字段统一为 type 字段
2. 结构统一：递归树和扁平数组统一展开为 id → 组件 的字典 + children ID 引用
3. 属性统一：散落在各层的属性统一归到 props，映射层只和 props 打交道

### 安全与防护

Agent 输出属于不可信输入，需建立安全基线。主要防护措施包括：

- **渲染深度限制**：上限 50 层，超深嵌套渲染占位符，避免栈溢出
- **结构校验**：格式异常的报文直接拒收，保留上一帧，不白屏
- **未知组件降级**：未定义组件渲染为占位卡片，不能崩溃、不丢弃整帧
- **URL 白名单**：仅允许 http(s) 与 resources:// 协议，阻断 file:// 注入
- **单行错误定位**：解析失败定位至具体行号，报错明确，不静默丢弃

> 座舱场景还加了行驶安全校验。按挡位与车速判定行驶状态，行驶中 Tabs、Modal、List、MultipleChoice、Video、DateTimeInput 这类复杂或强交互组件会被拦截，非必须，可调整。

## 主题模块

生成式 UI 的视觉质量不取决于模型，而取决于主题系统的设计资产质量。本项目开发之初，链路虽然打通但视觉质量不足，根本原因是主题资产匮乏。

### 设计基准的选择

本系统选用 sinanata 的 unity-ui-toolkit-design-system 作为设计基准。该设计系统包含 15 份 USS 文件与 120 个 SVG 图标，具备完整的美术指导体系。其设计语言朴素平铺，无阴影、无渐变，与引擎能力匹配。视觉质量来自美术指导与 token 纪律，而非引擎特效。

### 主题机制与扩展

主题系统采用语义 token 架构，组件代码不写死颜色值，而是用变量名。这样换主题，只改变变量的值，组件代码不动。

架构上，分为：

1. 语义变量层：存所有样式变量的取值。
2. 主题类层：把变量包成一个CSS class，每个主题对应一个class
3. 组件层：所有组件只引用语义变量，组件不关心主题。

![3](./3.png)

> 自测的时候，如果要新增一份主题，可以在 Styles 的任意子目录下放置一份 FigmaTokens.uss 文件，注册表会自动发现，测试面板与场景宿主的主题下拉菜单自动新增选项。

### Figma 转换

Figma 侧管线实现从设计稿到 USS 主题的自动转换。

![4](./4.png)

Figma设计稿需要按“别名 / 组件:variant”规范命名，转换器直接读取节点的真实属性，提取四类信息：

- 语义色：从命名为语义别名的节点提取颜色值
- 字号梯度：从各层级文字节点提取字号，生成完整的字号体系
- 内边距：从组件节点提取 padding 值
- 圆角：从容器节点提取 radius 值

将以上提取的结果生成USS主题文件。为了验证 Figma 设计稿和 3D引擎实际渲染的一致性，配套了跨渲染器校准工具，可自行比对。

## 引擎兼容性

UI Toolkit 与标准 CSS 在布局与样式行为上存在多处差异，是开发中的主要隐性成本。项目中已做了 30 余条实测兼容条目（基于 Tuanjie 2022.3.55t4），小到 CSS 变量 fallback 写法被静默丢弃、flex 默认收缩行为和标准相反，大到写个 transform 直接崩溃、滚动条多占 24 像素高度、动态加 class 越界闪退，甚至连字体加载都可能不稳定。这些坑在代码里都有尽力做一些防御，已经能降低渲染层改动的排查成本。

> 具体信息写在  docs/[engine-compat-tuanjie.md](http://engine-compat-tuanjie.md)

## 回归测试体系

这套生成式 UI 的典型风险是改动之后，可能导致多处界面异常，人工验证成本高，所以写了自动化回归测试，以期能减少一些问题。

![5](./5.png)

## **局限**

- 视频与音频播放当前为信息占位；
- 日期输入为 ISO 字符串输入框；
- Modal 缺少遮罩与焦点锁定
- 长列表未实现虚拟化，当前为全量渲染，数据太多时性能将下降。
- Slider 拖柄尚未接入主题，应是引擎选择器未命中的已知问题。
- 需要更多的主题测试，发现映射层的隐藏问题。

## 试用与参与

> clone 仓库、用 Tuanjie或者Unity 打开、在 Play 之后，打开 A2UISchemeA 的测试发送面板，选择样例并发送。也可以模拟 Agent 推流去执行一条 Python 命令
>
> - 仓库地址：[https://github.com/SamXiaBing/a2ui-unity-toolkit](https://github.com/SamXiaBing/a2ui-unity-toolkit)
>
> 动手改代码前，建议先看一眼 docs/[engine-compat-tuanjie.md](http://engine-compat-tuanjie.md)，这里有之前踩坑的清单。
>
> 如果你也遇到了新的兼容坑、想加一个新主题，或者有座舱场景的组件需求，欢迎提 issue 。

