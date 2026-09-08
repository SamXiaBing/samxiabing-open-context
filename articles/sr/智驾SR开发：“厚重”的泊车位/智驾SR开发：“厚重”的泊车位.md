---
title: "智驾SR开发：“厚重”的泊车位"
date: 2026-05-14
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 泊车位（Parking Slot / Parking Space）是一个比较有特点的感知物，单拎出来写一篇，是因为它本身丰富的业务关联。几何角度，就是4个角点，但是因为横向/纵向/斜列车位类型、限位器、车位特效、可选序号、点击检测、泊入交互等，而产生了很多细节需要处理。

本文整理泊车位的绘制流程，罗列相关的业务逻辑、功能要点，基于有限的所见所闻梳理出泊车位相关的开发要点。

---

## 1. 数据形式

大体来说就是 **4个点 + 1个车位类型 + 限位器数据 + 车位序号 + 车位状态 + 其他相关功能值（比如 窄车位）** 就是一个泊车位的常见数据。

### 1.1 字段解释

在实际开发中，每一种数据都和相应的功能有关：


| 字段              | 业务意图                                                                        |
| --------------- | --------------------------------------------------------------------------- |
| `slot_id`       | 车位的唯一标识。用户点击某个车位后，系统需要知道用户选的是哪个车位，才能下发泊入命令。                                 |
| `slot_type`     | 车位类型（横向/纵向/斜列）。不同类型的车位，几何计算逻辑不同——横向车位的车长方向与车道平行，纵向车位与车道垂直，斜列车位则需要按实际角度计算。   |
| `corner_points` | 4个角点坐标。这是车位的几何基础，决定了车位在画面中的位置、形状、朝向。绘制车位底板、边框、检测点击，都依赖这4个点。                 |
| `slot_status`   | 车位状态（已搜索/可停/可选/正在泊/完成等）。状态决定视觉表现——搜索态显示普通边框，可泊态显示蓝色高亮，正在泊入显示开口边框，完成态显示绿色特效。 |
| `slot_num`      | 车位编号（如"8号库位"）。显示在车位上的数字，让用户和客服人员能准确描述"我要泊入8号车位"。                            |
| `limiters`      | 限位器（车挡/轮挡）的两个端点坐标。渲染时需要把这两个点转换成车位内的一个位置部署限位器模型。                             |
| `narrowSlot`    | 窄库位标志。特殊车位或左右已停车导致的比标准车位窄的车位，这个标志触发窄位警示显示，提醒用户车位较窄要小心。                      |


### 1.2 角点顺序与开口方向

角点的排列顺序直接影响这个泊车位泊入开口方向的判断：

- **角点排列：我遇到有两种，依次以数组下标**`[0, 1, 2, 3]`：

1. **逆时针 排列**：俯视图下沿开口侧行走，角点序号沿边界递增（下图为一种常见约定：0→1 为开口边，整体逆时针）。

*[配图见公众号原文]*

2. **Z字型 排列**：另一种常见约定是按「Z」字形串联序号

*[配图见公众号原文]*

- **朝向计算**：`点0 至 点1` 的这条边是开口端（车可以进去的一侧），Mesh的宽高由短边/长边决定（横向车位短边约2.5米，长边约5-6米）

### 1.3 预制体的组成结构

在实际开发中，一个泊车位预制体，下面会根据业务需求，挂载各种子物体：

```
ParkingSlot（根节点）
├── Base                    # 车位底板面片
├── Frame                   # 车位边框
│   ├── Corner_0 / 1 / 2 / 3   # 四个角件
│   └── Edge_0 / 1 / 2 / 3     # 四条边件
├── Number                  # 车位编号数字（"8号库位"）
├── Icon_P                   # P图标（可泊入时显示）
├── Effect               # 泊入完成特效（绿圈/打勾等）
├── Switch               # 泊入方向切换片（头/尾图标）
└── Limiter                  # 限位器图标（车挡）

```

> Frame 这个物体，根据实际设计需求决定要不要，有的HMI设计方案，只需要泊车位呈现一个面片的状态配合贴图即可，这种其实后续逻辑会简单得多。有的HMI设计方案会要求用三维模型表达边框，此时就需要以圆角模型部署在角点，框边模型根据计算部署。

---

## 2. 停车位几何构建

在智驾SR开发中，停车位的几何构建有两种方案，分别适配不同性能和交互需求：


| 方案  | 构成                                    | 适用场景                       |
| --- | ------------------------------------- | -------------------------- |
| 方式一 | Corner（角件）+ Edge（边条）+ Base（底面片）拼出带框车位 | 自动泊车近场场景，需要支持交互和精细显示       |
| 方式二 | 单张 Quad + 配套贴图 做轻量面片                  | 记忆泊车巡航/多楼层场景，库位数量大，仅需基础可读性 |


