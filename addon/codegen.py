"""Generate OSL shader source from template and lens prescriptions."""

from pathlib import Path

from .lenses import MAX_SURFACES, load_lenses

N_EXTRA = 4

_COATING_VALUES = {"none": 0.0, "single": 1.0, "multi": 2.0}
_TYPE_VALUES = {"spherical": 0, "flat": 1, "stop": 2}


def _format_surface_assignments(surfaces: list[dict], surface_types: list[str]) -> str:
    """Generate OSL assignment lines for one lens's surface data."""
    lines = []
    for i, s in enumerate(surfaces):
        idx = f"[{i}]"
        lines.append(
            f"        radii{idx:<4} = {s['radius']:>8};  "
            f"thicknesses{idx:<4} = {s['thickness']:>6};  "
            f"iors{idx:<4} = {s['ior']};  "
            f"apertures{idx:<4} = {s['aperture']};  "
            f"abbe_v{idx:<4} = {s['abbe_v']};"
        )
    lines.append("")
    for i, st in enumerate(surface_types):
        lines.append(
            f"        surface_types[{i}] = {_TYPE_VALUES[st]};"
        )
    lines.append("")
    for i in range(len(surfaces)):
        base = i * N_EXTRA
        lines.append(
            f"        extra[{base}] = 0.0;  "
            f"extra[{base + 1}] = 0.0;  "
            f"extra[{base + 2}] = 0.0;  "
            f"extra[{base + 3}] = 0.0;"
        )
    return "\n".join(lines)


def _generate_load_lens_data(lenses: list[dict]) -> str:
    """Generate the #define and load_lens_data() function."""
    max_extra = MAX_SURFACES * N_EXTRA
    lines = [
        f"#define MAX_SURFACES {MAX_SURFACES}",
        f"#define N_EXTRA {N_EXTRA}",
        f"#define MAX_EXTRA {max_extra}",
        "",
        "#define SURFACE_SPHERICAL 0",
        "#define SURFACE_FLAT      1",
        "#define SURFACE_STOP      2",
        "",
        "// extra[i*N_EXTRA + 0] = conic constant (future: aspheric surfaces)",
        "// extra[i*N_EXTRA + 1] = reserved (future: second radius for anamorphic)",
        "// extra[i*N_EXTRA + 2] = reserved",
        "// extra[i*N_EXTRA + 3] = reserved",
        "",
        "void load_lens_data(",
        "    int lens_type,",
        "    output float radii[MAX_SURFACES],",
        "    output float thicknesses[MAX_SURFACES],",
        "    output float iors[MAX_SURFACES],",
        "    output float apertures[MAX_SURFACES],",
        "    output float abbe_v[MAX_SURFACES],",
        "    output int surface_types[MAX_SURFACES],",
        "    output float extra[MAX_EXTRA],",
        "    output int num_surfaces,",
        "    output float coating)",
        "{",
    ]

    for i, lens in enumerate(lenses):
        keyword = "if" if i == 0 else "else if"
        coating_val = _COATING_VALUES[lens["coating"]]
        lines.append(f"    {keyword} (lens_type == {i}) {{")
        lines.append(f"        // {lens['name']}")
        lines.append(f"        num_surfaces = {len(lens['surfaces'])};")
        lines.append(f"        coating = {coating_val};")
        lines.append(_format_surface_assignments(
            lens["surfaces"], lens["surface_types"]
        ))
        lines.append("    }")

    default = lenses[0]
    default_coating = _COATING_VALUES[default["coating"]]
    lines.append("    else {")
    lines.append(f"        // Fallback to {default['name']}")
    lines.append(f"        num_surfaces = {len(default['surfaces'])};")
    lines.append(f"        coating = {default_coating};")
    lines.append(_format_surface_assignments(
        default["surfaces"], default["surface_types"]
    ))
    lines.append("    }")

    lines.append("}")
    return "\n".join(lines)


def generate_osl(
    template_path: Path, lens_dir: Path
) -> tuple[str, list[dict]]:
    """Generate OSL source from template + TOML lenses. Returns (source, lenses)."""
    lenses = load_lenses(lens_dir)
    if not lenses:
        raise ValueError(f"No .toml lens files found in {lens_dir}")

    template = template_path.read_text()
    lens_data_block = _generate_load_lens_data(lenses)
    osl_source = template.replace("// {{LENS_DATA}}", lens_data_block)

    return osl_source, lenses
