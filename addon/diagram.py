"""Render lens cross-section diagrams into Blender preview icons."""

import math

import bpy.utils.previews

_preview_collection = None
_ICON_SIZE = 256
_SUPERSAMPLE = 2
_RENDER_SIZE = _ICON_SIZE * _SUPERSAMPLE
_PADDING = 24 * _SUPERSAMPLE
_GLASS_FILL = (0.5, 0.7, 0.9, 0.35)
_SURFACE_LINE = (0.85, 0.85, 0.85, 1.0)
_CEMENTED_LINE = (0.65, 0.65, 0.65, 0.6)
_STOP_COLOR = (0.85, 0.85, 0.85, 1.0)
_AXIS_COLOR = (0.5, 0.5, 0.5, 0.35)


def _compute_vertex_positions(surfaces):
    """Accumulate thicknesses to get each surface's z position along the axis."""
    positions = [0.0]
    for s in surfaces[:-1]:
        positions.append(positions[-1] + s["thickness"])
    return positions


def _find_elements(surfaces):
    """Group consecutive surfaces into glass elements based on ior > 1."""
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
    """Compute x position on a spherical arc at height y."""
    if radius == 0.0:
        return vertex_x
    center_x = vertex_x + radius
    r_sq = radius * radius
    y_sq = y * y
    if y_sq >= r_sq:
        return vertex_x
    return center_x - math.copysign(math.sqrt(r_sq - y_sq), radius)


def _blend_pixel(buf, idx, color):
    """Alpha-composite color onto existing pixel in buffer."""
    sr, sg, sb, sa = color
    dr, dg, db, da = buf[idx], buf[idx + 1], buf[idx + 2], buf[idx + 3]
    out_a = sa + da * (1.0 - sa)
    if out_a < 1e-6:
        return
    buf[idx] = (sr * sa + dr * da * (1.0 - sa)) / out_a
    buf[idx + 1] = (sg * sa + dg * da * (1.0 - sa)) / out_a
    buf[idx + 2] = (sb * sa + db * da * (1.0 - sa)) / out_a
    buf[idx + 3] = out_a


def _draw_line(buf, x0, y0, x1, y1, color, width=1.0):
    """Draw a line with coverage-based anti-aliasing."""
    size = _RENDER_SIZE
    dx = x1 - x0
    dy = y1 - y0
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.5:
        return
    steps = max(int(length * 2), 1)
    half_w = width * 0.5
    r = int(half_w + 1.5)
    for i in range(steps + 1):
        t = i / steps
        px = x0 + dx * t
        py = y0 + dy * t
        ix, iy = int(px), int(py)
        for oy in range(-r, r + 1):
            sy = iy + oy
            if not (0 <= sy < size):
                continue
            for ox in range(-r, r + 1):
                sx = ix + ox
                if not (0 <= sx < size):
                    continue
                dist = math.sqrt((sx - px) ** 2 + (sy - py) ** 2)
                coverage = max(0.0, min(1.0, half_w + 0.5 - dist))
                if coverage > 0:
                    c = (color[0], color[1], color[2], color[3] * coverage)
                    _blend_pixel(buf, (sy * size + sx) * 4, c)


def _draw_arc(buf, vertex_x, radius, semi_ap, to_px, color, width=1.0):
    """Draw a surface arc from -semi_ap to +semi_ap."""
    steps = 64
    for i in range(steps):
        y0 = -semi_ap + (2 * semi_ap) * i / steps
        y1 = -semi_ap + (2 * semi_ap) * (i + 1) / steps
        ax0 = _arc_x(vertex_x, radius, y0)
        ax1 = _arc_x(vertex_x, radius, y1)
        px0, py0 = to_px(ax0, y0)
        px1, py1 = to_px(ax1, y1)
        _draw_line(buf, px0, py0, px1, py1, color, width)


