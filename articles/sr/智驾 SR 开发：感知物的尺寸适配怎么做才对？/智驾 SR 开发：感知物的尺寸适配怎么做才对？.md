---
title: "智驾 SR 开发：感知物的尺寸适配怎么做才对？"
date: 2026-08-20
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> 今天翻工程，看到减速带的时候，想到以前因为减速带的长短不一、宽高比各异还专门有做过缩放处理。于是就想到，也许可以针对所有这类因为感知数据变化，而对物体形状有收缩拉伸需求的情况做个处理方式的总结。从这个角度出发，也许会是个有趣的话题。

SR感知数据中，我们会接触到减速带、车位面、车位框、斑马线等，这些感知物体与其他感知物有一个不同的地方，就是它们是需要根据数据去做缩放的。然而，感知车辆、锥形桶、行人并不要求根据感知的尺寸（若有）去变化它们的大小。

但美术制作上，咱们不可能为不同的尺寸去准备多份素材。所以局面往往是，同一份素材，素材的形态可以调整，但是最终要跟着感知数据变长、变宽、变方向。

下文将列举一些曾经接触过的案例。

![1](./1.png)

---

# 1. 模块拼接

这是看上去最"累"的一种处理方案，适合**物体自身是由规则的、标准的单元件组成的情况**。减速带本身就是一节一节黑黄相间，所以干脆把单节做成一个固定模块，按感知的长度算"要几节"，一节节并排拼出来：

*[配图见公众号原文]*

关键要注意去**复用**，因为减速带的位置和长度数据每一帧都可能变，如果每帧重新创建一排物体然后再销毁旧的，GC 和实例化开销都很大。所以这里可以用上之前写的对象池来获取单元物体。

示意代码：

```csharp
// 感知宽度（毫米转米）除以单节宽度，向下取整得到节数
float width = SizeX * 0.001f;
int count = Mathf.FloorToInt(width / _moduleWidth);   // 0.25m 一节

// 居中起算、交替黑色和黄色两种单元物体
float startX = -(width / 2) + (_moduleWidth / 2);
for (int i = 0; i < count; i++)
{
    var go = _modules.Count <= i ? NewModule() : _modules[i];  // 不够才实例化
    go.transform.localPosition = new Vector3(startX + i * _moduleWidth, 0, 0);
    go.GetComponent<Renderer>().material.color = (i % 2 == 0) ? Color.black : Color.yellow;
    go.SetActive(true);
}

```

---

# 2. 动态 Mesh 生成

比模块拼接更通用的是**直接根据数据把网格建出来**，适合形状无法规则化，同时纹理又几乎没有图像内容变化的物体。这种处理方式常见于车位的Base面，车道线、引导线这类物体上。

**车位**

车位至少会使用一个基础面片去表达，它有的时候是灰色的，有的时候是淡蓝色的。但它不会是条纹的，所以拉伸对它的视觉影响是可以忽略的。总的来说，我们要解决三类问题（1）车位长宽有明显区别，有的6米乘2.5米，有的可能12米乘4米等等。（2）同时适配横向车位和纵向车位，数据的含义是“进深”和“面宽”，但是物体的Scale没有这个语义。（3）斜列车位，这就不可能用一个物体去变化Scale可以解决了。

*[配图见公众号原文]*

所以就可以依靠感知数据给到的4个角点的坐标，去绘制一个简单的Mesh，然后使用上纯色半透明的材质，这样就总能和实际感知一致。这种基础面片是不管车位类型的，也不管开口方向。

> 这里得说下车头车尾泊入图，在基础面片之上还有这个图层需要表现，但是这图一旦拉伸，肯定就不会是原图的样式。所以它是要根据角点的排序创建Mesh，保证UV 0到1的方向正确的基础上，根据车位类型使用贴图。

**车道线/引导线/停止线**

简单说就是网格生成器把点数组向两侧扩宽成一个带状 Mesh，并**按沿路累计弧长铺 UV**。这一类如何创建之前文章写过了，这里就不赘述细节了。

---

# 3. 缩放

虽然缩放看上去就是那个最“笨”，最“暴力”的方法，但是我发现它还是会被用到的，它适用于**变形根本不重要**的情况。比如可以接受斜列时接受矩形旋转即可的车位，还有路标(Roadmark)。

**车位面片**

拿到感知角点后：

1. **算宽长**：宽度=角点到对边的垂直距离，长度=两对边平均
2. **判方向**：`width > length` 是横向车位，否则纵向
3. **缩放 + 旋转**：横向就 `scale=(length/2.5, 1, width/5)` 且转 `-90°`；纵向就 `scale=(width/2.5, 1, length/5)` 不旋转。不管斜列，直接矩形。

示意代码：

