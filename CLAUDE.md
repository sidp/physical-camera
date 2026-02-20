# CLAUDE.md

## Project Overview

Physical Camera — a Blender extension that replaces Blender's built-in camera with a physically-based lens simulation using OSL (Open Shading Language). Rays are traced backwards through real lens prescriptions (spherical surfaces, aperture stops, Fresnel transmission, chromatic dispersion) to produce realistic depth of field, bokeh, and aberrations.

Requires Blender 4.5+ with Cycles and OSL enabled.

## Goals

The primary goal is to accurately and realistically simulate real-world lenses. Accuracy and realism take priority in design decisions.

Performance and code architecture are secondary but important constraints:

- **Performance** — Rendering is expected to be slower than Blender's built-in camera due to the physically-based lens model. Features that add significant per-ray cost should be toggleable so users can choose the accuracy/speed tradeoff. Before implementing an expensive feature, consider whether approximations or importance sampling can bring the cost down
- **Complexity** — Features that can't be cleanly integrated into the existing architecture should prompt a refactor before implementation, not after. Avoid bolting complex behavior onto code that wasn't designed for it — restructure first so the new feature fits naturally

## Architecture

There are two main parts:

### OSL Shader (`addon/lens_camera.osl.template`)
- The template has a `// {{LENS_DATA}}` placeholder that gets replaced with generated lens data at addon registration time
- The shader implements backward ray tracing (sensor → scene) through a multi-surface lens system using ABCD matrix optics for focus computation and exit pupil aiming
- Surfaces are listed front-to-back but traced rear-to-front (sensor side first)
- `MAX_SURFACES` is defined as 36 — any new lens must fit within this limit

### Blender Addon (`addon/`)
- `__init__.py` — Registers the Blender extension: properties, operators, UI panel in Camera Properties. On register, calls `codegen.generate_osl()` to produce the final OSL source and stores it in a Blender text datablock
- `lenses.py` — Reads TOML lens files from `addon/lenses/` into dicts (no bpy dependency, shared by the build script). Infers a `surface_types` list per lens (`"spherical"`, `"flat"`, `"stop"`, `"aspheric"`, `"cylindrical_x"`, `"cylindrical_y"`)
- `codegen.py` — Generates the `load_lens_data()` function and injects it into the OSL template. Emits `surface_types[]`, `extra[]`, `thicknesses_close[]` arrays, `focus_close_distance`, `squeeze`, and `SURFACE_*` type constants
- `diagram.py` — Loads pre-rendered lens diagram PNGs from `addon/previews/` as Blender preview icons
- `addon/lenses/*.toml` — Lens prescriptions in TOML format. Each file defines `[lens]` metadata (name, focal_length, max_fstop, optional squeeze), `[[surface]]` entries (radius, thickness, ior, aperture, abbe_v), and an optional `[focus]` section for variable element spacing. The aperture stop surface must have `type = "stop"`. Aspheric surfaces use `type = "aspheric"` with `conic` and `aspheric_coeffs` fields. Cylindrical surfaces use `type = "cylindrical_x"` (curvature in X only) or `type = "cylindrical_y"` (curvature in Y only). Other surfaces infer their type from `radius` (0 = flat, nonzero = spherical)
- `blender_manifest.toml` — Blender extension manifest

## Adding a New Lens

1. Create a new `.toml` file in `addon/lenses/` following the existing format
2. Surface data uses the PBRT convention: radii of curvature in mm, positive = center of curvature toward the sensor
3. The aperture stop surface must have `type = "stop"` (radius=0, ior=1.0). Exactly one stop per lens is required
4. Lens files are loaded alphabetically — the filename determines the enum order in the UI
5. Regenerate lens diagram PNGs: `uv run scripts/build_diagrams.py`
6. Optionally add a `[focus]` section for variable element spacing (see below). Lenses without this section use unit focusing (sensor-plane movement only)
7. For anamorphic lenses, add `squeeze = 2.0` (or the appropriate factor) to the `[lens]` section. The shader scales sensor X coordinates by this factor to automatically desqueeze the output. Spherical lenses omit this field (defaults to 1.0)
8. Update the "Included Lenses" list in `README.md`

### Variable Element Spacing

When patent data provides element spacings at both infinity and a close-focus distance, add a `[focus]` section to enable internal focusing:

```toml
[focus]
close_distance = 301.0  # object distance from front vertex, in mm (patent convention)

[[focus.variable]]
surface = 16             # 0-based surface index whose thickness varies
thickness_close = 0.89   # thickness at close_distance (infinity value lives in [[surface]])
```

