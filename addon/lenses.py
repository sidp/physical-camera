"""Load lens prescriptions from TOML files."""

import tomllib
from pathlib import Path

MAX_SURFACES = 24
VALID_SURFACE_TYPES = ("spherical", "flat", "stop")


def _infer_surface_types(
    surfaces: list[dict], stop_index: int, filename: str
) -> list[str]:
    """Infer or validate the type field for each surface."""
    types = []
    for i, s in enumerate(surfaces):
        explicit = s.get("type")
        if explicit is not None:
            if explicit not in VALID_SURFACE_TYPES:
                raise ValueError(
                    f"{filename}: surface {i} type {explicit!r} must be one "
                    f"of {VALID_SURFACE_TYPES}"
                )
            if explicit == "stop" and i != stop_index:
                raise ValueError(
                    f"{filename}: surface {i} has type='stop' but "
                    f"stop_index is {stop_index}"
                )
            types.append(explicit)
        elif i == stop_index and s["radius"] == 0:
            types.append("stop")
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
        stop_index = lens["stop_index"]
        if not (0 <= stop_index < len(surfaces)):
            raise ValueError(
                f"{toml_path.name}: stop_index {stop_index} is out of range "
                f"for {len(surfaces)} surfaces"
            )
        coating = lens.get("coating", "none")
        valid_coatings = ("none", "single", "multi")
        if coating not in valid_coatings:
            raise ValueError(
                f"{toml_path.name}: coating {coating!r} must be one of "
                f"{valid_coatings}"
            )
        surface_types = _infer_surface_types(
            surfaces, stop_index, toml_path.name
        )
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
