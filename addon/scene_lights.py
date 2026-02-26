"""Collect scene lights and generate OSL loader function."""

MAX_LIGHTS = 16


def collect_lights(scene, camera_obj):
    """Collect lights from the scene, transformed to lens space.

    Finds both Blender LIGHT objects and mesh objects with emissive
    materials (Emission shader or Principled BSDF with emission).

    Returns a list of dicts with keys: type (0=positional, 1=sun),
    pos, dir, intensity, radius.
    """
    cam_inv = camera_obj.matrix_world.inverted()
    lights = []

    for obj in scene.objects:
        if obj.type == 'LIGHT':
            _collect_light_object(obj, cam_inv, lights)
        elif obj.type == 'MESH':
            _collect_emissive_mesh(obj, cam_inv, lights)

    lights.sort(key=lambda l: l["intensity"], reverse=True)
    return lights[:MAX_LIGHTS]


def _collect_light_object(obj, cam_inv, lights):
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
            return
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
        if pz > 0:
            return
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


def _collect_emissive_mesh(obj, cam_inv, lights):
    """Check mesh materials for emission and add as a positional light."""
    emission = _get_mesh_emission(obj)
    if emission is None:
        return

    strength, color_r, color_g, color_b = emission
    intensity = strength * _luminance((color_r, color_g, color_b))
    if intensity <= 0.0:
        return

    cam_pos = cam_inv @ obj.matrix_world.translation
    px = cam_pos.x * 1000
    py = cam_pos.y * 1000
    pz = cam_pos.z * 1000
    if pz > 0:
        return

    # Estimate radius from object dimensions (world-space bounding box)
    dims = obj.dimensions
    radius = max(dims.x, dims.y, dims.z) * 0.5 * 1000

    lights.append({
        "type": 0,
        "pos": (px, py, pz),
        "dir": (0.0, 0.0, 0.0),
        "intensity": intensity,
        "radius": radius,
    })


def _get_mesh_emission(obj):
    """Extract emission (strength, r, g, b) from an object's materials.

    Checks for Emission shader nodes and Principled BSDF emission.
    Returns the brightest emission found, or None.
    """
    best = None
    best_intensity = 0.0

    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            strength = 0.0
            color = (1.0, 1.0, 1.0)

            if node.type == 'EMISSION':
                color = _socket_default(node.inputs['Color'], (1.0, 1.0, 1.0))
                strength = _socket_default(node.inputs['Strength'], 1.0)

            elif node.type == 'BSDF_PRINCIPLED':
                strength = _socket_default(
                    node.inputs.get('Emission Strength'), 0.0)
                if strength <= 0.0:
                    continue
                color = _socket_default(
                    node.inputs.get('Emission Color'), (1.0, 1.0, 1.0))

            else:
                continue

            intensity = strength * _luminance(color)
            if intensity > best_intensity:
                best_intensity = intensity
                best = (strength, color[0], color[1], color[2])

    return best


def _socket_default(socket, fallback):
    """Get a socket's default value, or fallback if socket is None."""
    if socket is None:
        return fallback
    val = socket.default_value
    if hasattr(val, '__len__'):
        return tuple(val)[:len(fallback)] if hasattr(fallback, '__len__') else val
    return float(val)


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