无论采用哪种方案，初始化都遵循三步流程：

*[配图见公众号原文]*

1. **确定位置**：默认取四边形平面中心，搭配统一地面高度即可；如果地面需要保留起伏，可以保留四个角点原始高度后取平均值作为高度。
2. **计算航向**：根据当前角点顺序的约定，计算偏航角；斜列车位需要单独结合邻边长度联合判断。
3. **计算车位尺寸**：由尺寸工具类，根据角点顺序约定计算车位宽度width和长度length。

### 2.1 方式一：Corner + Edge + Base 带框构建

对应项目预制体中 Frame 子物体 + 底面 Base 的结构：四个角件、四条边条，叠加底面片组成完整车位。输入依然是4个角点 + 车位类型，工程实现上不会为横向/纵向/斜列三种类型各开发一套独立的的逻辑，而是通过装配实现，步骤如下：

1. 根据当前角点约定（必须和联调结论对齐，例如Z形序约定下，0→1为开口端），计算得到width和length。
2. 角件（Corner）摆放：在车位根节点的局部水平面内，把四个角件摆放到标准矩形的四个角（坐标为 ±半宽、±半长）；角件一般是预制圆角柱体，只需要修改localPosition等变换参数即可，只需一个预置体。
3. 边条（Edge）拉伸：边条对应放在对边位置，通过修改localScale拉伸长度，并且要扣除角件的圆角半径，减轻角件和边条的穿插重叠；如果是开口框模式，开口对侧的顶边可以整段关闭，只保留两端的圆角柱即可，避免画出多余的假边。
4. 底面片（Base）适配：在和边框同一update渲染流程中，使用同一套宽高设置底面片的localScale和局部欧拉角：通过 宽大于长 判定为横向车位时，底面片额外旋转 -90°，并且通过材质_IsHorizontal标记通知Shader切换UV排布；纵向和斜列车位直接共用这套流程，不需要额外分支。

> 这种复杂的做法，最根本的目的就是为了避免库位长宽在横纵车位类型变化的时候，因为scale的拉伸造成模型的不合理的变形。

### 2.2 方式二：单 Quad + 贴图 轻量面片构建

当库位数量大，或者只需要满足建图结果全览级可读性时，通常不会挂载方式一整套Corner/Edge子物体，仅保留一张Quad配合日夜贴图，通过切换主图或材质参数改变状态，还可以配合GPU实例化进一步降低性能开销，具体步骤：

1. 角点遵循排列约定，计算宽高。
2. 根节点：中心（各角高度取平均）的位置和旋转和数据一致；斜列车位用开口相邻边计算航向；横向车位在航向角基础上额外补充+90°旋转。
3. Quad面片：用localScale拟合计算出的宽长；横向车位在缩放阶段，交换两个水平轴的宽高值，保证贴图长轴和车位长边方向一致。不至于拉伸贴图造成畸形。

---

## 3. 车位附属物与交互

### 3.1 车位编号

车位编号一般是在泊车的时候，有多个车位可以选择的时候，非推荐车位需要显示的图片。为了需要让用户能够方便阅读，基于当前相机的旋转（在俯视基础上），需要让数字的底边基本平行于整个CSD屏幕的底边。

**朝向计算**：

```csharp
/// <summary>更新图标朝向，始终面向相机（Billboard效果）</summary>
private void UpdateIconRotation()
{
    if (slotIcon != null)
    {
        // 第一步：计算相机到图标的方向（去掉Y轴，只在水平面内旋转）
        Vector3 direction = Camera.transform.position - slotIcon.transform.position;
        direction.y = 0;
        
        // 第二步：计算朝向角度并应用
        slotIcon.transform.rotation = 
            Quaternion.Euler(0, Quaternion.LookRotation(direction, Vector3.up).eulerAngles.y, 0);
    }
}

```

**角度离散化**：设计上不追求每帧精确朝向相机，而是把连续的值离散到 **0/±90/180** 四档。这样斜视时仍保持"横平竖直"，避免出现有的车位是水平的，数字也横着，就很不易读了。

### 3.2 窄车位

**窄车位（narrowSlot）**：宽度小于标准车位的库位，通常出现在立体车库等场景。窄位标志仅驱动是否额外显示窄位警示子物体，本质上就是一张贴图，不改变四角点几何，没有什么可多说的。

### 3.3 限位器

**限位器（Limiter / 轮挡）**：数据格式是**两个端点坐标**：

```protobuf
message SlotFusionLimiter {
    uint32 id = 1;
    repeated Vector2 end_points = 2;  // 两个端点坐标（固定2个）
}

```

**限位器的位置计算**（8步）：

