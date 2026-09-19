"""Primitives: the geometry §3.3 asks for, as scene elements rather than as SVG strings.

Every function here returns an element dict ready to hand to `model.add`. Nothing draws,
nothing renders, nothing touches a file -- a primitive is a value, which is what lets the
whole family be tested by measuring what it produces rather than by looking at it.

**Curves are cubics, always.** An ellipse is four cubics, an arc is one cubic per quarter
turn or less, a rounded corner is a cubic. The scene format has one spelling of a curve
(§`docs/scene-format.md`), so the conversion happens here, once, instead of in every measure
that would otherwise have to understand arcs.
"""
import math

__all__ = ["line", "polyline", "rect", "ellipse", "circle", "polygon", "star", "arc",
           "through", "path", "region", "group", "text", "arrowhead", "bracket",
           "KAPPA"]

#: The magic number that makes four cubics into an ellipse: 4/3·(√2 − 1). The resulting
#: curve's radial error is about 0.027% of the radius -- far below the resolution of
#: anything printed, and stated because it is an approximation and not an identity.
KAPPA = 4.0 / 3.0 * (math.sqrt(2.0) - 1.0)


def _el(name, kind, geometry, role=None, style=None, **extra):
    out = {"name": name, "type": kind, "geometry": geometry}
    if role:
        out["role"] = role
    if style:
        out["style"] = dict(style)
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def path(name, segments, closed=False, role=None, style=None, **extra):
    """An element from raw segments, for geometry the helpers below do not cover."""
    g = {"kind": "path", "d": list(segments)}
    if closed:
        g["closed"] = True
    return _el(name, "path", g, role, style, **extra)


def region(name, loops, fill_rule="evenodd", role=None, style=None, **extra):
    """A filled area with holes: the outer loop first, then each hole."""
    return _el(name, "region",
               {"kind": "region", "fill_rule": fill_rule, "loops": [list(l) for l in loops]},
               role, style, **extra)


def group(name, children=None, frame=None, role=None, **extra):
    out = {"name": name, "type": "group", "children": list(children or [])}
    if frame:
        out["frame"] = frame
    if role:
        out["role"] = role
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def text(name, string, at, family="Helvetica", size=10, align="start",
         baseline="alphabetic", role=None, style=None, **extra):
    """A text run. The metrics are NOT taken here -- see `measure.text` and `fit`.

    `family` or `size` of None writes nothing, leaving the element to take them from its
    role. Writing them as literal ``None`` looked harmless and was not: a literal overrides a
    role, so a text element asking for `caption` came back with no font at all and measured
    as unmeasurable.
    """
    st = {k: v for k, v in (("font_family", family), ("font_size", size))
          if v is not None}
    st.update(style or {})
    return _el(name, "text",
               {"kind": "text", "text": string, "at": [float(at[0]), float(at[1])],
                "align": align, "baseline": baseline}, role, st or None, **extra)


# --------------------------------------------------------------------- straight things
def line(name, a, b, role=None, style=None, **extra):
    return path(name, [["M", float(a[0]), float(a[1])], ["L", float(b[0]), float(b[1])]],
                role=role, style=style, **extra)


def polyline(name, points, closed=False, role=None, style=None, **extra):
    pts = [(float(x), float(y)) for x, y in points]
    if not pts:
        raise ValueError("a polyline needs at least one point")
    segs = [["M", pts[0][0], pts[0][1]]] + [["L", x, y] for x, y in pts[1:]]
    if closed:
        segs.append(["Z"])
    return path(name, segs, closed=closed, role=role, style=style, **extra)


def rect(name, x, y, width, height, radius=0.0, role=None, style=None, **extra):
    """A rectangle, with optional corner rounding. `radius` is clamped to what fits."""
    if width <= 0 or height <= 0:
        raise ValueError(f"a rectangle needs a positive size, got {width}x{height}")
    r = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    x, y, w, h = float(x), float(y), float(width), float(height)
    if r <= 0:
        return polyline(name, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                        closed=True, role=role, style=style, **extra)
    k = r * KAPPA
    segs = [
        ["M", x + r, y],
        ["L", x + w - r, y],
        ["C", x + w - r + k, y, x + w, y + r - k, x + w, y + r],
        ["L", x + w, y + h - r],
        ["C", x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h],
        ["L", x + r, y + h],
        ["C", x + r - k, y + h, x, y + h - r + k, x, y + h - r],
        ["L", x, y + r],
        ["C", x, y + r - k, x + r - k, y, x + r, y],
        ["Z"],
    ]
    return path(name, segs, closed=True, role=role, style=style, **extra)


def polygon(name, cx, cy, radius, sides, rotation=0.0, role=None, style=None, **extra):
    """A regular polygon, first vertex at `rotation` radians from the +x axis."""
    if sides < 3:
        raise ValueError(f"a polygon needs at least 3 sides, got {sides}")
    pts = [(cx + radius * math.cos(rotation + 2 * math.pi * i / sides),
            cy + radius * math.sin(rotation + 2 * math.pi * i / sides))
           for i in range(sides)]
    return polyline(name, pts, closed=True, role=role, style=style, **extra)


def star(name, cx, cy, outer, inner, points=5, rotation=-math.pi / 2, role=None,
         style=None, **extra):
    if points < 2:
        raise ValueError(f"a star needs at least 2 points, got {points}")
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = rotation + math.pi * i / points
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return polyline(name, pts, closed=True, role=role, style=style, **extra)