- `close_distance` is the object distance from the front vertex in mm, matching patent variable-distance tables
- Multiple `[[focus.variable]]` entries support floating-element designs with more than one moving group
- Referenced surfaces must be air gaps (`ior = 1.0`)
- The shader interpolates linearly in reciprocal object-distance space between the infinity and close-focus calibration points. At distances closer than the calibration point, close-focus thicknesses are used as-is

### Aspheric Surfaces

For surfaces with even-polynomial aspheric departures, use `type = "aspheric"`:

```toml
[[surface]]
type = "aspheric"
radius = 75.484
thickness = 2.5
ior = 1.85478
aperture = 82.48
abbe_v = 24.8
conic = 0.0                                       # optional, defaults to 0.0
aspheric_coeffs = [-2.2875e-6, -2.1286e-10, 2.6709e-13]  # [A4, A6, A8] or [A4, A6, A8, A10]
```

- `aspheric_coeffs` is a list of 3 or 4 floats: 4th, 6th, 8th (and optionally 10th) order even-polynomial coefficients
- `conic` is the conic constant k (0 = sphere, -1 = paraboloid); optional, defaults to 0
- The surface must have nonzero `radius` (the base radius of curvature)
- Non-aspheric surfaces must not have `aspheric_coeffs` or `conic` fields

### Cylindrical Surfaces (Anamorphic)

For anamorphic lenses with surfaces that have curvature in only one axis:

```toml
[[surface]]
type = "cylindrical_x"   # curvature in X only, flat in Y
radius = -99.505
thickness = 3.0
ior = 1.560
aperture = 28.204
abbe_v = 68.8

[[surface]]
type = "cylindrical_y"   # curvature in Y only, flat in X
radius = 80.514
thickness = 4.9899
ior = 1.761
aperture = 42.07
abbe_v = 26.5
```