```csharp
/// <summary>计算限位器在车位边框上的位置</summary>
public void UpdateTransform(
    SlotFusionLimiter limiter,
    SlotType slotType,
    Transform slotRoot,
    Vector2[] cornerWorldXz)
{
    // 目的1：把世界坐标转成局部坐标，这样移动slotRoot时限位器会跟着动
    Vector3 lp0 = slotRoot.InverseTransformPoint(p0);
    
    // 目的2：根据融合中点判断限位器应该在"哪条边"旁边
    bool edge03 = true;
    if (hasFusionMid)
    {
        // 比较中点到边03和边12的距离，距离小的就是限位器所在的边
        float d03 = (fusionMid - m03).sqrMagnitude;
        float d12 = (fusionMid - m12).sqrMagnitude;
        edge03 = d03 < d12;
    }
    
    // 目的3：确定这条边的两个端点
    a = edge03 ? lp0 : lp1;
    b = edge03 ? lp3 : lp2;
    
    // 目的4：计算边的中点和切线方向
    Vector3 edgeMid = (a + b) * 0.5f;
    Vector3 tangent = b - a;
    
    // 目的5：计算内向法向量（指向车位内部）
    // 用叉积得到垂直于切线的方向，Y轴向上所以结果是水平的
    Vector3 inward = Vector3.Cross(Vector3.up, tangent).normalized;
    
    // 目的6：确保inward真的指向车位中心（而不是指向外面）
    Vector3 toCenter = (lp0 + lp1 + lp2 + lp3) * 0.25f - edgeMid;
    if (Vector3.Dot(inward, toCenter) < 0f) inward = -inward;
    
    // 目的7：计算限位器位置（距边线0.8米，向内偏移）
    Vector3 midLocal = edgeMid + inward * 0.8f;
    
    // 目的8：设置位置和旋转
    limiterTransform.localPosition = midLocal;
    limiterTransform.localRotation = Quaternion.Euler(0, r, 0);
}

```

### 3.4 泊入方向

车位上显示的泊入方向图（一张类似压扁的车体的图，能清晰分辨哪一头是车头，哪一头是车尾），用来告诉用户，泊车将要**车头朝内还是车尾朝内**。

纵向和斜列车位，智驾供应商的数据协议的泊入方向字段，可以用来显示**泊入方向图**。但对于横向车位我遇到过智驾供应商无法给到**横向车位泊入方向**值的情况，于是这里有一个**应用层兜底逻辑**——需要自己算：

```csharp
/// <summary>根据自车车头方向计算横向车位的泊入方向</summary>
// 判断逻辑：角点1→角点0的单位向量与自车heading向量点积小于1e-9时（避免浮点误差），
// 车头是角点1和角点3那条边；否则是角点0和角点2那条边
if (Vector3.Dot(heading, slotDir) < 1e-9f)
{
    // 车头在角点1-3边 → 尾泊入
    parkingDir = 1;
}
else
{
    // 车头在角点0-2边 → 头泊入
    parkingDir = 0;
}

```

## 4. 点击检测

泊车位的点击检测依赖于精确的碰撞体计算，然后基于相机发射射线：

```csharp
/// <summary>更新碰撞体Bounds</summary>
var rendererBounds = slotObject.GetColliderBounds();
collider.center = transform.InverseTransformPoint(rendererBounds.center);

Vector3 localSize = new Vector3(
    rendererBounds.size.x / transform.lossyScale.x,
    rendererBounds.size.y / transform.lossyScale.y,
    rendererBounds.size.z / transform.lossyScale.z
);
collider.size = localSize;

```

```csharp
/// <summary>处理车位点击选择（把屏幕点击位置转成一条射线）</summary>
void HandleSelection(Vector2 screenPos)
{
    // 第一步：把屏幕点击位置转成一条射线
    Ray ray = Camera.ScreenPointToRay(screenPos);
    
    // 第二步：检测射线击中了哪个车位
    if (CheckSlotHit(ray, out SlotObject slot))
    {
        // 处理车位选择逻辑
    }
}

/// <summary>检测射线是否与车位碰撞</summary>
private bool CheckSlotHit(Ray ray, out SlotObject slot)
{
    slot = null;
    foreach (SlotObject s in slots)
    {
        var bounds = s.GetColliderBounds();
        if (bounds != null && bounds.IntersectRay(ray))
        {
            slot = s;
        }
    }
    return slot != null;
}

```

---

## 结语

从四个角点到可交互的停车位，整个开发链路其实是智驾SR开发的一个典型缩影：输入简单，但工程落地细节极多——协议约定的微小差异，会传导成几何、渲染、交互全链路的问题；而我们做的所有工程优化，本质都是在**效果还原**和**运行性能**之间找平衡。