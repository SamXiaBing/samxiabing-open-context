---
title: "座舱3D HMI性能：Instantiate 太多卡成 PPT？试试分帧加载"
date: 2026-08-13
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> 上一篇讲了把 CPU 的网格生成工作交给 GPU ComputeShader 的思路，但有些时候即便是把复杂的数据处理交给了GPU，仍然会面临要创建的物体太多，导致对画面的流畅性造成影响。比如记忆泊车的建图结果过于复杂的时候。

当咱们已经尝试简化功能需求，并且在创建物体的时候也用上了Compute Shader，但仍然碰到创建的任务过重带来的卡顿问题时，也许可以考虑一下分帧加载：把一帧干完的事改成每帧干一点。

---

# 问题表现

测试反馈：

> "记忆泊车建图完成后切到全览，相机推过去的时候画面一卡一卡的。"

打开 Profiler，FPS的尖峰时刻，总是能看到 `GameObject.Instantiate` 预制体实例化在占用大量时间，伴随它的，也有相机动画的blend处理 `CinemachineBrain.Update` 和与mesh的创建相关的  `Mesh.RecalculateBounds`等。

---

# 分帧的本质

分帧的本质就是**给主线程每帧一个时间预算（或是任务数的预算），预算用完就 yield**（这一帧不处理了，让引擎runtime的生命周期往下走，直到下一帧的处理再进来）**，把剩余工作留到下一帧。**

这是**单线程内的分时复用**。Unity的协程 `yield return null` 语义是"本帧到这里为止，下一帧从 yield 后面继续"。每帧做一些工作。在Unreal 5 中可以使用 TCoroutine 在需要等帧的时候 co_await。

*[配图见公众号原文]*

在使用中，我遇到过有两个场景都需要分帧，但因为业务特征不同，各自写了一套处理。

---

# 场景一：地图瓦片加载器

SR 的高精地图开发中，依赖瓦片机制。车快要开到新的区域，就得加载一个新的地块数据，每个数据块包含道路面、车道线、箭头、楼房等多种数据。如果一次性全部 `Instantiate` ，加载地图就可能会出现卡顿。

这里同时使用生成数和处理时间两个标准来分帧，示意代码：

```csharp
// 每帧最多可用的时间（毫秒）
public static int timeBudget = 3;
// 每帧最多处理的对象数量
public static int countBudget = 10;

IEnumerator LoadGameObjects()
{
    while (true)
    {
        float startTime = Time.realtimeSinceStartup;
        int count = 0;

        // 双条件：时间没超 AND 数量没超，才继续处理
        while (loadItems.Count > 0
               && Time.realtimeSinceStartup - startTime < timeBudget / 1000f
               && count < countBudget)
        {
            LoadTask item = loadItems.First.Value;
            loadItems.RemoveFirst();

            GameObject go = MeshUtil.CreateTileGameobject(item.tileData);
            item.onComplete?.Invoke(go);
            count++;
        }

        if (loadItems.Count > 0)
            yield return null;                              // 还有活，下帧继续
        else
            yield return new WaitUntil(() => loadItems.Count > 0);  // 没活了，等新任务
    }
}
```

这样就同时遏制住了生成数量多和生成数据大两种情况。

> 另外，在这个情景中，还可以针对不同的生成物进行优先级的分档。在给 `LinkedList<LoadTask> loadItems`  添加任务的同时，去维护一个`PriorityQueue<LoadTask>`

---

# 场景二：建图结果全览

记忆泊车建图完成，服务端推建图数据下来，包含多楼层的车位、道路、障碍、轨迹线数据。我们收到后要遍历所有楼层，逐个生成 GameObject，算 bounds，最后驱动全览相机动画。

这个场景属于事件型突发的场景，不会取消，没有创建优先级分档，特点在于**构建完之后要求相机动画不能卡。**

## 逐楼层分帧构建

确认需要重建后，启动异步协程：

```csharp

[SerializeField] private bool enableAsyncBuild = true;       // 分帧开关
[SerializeField] private float frameBudgetMs = 6f;          // 每帧预算 6ms
[SerializeField] private int yieldEveryFloors = 1;           // 每处理 N 层 yield

private int mapBuildVersion;  // 版本号，防旧协程数据污染

void HandleMapData(string mapId, MapData mapData)
{
    // ... 指纹去重 ...

    if (enableAsyncBuild)
    {
        mapBuildVersion++;  // 新版本，旧协程会自动退出
        int buildVersion = mapBuildVersion;
        buildCoroutine = StartCoroutine(
            ProcessAllFloorsAsync(buildVersion, mapId, fingerprint, tHandleStart));
    }
    else
    {
        ProcessAllFloors();  // 同步构建（调试用）
        FinalizeAfterBuild(mapId, fingerprint, tHandleStart);
    }
}
```

> 关于 buildVersion  服务端可能先推了一个包，还在分帧构建中（协程 yield 在某一层中间），又推了第二个包。如果不处理，旧协程会继续跑，和新协程同时往列表里写数据，造成污染。因此每次 yield 回来检查版本号，不匹配就要终止，见下面代码。

协程主体示意代码如下：

```csharp
IEnumerator ProcessAllFloorsAsync(int buildVersion)
{
    float frameStart = Time.realtimeSinceStartup;

    for (int i = 0; i < mapData.Floor.Count; i++)
    {
        if (buildVersion != mapBuildVersion) yield break;

        // 处理本层：车位 / 道路 / 障碍 / 轨迹
        ProcessFloor(mapData.Floor[i]);

        // 楼层间隔 或 时间预算，谁先到谁让出
        bool hitFloor  = (i + 1) % yieldEveryFloors == 0;
        bool hitBudget = (Time.realtimeSinceStartup - frameStart) * 1000f >= frameBudgetMs;
        if (hitFloor || hitBudget)
        {
            yield return null;
            frameStart = Time.realtimeSinceStartup;
        }
    }

    // 收尾：合并轨迹、更新目标车位
    FinalizeBuild();
}
```

这里的双限制条件，改成了时间+楼层。其他并没有什么新意。

---

# 结语

写到这里回头看，分帧加载其实不是什么高深技术，更像是一种平衡取舍的思维。做应用开发总是会在前中期碰到一些什么东西都想往上加，往外显的时候。这时候就不仅要思考怎么干得更快，还得思考是不是非得一帧干完？不过分帧这种处理方式也提升了代码复杂度，可能因此新增状态和数据管理上的bug。