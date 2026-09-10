---
title: "Cockpit 3D HMI Performance: Too Many Instantiates Stuttering Like a Slideshow? Try Frame-Spread Loading"
lang: en
date: 2026-08-17
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article covered the idea of handing mesh generation from the CPU over to GPU ComputeShaders. But sometimes, even with the complex data processing delegated to the GPU, you still face a situation where too many objects need to be created, hurting frame smoothness — for example, when a memory-parking mapping result is overly complex.

When you've already tried simplifying the feature requirements and used Compute Shaders for object creation, but still hit stuttering caused by overly heavy creation tasks, it may be time to consider frame-spread loading: turn "finish it all in one frame" into "do a little each frame".

---

# The symptom

Tester feedback:

> "After memory parking finishes mapping and we switch to the overview, the picture stutters along as the camera pushes in."

Open the Profiler, and at the FPS spike moments you'll always see `GameObject.Instantiate` prefab instantiation eating up large amounts of time — accompanied by the camera animation blending in `CinemachineBrain.Update` and mesh-creation-related calls like `Mesh.RecalculateBounds`.

---

# The essence of frame-spreading

The essence of frame-spreading is **giving the main thread a per-frame time budget (or a task-count budget); once the budget is used up, yield** (this frame stops processing — the engine runtime's lifecycle moves on until the next frame's processing comes back in) **and leave the remaining work for the next frame.**

This is **time-slicing within a single thread**. Unity's coroutine `yield return null` means "that's it for this frame; next frame, resume right after the yield". Do a bit of work each frame. In Unreal 5, you can use TCoroutine and co_await when you need to wait for a frame.

*[Figures omitted; see the original WeChat article]*

In practice, I've run into two scenarios that both needed frame-spreading, but because their business characteristics differ, I wrote a separate handler for each.

---

# Scenario 1: the map tile loader

HD map development for SR relies on a tile mechanism. As the car approaches a new area, a new chunk of tile data has to be loaded; each data block contains road surfaces, lane lines, arrows, buildings, and other data types. If everything is `Instantiate`-ed at once, loading the map can hitch.

Here, both criteria — spawn count and processing time — are used for frame-spreading. Illustrative code:

```csharp
// Maximum time available per frame (ms)
public static int timeBudget = 3;
// Maximum number of objects processed per frame
public static int countBudget = 10;

IEnumerator LoadGameObjects()
{
    while (true)
    {
        float startTime = Time.realtimeSinceStartup;
        int count = 0;

        // Two conditions: time not exceeded AND count not exceeded — only then keep processing
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
            yield return null;                              // work remains; continue next frame
        else
            yield return new WaitUntil(() => loadItems.Count > 0);  // no work left; wait for new tasks
    }
}
```

This reins in both cases at once: too many objects to spawn, and too much data per spawn.

> Also, in this scenario, you can tier the different spawnables by priority: while adding tasks to the `LinkedList<LoadTask> loadItems`, maintain a `PriorityQueue<LoadTask>` as well.

---

# Scenario 2: the mapping-result overview

When memory parking finishes mapping, the server pushes the mapping data down: parking spaces, roads, obstacles, and trajectory lines across multiple floors. On receipt, we need to traverse every floor, generate the GameObjects one by one, compute bounds, and finally drive the overview camera animation.

This scenario is an event-driven burst: it isn't cancelled, there's no creation-priority tiering, and its defining requirement is **that the camera animation must not stutter once the build completes.**

## Floor-by-floor frame-spread building

Once a rebuild is confirmed, start the async coroutine:

```csharp

[SerializeField] private bool enableAsyncBuild = true;       // frame-spreading switch
[SerializeField] private float frameBudgetMs = 6f;          // 6ms budget per frame
[SerializeField] private int yieldEveryFloors = 1;           // yield every N floors processed

private int mapBuildVersion;  // version number, to keep stale coroutine data from polluting

void HandleMapData(string mapId, MapData mapData)
{
    // ... fingerprint dedup ...

    if (enableAsyncBuild)
    {
        mapBuildVersion++;  // new version; the old coroutine will exit on its own
        int buildVersion = mapBuildVersion;
        buildCoroutine = StartCoroutine(
            ProcessAllFloorsAsync(buildVersion, mapId, fingerprint, tHandleStart));
    }
    else
    {
        ProcessAllFloors();  // synchronous build (for debugging)
        FinalizeAfterBuild(mapId, fingerprint, tHandleStart);
    }
}
```

> About buildVersion: the server may push one packet, and while the frame-spread build is still running (the coroutine yielded in the middle of some floor), push a second packet. If this isn't handled, the old coroutine keeps running and writes into the list at the same time as the new one, causing pollution. So on every yield return, check the version number; if it doesn't match, terminate — see the code below.

The coroutine body, in illustrative code:

```csharp
IEnumerator ProcessAllFloorsAsync(int buildVersion)
{
    float frameStart = Time.realtimeSinceStartup;

    for (int i = 0; i < mapData.Floor.Count; i++)
    {
        if (buildVersion != mapBuildVersion) yield break;

        // Process this floor: parking spaces / roads / obstacles / trajectories
        ProcessFloor(mapData.Floor[i]);

        // Floor interval OR time budget — whichever hits first yields
        bool hitFloor  = (i + 1) % yieldEveryFloors == 0;
        bool hitBudget = (Time.realtimeSinceStartup - frameStart) * 1000f >= frameBudgetMs;
        if (hitFloor || hitBudget)
        {
            yield return null;
            frameStart = Time.realtimeSinceStartup;
        }
    }

    // Wrap-up: merge trajectories, update the target parking space
    FinalizeBuild();
}
```

The dual constraint here was changed to time + floors. Nothing else particularly novel.

---

# Closing thoughts

Looking back from here, frame-spread loading isn't some profound technique — it's more a mindset of balancing trade-offs. In application development, the early and middle stages always bring moments when people want to add everything and display everything. At times like that, you have to think not only about how to work faster, but also whether it truly has to be finished in a single frame. That said, frame-spreading does raise code complexity, and may introduce new bugs around state and data management.