# --------------------------------------------------------------------- round things
def _arc_segments(cx, cy, rx, ry, start, sweep, rotation=0.0):
    """An elliptical arc as cubics, at most a quarter turn each."""
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 2) - 1e-9)))
    step = sweep / n
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    cosr, sinr = math.cos(rotation), math.sin(rotation)

    def at(a):
        x, y = rx * math.cos(a), ry * math.sin(a)
        return (cx + x * cosr - y * sinr, cy + x * sinr + y * cosr)

    def d_at(a):
        x, y = -rx * math.sin(a), ry * math.cos(a)
        return (x * cosr - y * sinr, x * sinr + y * cosr)

    out = []
    a = start
    p = at(a)
    for _i in range(n):
        b = a + step
        q = at(b)
        da, db = d_at(a), d_at(b)
        out.append(["C", p[0] + k * da[0], p[1] + k * da[1],
                    q[0] - k * db[0], q[1] - k * db[1], q[0], q[1]])
        a, p = b, q
    return at(start), out


def arc(name, cx, cy, radius, start_deg, end_deg, ry=None, rotation_deg=0.0,
        role=None, style=None, **extra):
    """An open arc. Angles in degrees, counter-clockwise, 0 at the +x axis."""
    start = math.radians(start_deg)
    sweep = math.radians(end_deg - start_deg)
    p0, segs = _arc_segments(cx, cy, radius, ry if ry is not None else radius, start,
                             sweep, math.radians(rotation_deg))
    return path(name, [["M", p0[0], p0[1]]] + segs, role=role, style=style, **extra)


def ellipse(name, cx, cy, rx, ry, rotation_deg=0.0, role=None, style=None, **extra):
    """A closed ellipse, as four cubics."""
    if rx <= 0 or ry <= 0:
        raise ValueError(f"an ellipse needs positive radii, got {rx}x{ry}")
    p0, segs = _arc_segments(cx, cy, rx, ry, 0.0, 2 * math.pi, math.radians(rotation_deg))
    return path(name, [["M", p0[0], p0[1]]] + segs + [["Z"]], closed=True, role=role,
                style=style, **extra)


def circle(name, cx, cy, radius, role=None, style=None, **extra):
    return ellipse(name, cx, cy, radius, radius, role=role, style=style, **extra)


# --------------------------------------------------------------------- interpolation
def through(name, points, tension=0.5, closed=False, role=None, style=None, **extra):
    """A smooth curve passing THROUGH every point, Catmull-Rom converted to cubics.

    Passing through rather than near: a curve fitted to data must hit the data. `tension`
    0 gives straight lines between the points and 1 a very loose curve; 0.5 is the usual
    Catmull-Rom.
    """
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        raise ValueError("a curve through points needs at least two of them")
    if closed:
        ring = pts + pts[:1]
    else:
        ring = pts
    segs = [["M", ring[0][0], ring[0][1]]]
    n = len(ring)
    for i in range(n - 1):
        p0 = ring[i - 1] if i > 0 else (ring[-2] if closed else ring[0])
        p1, p2 = ring[i], ring[i + 1]
        p3 = ring[i + 2] if i + 2 < n else (ring[1] if closed else ring[-1])
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3.0,
              p1[1] + (p2[1] - p0[1]) * tension / 3.0)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3.0,
              p2[1] - (p3[1] - p1[1]) * tension / 3.0)
        segs.append(["C", c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]])
    if closed:
        segs.append(["Z"])
    return path(name, segs, closed=closed, role=role, style=style, **extra)


# --------------------------------------------------------------------- furniture
def arrowhead(name, tip, direction, size=3.0, spread_deg=22.0, filled=True, role=None,
              style=None, **extra):
    """An arrowhead at `tip`, pointing along `direction`.

    A catalogue entry rather than a marker attribute: as geometry it can be measured,
    collided with and moved by a relation, which an SVG `marker-end` cannot.
    """
    dx, dy = float(direction[0]), float(direction[1])
    n = math.hypot(dx, dy)
    if n < 1e-12:
        raise ValueError("an arrowhead needs a direction with a length")
    dx, dy = dx / n, dy / n
    a = math.radians(spread_deg)
    back = math.atan2(-dy, -dx)
    p1 = (tip[0] + size * math.cos(back - a), tip[1] + size * math.sin(back - a))
    p2 = (tip[0] + size * math.cos(back + a), tip[1] + size * math.sin(back + a))
    pts = [(float(tip[0]), float(tip[1])), p1, p2]
    if filled:
        return region(name, [[["M", pts[0][0], pts[0][1]],
                              ["L", pts[1][0], pts[1][1]],
                              ["L", pts[2][0], pts[2][1]], ["Z"]]],
                      role=role, style=style, **extra)
    return polyline(name, [p1, pts[0], p2], role=role, style=style, **extra)


def bracket(name, a, b, depth=2.0, role=None, style=None, **extra):
    """A square bracket spanning a to b, opening towards the side `depth` points."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n < 1e-12:
        raise ValueError("a bracket needs two distinct ends")
    nx, ny = -dy / n * depth, dx / n * depth
    return polyline(name, [(ax + nx, ay + ny), (ax, ay), (bx, by), (bx + nx, by + ny)],
                    role=role, style=style, **extra)