```csharp
bool isHorizontal = width > length;                 // 只要横 / 纵二选一
Vector3 s;
if (isHorizontal) { s = new Vector3(length/2.5f, 1, width/5f); rotY = -90f; }
else              { s = new Vector3(width/2.5f, 1, length/5f); rotY = 0f;  }
slotBase.localScale  = s;                            // 面片本地只负责长条方向
slotBase.localEulerAngles = new Vector3(0, rotY, 0);
// 斜列：父节点 rotation = 感知角点 Atan2 朝向，面片不管斜角，只管横竖
transform.rotation = Quaternion.Euler(0, Atan2Angle(corners), 0);

```

**路标 Roadmark**

路面标识（直行 / 转弯箭头 / 掉头标等）为什么也"敢"用缩放？因为这类东西在现实世界里就是**标准尺寸**的，很少会出现非标的路标图案。所以只要素材图是按照国家标准的去画的，只要把它缩放到感知的尺度就可以了

> 甚至后来连缩放也不做了，如代码所示。

![fig_route3_roadmark](./fig_route3_roadmark.png)

```csharp
// 感知下发的类型 → 选素材图 + 定缩放比（每种类型一个固定比例）
var type = (RoadmarkType)data.roadMarkTypeSeN;
Vector3 scale = new Vector3(1, 1, 4);                 // 默认
switch (type)
{
    case RoadmarkType.LEFT_RIGHT_TURN:   scale = new Vector3(1.8f, 1, 4); break;
    case RoadmarkType.STRAIGHT_LEFT_TURN:scale = new Vector3(2, 1, 4);     break;
    case RoadmarkType.U_TURN:            scale = new Vector3(1.5f, 1, 4); break;
}
if (!_textures.TryGetValue(type.ToString(), out Texture tex)) return;  // 素材要能查到

// 位置 = 感知角点中心，朝向 = 感知方向
Vector3 pos = (corners[0] + corners[1] + corners[2] + corners[3]) / 4;
Quaternion rot = Quaternion.Euler(0, -data.heading * 0.0573f - 90, 0);

go.transform.SetPositionAndRotation(pos, rot);
go.transform.localScale = scale;              // 缩放比来自类型，不来自尺寸
mat.SetTexture("_BaseMap", tex);
```

---

## 组合用法：车位框 = 角点定位 + 边条 Scale

我遇到过一类车位，这个车位它要求绘制一圈框体，是实实在在的3D物体呈现出来的边框，同时它要能表现出开口方向。这个时候我用的就是组合的方法了。因为它既不像面片那样只要一个 Quad，也不像车道线那样重画整条 Mesh，而是把**拼接（角点的物体）**和 **缩放（边条）**结合在一起用。

> 预制体的层级编排是：车位根节点挂一个边框管理组件，底下管 4 个角点对象 + 4 条边对象。

![fig_route5_slotframe](./fig_route5_slotframe.png)

每帧拿到感知角点后：**算宽长** -> **摆角点（"拼"的部分）**：把 4 个角点对象放到标准矩形的四角 `(±width/2, ±length/2)`，角点物体本身不缩放，保持固定大小 -> **拉边条（"缩放"的部分）**：每条边用 `localScale` 按 `(width - 2*角点半径) * 缩放因子` 动态拉长。

示意代码：

```csharp
// 底边：居中摆位，宽度方向按 (感知宽度 - 2*角点半径) * 缩放因子 拉伸
Edge_32.localPosition = new Vector3(0, 0, -length/2f);
Edge_32.localScale    = new Vector3((width - cornerR*2f) * H_STICK_PARAM, 1, 1);

// 左右边：居中摆位，长度方向同理拉伸
Edge_30.localPosition = new Vector3(width/2f, 0, 0);
Edge_30.localScale    = new Vector3(1, 1, (length - cornerR*2f) * V_STICK_PARAM);

```

---

# 4. UV 平铺 / Tiling

最后一种最省性能了，就依靠材质本身的能力就好了，处理的场景和方法1的拼接很像，适用于**可以把"重复"放进 UV 里**。比如斑马线的白条间距、车道线的虚线密度，这些都是规则重复的纹理，让 UV 按物理长度平铺，模型本身线性缩放，重复单元自动被成倍数铺满，不用改Mesh和材质实例。

![fig_route4_uvtiling](./fig_route4_uvtiling.png)

控制的是材质属性 `_MainTexST`：

- `y`：沿模型长度方向平铺 N 次，间距不变。
- `x`：沿宽度方向平铺。
- `Offset`：移动纹理起点，比如要做虚线的偏移运动。

```
// _MainTex_ST.x = Tiling X, _MainTex_ST.y = Tiling Y
// _MainTex_ST.z = Offset X,  _MainTex_ST.w = Offset Y
float4 _MainTex_ST;

float2 transformedUV = uv.xy * _MainTex_ST.xy + _MainTex_ST.zw;
half4 color = tex2D(_MainTex, transformedUV);
```

---

## 结语

以上内容，体现出来的是面对一个个细小的问题，使用巧妙的工程方法（拆解、妥协...）去满足需求的过程。希望你也会觉得有趣，并在以后面对类似问题的时候胸有成竹。

