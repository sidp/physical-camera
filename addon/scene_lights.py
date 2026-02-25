"""Collect scene lights and generate OSL loader function."""

MAX_LIGHTS = 16


def collect_lights(scene, camera_obj):
    """Collect lights from the scene, transformed to lens space.

    Returns a list of dicts with keys: type (0=positional, 1=sun),
    pos, dir, intensity, radius.
    """
    cam_inv = camera_obj.matrix_world.inverted()
    lights = []

    for obj in scene.objects:
        if obj.type != 'LIGHT':
            continue
        light = obj.data

        # Camera-local position/direction to lens space: both use -z toward
        # scene, so positions just scale by 1000 (no z flip). Sun directions
        # are negated to store "toward source" instead of emission direction.
        cam_space = cam_inv @ obj.matrix_world

        if light.type == 'SUN':
            from mathutils import Vector
            emission_dir = cam_space.to_3x3() @ Vector((0, 0, -1))
            # Negate to get "toward source" direction for the shader's
            # theta = -dir_transverse / dir_z formula
            dx = -emission_dir.x * 1000
            dy = -emission_dir.y * 1000
            dz = -emission_dir.z * 1000
            # Skip if sun is behind camera (toward-source z would be positive)
            if dz >= 0:
                continue
            lights.append({
                "type": 1,
                "pos": (0.0, 0.0, 0.0),
                "dir": (dx, dy, dz),
                "intensity": light.energy * _luminance(light.color),
                "radius": 0.0,
            })
        else:
            # POINT, SPOT, AREA
            pos = cam_space.translation
            px = pos.x * 1000
            py = pos.y * 1000
            pz = pos.z * 1000
            # Skip if behind rear vertex (can't enter lens)
            if pz > 0:
                continue
            if light.type == 'AREA':
                radius = max(light.size, getattr(light, 'size_y', light.size)) * 1000
            else:
                radius = light.shadow_soft_size * 1000
            lights.append({
                "type": 0,
                "pos": (px, py, pz),
                "dir": (0.0, 0.0, 0.0),
                "intensity": light.energy * _luminance(light.color),
                "radius": radius,
            })

    lights.sort(key=lambda l: l["intensity"], reverse=True)
    return lights[:MAX_LIGHTS]


def _luminance(color):
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def generate_load_scene_lights(lights):
    """Generate an OSL function body that loads scene light data."""
    max3 = MAX_LIGHTS * 3
    lines = [
        f"#define MAX_LIGHTS {MAX_LIGHTS}",
        f"#define MAX_LIGHTS_3 {max3}",
        "",
        "void load_scene_lights(",
        "    output int num_lights,",
        "    output int light_types[MAX_LIGHTS],",
        "    output float light_pos[MAX_LIGHTS_3],",
        "    output float light_dir[MAX_LIGHTS_3],",
        "    output float light_intensity[MAX_LIGHTS],",
        "    output float light_radius[MAX_LIGHTS])",
        "{",
        f"    num_lights = {len(lights)};",
    ]

    for i, lt in enumerate(lights):
        lines.append(f"    light_types[{i}] = {lt['type']};")
        lines.append(
            f"    light_pos[{i*3}] = {lt['pos'][0]};  "
            f"light_pos[{i*3+1}] = {lt['pos'][1]};  "
            f"light_pos[{i*3+2}] = {lt['pos'][2]};"
        )
        lines.append(
            f"    light_dir[{i*3}] = {lt['dir'][0]};  "
            f"light_dir[{i*3+1}] = {lt['dir'][1]};  "
            f"light_dir[{i*3+2}] = {lt['dir'][2]};"
        )
        lines.append(f"    light_intensity[{i}] = {lt['intensity']};")
        lines.append(f"    light_radius[{i}] = {lt['radius']};")

    lines.append("}")
    return "\n".join(lines)