- `cylindrical_x`: curvature in the X-Z plane only (ray height in X sees a curved surface, Y sees flat). Used for horizontal squeeze elements
- `cylindrical_y`: curvature in the Y-Z plane only. Used for vertical stretch elements
- The surface must have nonzero `radius` (the curved axis's radius of curvature)
- Cylindrical surfaces must not have `aspheric_coeffs` or `conic`
- For anamorphic lenses, the ABCD paraxial traces carry separate X and Y matrices. Sensor distance is derived from the Y axis (spherical meridian), matching cinematographic focus convention
- The exit pupil has separate X/Y magnifications, producing elliptical bokeh sampling

## Shader Function Pipeline

1. `load_lens_data()` — generated at registration; selects lens prescription by index. Outputs `surface_types[]` (int per surface: `SURFACE_SPHERICAL=0`, `SURFACE_FLAT=1`, `SURFACE_STOP=2`, `SURFACE_ASPHERIC=3`, `SURFACE_CYLINDRICAL_X=4`, `SURFACE_CYLINDRICAL_Y=5`), `extra[]` (8 floats per surface: k, A4, A6, A8, A10, reserved×3), `thicknesses_close[]`, `focus_close_distance` for variable element spacing, and `squeeze` for anamorphic desqueeze
2. Thickness interpolation — when `focus_close_distance > 0`, interpolates `thicknesses[]` between infinity and close-focus values using `alpha = clamp(close_distance / d_obj, 0, 1)` in reciprocal object-distance space. All downstream functions receive the adjusted thicknesses
3. `compute_sensor_distance()` — Y-axis ABCD matrix paraxial trace (front-to-back) to find sensor plane position from focus distance. Cylindrical_x surfaces are skipped (no Y power); cylindrical_y surfaces contribute
4. `compute_exit_pupil()` — Dual X/Y ABCD matrices for rear subsystem to find exit pupil position/magnification per axis. Derives stop index from `surface_types[]`
5. `compute_field_exit_pupil()` — tightens the exit pupil disk for off-axis sensor points by projecting rear element apertures. Derives stop index from `surface_types[]`
6. `trace_lens_system()` — sequential ray trace (rear-to-front) calling `refract_at_surface()` per element. Uses `surface_types[]` for all type dispatch. Includes sphere-overlap retry logic for thin flat surfaces adjacent to curved ones
7. `find_surface_intersection()` — geometry-only helper: finds intersection point and surface normal for any surface type (flat, stop, spherical, aspheric, cylindrical). Returns 1=hit, 0=miss, -1=clipped
8. `refract_at_surface()` — calls `find_surface_intersection()`, then applies Snell's law + Fresnel transmittance. Stops pass through without refraction
9. `reflect_at_surface()` — calls `find_surface_intersection()`, then applies `reflect()` + Fresnel reflectance. Used for ghost bounces (never called on stops)
10. `trace_surface_range()` — traces a contiguous range of surfaces in either direction (step=±1). Refracts at each surface except an optional reflect_at_idx where it reflects. No sphere-overlap retry logic
11. `trace_ghost_path()` — composes three `trace_surface_range()` calls for a double-bounce ghost path: (a) rear→bounce_a with reflect, (b) bounce_a+1→bounce_b with reflect, (c) bounce_b-1→front with refract
12. `check_aperture_at_plane()` — projects a ray to a z-plane and checks circular or n-gon aperture clip
13. `refract_at_flat_plane()` — Snell's law at a flat surface with Fresnel transmittance

Throughput weighting applies cos^4 radiometric falloff and normalizes Fresnel loss against on-axis transmission. When chromatic aberration is enabled, wavelength is sampled uniformly over 400–700nm with golden-ratio decorrelation for the aperture radius sample.

### Ghost/Flare Simulation

When `lens_ghosts` is enabled, a fraction (`ghost_fraction`, default 0.1) of samples trace ghost paths instead of direct paths. Ghost pairs are enumerated from all surfaces with a Fresnel interface (non-stop surfaces where IOR changes), excluding same-IOR boundaries. A random pair is selected per sample.

- Ghost throughput: `cos^4 * (ghost_T / onaxis_T) * num_pairs / ghost_fraction * ghost_intensity`
- Direct throughput (when ghosts active): `cos^4 * (T / onaxis_T) / (1 - ghost_fraction)`
- Debug mode 4 ("Ghosts Only"): all samples trace ghost paths, direct rays suppressed

## Coordinate System

- Lens space: rear element vertex at z=0, front element at z=-total_length, sensor at z=+sensor_distance
- Lens space has -z toward the scene; Blender camera space has +z toward the scene
- Output conversion: z is negated and mm are converted to meters (×0.001)
- Sphere centers sit at `vertex_z + radius` along the optical axis
- Ray-sphere intersection picks the hit closest to the vertex (not the far side)

## Key Conventions

- All lens dimensions are in millimeters within the shader; Blender's camera space uses meters
- `iors[i]` represents the medium *after* surface i (toward sensor), not before it
- The aperture stop surface has `radius=0` and `ior=1.0`; it clips rays but does not refract. Identified by `surface_types[i] == SURFACE_STOP`, not by index
- `surface_types[]` determines how each surface is processed — all type branching uses these constants rather than checking `radius == 0` or comparing to a stop index
- `extra[]` has 8 float slots per surface (`extra[i*N_EXTRA + 0..7]`): slots 0–4 are conic constant k, A4, A6, A8, A10 aspheric coefficients; slots 5–7 are reserved. Non-aspheric surfaces have all zeros
- `is_curved_surface()` returns true for `SURFACE_SPHERICAL`, `SURFACE_ASPHERIC`, `SURFACE_CYLINDRICAL_X`, and `SURFACE_CYLINDRICAL_Y` — used for ABCD power and sphere-overlap logic
- Focusing uses variable element spacing when patent data is available (`focus_close_distance > 0`), falling back to unit focusing (sensor-plane movement only) otherwise. The ABCD solve computes the correct sensor position for either case
- Fresnel transmission is tracked per-surface and normalized against on-axis transmission for exposure compensation

## OSL Language Constraints (Blender/Cycles)

- **CPU and OptiX only** — no CUDA, HIP, or Metal
- No structs — use parallel arrays or multiple variables
- No `#include` — everything in one `.osl` file
- No file I/O — lens data must be hardcoded or generated into the source
- Fixed-size arrays only — size must be a compile-time constant (`#define` works)
- Array shader parameters have a UI bug — values set in the UI may not reach the shader; hardcode arrays inside functions instead
- `refract(I, N, eta)` returns zero vector on TIR; `I` must be normalized; `N` must face the incoming ray; `eta = n1/n2`
- Functions must be declared before use (no forward declarations)

## Blender OSL Camera API

The shader entry point must output `position`, `direction`, and `throughput` (set throughput to 0 to kill a ray). Key built-in functions:
- `camera_shader_raster_position()` — normalized sensor position (0–1)
- `camera_shader_random_sample()` — two uniform random values in x/y
- `getattribute("cam:sensor_size", ...)` — physical sensor dimensions in mm
- `getattribute("cam:focal_distance", ...)` — focus distance in meters

