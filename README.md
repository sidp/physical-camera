# Physical Camera

A Blender extension that replaces Blender's built-in camera with a physically-based lens simulation. Rays are traced through real lens prescriptions to produce realistic depth of field, bokeh shapes, chromatic aberration, and vignetting.

## Features

- Sequential ray tracing through multi-element lens designs
- Fresnel transmission loss and natural vignetting (cos^4 falloff)
- Spectral chromatic aberration (400-700nm continuous sampling)
- Polygonal aperture blades with adjustable rotation
- Focus distance driven by Blender's camera settings
- Debug visualization modes for diagnosing ray behavior

## Requirements

- Blender 4.5 or later
- Cycles render engine with OSL enabled
- CPU or OptiX rendering (OSL cameras are not supported on CUDA, HIP, or Metal)

## Installation

1. Download or clone this repository
2. In Blender, go to Edit > Preferences > Add-ons > Install from Disk
3. Select the `addon` directory

## Usage

1. Select a camera in your scene
2. Open the Camera Properties panel
3. In the "Physical Lens" panel, click "Enable Physical Lens"
4. Choose a lens and adjust settings:
   - **Lens** — select from available lens prescriptions
   - **f-stop** — aperture size (clamped to the lens's maximum)
   - **Aperture Blades** — 0 for circular, 3+ for polygonal bokeh
   - **Blade Rotation** — rotate the aperture shape
   - **Chromatic Aberration** — toggle spectral dispersion
   - **Debug Mode** — Normal, Pinhole, Diagnostic (failure visualization), or Exit Direction

Focus distance is controlled through Blender's standard camera Depth of Field settings.

## Included Lenses

- Double Gauss 50mm f/2 (US Patent 2,673,491)
- Double Gauss 100mm f/1.7 (US Patent 2,784,643)

## Adding a Lens

Create a `.toml` file in `addon/lenses/` with the following format:

```toml
[lens]
name = "Lens Name"
focal_length = 50.0
max_fstop = 2.0
stop_index = 5

[[surface]]
radius = 29.475
thickness = 3.76
ior = 1.67
aperture = 25.2
abbe_v = 57.0

# ... more surfaces
```

Surfaces are listed front-to-back (scene-side to sensor-side). The aperture stop surface should have `radius = 0` and `ior = 1.0`. All dimensions are in millimeters.

## License

GPL-3.0-or-later
