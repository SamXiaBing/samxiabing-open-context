---
title: "Smart Driving SR Development: The “Weighty” Parking Slot"
lang: en
date: 2026-05-14
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> The parking slot (Parking Slot / Parking Space) is a rather distinctive perception object, and the reason it gets an article of its own is how richly it connects to the rest of the business. Geometrically it is just 4 corner points, but slot types (horizontal / vertical / angled), limiters, slot effects, optional numbering, click detection, parking-in interaction, and so on all introduce a lot of details to handle.

This article walks through the parking slot rendering pipeline, lists the related business logic and feature points, and organizes the development takeaways for parking slots based on what I have seen and heard — which is necessarily limited.

---

## 1. Data Format

Broadly speaking, **4 points + 1 slot type + limiter data + slot number + slot status + other feature values (e.g., narrow slot)** make up the common data set of a parking slot.

### 1.1 Field Descriptions

In actual development, every piece of data maps to a specific feature:


| Field           | Business intent                                                                                                                                                             |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `slot_id`       | Unique identifier of the slot. After the user taps a slot, the system needs to know which slot was chosen before it can issue the parking-in command.                       |
| `slot_type`     | Slot type (horizontal / vertical / angled). Different types use different geometry logic — in a horizontal slot the car's length direction is parallel to the lane, in a vertical slot it is perpendicular, and angled slots must be computed from the actual angle. |
| `corner_points` | Coordinates of the 4 corner points. This is the geometric foundation of the slot, determining its position, shape, and orientation on screen. Drawing the base plate and frame, and hit-testing clicks, all depend on these 4 points. |
| `slot_status`   | Slot status (searched / parkable / selectable / parking / completed, etc.). Status drives the visuals — the searched state shows a plain frame, the parkable state a blue highlight, the parking-in-progress state an open-ended frame, and the completed state a green effect. |
| `slot_num`      | Slot number (e.g., "Slot 8"). The digit displayed on the slot, so users and support staff can describe precisely "I want to park in slot 8."                                |
| `limiters`      | Coordinates of the two endpoints of the limiter (wheel stop). At render time these two points are converted into a position inside the slot where the limiter model is placed. |
| `narrowSlot`    | Narrow-slot flag. Marks slots narrower than standard — either specially designed ones or slots narrowed by parked cars on both sides. This flag triggers a narrow-slot warning display, reminding the user that the slot is tight and to be careful. |


### 1.2 Corner Order and Opening Direction

The order in which corner points are arranged directly affects the judgment of the slot's parking-in opening direction:

- **Corner arrangements: I have come across two kinds, indexed in order by array subscript** `[0, 1, 2, 3]`:

1. **Counterclockwise ordering**: viewed from the top, walking along the opening side, corner indices increase along the boundary (the figure below shows a common convention: 0→1 is the opening edge, and the whole loop runs counterclockwise).

*[Figures omitted; see the original WeChat article]*

2. **Z-shaped ordering**: another common convention chains the indices in a "Z" pattern.

*[Figures omitted; see the original WeChat article]*

- **Orientation calculation**: the edge from `point 0 to point 1` is the opening end (the side the car can enter from); the mesh's width and height are determined by the short/long sides (a horizontal slot's short side is about 2.5 m, its long side about 5–6 m).

### 1.3 Prefab Structure

In real projects, a parking slot prefab carries various child objects underneath, depending on business needs:

```
ParkingSlot (root node)
├── Base                    # slot base plate quad
├── Frame                   # slot frame
│   ├── Corner_0 / 1 / 2 / 3   # four corner pieces
│   └── Edge_0 / 1 / 2 / 3     # four edge pieces
├── Number                  # slot number digits ("Slot 8")
├── Icon_P                  # "P" icon (shown when the slot is parkable)
├── Effect                  # parking-complete effect (green ring / checkmark, etc.)
├── Switch                  # parking-direction toggle (nose/tail icon)
└── Limiter                 # limiter icon (wheel stop)

```

> Whether you need the Frame object at all depends on the actual design. Some HMI designs only require the slot to appear as a single quad with a texture, in which case the downstream logic is considerably simpler. Other HMI designs require the frame to be expressed with 3D models; in that case you deploy rounded-corner models at the corner points and place the edge models by calculation.

---

## 2. Slot Geometry Construction

In Smart Driving SR development, there are two approaches to slot geometry construction, each suited to different performance and interaction needs:


| Approach  | Composition                                                                 | Applicable scenario                                                              |
| --------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Approach 1 | Corner pieces + Edge strips + Base quad assembled into a framed slot        | Near-field auto parking scenes that need interaction and fine-grained display    |
| Approach 2 | A single quad + matching textures as a lightweight plane                    | Memory-parking cruising / multi-floor scenes with many slots, only basic readability needed |