def _fill_element(buf, surfaces, positions, front_i, back_i, to_px, scale):
    """Scanline-fill a glass element between its front and back surface arcs."""
    size = _RENDER_SIZE
    front_s = surfaces[front_i]
    back_s = surfaces[back_i]
    front_vx = positions[front_i]
    back_vx = positions[back_i]
    front_r = front_s["radius"]
    back_r = back_s["radius"]
    front_ap = front_s["aperture"] * 0.5
    back_ap = back_s["aperture"] * 0.5
    max_ap = max(front_ap, back_ap)

    # Closing edge tip positions for interpolation in the tapered zone
    front_tip_x_pos = _arc_x(front_vx, front_r, front_ap)
    back_tip_x_pos = _arc_x(back_vx, back_r, back_ap)
    front_tip_x_neg = _arc_x(front_vx, front_r, -front_ap)
    back_tip_x_neg = _arc_x(back_vx, back_r, -back_ap)

    for py in range(size):
        lens_y = ((size - 1 - py) - (size - 1) * 0.5) / scale
        abs_y = abs(lens_y)
        if abs_y > max_ap:
            continue

        if abs_y <= front_ap and abs_y <= back_ap:
            x_a = _arc_x(front_vx, front_r, lens_y)
            x_b = _arc_x(back_vx, back_r, lens_y)
        elif abs_y <= front_ap:
            # Back arc ended; interpolate closing edge for that side
            x_a = _arc_x(front_vx, front_r, lens_y)
            t = (abs_y - back_ap) / (front_ap - back_ap)
            if lens_y >= 0:
                x_b = back_tip_x_pos + t * (front_tip_x_pos - back_tip_x_pos)
            else:
                x_b = back_tip_x_neg + t * (front_tip_x_neg - back_tip_x_neg)
        else:
            # Front arc ended; interpolate closing edge for that side
            x_b = _arc_x(back_vx, back_r, lens_y)
            t = (abs_y - front_ap) / (back_ap - front_ap)
            if lens_y >= 0:
                x_a = front_tip_x_pos + t * (back_tip_x_pos - front_tip_x_pos)
            else:
                x_a = front_tip_x_neg + t * (back_tip_x_neg - front_tip_x_neg)

        px_a, _ = to_px(x_a, lens_y)
        px_b, _ = to_px(x_b, lens_y)
        px_left, px_right = (px_a, px_b) if px_a <= px_b else (px_b, px_a)
        left = max(0, int(px_left))
        right = min(size - 1, int(px_right))
        for px in range(left, right + 1):
            _blend_pixel(buf, (py * size + px) * 4, _GLASS_FILL)


def _downsample(buf):
    """Box-filter downsample from _RENDER_SIZE to _ICON_SIZE."""
    ss = _SUPERSAMPLE
    out_size = _ICON_SIZE
    in_size = _RENDER_SIZE
    out = [0.0] * (out_size * out_size * 4)
    inv = 1.0 / (ss * ss)
    for oy in range(out_size):
        for ox in range(out_size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    idx = ((oy * ss + sy) * in_size + (ox * ss + sx)) * 4
                    pa = buf[idx + 3]
                    r += buf[idx] * pa
                    g += buf[idx + 1] * pa
                    b += buf[idx + 2] * pa
                    a += pa
            oi = (oy * out_size + ox) * 4
            a_avg = a * inv
            if a_avg > 1e-6:
                out[oi] = (r * inv) / a_avg
                out[oi + 1] = (g * inv) / a_avg
                out[oi + 2] = (b * inv) / a_avg
            out[oi + 3] = a_avg
    return out


def _render_lens(surfaces):
    """Render a single lens diagram, supersampled and downsampled."""
    size = _RENDER_SIZE
    buf = [0.0] * (size * size * 4)

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
        return px, py

    # Optical axis
    _draw_line(buf, _PADDING * 0.5, y_center, size - _PADDING * 0.5, y_center,
               _AXIS_COLOR, 1.0 * _SUPERSAMPLE)

    # Fill glass elements (per consecutive surface pair within each element)
    for front_i, back_i in elements:
        for j in range(front_i, back_i):
            _fill_element(buf, surfaces, positions, j, j + 1, to_px, scale)

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
            _draw_arc(buf, positions[i], s["radius"], semi_ap, to_px,
                      _CEMENTED_LINE, 1.5 * _SUPERSAMPLE)
        else:
            _draw_arc(buf, positions[i], s["radius"], semi_ap, to_px,
                      _SURFACE_LINE, 2.0 * _SUPERSAMPLE)

    # Draw element closing edges per consecutive surface pair
    for front_i, back_i in elements:
        for j in range(front_i, back_i):
            s_j = surfaces[j]
            s_j1 = surfaces[j + 1]
            ap_j = s_j["aperture"] * 0.5
            ap_j1 = s_j1["aperture"] * 0.5
            for sign in (1.0, -1.0):
                x_j = _arc_x(positions[j], s_j["radius"], sign * ap_j)
                x_j1 = _arc_x(positions[j + 1], s_j1["radius"],
                              sign * ap_j1)
                px0, py0 = to_px(x_j, sign * ap_j)
                px1, py1 = to_px(x_j1, sign * ap_j1)
                _draw_line(buf, px0, py0, px1, py1, _SURFACE_LINE,
                           2.0 * _SUPERSAMPLE)

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
                _draw_line(buf, px_stop, py_outer, px_stop, py_ap,
                           _STOP_COLOR, 2.0 * _SUPERSAMPLE)
                _, py_notch = to_px(0, sign * (semi_ap - notch))
                _draw_line(buf, px_stop, py_ap, px_stop, py_notch,
                           _STOP_COLOR, 3.5 * _SUPERSAMPLE)

    return _downsample(buf)


def generate_previews(lenses):
    """Pre-render lens diagrams into a preview collection."""
    global _preview_collection
    _preview_collection = bpy.utils.previews.new()
    for i, lens in enumerate(lenses):
        key = f"lens_{i}"
        preview = _preview_collection.new(key)
        preview.image_size = (_ICON_SIZE, _ICON_SIZE)
        buf = _render_lens(lens["surfaces"])
        preview.image_pixels_float[:] = buf


def get_icon_id(lens_index):
    """Return the preview icon_id for a given lens index."""
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
