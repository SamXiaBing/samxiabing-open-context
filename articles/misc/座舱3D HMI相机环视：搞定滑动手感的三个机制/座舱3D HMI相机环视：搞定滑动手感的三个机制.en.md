---
title: "Cockpit 3D HMI Camera Orbit: Three Mechanisms for a Great Swipe Feel"
lang: en
date: 2026-05-20
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> The 3D car-model desktop is the signature application of today's smart-cockpit HMI, and it has become standard equipment. A virtual camera that orbits the ego vehicle following touch interaction is a standard part of that 3D car-model desktop. Based on previous delivery experience, this post focuses on single-finger touch orbiting.

As mentioned in my earlier article on the camera state machine, Cinemachine already provides orbit components on rails at different heights, and they are fairly convenient to use. But once finer-grained feel requirements (bounce-back, damping on the push, inertia) or business requirements (showing/hiding vehicle-control icons while dragging, interaction on/off switches) get coupled in, you may well want to write this basic capability yourself.

---

## 1. The Basics:

### 1.1 The Three-Layer Structure of the Orbit Camera

The ego-vehicle orbiting scenario in this post is based on the three-layer camera node structure described in [Unity Camera Animation with an Adobe After Effects Mindset: The Camera Motion Module in 3D HMI Practice](%5Bhttps://mp.weixin.qq.com/s/oZkMQoVgXFcE5-f98MGuZg%5D(https://mp.weixin.qq.com/s/oZkMQoVgXFcE5-f98MGuZg)):

```
Center (located at the ego-vehicle center; the rotation center)
└── Root (horizontal rotation around the Y axis → in charge of "turning the car")
    └── Main Camera (pitch rotation around the X axis → in charge of "looking up/down")

```

- **Horizontal rotation** happens at the Root layer: Root does `RotateAround` lookAt (the ego-vehicle center) along the world Y axis, and the Main Camera, as a child node, orbits the vehicle along with it.
- **Pitch rotation** also happens at the Root layer: Root does `RotateAround` lookAt (the ego-vehicle center) along its own right axis, and the Main Camera pitches along with Root.

This means:

> A horizontal finger swipe drives the Root's orbit around the ego-vehicle center along the world Y axis;
>
> A vertical finger swipe drives the Root's orbit around the ego-vehicle center along its right axis;
>
> The camera always looks at the ego-vehicle center because lookAt is anchored at the vehicle center, and both the horizontal and pitch rotations use `RotateAround` around that point.

```
// 1. Rotates its own position by the given angle around the specified axis
// 2. After the rotation, the distance from its own position to point stays unchanged (always constant)
// 3. The orientation adjusts automatically so that the new position looks straight at point
Transform.RotateAround(point, axis, angle)`

```

The parent-child relationship of the three nodes ensures the Main Camera moves together with Root.

### 1.2 Touch Input

The raw data of a finger sliding on the screen is **pixel displacement** (dx, dy). Our goal is to turn the on-screen dx/dy into **angle increments** (deltaYaw, deltaPitch). The distilled logic in code:

**Step 1: Touch input → angular velocity**

While dragging, each time we receive this frame's dx/dy, we multiply by sensitivity and write it into `_velocity`:

```csharp
// sensitivity is the number-one tuning parameter: with the same rotation formulas, it decides how fast the car turns for the same swipe distance
_velocity.x = data.delta.x * sensitivity;
_velocity.y = data.delta.y * sensitivity;

```

**Step 2: In LateUpdate each frame, angular velocity → angle increment**

In `LateUpdate`, we use deltaTime to convert angular velocity into angle increments and apply them to `_angles`:

```csharp
// _velocity decays every frame (see the next section); multiplying by deltaTime here converts angular velocity into the angle actually rotated this frame
float deltaYaw   = _velocity.x * speed.x * Time.deltaTime;
float deltaPitch = _velocity.y * speed.y * Time.deltaTime;

_angles.x += deltaPitch;  // Pitch angle
_angles.y += deltaYaw;    // Yaw angle

```

**Step 3: Angles → RotateAround to orbit the camera around lookAt**

Apply the accumulated angle increments to the camera rotation while keeping the camera always facing the ego-vehicle center:

```csharp
transform.RotateAround(lookAt.position, Vector3.up, deltaYaw);      // Horizontal: around the world Y axis
transform.RotateAround(lookAt.position, transform.right, deltaPitch); // Vertical: around the camera's local X axis

```

**Key point**: what we change is always the **angle**, never the position. This is what distinguishes an orbit camera from ordinary positional movement — no matter how fast or how far the finger swipes, only the direction the camera should look at changes.

### 1.3 Interaction Parameters

**Target and feel**


| Variable | Type | Typical Default | Meaning |
| ------------- | --------- | --------- | ------------------------------ |
| `lookAt` | Transform | — | Rotation center, usually the vehicle center |
| `speed` | Vector2 | (15, -15) | Horizontal / vertical angular velocity coefficients; y is usually negative, aligned with the screen Y axis direction |
| `sensitivity` | float | 8 | Multiplier from touch displacement to angular velocity |
| `inertia` | float | 0.8 | Per-frame velocity decay; the larger it is, the farther you coast after release |


**Pitch limits**


| Variable | Type | Typical Default | Meaning |
| ---------- | ----- | ---- | --------- |
| `pitchMin` | float | 0° | Lower pitch limit (hard boundary) |
| `pitchMax` | float | 40° | Upper pitch limit (hard boundary) |


**Boundary damping and bounce**


| Variable | Type | Typical Default | Meaning |
| ------------------- | ----- | ---- | -------------------- |
| `pitchMinDampRange` | float | 15° | Angle range in which damping takes effect near the lower boundary |
| `pitchMaxDampRange` | float | 20° | Angle range in which damping takes effect near the upper boundary |
| `pitchMinBounce` | float | 4 | Magnitude of the soft bounce zone beyond the lower boundary |
| `pitchMaxBounce` | float | 0 | Magnitude of the soft bounce zone beyond the upper boundary |
| `maxDampFactor` | float | 0.9 | Upper bound of damping strength; the closer to 1, the "stickier" the boundary |


**Runtime state**


| Variable | Meaning |
| --------------- | ---------------------------------------------- |
| `_angles` | Current pitch / yaw angles |
| `_velocity` | Current angular velocity, written by input and decayed per frame by inertia |
| `_isDragging` | Whether the finger is still on the screen |
| `_interactable` | Whether input is responded to; together with `activeInHierarchy` it decides whether `IsActive` holds |


---

## 2. The Feel: Inertia, Upward-Swipe Damping, Downward-Swipe Bounce

*[Figures omitted; see the original WeChat article]*

### 2.1 Inertia

After you release, the camera doesn't stop instantly; it keeps coasting for a while. This relies on `_velocity` being multiplied by `inertia` every frame so it decays:

```csharp
// inertia ∈ (0, 1); the larger it is, the slower the decay and the farther you coast after release
_velocity *= inertia;
if (Mathf.Abs(_velocity.x) < threshold) _velocity.x = 0;
if (Mathf.Abs(_velocity.y) < threshold) _velocity.y = 0;

```

Horizontal rotation is pure inertia, governed only by `inertia`.

### 2.2 Upward-Swipe Damping

When approaching the lower boundary (the pitch-down limit) and pressing further downward, the angular velocity shrinks linearly with proximity to the boundary. The feel is like a "soft wall" — the harder you push toward the lower boundary, the less it moves:

```csharp
// damp ∈ [0, maxDampFactor]; the closer to the boundary, the smaller it gets
damp = maxDampFactor;
if (pitch < pitchMin + pitchMinBounce && velocity.y < 0)
    damp = (pitch - (pitchMin - pitchMinBounce)) / pitchMinDampRange;

// Damping takes effect: this frame's pitch increment is multiplied by damp²; squaring makes the deceleration steeper
deltaPitch = _velocity.y * speed.y * Time.deltaTime * damp * damp;

```

### 2.3 Downward-Swipe Bounce

When the pitch angle has already exceeded pitchMax (i.e., it has pushed against the upper limit), continuing to swipe down causes this frame's pitch increment to be **truncated** outright — the increment becomes zero, and the frame is as if nothing happened. In feel, you've hit the top and can't push any further.

At the same time, a soft bounce (bounce) is also accounted for, and it triggers only after you release while the pitch angle is still within the pitchMaxBounce range. That is, after release, the camera slowly slides back inside the pitchMax boundary under inertia.

So:

- **Push to the limit and keep pushing**: the feel is dead-stopped (increment truncation)
- **Still in the soft zone after release**: the feel is bouncing back (bounce decay)

The code implementation of the bounce:

```csharp
deltaPitch = _velocity.y * speed.y * Time.deltaTime * damp * damp;
if (pitch + deltaPitch > pitchMax + pitchMaxBounce)
    deltaPitch = pitchMax + pitchMaxBounce - pitch;  // Truncate at the upper boundary
else if (pitch + deltaPitch < pitchMin - pitchMinBounce)
    deltaPitch = pitchMin - pitchMinBounce - pitch;  // Truncate at the lower boundary

```

---

## 3. Wrap-Up

This post only described the component-level capability of orbiting. As interactions grow more complex, dragging alone isn't enough — you will also need two-finger pinch to zoom the view and two-finger pan to move the view, especially in SR development. So in a later post I'll cover how to implement these compound requirements.