Whichever approach you use, initialization follows a three-step process:

*[Figures omitted; see the original WeChat article]*

1. **Determine position**: by default, take the center of the quadrilateral plane and pair it with a uniform ground height; if the ground needs to keep its undulation, keep the four corners' original heights and use their average as the height.
2. **Compute heading**: compute the yaw angle according to the current corner-order convention; angled slots need a separate judgment that also factors in adjacent edge lengths.
3. **Compute slot dimensions**: a size utility class computes the slot's width and length according to the corner-order convention.

### 2.1 Approach 1: Corner + Edge + Base Framed Construction

This corresponds to the Frame child object plus the base Base quad in the project prefab: four corner pieces and four edge strips, layered over the base quad, form the complete slot. The input is still the 4 corner points plus the slot type. In engineering practice you would not develop a separate logic set for each of the three types (horizontal / vertical / angled); instead it is implemented through assembly, with the following steps:

1. Compute width and length according to the current corner convention (it must be aligned with the conclusions agreed during integration testing; for example, under the Z-shaped convention, 0→1 is the opening end).
2. Placing the corners: in the local horizontal plane of the slot root node, place the four corner pieces at the four corners of the standard rectangle (coordinates ±half-width, ±half-length); a corner piece is usually a pre-made rounded column, so you only need to modify transform parameters such as localPosition — a single prefab is all you need.
3. Stretching the edges: each edge strip sits at its opposite-side position; stretch its length via localScale, and subtract the corner pieces' rounded radius to reduce interpenetration and overlap between corners and edges. In the open-frame mode, the edge opposite the opening can be turned off entirely — keep only the rounded columns at both ends, avoiding a spurious fake edge.
4. Fitting the base quad: in the same update/render flow as the frame, use the same set of width/height values to set the base quad's localScale and local Euler angles: when width > length indicates a horizontal slot, the base quad is additionally rotated -90°, and a material flag `_IsHorizontal` notifies the shader to switch the UV layout; vertical and angled slots share this same flow with no extra branching.

> The fundamental purpose of this complicated approach is to avoid unreasonable model deformation caused by scale stretching when the slot's width/length flips between horizontal and vertical slot types.

### 2.2 Approach 2: Lightweight Single Quad + Texture Construction

When there are many slots, or you only need overview-level readability of the map-building result, you typically do not attach the whole set of Corner/Edge child objects from Approach 1. You keep just one quad paired with day/night textures, change states by swapping the main texture or material parameters, and can combine GPU instancing to further reduce the performance overhead. The concrete steps:

1. Follow the corner ordering convention and compute the width/height.
2. Root node: its position (corner heights averaged) and rotation match the data; angled slots compute the heading from the edge adjacent to the opening; horizontal slots add an extra +90° rotation on top of the heading angle.
3. Quad plane: fit the computed width/length with localScale; for horizontal slots, swap the width/height values of the two horizontal axes during scaling so the texture's long axis aligns with the slot's long edge, preventing the texture from being stretched into a distortion.

---

## 3. Slot Attachments and Interaction

### 3.1 Slot Number

The slot number is usually an image that needs to be displayed on non-recommended slots when there are multiple slots to choose from during parking. To make it easy for the user to read, based on the current camera rotation (on top of the top-down view), the digit's bottom edge should stay roughly parallel to the bottom edge of the entire CSD screen.

**Orientation calculation**:

```csharp
/// <summary>Updates the icon orientation so it always faces the camera (billboard effect)</summary>
private void UpdateIconRotation()
{
    if (slotIcon != null)
    {
        // Step 1: compute the direction from camera to icon (zero out the Y axis; rotate only in the horizontal plane)
        Vector3 direction = Camera.transform.position - slotIcon.transform.position;
        direction.y = 0;
        
        // Step 2: compute the facing angle and apply it
        slotIcon.transform.rotation = 
            Quaternion.Euler(0, Quaternion.LookRotation(direction, Vector3.up).eulerAngles.y, 0);
    }
}

```

**Angle discretization**: the design does not chase exact camera-facing every frame; instead the continuous value is snapped into four steps: **0/±90/180**. This keeps the digits "straight and level" even at oblique viewing angles, avoiding a situation where a horizontal slot has its digits lying sideways too — which becomes very hard to read.

### 3.2 Narrow Slot

**Narrow slot (narrowSlot)**: a slot narrower than the standard width, typically seen in multi-story garages and similar scenarios. The narrow-slot flag only drives whether an extra narrow-slot warning child object is shown; it is essentially just a texture and does not change the four-corner geometry — there is not much more to say about it.

