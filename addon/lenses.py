"""Load lens prescriptions from TOML files."""

import tomllib
from pathlib import Path

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
        stop_index = lens["stop_index"]
        if not (0 <= stop_index < len(surfaces)):
            raise ValueError(
                f"{toml_path.name}: stop_index {stop_index} is out of range "
                f"for {len(surfaces)} surfaces"
            )
        lenses.append({
            "name": lens["name"],
            "filename_stem": toml_path.stem,
            "focal_length": lens["focal_length"],
            "max_fstop": lens["max_fstop"],
            "stop_index": stop_index,
            "surfaces": surfaces,
        })
    return lenses
