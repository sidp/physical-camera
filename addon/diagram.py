"""Load pre-rendered lens diagram PNGs as Blender preview icons."""

from pathlib import Path

import bpy.utils.previews

_preview_collection = None


def load_previews(lenses):
    """Load pre-rendered PNG diagrams into a preview collection."""
    global _preview_collection
    _preview_collection = bpy.utils.previews.new()
    previews_dir = Path(__file__).parent / "previews"
    for i, lens in enumerate(lenses):
        key = f"lens_{i}"
        png_path = previews_dir / f"{lens['filename_stem']}.png"
        if png_path.exists():
            _preview_collection.load(key, str(png_path), 'IMAGE')


def has_previews():
    """Return whether any diagram previews are loaded."""
    return bool(_preview_collection)


def get_icon_id(lens_index):
    """Return the preview icon_id for a given lens index, or 0 if not ready."""
    if _preview_collection is None:
        return 0
    key = f"lens_{lens_index}"
    if key in _preview_collection:
        return _preview_collection[key].icon_id
    return 0


def cleanup():
    """Remove the preview collection."""
    global _preview_collection
    if _preview_collection is not None:
        bpy.utils.previews.remove(_preview_collection)
        _preview_collection = None
