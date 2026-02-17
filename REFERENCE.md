# OSL Camera Shader Reference

## Blender OSL Camera API

### Setup
- Camera Properties > Lens > Type: Panoramic > Projection: Script
- Point at an `.osl` file or internal Text datablock
- **CPU and OptiX only** — no CUDA, HIP, or Metal

### Shader signature

```osl
shader my_camera(
    // custom parameters here
    output point position = 0,      // ray origin (camera space)
    output vector direction = 0,    // ray direction (camera space)
    output color throughput = 1     // 0 = kill ray, 1 = full weight
)
```

### Built-in functions

| Function | Returns | Notes |
|----------|---------|-------|
| `camera_shader_raster_position()` | `point` | Normalized sensor position (0–1 in x/y) |
| `camera_shader_random_sample()` | `point` | Two uniform random values in x/y (for aperture/DOF sampling) |

### Camera attributes via `getattribute()`

```osl
vector sensor_size;
getattribute("cam:sensor_size", sensor_size);     // physical sensor dimensions in mm

int resolution[2];
getattribute("cam:resolution", resolution);        // render resolution in pixels

float focal_dist;
getattribute("cam:focal_distance", focal_dist);    // focus distance in meters (scene units)
```

### Coordinate transforms

Output `position` and `direction` are in **camera space** by default. To convert:

```osl
position  = transform("camera", "world", local_pos);
direction = transform("camera", "world", local_dir);
```

### Blender 5.0 breaking change

Aperture position no longer depends on camera focal length. If using `getattribute("cam:aperture_position", ...)`, multiply by focal length manually:

```osl
getattribute("cam:aperture_position", position);
position *= focal_length * 1e-3;
```

## OSL Language Constraints (Blender/Cycles)

- **No structs** — use parallel arrays or multiple variables
- **No `#include`** — everything in one `.osl` file
- **No file I/O** — lens data must be hardcoded or passed as parameters
- **Fixed-size arrays only** — size must be a compile-time constant (`#define` works)
- **Array shader parameters have a UI bug** — values set in the UI may not reach the shader. Hardcode arrays inside functions instead.
- **`refract(I, N, eta)`** — built-in. Returns zero vector on total internal reflection. `I` must be normalized. `N` must face the incoming ray. `eta = n1/n2`.
- Functions must be declared before use (no forward declarations)

## Sequential Ray Tracing Through Lens Elements

### Lens prescription format

Each surface is defined by four values:

| Field | Unit | Description |
|-------|------|-------------|
| Curvature radius | mm | Signed. Positive = center of curvature to the right of the vertex. 0 = flat (aperture stop). |
| Thickness | mm | Axial distance from this surface to the next. |
| Index of refraction | — | IOR of the medium to the right of this interface. 1.0 = air. 0 = sentinel for aperture stop. |
| Aperture diameter | mm | Full clear diameter (halve for semi-diameter in code). |

### Tracing direction

Rays trace from sensor through the lens toward the scene:
- Sensor at negative Z, scene at positive Z
- Traverse surfaces from rear (sensor-side) to front (scene-side)
- PBRT convention lists surfaces front-to-back, so we iterate in reverse when tracing from sensor

### Algorithm per surface

1. **Ray-sphere intersection** — sphere center at `(0, 0, vertex_z + radius)` on the optical axis
2. **Aperture check** — reject if intersection point's radial distance exceeds semi-aperture
3. **Surface normal** — `normalize(hit_point - sphere_center)`, flipped to face incoming ray
4. **Refraction** — `refract(normalize(ray_dir), normal, n1/n2)`
5. **TIR check** — if `refract()` returns zero vector, kill the ray

For the aperture stop (radius = 0): intersect with a z-plane instead, check radial distance only, no refraction.

### Sphere center placement

The vertex of surface `i` sits at accumulated z position. The sphere center is displaced from the vertex by the radius value along z:

```
sphere_center_z = vertex_z + radius
```

### Choosing the correct intersection

For a ray-sphere intersection there are two solutions (t1, t2). Choose the one that produces a hit point closest to the vertex z-position (on the "vertex side" of the sphere).

## Double Gauss 50mm f/2 Lens Prescription

Source: PBRT v3, US Patent 2,673,491 (Tronnier). Listed front-to-back (scene-side first).

| Surf | Radius (mm) | Thickness (mm) | IOR   | Aperture Dia (mm) |
|------|-------------|-----------------|-------|--------------------|
| 0    | 29.475      | 3.76            | 1.67  | 25.2               |
| 1    | 84.83       | 0.12            | 1.0   | 25.2               |
| 2    | 19.275      | 4.025           | 1.67  | 23.0               |
| 3    | 40.77       | 3.275           | 1.699 | 23.0               |
| 4    | 12.75       | 5.705           | 1.0   | 18.0               |
| 5    | 0 (stop)    | 4.5             | 1.0   | 17.1               |
| 6    | -14.495     | 1.18            | 1.603 | 17.0               |
| 7    | 40.77       | 6.065           | 1.658 | 20.0               |
| 8    | -20.385     | 0.19            | 1.0   | 20.0               |
| 9    | 437.065     | 3.22            | 1.717 | 20.0               |
| 10   | -39.73      | 0.0             | 1.0   | 20.0               |

Total lens length (sum of thicknesses surfaces 0–9): ~32.32 mm. The last thickness (surface 10) is 0 — replace with the back focal distance to the sensor.

## Key References

- [Blender Manual — Custom Camera](https://docs.blender.org/manual/en/latest/render/cycles/osl/camera.html)
- [Cycles OSL Camera Feedback](https://devtalk.blender.org/t/cycles-osl-camera-feedback/38039)
- [Blender 5.0 Cycles Release Notes](https://developer.blender.org/docs/release_notes/5.0/cycles/)
- [PBRT — Realistic Cameras](https://www.pbr-book.org/3ed-2018/Camera_Models/Realistic_Cameras)
- [PBRT v3 realistic.cpp](https://github.com/mmp/pbrt-v3/blob/master/src/cameras/realistic.cpp)
- [Kolb et al. — A Realistic Camera Model](https://www.cs.utexas.edu/~fussell/courses/cs395t/lens.pdf)
- [OSL Standard Library](https://open-shading-language.readthedocs.io/en/latest/stdlib.html)
