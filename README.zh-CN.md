# 座舱 3D HMI 写作语料库（SamXiaBing · Open Context）

车机 3D HMI 一线工程的公开写作语料：车漆渲染、场景材质、性能优化、稳定性保障、
开发框架、本地化、工具链与智驾 SR 业务实现。公众号为首发平台，本仓库是
**带日期、带目录、可机器检索**的开放快照——对标 [lizheng-open-context](https://github.com/sunyuzheng/lizheng-open-context)，
不是人格提示词，而是有出处、有时间、可引用、可继续开发的公共材料。

## 三类访客怎么用

- **同行工程师**：下面的系列索引即学习路径；方案含踩坑与 trade-off，可直接对照实践。
- **AI / 检索**：`catalog.jsonl` 为机器可读目录（一行一篇），配合全文检索回答领域问题；
  引用请注明文章路径。
- **写作者**：脱敏规范（讲工艺不讲业务）与逐系列编号实践可参考。

## 系列索引

共 79 篇已发表文章，其中 79 篇提供英文版（*.en.md，与原文同目录）。英文主版索引见 [README.md](README.md)。

### 车漆材质系列（Car Paint Materials）（6 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-07-22 | 座舱3D HMI材质：车漆（一）分层结构与整体构成 | [Cockpit 3D HMI Materials: Car Paint (Part 1) — Layered Structure and Overall Composition](articles/carpaint/座舱3D HMI材质：车漆（一）分层结构与整体构成/座舱3D HMI材质：车漆（一）分层结构与整体构成.en.md) |
| 2026-07-29 | 座舱3D HMI材质：车漆（二）Base 层：主色、边缘色与过渡 | [Cockpit 3D HMI Materials: Car Paint (Part 2) — The Base Layer: Main Color, Edge Color, and Transition](articles/carpaint/座舱3D HMI材质：车漆（二）Base 层：主色、边缘色与过渡/座舱3D HMI材质：车漆（二）Base 层：主色、边缘色与过渡.en.md) |
| 2026-08-05 | 座舱3D HMI材质：车漆（三）Flake 层：金属颗粒与珠光 | [Cockpit 3D HMI Materials: Car Paint (Part 3) — The Flake Layer: Metallic Flakes and Pearlescence](articles/carpaint/座舱3D HMI材质：车漆（三）Flake 层：金属颗粒与珠光/座舱3D HMI材质：车漆（三）Flake 层：金属颗粒与珠光.en.md) |
| 2026-08-12 | 座舱3D HMI材质：车漆（四）ClearCoat 层：清漆与镜面反射 | [Cockpit 3D HMI Materials: Car Paint (Part 4) — The ClearCoat Layer: Clearcoat and Mirror Reflection](articles/carpaint/座舱3D HMI材质：车漆（四）ClearCoat 层：清漆与镜面反射/座舱3D HMI材质：车漆（四）ClearCoat 层：清漆与镜面反射.en.md) |
| 2026-08-19 | 座舱3D HMI材质：车漆（五）车衣遮罩层 | [Cockpit 3D HMI Materials: Car Paint (Part 5) — The Wrap Mask Layer](articles/carpaint/座舱3D HMI材质：车漆（五）车衣遮罩层/座舱3D HMI材质：车漆（五）车衣遮罩层.en.md) |
| 2026-08-26 | 座舱3D HMI材质：车漆（六）天气特效层 | [Cockpit 3D HMI Materials: Car Paint (Part 6) — The Weather Effects Layer](articles/carpaint/座舱3D HMI材质：车漆（六）天气特效层/座舱3D HMI材质：车漆（六）天气特效层.en.md) |

### 场景材质系列（Scene Materials & Effects）（11 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-05-26 | 座舱3D HMI场景：墙面的摇曳树影 | [Cockpit 3D HMI Scenes: Swaying Tree Shadows on the Wall](articles/rendering/座舱3D HMI场景：墙面的摇曳树影/座舱3D HMI场景：墙面的摇曳树影.en.md) |
| 2026-05-27 | 座舱3D HMI场景：URP倒影效果实现 | [Cockpit 3D HMI Scenes: Implementing Planar Reflections in URP](articles/rendering/座舱3D HMI场景：URP倒影效果实现/座舱3D HMI场景：URP倒影效果实现.en.md) |
| 2026-05-28 | 座舱3D HMI场景：充电特效 | [Cockpit 3D HMI Scene: The Charging Effect](articles/rendering/座舱3D HMI场景：充电特效/座舱3D HMI场景：充电特效.en.md) |
| 2026-05-29 | 座舱3D HMI场景：放电特效 | [Cockpit 3D HMI Scene: Discharge Effect](articles/rendering/座舱3D HMI场景：放电特效/座舱3D HMI场景：放电特效.en.md) |
| 2026-06-22 | 座舱3D HMI场景化动态帧率：在算力约束下寻求体验平衡 | [Scenario-Based Dynamic Frame Rate for Cockpit 3D HMI: Seeking the Experience Balance Under Compute Constraints](articles/rendering/座舱3D HMI场景化动态帧率：在算力约束下寻求体验平衡/座舱3D HMI场景化动态帧率：在算力约束下寻求体验平衡.en.md) |
| 2026-07-01 | 座舱3D HMI场景：全局模糊优化的毛玻璃材质方案 | [Cockpit 3D HMI Scenes: A Frosted Glass Material Approach Built on Global Blur](articles/rendering/座舱3D HMI场景：全局模糊优化的毛玻璃材质方案/座舱3D HMI场景：全局模糊优化的毛玻璃材质方案.en.md) |
| 2026-07-02 | 座舱3D HMI场景：探索液态玻璃效果 | [Cockpit 3D HMI Scenes: Exploring the Liquid Glass Effect](articles/rendering/座舱3D HMI场景：探索液态玻璃效果/座舱3D HMI场景：探索液态玻璃效果.en.md) |
| 2026-07-02 | 座舱3D HMI场景：车窗的透明玻璃材质 | [Cockpit 3D HMI Scenes: Transparent Glass Materials for Car Windows](articles/rendering/座舱3D HMI场景：车窗的透明玻璃材质/座舱3D HMI场景：车窗的透明玻璃材质.en.md) |
| 2026-07-08 | 座舱3D HMI场景：Dual Kawase 模糊的工程思维 | [Cockpit 3D HMI Scenes: The Engineering Mindset Behind Dual Kawase Blur](articles/rendering/座舱3D HMI场景：Dual Kawase 模糊的工程思维/座舱3D HMI场景：Dual Kawase 模糊的工程思维.en.md) |
| 2026-07-15 | 座舱3D HMI场景：车灯光柱的体积光效果 | [Cockpit 3D HMI Scenes: Volumetric Light Beams for Car Lights](articles/rendering/座舱3D HMI场景：车灯光柱的体积光效果/座舱3D HMI场景：车灯光柱的体积光效果.en.md) |
| 2026-09-02 | 座舱3D HMI场景：水面效果 | [Cockpit 3D HMI Scenes: The Water Surface Effect](articles/rendering/座舱3D HMI场景：水面效果/座舱3D HMI场景：水面效果.en.md) |

### 性能优化系列（Performance）（7 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-07-13 | 座舱3D HMI性能：帧率与内存异常自动数据捕获方案 | [Cockpit 3D HMI Performance: Auto-Capturing Data on Frame Rate and Memory Anomalies](articles/perf/座舱3D HMI性能：帧率与内存异常自动数据捕获方案/座舱3D HMI性能：帧率与内存异常自动数据捕获方案.en.md) |
| 2026-07-20 | 座舱3D HMI性能：LINQ写得爽，GC火葬场 | [Cockpit 3D HMI Performance: LINQ Feels Great to Write, the GC Ends Up in the Crematorium](articles/perf/座舱3D HMI性能：LINQ写得爽，GC火葬场/座舱3D HMI性能：LINQ写得爽，GC火葬场.en.md) |
| 2026-07-27 | 座舱3D HMI性能：材质实例化与内存泄漏 | [Cockpit 3D HMI Performance: Material Instantiation and Memory Leaks](articles/perf/座舱3D HMI性能：材质实例化与内存泄漏/座舱3D HMI性能：材质实例化与内存泄漏.en.md) |
| 2026-08-03 | 座舱3D HMI性能：不走冤枉路的网格重建 | [Cockpit 3D HMI Performance: Mesh Rebuilds Without the Wasted Trip](articles/perf/座舱3D HMI性能：不走冤枉路的网格重建/座舱3D HMI性能：不走冤枉路的网格重建.en.md) |
| 2026-08-10 | 座舱3D HMI性能：把CPU的工作交给GPU | [Cockpit 3D HMI Performance: Offloading CPU Work to the GPU](articles/perf/座舱3D HMI性能：把CPU的工作交给GPU/座舱3D HMI性能：把CPU的工作交给GPU.en.md) |
| 2026-08-17 | 座舱3D HMI性能：Instantiate 太多卡成 PPT？试试分帧加载 | [Cockpit 3D HMI Performance: Too Many Instantiates Stuttering Like a Slideshow? Try Frame-Spread Loading](articles/perf/座舱3D HMI性能：Instantiate 太多卡成 PPT？试试分帧加载/座舱3D HMI性能：Instantiate 太多卡成 PPT？试试分帧加载.en.md) |
| 2026-09-07 | 座舱3D HMI性能：内存泄漏？关于“回收”的陷阱 | [Cockpit 3D HMI Performance: Memory Leak? The Trap of “Recycling”](articles/perf/座舱3D HMI性能：内存泄漏？关于“回收”的陷阱/座舱3D HMI性能：内存泄漏？关于“回收”的陷阱.en.md) |

### 稳定性系列（Stability）（4 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-07-03 | 座舱3D HMI稳定性：ANR 主动检测方案（一） | [Cockpit 3D HMI Stability: A Proactive ANR Detection Solution (Part 1)](articles/stability/座舱3D HMI稳定性：ANR 主动检测方案（一）/座舱3D HMI稳定性：ANR 主动检测方案（一）.en.md) |
| 2026-07-06 | 座舱3D HMI稳定性：ANR 主动检测方案（二） | [Cockpit 3D HMI Stability: A Proactive ANR Detection Scheme (Part 2)](articles/stability/座舱3D HMI稳定性：ANR 主动检测方案（二）/座舱3D HMI稳定性：ANR 主动检测方案（二）.en.md) |
| 2026-08-24 | 座舱3D HMI稳定性：黑屏 · binder清理与锁竞争 | [Cockpit 3D HMI Stability: Black Screens · Binder Cleanup and Lock Contention](articles/stability/座舱3D HMI稳定性：黑屏 · binder清理与锁竞争/座舱3D HMI稳定性：黑屏 · binder清理与锁竞争.en.md) |
| 2026-08-31 | 座舱3D HMI稳定性：黑屏 · STR引发的误杀 | [Cockpit 3D HMI Stability: Black Screen · False Kills Triggered by STR](articles/stability/座舱3D HMI稳定性：黑屏 · STR引发的误杀/座舱3D HMI稳定性：黑屏 · STR引发的误杀.en.md) |

### 开发框架系列（Dev Framework）（7 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-07-24 | 座舱3D HMI开发框架：引用池 | [Cockpit 3D HMI Development Framework: The Reference Pool](articles/framework/座舱3D HMI开发框架：引用池/座舱3D HMI开发框架：引用池.en.md) |
| 2026-07-31 | 座舱3D HMI开发框架：对象池 | [Cockpit 3D HMI Development Framework: The Object Pool](articles/framework/座舱3D HMI开发框架：对象池/座舱3D HMI开发框架：对象池.en.md) |
| 2026-08-07 | 座舱3D HMI 框架：BindableProperty 与数据驱动的起点 | [Cockpit 3D HMI Framework: BindableProperty and the Starting Point of Data-Driven Design](articles/framework/座舱3D HMI 框架：BindableProperty 与数据驱动的起点/座舱3D HMI 框架：BindableProperty 与数据驱动的起点.en.md) |
| 2026-08-14 | 座舱3D HMI 框架：EventPool 的事件派发机制 | [Cockpit 3D HMI Framework: The EventPool Event Dispatching Mechanism](articles/framework/座舱3D HMI 框架：EventPool 的事件派发机制/座舱3D HMI 框架：EventPool 的事件派发机制.en.md) |
| 2026-08-21 | 座舱3D HMI 框架：从 Fsm 状态机到 Procedure 流程管理 | [Cockpit 3D HMI Framework: From the Fsm State Machine to Procedure Flow Management](articles/framework/座舱3D HMI 框架：从 Fsm 状态机到 Procedure 流程管理/座舱3D HMI 框架：从 Fsm 状态机到 Procedure 流程管理.en.md) |
| 2026-08-28 | 座舱3D HMI 框架：模块的抽象、注册与调度 | [Cockpit 3D HMI Framework: Module Abstraction, Registration, and Scheduling](articles/framework/座舱3D HMI 框架：模块的抽象、注册与调度/座舱3D HMI 框架：模块的抽象、注册与调度.en.md) |
| 2026-09-04 | 座舱3D HMI 框架：应用框架的入口设计与启动流程 | [Cockpit 3D HMI Framework: Entry Point Design and the Startup Flow](articles/framework/座舱3D HMI 框架：应用框架的入口设计与启动流程/座舱3D HMI 框架：应用框架的入口设计与启动流程.en.md) |

### 本地化系列（Localization）（5 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-06-08 | 座舱3D HMI本地化：从拿到Locale开始 | [Cockpit 3D HMI Localization: It Starts with Getting the Locale](articles/localization/座舱3D HMI本地化：从拿到Locale开始/座舱3D HMI本地化：从拿到Locale开始.en.md) |
| 2026-06-09 | 座舱3D HMI本地化：文言翻译表的导入工具 | [Cockpit 3D HMI Localization: A Tool for Importing Translation Tables](articles/localization/座舱3D HMI本地化：文言翻译表的导入工具/座舱3D HMI本地化：文言翻译表的导入工具.en.md) |
| 2026-06-10 | 座舱3D HMI本地化：换语种不只是换文本 | [Cockpit 3D HMI Localization: Switching Languages Is More Than Swapping Text](articles/localization/座舱3D HMI本地化：换语种不只是换文本/座舱3D HMI本地化：换语种不只是换文本.en.md) |
| 2026-06-11 | 座舱3D HMI本地化：RTL字符串里的工序思维 | [Cockpit 3D HMI Localization: The Pipeline Mindset in RTL String Processing](articles/localization/座舱3D HMI本地化：RTL字符串里的工序思维/座舱3D HMI本地化：RTL字符串里的工序思维.en.md) |
| 2026-06-12 | 座舱3D HMI本地化：文言变“砖”排查手记 | [Cockpit 3D HMI Localization: Debugging When Text Turns into 'Bricks](articles/localization/座舱3D HMI本地化：文言变“砖”排查手记/座舱3D HMI本地化：文言变“砖”排查手记.en.md) |

### 工具链系列（Toolchain）（4 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-06-05 | 座舱 SR 数据回放工具：从录制到回放的完整设计 | [Cockpit SR Data Replay Tool: Complete Design from Recording to Playback](articles/tools/座舱 SR 数据回放工具：从录制到回放的完整设计/座舱 SR 数据回放工具：从录制到回放的完整设计.en.md) |
| 2026-06-29 | 座舱 SR 数据回放演变：从单通道到多链路 | [Cockpit SR Data Replay Evolution: From Single Channel to Multi-Link](articles/tools/座舱 SR 数据回放演变：从单通道到多链路/座舱 SR 数据回放演变：从单通道到多链路.en.md) |
| 2026-07-10 | 座舱3D HMI工具链：资产导入规则模块 | [Cockpit 3D HMI Toolchain: The Asset Import Rules Module](articles/tools/座舱3D HMI工具链：资产导入规则模块/座舱3D HMI工具链：资产导入规则模块.en.md) |
| 2026-07-17 | 座舱3D HMI工具链：依据配置文件生成的调试面板 | [Cockpit 3D HMI Toolchain: A Debug Panel Generated from Configuration Files](articles/tools/座舱3D HMI工具链：依据配置文件生成的调试面板/座舱3D HMI工具链：依据配置文件生成的调试面板.en.md) |

### 智驾 SR 系列（SR · Surround Rendering）（21 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-05-07 | 智驾SR开发：点与坐标系 | [Smart Driving SR Development: Points and Coordinate Systems](articles/sr/智驾SR开发：点与坐标系/环境感知模拟—画点.en.md) |
| 2026-05-08 | 智驾SR开发：从输入数据看“线”的五种生成方式 | [Smart Driving SR Development: Five Ways to Generate Lines from Input Data](articles/sr/智驾SR开发：从输入数据看“线”的五种生成方式/智驾SR开发：从输入数据看“线”的五种生成方式.en.md) |
| 2026-05-09 | 智驾 SR 开发：画线的五个“避坑”指南 | [Smart-Driving SR Development: Five Pitfalls to Avoid When Drawing Lines](articles/sr/智驾 SR 开发：画线的五个“避坑”指南/智驾 SR 开发：画线的五个“避坑”指南.en.md) |
| 2026-05-11 | 智驾 SR 开发：可行驶区域三种工程实现指南 | [Intelligent Driving SR Development: Three Engineering Approaches for Rendering the Drivable Area](articles/sr/智驾 SR 开发：可行驶区域三种工程实现指南/智驾 SR 开发：可行驶区域三种工程实现指南.en.md) |
| 2026-05-12 | 智驾 SR 开发：泊车OCC可视化从体素网格到障碍表面的两种工程实现 | [Intelligent Driving SR Development: Two Engineering Implementations for Parking OCC Visualization, from Voxel Grid to Obstacle Surfaces](articles/sr/智驾 SR 开发：泊车OCC可视化从体素网格到障碍表面的两种工程实现/智驾 SR 开发：泊车OCC可视化从体素网格到障碍表面的两种工程实现.en.md) |
| 2026-05-13 | 智驾 SR 开发：感知物全拆解 | [ADAS SR Development: A Complete Breakdown of Perception Objects](articles/sr/智驾 SR 开发：感知物全拆解/智驾SR开发：感知物全拆解.en.md) |
| 2026-05-14 | 智驾SR开发：“厚重”的泊车位 | [Smart Driving SR Development: The “Weighty” Parking Slot](articles/sr/智驾SR开发：“厚重”的泊车位/智驾SR开发：“厚重”的泊车位.en.md) |
| 2026-05-15 | 车载智驾信号怎么到座舱3D渲染？一文拆解两种落地架构 | [How ADAS Signals Reach In-Cabin 3D Rendering: Two Production Architectures, Broken Down](articles/sr/车载智驾信号怎么到座舱3D渲染？一文拆解两种落地架构/车载智驾信号怎么到座舱3D渲染？一文拆解两种落地架构.en.md) |
| 2026-05-21 | 智驾SR开发：HMI相机交互分层实现方案 | [Intelligent Driving SR Development: A Layered Implementation of HMI Camera Interaction](articles/sr/智驾SR开发：HMI相机交互分层实现方案/智驾SR开发：HMI相机交互分层实现方案.en.md) |
| 2026-05-22 | 智驾SR开发：记忆泊车建图全览 | [Intelligent Driving SR Development: A Complete Overview of Memory Parking Mapping](articles/sr/智驾SR开发：记忆泊车建图全览/智驾SR开发：记忆泊车建图全览.en.md) |
| 2026-06-23 | 智驾 SR 开发：他们说的 SOMEIP 是想指什么？ | [Smart Driving SR Development: What Do People Actually Mean by SOME/IP?](articles/sr/智驾 SR 开发：他们说的 SOMEIP 是想指什么？/智驾 SR 开发：他们说的 SOMEIP 是想指什么？.en.md) |
| 2026-06-26 | 智驾 SR 开发：共享内存是条必经之路 | [Intelligent Driving SR Development: Shared Memory Is a Road You Must Take](articles/sr/智驾 SR 开发：共享内存是条必经之路/智驾 SR 开发：共享内存是条必经之路.en.md) |
| 2026-07-09 | 智驾 SR 开发：机位状态与场景流转梳理 | [Intelligent Driving SR Development: A Survey of Camera-Position States and Scene Transitions](articles/sr/智驾 SR 开发：机位状态与场景流转梳理/智驾 SR 开发：机位状态与场景流转梳理.en.md) |
| 2026-07-16 | 智驾 SR 开发：记忆泊车全览视角的自动构图方法 | [ADAS SR Development: Automatic Camera Framing for the Memory Parking Overview View](articles/sr/智驾 SR 开发：记忆泊车全览视角的自动构图方法/智驾 SR 开发：记忆泊车全览视角的自动构图方法.en.md) |
| 2026-07-23 | 智驾 SR 开发：场景元素的 Layer 化分层管理 | [Intelligent Driving SR Development: Layer-Based Hierarchical Management of Scene Elements](articles/sr/智驾 SR 开发：场景元素的 Layer 化分层管理/智驾 SR 开发：场景元素的 Layer 化分层管理.en.md) |
| 2026-07-30 | 智驾 SR 开发：SR 场景样式与主题管理 | [ADAS SR Development: SR Scene Styles and Theme Management](articles/sr/智驾 SR 开发：SR 场景样式与主题管理/智驾 SR 开发：SR 场景样式与主题管理.en.md) |
| 2026-08-06 | 智驾 SR 开发：自车视角遮挡检测与半透明化实现 | [Intelligent Driving SR Development: Occlusion Detection and Semi-Transparency from the Ego-Vehicle View](articles/sr/智驾 SR 开发：自车视角遮挡检测与半透明化实现/智驾 SR 开发：自车视角遮挡检测与半透明化实现.en.md) |
| 2026-08-13 | 智驾 SR 开发：感知物轨迹平滑的卡尔曼滤波实践 | [ADAS SR Development: Kalman Filtering in Practice for Smoothing Perception Trajectories](articles/sr/智驾 SR 开发：感知物轨迹平滑的卡尔曼滤波实践/智驾 SR 开发：感知物轨迹平滑的卡尔曼滤波实践.en.md) |
| 2026-08-20 | 智驾 SR 开发：感知物的尺寸适配怎么做才对？ | [Intelligent Driving SR Development: What's the Right Way to Fit Perceived-Object Sizes?](articles/sr/智驾 SR 开发：感知物的尺寸适配怎么做才对？/智驾 SR 开发：感知物的尺寸适配怎么做才对？.en.md) |
| 2026-08-27 | 智驾 SR 开发：PDC 环绕波纹的单材质工程实践 | [ADAS SR Development: Engineering a Single-Material Approach to the PDC Surrounding Ripple](articles/sr/智驾 SR 开发：PDC 环绕波纹的单材质工程实践/智驾 SR 开发：PDC 环绕波纹的单材质工程实践.en.md) |
| 2026-09-03 | 智驾 SR 开发：一条灯带的多重身份 | [Intelligent Driving SR Development: The Multiple Identities of a Light Strip](articles/sr/智驾 SR 开发：一条灯带的多重身份/智驾 SR 开发：一条灯带的多重身份.en.md) |

### 工程实践拾遗（Engineering Notes）（14 篇）

| 日期 | 标题 | English |
|---|---|---|
| 2026-05-18 | 用Adobe After Effects思维做Unity相机动画：相机运动模块3D HMI实践 | [Doing Unity Camera Animation with an Adobe After Effects Mindset: A Camera Motion Module in 3D HMI Practice](articles/misc/用Adobe After Effects思维做Unity相机动画：相机运动模块3D HMI实践/用Adobe After Effects思维做Unity相机动画：相机运动模块3D HMI实践.en.md) |
| 2026-05-19 | 3D HMI还原度：镜头动效曲线从公式到资产的转化 | [3D HMI Fidelity: Camera Motion Curves — From Formula to Asset](articles/misc/3D HMI还原度：镜头动效曲线从公式到资产的转化/3D HMI还原度：镜头动效曲线从公式到资产的转化.en.md) |
| 2026-05-20 | 座舱3D HMI相机环视：搞定滑动手感的三个机制 | [Cockpit 3D HMI Camera Orbit: Three Mechanisms for a Great Swipe Feel](articles/misc/座舱3D HMI相机环视：搞定滑动手感的三个机制/座舱3D HMI相机环视：搞定滑动手感的三个机制.en.md) |
| 2026-05-25 | 重做Unity的Play按钮：为平台化开发提效 | [Rethinking Unity's Play Button: Boosting Efficiency for Platform-Based Development](articles/misc/重做Unity的Play按钮：为平台化开发提效/重做Unity的Play按钮：为平台化开发提效.en.md) |
| 2026-06-01 | 智能座舱3D HMI：服务化渲染架构剖析 | [Smart-Cockpit 3D HMI: Dissecting the Service-Based Rendering Architecture](articles/misc/智能座舱3D HMI：服务化渲染架构剖析/智能座舱3D HMI：服务化渲染架构剖析.en.md) |
| 2026-06-03 | 智能座舱3D HMI：设计服务化渲染-安卓端 | [Smart Cockpit 3D HMI: Designing Service-Oriented Rendering — The Android Side](articles/misc/智能座舱3D HMI：设计服务化渲染-安卓端/智能座舱3D HMI：设计服务化渲染-安卓端.en.md) |
| 2026-06-04 | 智能座舱3D HMI：设计服务化渲染-引擎端 | [Smart Cockpit 3D HMI: Service-Based Rendering — The Engine Side](articles/misc/智能座舱3D HMI：设计服务化渲染-引擎端/智能座舱3D HMI：设计服务化渲染-引擎端.en.md) |
| 2026-06-15 | 3D HMI 应用内一镜到底：从设计决策到技术落地 | [In-App One-Take Camera Transitions in 3D HMI: From Design Decisions to Implementation](articles/misc/3D HMI 应用内一镜到底：从设计决策到技术落地/3D HMI应用内一镜到底：从设计决策到技术落地.en.md) |
| 2026-06-16 | 3D HMI 跨应用一镜到底：帧画面衔接技术 | [3D HMI Cross-App One Continuous Shot: Frame Continuity Techniques](articles/misc/3D HMI 跨应用一镜到底：帧画面衔接技术/3D HMI 跨应用一镜到底：帧画面衔接技术.en.md) |
| 2026-06-17 | 3D HMI 一镜到底：典型问题分析与修复 | [3D HMI One-Take Transitions: Typical Problems and Fixes](articles/misc/3D HMI 一镜到底：典型问题分析与修复/3D HMI 一镜到底：典型问题分析与修复.en.md) |
| 2026-06-18 | 从全屏到三七分屏：车机 3D HMI 分屏的落地路径 | [From Full Screen to 30/70 Split Screen: A Practical Path for Split-Screen in IVI 3D HMI](articles/misc/从全屏到三七分屏：车机 3D HMI 分屏的落地路径/从全屏到三七分屏：车机 3D HMI 分屏的落地路径.en.md) |
| 2026-06-19 | 车机端 3D HMI 日志打印：性能影响与控制策略 | [3D HMI Logging on In-Vehicle Units: Performance Costs and Control Strategies](articles/misc/车机端 3D HMI 日志打印：性能影响与控制策略/车机端 3D HMI 日志打印：性能影响与控制策略.en.md) |
| 2026-06-24 | 3D 视图挖个洞，把视频画面填进去 | [Punch a Hole in the 3D View and Fill It with Video](articles/misc/3D 视图挖个洞，把视频画面填进去/3D 视图挖个洞，把视频画面填进去.en.md) |
| 2026-09-05 | 车机端生成式 UI 实践：A2UI 协议的 Unity UI Toolkit 原生渲染方案 | [Generative UI on the Vehicle Head Unit: A Native Unity UI Toolkit Renderer for the A2UI Protocol](articles/misc/车机端生成式 UI 实践：A2UI 协议的 Unity UI Toolkit 原生渲染方案/车机端生成式 UI 实践：A2UI 协议的 Unity UI Toolkit 原生渲染方案.en.md) |

## 数据层

- 每篇文章位于 `articles/<系列>/<标题>/`，md 文首带 frontmatter 元数据，图片为本地相对路径，
  英文版为同目录 `<标题>.en.md`
- `scripts/build_catalog.py` 重新生成目录与两个 README；`scripts/validate_corpus.py` 校验完整性

## 边界与声明

- 全部代码片段均为**脱敏示意代码**：讲工艺不讲业务，与真实工程无对应关系
- 本仓库不包含：未发表草稿、职场系列、任何客户与项目标识信息
- 文中观点为作者个人观点，与雇主无关
- 部分早期文章配图因公众号图床防盗链遗失，已标注 *[配图见公众号原文]*

## License

内容：[CC BY-NC-ND 4.0](LICENSE-CONTENT.md)（署名—非商业—禁止演绎）。转载请署名并附链接。

---

公众号：首发平台（名称待补） · GitHub：[SamXiaBing](https://github.com/SamXiaBing)