### 3.3 Limiter

**Limiter (wheel stop)**: the data format is **two endpoint coordinates**:

```protobuf
message SlotFusionLimiter {
    uint32 id = 1;
    repeated Vector2 end_points = 2;  // two endpoint coordinates (fixed at 2)
}

```

**Limiter position calculation** (8 steps):

```csharp
/// <summary>Computes the limiter's position along the slot frame</summary>
public void UpdateTransform(
    SlotFusionLimiter limiter,
    SlotType slotType,
    Transform slotRoot,
    Vector2[] cornerWorldXz)
{
    // Goal 1: convert world coordinates to local ones, so the limiter follows when slotRoot moves
    Vector3 lp0 = slotRoot.InverseTransformPoint(p0);
    
    // Goal 2: use the fusion midpoint to decide which edge the limiter should sit next to
    bool edge03 = true;
    if (hasFusionMid)
    {
        // Compare the midpoint's distance to edge 03 and edge 12; the closer one is the limiter's edge
        float d03 = (fusionMid - m03).sqrMagnitude;
        float d12 = (fusionMid - m12).sqrMagnitude;
        edge03 = d03 < d12;
    }
    
    // Goal 3: determine the two endpoints of that edge
    a = edge03 ? lp0 : lp1;
    b = edge03 ? lp3 : lp2;
    
    // Goal 4: compute the edge midpoint and tangent direction
    Vector3 edgeMid = (a + b) * 0.5f;
    Vector3 tangent = b - a;
    
    // Goal 5: compute the inward normal (pointing into the slot)
    // The cross product gives a direction perpendicular to the tangent; with Y up, the result is horizontal
    Vector3 inward = Vector3.Cross(Vector3.up, tangent).normalized;
    
    // Goal 6: make sure inward really points toward the slot center (not outward)
    Vector3 toCenter = (lp0 + lp1 + lp2 + lp3) * 0.25f - edgeMid;
    if (Vector3.Dot(inward, toCenter) < 0f) inward = -inward;
    
    // Goal 7: compute the limiter position (0.8 m off the edge line, offset inward)
    Vector3 midLocal = edgeMid + inward * 0.8f;
    
    // Goal 8: set position and rotation
    limiterTransform.localPosition = midLocal;
    limiterTransform.localRotation = Quaternion.Euler(0, r, 0);
}

```

### 3.4 Parking-In Direction

The parking-in direction graphic shown on the slot (a flattened car-body-like image that clearly distinguishes which end is the front and which is the rear) tells the user whether the car will park **nose-in or tail-in**.

For vertical and angled slots, the parking-in direction field in the Smart Driving supplier's data protocol can be used to display the **direction graphic**. But for horizontal slots, I have run into cases where the Smart Driving supplier could not provide a **parking-in direction value for horizontal slots**. Hence there is an **application-layer fallback** here — you have to compute it yourself:

```csharp
/// <summary>Computes the horizontal slot's parking-in direction from the ego vehicle's heading</summary>
// Decision logic: when the dot product of the unit vector from corner 1 to corner 0 and the ego heading
// is below 1e-9 (to avoid floating-point error), the nose is on the corner-1/corner-3 edge; otherwise on the corner-0/corner-2 edge
if (Vector3.Dot(heading, slotDir) < 1e-9f)
{
    // Nose on the corner 1–3 edge → tail-in parking
    parkingDir = 1;
}
else
{
    // Nose on the corner 0–2 edge → nose-in parking
    parkingDir = 0;
}

```

## 4. Click Detection

Parking slot click detection relies on accurate collider computation, then casts a ray from the camera:

```csharp
/// <summary>Updates the collider bounds</summary>
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
/// <summary>Handles slot click selection (converts the screen tap position into a ray)</summary>
void HandleSelection(Vector2 screenPos)
{
    // Step 1: convert the screen tap position into a ray
    Ray ray = Camera.ScreenPointToRay(screenPos);
    
    // Step 2: detect which slot the ray hit
    if (CheckSlotHit(ray, out SlotObject slot))
    {
        // Handle the slot selection logic
    }
}

/// <summary>Checks whether the ray intersects a slot</summary>
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

## Conclusion

From four corner points to an interactive parking slot, this whole pipeline is in fact a typical microcosm of Smart Driving SR development: the input is simple, but the engineering details on the ground are legion — tiny differences in protocol agreements cascade into problems across the whole chain of geometry, rendering, and interaction; and all the engineering optimization we do is, at its core, a search for balance between **visual fidelity** and **runtime performance**.