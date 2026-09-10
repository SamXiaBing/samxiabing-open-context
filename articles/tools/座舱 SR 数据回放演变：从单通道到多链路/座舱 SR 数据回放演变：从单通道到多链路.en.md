---
title: "Cockpit SR Data Replay Evolution: From Single Channel to Multi-Link"
lang: en
date: 2026-06-29
series: tools
no: 
status: published
visibility: public
wechat_url: ""
---

> I previously wrote an article sharing the SR data replay tool: [Cockpit SR Data Replay Tool: Complete Design from Recording to Playback](https://www.xxx.com/). It covered specifically how SR perception data gets recorded and how the recorded files are used for simulated sending. This article extends that discussion at the design level.

Lately I keep getting bothered by mixed-type bugs, like this one: when the gear shifts to R, the car-model launcher's camera pulls up behind the ego vehicle and a full-screen AVM picture appears. When the gear shifts back to D, the AVM picture disappears immediately, and while the car-model launcher's camera returns to the eye-level ego view, a jitter occurs — and the perceived vehicle next to the ego car occludes it (no transparency treatment applied).

One look at this bug and you can see I can't reproduce it inside the editor:

1. Gear data travels over JNI; the signal logs are recorded in a logcat file, and the editor has a dedicated logcat signal-log replay tool.
2. Perception data is recorded in SR recording files, replayed with the dedicated SR replay tool.

> And 3: AVM goes full screen, the 3D thread gets Paused; AVM disappears, the 3D thread Resumes — that's in logcat too, but at the time there was no tool to extract and simulate it.

In other words, when some SR bugs are coupled with shared-memory data, vehicle-body signals, or cloud data signals (like car-skin data), having our simulation tools separated makes bugs harder to reproduce and slows down fixing.

So this article attempts to sort out an approach to solving this problem.

---

## The Problem | Limits of the Single Link

In real-world scenarios, the cockpit SR app receives and processes multiple types of data streams:

- **Middleware**: gear, body signals such as the "four doors and two lids", and cloud data come into 3D through the JNI channel, with adb logcat prints in the message-handling module.
- **Mapping results, OCC**: come into 3D through the shared-memory (MMKV) channel; either only some key information got printed to logcat without the full data body, or they were recorded only in the save/replay path written specifically for MMKV.
- **Perception & planning data**: data subscribed via FDBus — the main data SR displays. In the previous article, these were stored to file through the Android-side FileLogger class.

If each link runs its own separate pipeline, **maintenance costs are high, timestamps aren't unified, and it directly inflates the complexity of the replay tools**. Meanwhile, the PC-side replay tool is limited in which communication links it can simulate — for example, it can't simulate the JNI link.

So the natural conclusion: since data sources are scattered across different links, we need one unified data-ingest entry and one unified simulated-sending exit.

---

## Design Approach

1. No matter where the data comes from (shared memory, JNI, Socket, websocket...), do a unified signal aggregation on the Android side. Each communication channel has its own collector, but they all feed their data into the same aggregator.
2. During replay, don't simulate the communication links; instead, dispatch the data directly inside the editor to the corresponding parser by channel type.

![Figure 1](./图1.png)

**The editor panel is the preferred choice**, because it requires simulating no communication links — only file IO. Parsing logic is 100% reused, and the PC side can do it without depending on any hardware or Android environment. The drawback is obvious too, just as the previous article said: problems in the links themselves never surface — payload-size issues, efficiency/latency issues, and so on.

---

## The Recording Side

Design one unified recording entry on the Android side. Each record contains: channel type, timestamp, raw binary data.

### **Channel Definition**

```csharp
/// <summary>
/// Data channel enum, used to distinguish data sources across communication links
/// </summary>
public enum DataChannel : uint
{
    /// <summary>
    /// Shared-memory channel, for high-frequency data such as ADAS perception
    /// </summary>
    SharedMemory = 1,
    
    /// <summary>
    /// JNI bridge channel, for middleware data such as vehicle-body signals
    /// </summary>
    JNI = 2,
    
    /// <summary>
    /// Socket channel, for business data transfer
    /// </summary>
    Socket = 3,
    
    /// <summary>
    /// WebSocket channel, for custom protocols or real-time interactive data
    /// </summary>
    WebSocket = 4
}
```

### **Protocol Format**

```
[4-byte channel enum][8-byte timestamp][4-byte data length][N-byte data]
```

### **File Structure**

Building on the previous article's code, add a channel field to the frame header:

```
[FileHeader: "REC"(3B) + version(4B) + startTimestamp(8B)]
[Frame0: channel(4B) + timestamp(8B) + length(4B) + data]
[Frame1: channel(4B) + timestamp(8B) + length(4B) + data]
...
```

### **Frame Index Structure**

```csharp
/// <summary>
/// Frame index structure, containing only metadata, not the actual data
/// </summary>
public struct FrameIndex
{
    /// <summary>
    /// Data channel type
    /// </summary>
    public DataChannel Channel;
    
    /// <summary>
    /// Frame timestamp
    /// </summary>
    public DateTime Timestamp;
    
    /// <summary>
    /// Offset of the frame data within the file
    /// </summary>
    public long Position;
    
    /// <summary>
    /// Frame data length
    /// </summary>
    public long DataLength;
}
```

### The Recorder

Based on the previous code, this version just adds one more field to the Record method — the channel:

```
writer.Write((uint)channel);  // channel type, 4 bytes
```

Adjust the stitched-together positions and sizes accordingly.

The class itself doesn't change much; the main point is to use it for recording before any channel performs the "send" action toward 3D.

### The Collectors

Collectors are responsible for fetching data from the different sources — they are the data's entry point. Once data arrives, they call recorder.Record() to hand it to the recorder. For example, the **shared-memory collector**:

```csharp
// Recorder: writes to the file uniformly
private readonly MultiChannelRecorder recorder = new MultiChannelRecorder("recording.rec");

// Collector: fetches data from different channels and calls the recorder
public class SharedMemoryCollector
{
    private readonly MultiChannelRecorder recorder;
    
    public void OnDataReceived(byte[] data)
    {
        recorder.Record(DataChannel.SharedMemory, data);
    }
}
```

---

## The Replay Tool

### Index Scanning

Add the channel field on top of the single-link index.

While scanning frames when reading the file, build a Dictionary<DataChannel, List<FrameIndex>> to support fast per-channel lookup.

### Channel Dispatch

During replay, communication links are no longer simulated; data is dispatched directly inside the editor. Define an IDataParser interface, with each channel implementing its own parser:

```
public interface IDataParser
{
    void Parse(byte[] data, long timestamp);
}
```

MultiChannelReplayer looks up the corresponding parser by channel type and calls it.

### Timeline Synchronization

All channels use one unified clock source (UTC milliseconds); during replay, data is sorted by timestamp and dispatched in order.

---

## Extending It

Suppose you need to add a new link in the future (say MQTT). You'd need to:

1. Add a new type to the `DataChannel` enum
2. Write a collector that calls `MultiChannelRecorder.Record()`
3. Write a parser implementing the `IDataParser` interface
4. Register it in the replay engine's `parsers` dictionary

None of the business code, recording logic, or replay logic needs to change.

---

## Closing Thoughts

Software development sometimes hits those "**oops, I didn't think of that at the time**" moments: I built an SR replay tool without realizing that what we'd ultimately need wasn't an SR replay tool, but an all-data simulation replay tool.

But there's no need for self-blame, I think. What we build is, by nature, adapting to change and chasing requirements. What's worth scrutinizing is whether the design we made back then left an entry point for change — so that when you eventually come back to modify it, you don't get that powerless feeling of "**it can't be changed**".
