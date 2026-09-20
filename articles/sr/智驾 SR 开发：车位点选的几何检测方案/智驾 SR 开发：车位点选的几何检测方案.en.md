---
title: "ADAS SR Development: A Geometric Detection Scheme for Parking Slot Selection"
date: 2026-09-10
series: sr
no: 
status: published
visibility: public
lang: en
wechat_url: ""
---

> The previous post covered reusing the car light effects; this one shares some insights about click interactions. As we know, in the parking flow, once multiple parking slots have been detected, the user can tap to choose the slot they want to park into. So how is this tap interaction implemented? Are there alternative schemes, and what hidden pitfalls might exist?

In terms of processing flow, the pipeline looks roughly like this:

*[Figures omitted; see the original WeChat article]*

These steps are fairly common: detect the touch event, then use the event's coordinates to simulate a ray in world space cast from the camera viewport, collect whatever the ray hits, run a tag check to filter for objects that match the click intent, and finally report the selection result through the messaging module to the Android layer or the ADAS service. Tapping a new slot is a selection; tapping an already-selected slot again switches the parking-in direction.

The details worth sharing here are the ray and the detection part.

---

## Raycast Result Detection

*[Figures omitted; see the original WeChat article]*

The problem with an AABB (axis-aligned bounding box) is that it is larger than the object it wraps all around — a tap on the empty ground next to a slot would still count as hitting the box, so it can't be the final judge. For slot picking, the same machinery is simply used differently, serving as the first gatekeeper: if the ray doesn't even touch the bounding box, there's no need to check anything further — the vast majority of irrelevant slots get filtered out at this step. Only bounding-box hits move on to precise detection.

```csharp
public static bool CheckSlotClick(Vector2 screenPos, out ParkingSlot slot) {
    Ray ray = SceneRoot.Instance.SrCamera.ScreenPointToRay(screenPos);
    float closestDist = float.MaxValue;
    ParkingSlot closestSlot = null;

    foreach (ParkingSlot s in slots) {
        // Skip slots with missing components outright
        if (s.pickObject == null || s.pickMeshFilter == null || s.pickMeshRenderer == null) continue;

        var bounds = s.pickMeshRenderer.bounds;                  // AABB, from the MeshRenderer
        var t = s.pickObject.transform;                          // Slot transform
        var mesh = s.pickMeshFilter.mesh;                        // Mesh of the pickable surface
        if (bounds != null && bounds.IntersectRay(ray)) {        // Stage 1: coarse bounding-box filter
            if (RaycastMesh(ray, mesh, t, out float dist)) {     // Stage 2: per-triangle precise test
                if (dist < closestDist) {                        // On multiple hits, keep the closest
                    closestDist = dist;
                    closestSlot = s;
                }
            }
        }
    }
    slot = closestSlot;
    return closestSlot != null;
}

```

Parking slot objects enter and leave the field of view along with the perception data, so the static slots collection inevitably retains stale objects. The cleanup strategy is: while iterating slots, an invalid object cannot be removed directly (removing elements while iterating a HashSet / List causes problems), so it is first recorded in a pending-removal list. After the iteration ends, the objects on that list are removed from the collection in one pass.

Also, when the finger lands on the boundary between two slots, both sides may pass the coarse filter and the precise test. The code uses the closestDist variable to track the current closest distance, comparing after every hit:

```csharp
if (dist < closestDist) {
    closestDist = dist;
    closestSlot = s;
}

```

In the end it returns the slot closest to the ray origin, which matches user intuition.

---

## Hand-Writing Möller–Trumbore

The core of the second stage is ray–triangle intersection: first transform the ray into the slot's local space, then run an intersection test against every triangle of the mesh.

```csharp
static bool RaycastMesh(Ray ray, Mesh mesh, Transform t, out float distance) {
    distance = float.MaxValue;
    Matrix4x4 w2l = t.worldToLocalMatrix;    // world → slot local space
    Vector3 localOrigin = w2l.MultiplyPoint3x4(ray.origin);
    Vector3 localDir = w2l.MultiplyVector(ray.direction);

    Vector3[] vertices = mesh.vertices;
    int[] triangles = mesh.triangles;

    bool hit = false;
    for (int i = 0; i < triangles.Length; i += 3) {
        Vector3 v0 = vertices[triangles[i]];
        Vector3 v1 = vertices[triangles[i + 1]];
        Vector3 v2 = vertices[triangles[i + 2]];

        if (RayTriangleIntersect(localOrigin, localDir, v0, v1, v2, out float tDist) && tDist > 0) {
            // Convert the local-space distance back to world space
            float worldDist = tDist * localDir.magnitude / ray.direction.magnitude;
            if (worldDist < distance) {
                distance = worldDist;
                hit = true;
            }
        }
    }
    return hit;
}

```

To compute the exact intersection with the triangle faces, we chose to move the ray into the slot's local coordinate system for the collision test, rather than the other way around. As shown in the code, once we have the transform matrix, applying it to the ray's origin and direction respectively maps the ray into local space.

RayTriangleIntersect is the classic Möller–Trumbore algorithm from computer graphics:

```csharp
static bool RayTriangleIntersect(Vector3 origin, Vector3 dir,
                       Vector3 v0, Vector3 v1, Vector3 v2, out float t) {
    const float EPSILON = 1e-8f;

    Vector3 edge1 = v1 - v0, edge2 = v2 - v0;
    Vector3 h = Vector3.Cross(dir, edge2);
    float a = Vector3.Dot(edge1, h);   // Determinant, proportional to the volume spanned by the three vectors

    if (a > -EPSILON && a < EPSILON) return false; // Ray is parallel to the triangle

    float f = 1.0f / a;
    Vector3 s = origin - v0;
    float u = f * Vector3.Dot(s, h);
    if (u < 0.0f || u > 1.0f) return false;    // Intersection lies outside the triangle

    Vector3 q = Vector3.Cross(s, edge1);
    float v = f * Vector3.Dot(dir, q);
    if (v < 0.0f || u + v > 1.0f) return false;  // Intersection lies outside the triangle

    t = f * Vector3.Dot(edge2, q);
    return t > EPSILON;                        // Triangle lies in front of the ray
}

```

This is a utility function: it takes a ray and a triangle, and outputs whether the ray hit the triangle and, when it did, the distance t. a checks for parallelism, u/v check whether the intersection lies inside the shape (barycentric coordinates — it is inside only when all weights are positive), and t checks whether it lies in front of the ray.

This function is called on every triangle of the mesh of every slot that passed the coarse filter, to see which triangle face the ray actually lands on.

![Möller–Trumbore algorithm](./fig_moller_trumbore.png)

## Closing Thoughts

Looking back at this scheme, there is another interesting choice: we used neither Unity's Physics.Raycast, nor did we attach a BoxCollider to the slots.

The main consideration: a parking slot is purely visual and carries no physics responsibility. If picking a parking slot required attaching a Collider to every slot and using the physics engine's collision detection, the cost would be a bit high. After all, one more collider means one more piece of overhead; moreover, the slot's four corner points update frequently with the perception data, so the box's size would have to be recomputed and re-synced every frame so that the slot you see and the slot you hit stay aligned.

That's why this purely geometric scheme exists. Its benefit is a more controllable feel — you can control the computational cost. It doesn't depend on the physics engine, and it adds no burden to the physics pipeline. For a feature that may interact every frame, overhead at this magnitude feels much safer.
