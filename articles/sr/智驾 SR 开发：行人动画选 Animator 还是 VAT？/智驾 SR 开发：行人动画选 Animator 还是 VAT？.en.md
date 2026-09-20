---
title: "ADAS SR Development: Pedestrian Animation — Animator or VAT?"
lang: en
date: 2026-09-17
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> Among the perceived objects in SR, the pedestrian is a special one. On one hand, it is one of the few objects that uses a skinned mesh; on the other, it is a perceived object that can carry animations and actually move. So how do we make it move?

# 1. The Conventional Approach: Skeletal Animation

The standard way to make characters move has long been skeletal animation, driven by an engine-side Animator state machine. Artists rig bones and keyframe in a DCC tool, then export animation clips. Programmers import these FBX files (with the Animation inside) and let the runtime Animator component switch clips according to state. The skeleton hierarchy updates each node's Transform, and the skinned mesh deforms along with it. On the programming side, the animation state machine is controlled with a clip name and a speed value as parameters. This path is mature and intuitive, and the vast majority of projects do it this way.

But in our earlier SR development, animated pedestrians were not implemented this way. Instead, the skeletal animation was baked into textures, and playback control was placed inside the shader.

# 2. VAT: Vertex Animation Texture

The technique used for the pedestrian perceived object here is called VAT — Vertex Animation Texture. The idea is to **bake the position every vertex should be at in every frame of the animation into a texture, and at runtime the vertex shader reads the image on demand, like a table lookup.**

## Offline Baking: Two Textures

*[Figures omitted; see the original WeChat article]*

Baking is done offline. The artist creates the pedestrian's skeletal animations (standing, walking), and a baking tool outputs the two clips frame by frame into two textures:

- Position Map: each vertex records one RGB value — its position xyz in space for that frame, or rather, its offset.
- Normal/Rotation Map: records the normal orientation of that vertex in that frame.

Texture layout: the horizontal axis is ordered by vertex index, the vertical axis by animation frame. The texture has as many columns as there are vertices, and as many rows as there are baked frames for however long the walk clip runs. The whole animation is compressed into a single "vertex position lookup table."

## Runtime GPU Table Lookup

At runtime, the pedestrian's mesh no longer needs bones. The vertex shader code is as follows:

```csharp
// Vertex shader: table lookup by vertex ID + current frame number
float2 frameUV = float2(
    v.vertexID + 0.5,                            // Column: which vertex am I
    fmod(_TimeParameters.x, _VatAnimLength)      // Row: which frame we're on now
        * _VatAnimFps + 0.5);

float3 pos = tex2Dlod(_VatPositionTex, frameUV).rgb;
v.vertex.xyz += pos;                             // The vertex directly gets its position
v.ase_normal = tex2Dlod(_VatNormalTex, frameUV).rgb;
```

The column index is the vertex's own index — each vertex looks up its own column.

The row index comes from the shader built-in `_TimeParameters.x` (engine time), taken modulo the animation length and then multiplied by the frame rate. As time advances, the frame index pushes forward automatically, which gives looped playback.

Time advancement happens entirely inside the shader, with no C# code involved at all. Animation changes from "the CPU updating bone transforms frame by frame" to "the GPU reading a texture" — that is what makes VAT interesting.

## How to Switch Animations

If time advances automatically inside the shader and the animation is running on its own, how do I switch between different animations? For example: the pedestrian plays the standing clip while stationary, and switches to the walking clip once movement is detected.

First, a parameter `_AniWalk` is declared in the shader code. Based on this parameter, the C# side can control it like this:

```csharp
// C# side: speed decides which way the weight goes
if (base.Speed < 0.2f) {
    curProcess -= Time.deltaTime;               // Stopping: weight falls back
    if (curProcess < 0f) curProcess = 0f;
    Render.sharedMaterial.SetFloat("_AniWalk", curProcess);
} else {
    curProcess += Time.deltaTime;               // Walking: weight climbs up
    if (curProcess > 1f) curProcess = 1.0f;
    Render.sharedMaterial.SetFloat("_AniWalk", curProcess);
}
```

`_AniWalk` ranges from 0 to 1 and controls the weight between the two animations. If the perceived object's speed is below the threshold, the weight falls from 1 to 0 over about a second; once the speed goes above the threshold, the weight goes back to 1. The walk loop itself never stops — it keeps looping in the shader the whole time. Only this pose weight changes.

So what does the shader side do once it receives the weight? Essentially, blending:

```csharp
// Shader side: interpolate the two baked texture sets (idle and walk) by weight
float3 pos    = lerp(positionTex_idle, positionTex_walk, _AniWalk);
float3 normal = lerp(normalTex_idle,   normalTex_walk,   _AniWalk);
```

Weight 0 keeps the pedestrian in the standing pose; weight 1 is a normal walk; values in between are the transitional pose from standing to walking. It plays the role of the clip switching and cross-fading that an Animator state machine would normally do.

# 3. Performance Comparison

So, before writing this article, I built a demo in the editor to test the performance of the two approaches. The demo setup: take the same pedestrian model (1,977 vertices, with its own skeletal walk animation) and instantiate it in two ways:

- Animator group: skeletal animation + Animator component, with bone poses explicitly advanced every frame (the conventional approach);
- VAT group: the same mesh with a VAT material, playback driven automatically by the shader (the VAT approach).

The pedestrian count went from 20 to 50, then to 100. After warming up each group, I measured 200 consecutive frames and tallied the per-frame cost of "animation driving + camera rendering":

*[Figures omitted; see the original WeChat article]*

The results matched expectations:

- **The Animator group scales linearly with count**. 1.76 ms for 20 pedestrians, 3.76 ms for 100 — an average of 0.028 ms per pedestrian. That is the cost of the Animator state machine and skeleton hierarchy updates.
- **The VAT group barely changed**. 1.14 ms with 100 pedestrians versus a 0.97 ms empty-scene baseline. A hundred pedestrians walking had no obvious impact on the CPU.
- The larger the count, the larger the gap.

The data comes from per-frame measurements in the editor environment (animation driving + camera rendering) and does not include the other overheads of the full engine Player Loop, so real-device numbers will differ. But I believe the relative relationships here are real.

*[Figures omitted; see the original WeChat article]*

# Closing Thoughts

Choosing VAT for SR pedestrians is a decision with very typical conditions: a large number of the same kind of characters (perceived pedestrians appear in crowds), a tiny action set (just standing and walking), no need for individual expression, and fixed action rhythms. Only when all four of these characteristics hold does VAT's batching advantage outweigh the loss in expressiveness.

Conversely, for protagonist characters that need fine-grained expression and interaction-feedback animations, the Animator is still the right answer.
