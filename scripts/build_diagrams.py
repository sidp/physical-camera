"""Generate lens diagram PNGs from TOML lens prescriptions using Pillow."""
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_ADDON_DIR = Path(__file__).resolve().parent.parent / "addon"

# Add addon/ to sys.path so we can import lenses directly,
# bypassing addon/__init__.py which requires bpy
sys.path.insert(0, str(_ADDON_DIR))
from lenses import load_lenses

_ICON_SIZE = 256
_SUPERSAMPLE = 2
_RENDER_SIZE = _ICON_SIZE * _SUPERSAMPLE
_PADDING = 24 * _SUPERSAMPLE
_BG_COLOR = (0, 0, 0, 0)
_GLASS_FILL = (128, 179, 230, 89)
_SURFACE_LINE = (217, 217, 217, 255)
_CEMENTED_LINE = (166, 166, 166, 153)
_STOP_COLOR = (217, 217, 217, 255)
_AXIS_COLOR = (128, 128, 128, 89)


def _compute_vertex_positions(surfaces):
    positions = [0.0]
    for s in surfaces[:-1]:
        positions.append(positions[-1] + s["thickness"])
    return positions


def _find_elements(surfaces):
    elements = []
    start = None
    for i, s in enumerate(surfaces):
        if s["ior"] > 1.0:
            if start is None:
                start = i
        else:
            if start is not None:
                elements.append((start, i))
                start = None
    if start is not None:
        elements.append((start, len(surfaces) - 1))
    return elements


def _arc_x(vertex_x, radius, y):
    if radius == 0.0:
        return vertex_x
    center_x = vertex_x + radius
    r_sq = radius * radius
    y_sq = y * y
    if y_sq >= r_sq:
        return vertex_x
    return center_x - math.copysign(math.sqrt(r_sq - y_sq), radius)


def _arc_points(vertex_x, radius, semi_ap, to_px, steps=64):
    """Return list of pixel (x, y) tuples along an arc."""
    points = []
    for i in range(steps + 1):
        y = -semi_ap + (2 * semi_ap) * i / steps
        x = _arc_x(vertex_x, radius, y)
        points.append(to_px(x, y))
    return points


def _element_polygon(surfaces, positions, front_i, back_i, to_px):
    """Build a polygon outline for a glass element between two surfaces."""
    front_s = surfaces[front_i]
    back_s = surfaces[back_i]
    front_vx = positions[front_i]
    back_vx = positions[back_i]
    front_r = front_s["radius"]
    back_r = back_s["radius"]
    front_ap = front_s["aperture"] * 0.5
    back_ap = back_s["aperture"] * 0.5

    # Front arc from -front_ap to +front_ap
    front_pts = _arc_points(front_vx, front_r, front_ap, to_px)
    # Back arc from -back_ap to +back_ap
    back_pts = _arc_points(back_vx, back_r, back_ap, to_px)

    # Polygon: front arc top-to-bottom, closing edge to back bottom,
    # back arc bottom-to-top, closing edge to front top
    polygon = list(front_pts)
    polygon.append(back_pts[-1])
    polygon.extend(reversed(back_pts))
    polygon.append(front_pts[0])

    return polygon


def _draw_arc(draw, vertex_x, radius, semi_ap, to_px, color, width):
    points = _arc_points(vertex_x, radius, semi_ap, to_px)
    draw.line(points, fill=color, width=width)


def _render_lens(surfaces):
    size = _RENDER_SIZE
    img = Image.new("RGBA", (size, size), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    positions = _compute_vertex_positions(surfaces)
    elements = _find_elements(surfaces)

    total_length = positions[-1]
    max_aperture = max(s["aperture"] for s in surfaces) * 0.5

    draw_w = size - 2 * _PADDING
    draw_h = size - 2 * _PADDING
    scale_x = draw_w / total_length if total_length > 0 else 1.0
    scale_y = draw_h / (2 * max_aperture) if max_aperture > 0 else 1.0
    scale = min(scale_x, scale_y)

    x_offset = _PADDING + (draw_w - total_length * scale) * 0.5
    y_center = size * 0.5

    def to_px(lens_x, lens_y):
        px = x_offset + lens_x * scale
        py = y_center - lens_y * scale
        return (px, py)

    # Optical axis
    draw.line(
        [(_PADDING * 0.5, y_center), (size - _PADDING * 0.5, y_center)],
        fill=_AXIS_COLOR,
        width=1 * _SUPERSAMPLE,
    )

    # Fill glass elements
    for front_i, back_i in elements:
        for j in range(front_i, back_i):
            poly = _element_polygon(surfaces, positions, j, j + 1, to_px)
            draw.polygon(poly, fill=_GLASS_FILL)

    # Draw surface arcs
    for i, s in enumerate(surfaces):
        if s["radius"] == 0.0 and s["ior"] <= 1.0:
            continue
        semi_ap = s["aperture"] * 0.5
        is_cemented = False
        for front_i, back_i in elements:
            if front_i < i < back_i:
                is_cemented = True
                break
        if is_cemented:
            _draw_arc(draw, positions[i], s["radius"], semi_ap, to_px,
                       _CEMENTED_LINE, 2 * _SUPERSAMPLE)
        else:
            _draw_arc(draw, positions[i], s["radius"], semi_ap, to_px,
                       _SURFACE_LINE, 2 * _SUPERSAMPLE)

    # Draw element closing edges
    for front_i, back_i in elements:
        for j in range(front_i, back_i):
            s_j = surfaces[j]
            s_j1 = surfaces[j + 1]
            ap_j = s_j["aperture"] * 0.5
            ap_j1 = s_j1["aperture"] * 0.5
            for sign in (1.0, -1.0):
                p0 = to_px(
                    _arc_x(positions[j], s_j["radius"], sign * ap_j),
                    sign * ap_j,
                )
                p1 = to_px(
                    _arc_x(positions[j + 1], s_j1["radius"], sign * ap_j1),
                    sign * ap_j1,
                )
                draw.line([p0, p1], fill=_SURFACE_LINE, width=2 * _SUPERSAMPLE)

    # Draw aperture stop
    for i, s in enumerate(surfaces):
        if s["radius"] == 0.0 and s["ior"] <= 1.0:
            stop_x = positions[i]
            semi_ap = s["aperture"] * 0.5
            notch = semi_ap * 0.15
            px_stop, _ = to_px(stop_x, 0)
            for sign in (1.0, -1.0):
                _, py_outer = to_px(0, sign * max_aperture)
                _, py_ap = to_px(0, sign * semi_ap)
                draw.line(
                    [(px_stop, py_outer), (px_stop, py_ap)],
                    fill=_STOP_COLOR,
                    width=2 * _SUPERSAMPLE,
                )
                _, py_notch = to_px(0, sign * (semi_ap - notch))
                draw.line(
                    [(px_stop, py_ap), (px_stop, py_notch)],
                    fill=_STOP_COLOR,
                    width=4 * _SUPERSAMPLE,
                )

    return img.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)


def main():
    lens_dir = _ADDON_DIR / "lenses"
    output_dir = _ADDON_DIR / "previews"
    output_dir.mkdir(exist_ok=True)

    lenses = load_lenses(lens_dir)
    for lens in lenses:
        img = _render_lens(lens["surfaces"])
        out_path = output_dir / f"{lens['filename_stem']}.png"
        img.save(out_path)
        print(f"  {out_path.name}")

    print(f"Generated {len(lenses)} diagrams in {output_dir}")


if __name__ == "__main__":
    main()
