---
title: "Intelligent Driving SR Development: The Multiple Identities of a Light Strip"
date: 2026-09-03
series: sr
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered perceived-object size fitting; this one keeps digging through the details. When doing body-state synchronization for the vehicle model, you eventually reach the lamps—and those are genuinely troublesome things. A full-width light strip can be a position light, or a turn signal with a sweeping-light effect, and even the brake light may reuse part of it. The same light strip carries at least two identities. What clever tricks does its implementation involve?

![1](./1.png)

# 1. Reused Lamps

First, let me list the reuse scenarios that actually exist in the project. Different vehicle models have different lamp designs, so the reuse combinations may differ.

- The daytime running light, also called the front position light, shares the same set of LED beads with the front turn signal. With the front position light on, it's a steady white; when signaling, it switches to a yellow flowing light.
- The rear position light and the brake light are reused. Press the brake, and the taillight switches from ordinary dark red to a brighter red.
- The rear position light and the rear turn signal are reused. When signaling, the strip goes from full-length red to a yellow flowing-light effect on one of its segments, as shown in the diagram at the start of this article.

All three cases have existed before. The lamps are reused, which means the same mesh (possibly several meshes) must respond to multiple signals, and different signals require the material corresponding to this mesh to present different rendering states. So the first thing to expand on is how to define and control this at the logic level.

# 2. CarLightData and Signal Priority

The core idea is to attach a set of data entries to each light strip (i.e. each lamp object); each entry describes one identity. When signals change, arbitration by priority decides the winner that should currently be displayed.

## 2.1 Data Structure

Each light strip holds a group of CarLightData—mostly a single instance; reused lamps get multiple instances configured.

```csharp
public class CarLightData
{
    public LightZone lightZone;        // light zone, e.g. rear position light / brake light / turn signal
    [ColorUsage(true, true)]
    public Color lightColor;           // HDR emission color; brightness can exceed 1
    public int priority;               // priority
    public int lightValue;             // vehicle-control signal value
    public bool IsShow => lightValue == 1;
}

```

`lightZone` is the project's enum definition of the different light zones.

`lightColor` uses an HDR color to work with the Bloom post-processing for a glow effect.

Later, `priority`—plus special logic where necessary—will be used to control `lightValue`.

## 2.2 Signal Priority

At initialization, these lightDatas are sorted once.

```csharp
// Sort once at Init; higher priority first
Array.Sort(lightDatas, (p1, p2) =>
{
    if (p1.priority > p2.priority) return -1;
    if (p1.priority < p2.priority) return 1;
    return 0;
});

```

After sorting, handling each signal change only requires "finding the first lit light from the front":

```csharp
protected virtual void OnLightValueChanged(CarLightData data, int lightValue)
{
    data.lightValue = lightValue;
    var firstLight = FirstLight ?? data;   // FirstLight = lightDatas.FirstOrDefault(x => x.IsShow)
    curMat.SetColor(EmissionColorId, firstLight.lightColor);   // the winner's color directly overrides
    if (firstLight == data)
        firstLight.CarLightStyle.OnLightSwitch(curMat, IsEmission);
    else
        data.CarLightStyle.ResetProperty(curMat);
}

```

When three signals light up simultaneously, the array is sorted by priority in descending order, with the brake light first; the turn signal and position light are both instantly overridden, and the Reset operation of the Style corresponding to each of their two zones is executed.

> The Reset operation is necessary. Suppose the turn signal's flowing animation has swept halfway and the brake-light signal arrives—the turn signal's animation must be killed. If you don't kill it, parameter pollution may be left on the material.
>
> One more note. On some vehicle models, the light-strip material in the off state isn't pure black—the base color may be a dark red with a bit of reflector panel. This needs to be recorded at initialization and restored in ResetProperty.

## 2.3 About the Style: CarLightStyle

CarLightStyle: each type of lamp corresponds to one style. The so-called style here means overriding the on/off animation logic belonging to this type of lamp, plus the cleanup work needed for resetting.

