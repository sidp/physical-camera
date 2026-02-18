"""Generate OSL shader from template and TOML lens prescriptions."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

MAX_SURFACES = 24


def load_lenses(lens_dir: Path) -> list[dict]:
    """Read all .toml lens files from lens_dir, sorted by filename."""
    lenses = []
    for toml_path in sorted(lens_dir.glob("*.toml")):
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        lens = data["lens"]
        surfaces = data["surface"]
        if len(surfaces) > MAX_SURFACES:
            raise ValueError(
                f"{toml_path.name}: {len(surfaces)} surfaces exceeds "
                f"MAX_SURFACES ({MAX_SURFACES})"
            )
        lenses.append({
            "name": lens["name"],
            "focal_length": lens["focal_length"],
            "max_fstop": lens["max_fstop"],
            "stop_index": lens["stop_index"],
            "surfaces": surfaces,
        })
    return lenses


def _format_surface_assignments(surfaces: list[dict]) -> str:
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
    return "\n".join(lines)


def _generate_load_lens_data(lenses: list[dict]) -> str:
    """Generate the #define and load_lens_data() function."""
    lines = [
        f"#define MAX_SURFACES {MAX_SURFACES}",
        "",
        "void load_lens_data(",
        "    int lens_type,",
        "    output float radii[MAX_SURFACES],",
        "    output float thicknesses[MAX_SURFACES],",
        "    output float iors[MAX_SURFACES],",
        "    output float apertures[MAX_SURFACES],",
        "    output float abbe_v[MAX_SURFACES],",
        "    output int num_surfaces,",
        "    output int stop_index)",
        "{",
    ]

    for i, lens in enumerate(lenses):
        keyword = "if" if i == 0 else "else if"
        lines.append(f"    {keyword} (lens_type == {i}) {{")
        lines.append(f"        // {lens['name']}")
        lines.append(f"        num_surfaces = {len(lens['surfaces'])};")
        lines.append(f"        stop_index = {lens['stop_index']};")
        lines.append(_format_surface_assignments(lens["surfaces"]))
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
