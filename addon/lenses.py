"""Load lens prescriptions from TOML files."""

import tomllib
from pathlib import Path

MAX_SURFACES = 24
VALID_SURFACE_TYPES = ("spherical", "flat", "stop")


def _resolve_surface_types(surfaces: list[dict], filename: str) -> list[str]:
    """Resolve the type for each surface from explicit or inferred values."""
    types = []
    for i, s in enumerate(surfaces):
        explicit = s.get("type")
        if explicit is not None:
            if explicit not in VALID_SURFACE_TYPES:
                raise ValueError(
                    f"{filename}: surface {i} type {explicit!r} must be one "
                    f"of {VALID_SURFACE_TYPES}"
                )
            types.append(explicit)
        elif s["radius"] == 0:
            types.append("flat")
        else:
            types.append("spherical")
    return types


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
        coating = lens.get("coating", "none")
        valid_coatings = ("none", "single", "multi")
        if coating not in valid_coatings:
            raise ValueError(
                f"{toml_path.name}: coating {coating!r} must be one of "
                f"{valid_coatings}"
            )
        surface_types = _resolve_surface_types(surfaces, toml_path.name)
        stop_count = surface_types.count("stop")
        if stop_count != 1:
            raise ValueError(
                f"{toml_path.name}: expected exactly 1 stop surface, "
                f"found {stop_count}"
            )
        stop_index = surface_types.index("stop")
        lenses.append({
            "name": lens["name"],
            "filename_stem": toml_path.stem,
            "focal_length": lens["focal_length"],
            "max_fstop": lens["max_fstop"],
            "stop_index": stop_index,
            "coating": coating,
            "surfaces": surfaces,
            "surface_types": surface_types,
        })
    return lenses