```csharp
// Assign the style by light zone
protected virtual ICarLightStyle GetCarLightStyle(LightZone zone)
{
    if (zone == LightZone.BackLeftTurnSignal)  return BackTurnSignalStyle;   // body-segment turn signal
    if (zone == LightZone.DoorLeftTurnSignal)  return DoorTurnSignalStyle;   // door-segment turn signal
    if (zone == LightZone.BackStopSignal)      return BackRearPositionStyle; // brake (steady on)
    // ...
}

```

# 3. The Turn Signal's Flowing Effect

## 3.1 Shader

For the entire flowing effect, the core in the Shader is just this line:

```hlsl
// _IsFlowSwitch=0 steady on; =1 multiply by the scan-window intensity according to the flow progress
float flow = max((uv.x - 1.0) + min(_FlowAmount, 2.0), 0.0);
float4 final = _EmissionColor * tex2D(_EmissionMap, uv)
             * ((1.0 - _IsFlowSwitch) + (_IsFlowSwitch * flow));

```

A brightness gradient is designed here, expressed through the computation of the flow value. As `_FlowAmount` changes, flow varies between 0 and 2, ultimately driving the brightness gradient of the whole color.

The whole Shader has no Time—no animation that runs by itself over time. It relies on changes of FlowAmount, and that number is driven by the logic code.

## 3.2 Controlling It with a Tween Animation

The vehicle-control signal flips between on and off at a fixed frequency; each "on" triggers one flow sweep, and "off" extinguishes it.

```csharp
public void OnLightSwitch(Material material, bool b)
{
    if (_tweenFlowAni != null) { _tweenFlowAni.Kill(); _tweenFlowAni = null; }
    if (material != null && b)
    {
        material.SetFloat(FlowSwitchId, 1f);             // open the flow channel
        float number = 0;
        _tweenFlowAni = DOTween.To(() => number, x => number = x, 2.0f, 0.5f);
        _tweenFlowAni.OnUpdate(() => material.SetFloat(FlowAmountId, number));
        _tweenFlowAni.onComplete = () => { _tweenFlowAni.Kill(); _tweenFlowAni = null; };
    }
    else
        material.SetFloat(FlowSwitchId, 0f);             // close the flow
    _defaultStyle.OnLightSwitch(material, b);            // keyword switch (emission)
}

```

The Tween mechanism controls FlowAmountId, sweeping from 0 to 2 over 0.5 seconds. Each time the turn signal lights up, a sweep starts and is automatically Killed after finishing. Within 0.5 seconds the turn-signal signal may flip again, so you must Kill the previous animation before entering.

# 4. Caveats

## 4.1 Hazard-Light Synchronization

During hazard lights, the left and right turn signals light up simultaneously, and the flowing effects on the two sides are required to be strictly in step.

However, the left and right turn signals are two independent light-strip components, each with its own Tween animation instance, and the signals themselves are also received and processed with time skew. Relying only on such separate signal control, perceptible animation differences may appear.

So either accept it, or consider using only a single turn-signal continuous-state signal. This signal only expresses flashing vs. not flashing, but if you use it, you can no longer require the frequency to resemble the real vehicle's.

## 4.2 One Light Strip Split into Two Segments

As shown in the last partition diagram of the opening figure, the full-width taillight spans two sheet-metal panels—the tailgate and the body. Should you worry that the sweeping animation cannot be expressed as a whole?

No need to worry: the two light strips are two independent objects, but the UVs cannot—and will not—be independent. UV from 0 to 1 is essentially from the head of the left strip to the tail of the right strip. That way, using the shader approach above, you can sweep one strip to completion and then sweep the second.

# Closing Thoughts

Solving the reused-lamp problem means facing the essential problem of one entity with multiple presentations. We abstract states into data classes, abstract differences into style classes, and use priority sorting to resolve conflicts, ultimately forming this extensible lamp-driving scheme.
