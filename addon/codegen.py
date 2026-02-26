"""Generate OSL shader source from template and lens prescriptions."""

from pathlib import Path

from .lenses import MAX_SURFACES, load_lenses
from .scene_lights import generate_load_scene_lights

N_EXTRA = 8

_COATING_VALUES = {"none": 0.0, "single": 1.0, "multi": 2.0}
_TYPE_VALUES = {"spherical": 0, "flat": 1, "stop": 2, "aspheric": 3, "cylindrical_x": 4, "cylindrical_y": 5}


def _format_surface_assignments(
    surfaces: list[dict], surface_types: list[str], focus: dict | None
) -> str:
    """Generate OSL assignment lines for one lens's surface data."""
    # Build close-focus thickness lookup from focus data
    close_thicknesses = {}
    if focus is not None:
        for v in focus["variables"]:
            close_thicknesses[v["surface"]] = v["thickness_close"]

    lines = []
    for i, s in enumerate(surfaces):
        idx = f"[{i}]"
        lines.append(
            f"    radii{idx:<4} = {s['radius']:>8};  "
            f"thicknesses{idx:<4} = {s['thickness']:>6};  "
            f"iors{idx:<4} = {s['ior']};  "
            f"apertures{idx:<4} = {s['aperture']};  "
            f"abbe_v{idx:<4} = {s['abbe_v']};"
        )
    lines.append("")
    for i, s in enumerate(surfaces):
        close_val = close_thicknesses.get(i, s["thickness"])
        lines.append(f"    thicknesses_close[{i}] = {close_val};")
    lines.append("")
    for i, st in enumerate(surface_types):
        lines.append(
            f"    surface_types[{i}] = {_TYPE_VALUES[st]};"
        )
    lines.append("")
    for i, s in enumerate(surfaces):
        base = i * N_EXTRA
        k = s.get("conic", 0.0)
        coeffs = s.get("aspheric_coeffs", [0.0, 0.0, 0.0])
        a10 = coeffs[3] if len(coeffs) >= 4 else 0.0
        lines.append(
            f"    extra[{base}] = {k};  "
            f"extra[{base + 1}] = {coeffs[0]};  "
            f"extra[{base + 2}] = {coeffs[1]};  "
            f"extra[{base + 3}] = {coeffs[2]};"
        )
        lines.append(
            f"    extra[{base + 4}] = {a10};  "
            f"extra[{base + 5}] = 0.0;  "
            f"extra[{base + 6}] = 0.0;  "
            f"extra[{base + 7}] = 0.0;"
        )
    return "\n".join(lines)


def _generate_load_lens_data(lens: dict) -> str:
    """Generate the #define and load_lens_data() function for a single lens."""
    max_extra = MAX_SURFACES * N_EXTRA
    coating_val = _COATING_VALUES[lens["coating"]]
    focus = lens.get("focus")
    close_dist = focus["close_distance"] if focus else 0.0

    lines = [
        f"#define MAX_SURFACES {MAX_SURFACES}",
        f"#define N_EXTRA {N_EXTRA}",
        f"#define MAX_EXTRA {max_extra}",
        "",
        "#define SURFACE_SPHERICAL     0",
        "#define SURFACE_FLAT          1",
        "#define SURFACE_STOP          2",
        "#define SURFACE_ASPHERIC      3",
        "#define SURFACE_CYLINDRICAL_X 4",
        "#define SURFACE_CYLINDRICAL_Y 5",
        "",
        "// extra[i*N_EXTRA + 0] = k (conic constant)",
        "// extra[i*N_EXTRA + 1] = A4 (4th-order aspheric coefficient)",
        "// extra[i*N_EXTRA + 2] = A6 (6th-order aspheric coefficient)",
        "// extra[i*N_EXTRA + 3] = A8 (8th-order aspheric coefficient)",
        "// extra[i*N_EXTRA + 4] = A10 (10th-order aspheric coefficient)",
        "// extra[i*N_EXTRA + 5..7] = reserved",
        "",
        "void load_lens_data(",
        "    output float radii[MAX_SURFACES],",
        "    output float thicknesses[MAX_SURFACES],",
        "    output float iors[MAX_SURFACES],",
        "    output float apertures[MAX_SURFACES],",
        "    output float abbe_v[MAX_SURFACES],",
        "    output int surface_types[MAX_SURFACES],",
        "    output float extra[MAX_EXTRA],",
        "    output float thicknesses_close[MAX_SURFACES],",
        "    output float focus_close_distance,",
        "    output int num_surfaces,",
        "    output float coating,",
        "    output float squeeze)",
        "{",
        f"    // {lens['name']}",
        f"    num_surfaces = {len(lens['surfaces'])};",
        f"    coating = {coating_val};",
        f"    squeeze = {float(lens['squeeze'])};",
        f"    focus_close_distance = {close_dist};",
        _format_surface_assignments(
            lens["surfaces"], lens["surface_types"], focus
        ),
        "}",
    ]
    return "\n".join(lines)


def load_osl_template(
    template_path: Path, lens_dir: Path
) -> tuple[str, list[dict]]:
    """Load the OSL template and lens registry.

    Returns (template_text, lenses) where template_text has both
    {{LENS_DATA}} and {{SCENE_LIGHTS}} placeholders intact.
    """
    lenses = load_lenses(lens_dir)
    if not lenses:
        raise ValueError(f"No .toml lens files found in {lens_dir}")

    template = template_path.read_text()
    return template, lenses


def build_camera_osl(template: str, lens: dict, lights=None) -> str:
    """Build final OSL source for a single camera.

    Injects single-lens data into {{LENS_DATA}} and scene lights into
    {{SCENE_LIGHTS}}.
    """
    lens_data_block = _generate_load_lens_data(lens)
    lights_block = generate_load_scene_lights(lights or [])
    osl = template.replace("// {{LENS_DATA}}", lens_data_block)
    osl = osl.replace("// {{SCENE_LIGHTS}}", lights_block)
    return osl
