---
title: "Cockpit 3D HMI Performance: LINQ Feels Great to Write, the GC Ends Up in the Crematorium"
lang: en
date: 2026-07-20
series: perf
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article shared a scheme for triggering performance report capture with the 3D engine's own tooling at runtime, and noted that concrete data would be needed to analyze and solve problems case by case. So this article starts with the first case: periodic frame drops / stuttering.

# The symptom

Tester feedback:

> "Mostly it runs smoothly, but every once in a while it hitches for a moment (or the FPS shown in the corner of the screen suddenly drops), then immediately recovers."

---

# CPU Usage

Open the automatically captured Profiler data file and look at the frame time curve first. The shape probably looks something like this:

*[Figures omitted; see the original WeChat article]*

- Normal frames: around 16ms, running at 60fps.
- Abnormal frames: around 50ms, dropping to 20fps — spiky, shooting up fast and falling back just as fast.
- Timing of the anomalies: cross-checking against runtime observation, they're fairly regular — roughly every few seconds.

This is **periodic + immediate recovery**, which pretty much pins down the direction: somewhere on a high-frequency code path, managed objects with extremely short lifetimes are being created on the managed heap continuously. They aren't collected immediately, but they keep pushing up managed heap usage, eventually triggering periodic GC collections.

---

# Hierarchy

To confirm this direction, the next step is switching to the Hierarchy view:

Expand `PlayerLoop` → `Update.ScriptRunBehaviourUpdate`, and look at the **Self ms** and **GC Alloc** columns together:

*[Figures omitted; see the original WeChat article]*

1. `GC.Collect` will eat into Self ms.
2. Some business path keeps allocating hundreds of KB to several MB.
3. The allocation stacks most often land on `Enumerable.Select…` / `List.ToArray`.

> Prerequisites:
>
> ![image](./image.png)

At this point, it's time to dig into the code being pointed at — go find the List-related operations.

---

# Code analysis

The code located in the project, at the point where the lane-line perception point set undergoes a coordinate system conversion:

```csharp
// LaneDataProcessor.cs
laneline_piece_points[i] = LanelinePiece.PointsCurve.Points
    .Select(point => new UnityEngine.Vector3(-point.Y, point.Z, point.X))
    .ToList()
    .ToArray();
```

This pattern appears in more than one place in the same file — there's also the variant that does Select + ToList to build a temporary List, then AddRange into the target collection. The intent in all of these is the same: converting points from the perception coordinate system into Vector3. The problem is that this is a very high-frequency data processing path, and when there are many Piece segments, it generates a large number of temporary variables.

All we wanted in the end was a Vector3 array, but the `Select(...).ToList().ToArray()` chain creates at least three heap objects: the WhereSelect iterator, the intermediate List<Vector3> (possibly with capacity-growth waste on top), and the final array. Even simplified to Select(...).ToArray(), the iterator and result array allocations are still there.

*[Figures omitted; see the original WeChat article]*

# The fix

So on hot paths, stop using chained allocations like `Select().ToList().ToArray()` — use a for loop + a reusable buffer:

```csharp
int ConvertPointsNonAlloc(IList<ProtoVec3> src, ref Vector3[] buffer)
{
    int n = src.Count;
    if (buffer == null || buffer.Length < n)
        buffer = new Vector3[Mathf.NextPowerOfTwo(n)];
    for (int i = 0; i < n; i++)
    {
        var p = src[i];
        buffer[i] = new Vector3(-p.Y, p.Z, p.X);
    }
    return n;
}
```

After switching to a for loop that writes Vector3 directly into the reusable buffer, we no longer new up an iterator and a temporary List just as a "relay", and the short-lived managed objects are gone. Convention: downstream code should consume only the return value `n` (the valid length), never `buffer.Length`. One more note: this buffer only grows, never shrinks — after an occasional extra-large point set, steady-state memory stays elevated, so long-running projects need to watch the peak.

---

# Problems of the same family

### 1) Meaningless copies

`ToArray()` / `ToList()`

```csharp
// Illustration: we already have a List, yet every call copies out a new array for the downstream
mesh.SetVertices(tempList.ToArray());

```

If the downstream API has a `List<T>` / `NativeArray` overload, pass the List directly.

### 2) String interpolation and Format

```csharp
Log.Info($"lane={id} piece={i} count={count}");

string pieceID = string.Format("{0}_{1}", id, i);
```

Strings in C# are immutable: every Format / $"{id}_{i}" news up a new string object on the heap. If the string is only used for logging or as a temporary key, nothing references it after use — it becomes short-lived garbage and contributes to GC Alloc all the same. It's usually not the main factor, so skip the concatenation whenever you can. If it's logging, turn that print off in release builds.

### 3) Hidden allocations in APIs


| API | What happens |
| ------------------------------------------ | ------------------------------------------ |
| `renderer.material` | Covered in the next article |
| `GetComponents<T>()` / `FindObjectsOfType` | The parameterless overloads allocate new arrays; prefer the allocation-free `GetComponents(List)` overload |
| `new Mesh()` / per-frame `mesh.vertices = ...` | One copy from managed→native; assign less, prefer `SetVertices` |


---

# Closing thoughts

The problem isn't LINQ itself — it's chained heap allocations on hot paths. "Elegance" (chaining) in the wrong places may turn into "misery" (overtime) later on.
