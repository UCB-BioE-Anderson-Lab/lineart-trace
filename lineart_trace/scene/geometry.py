"""Curve arithmetic: what a path actually occupies, encloses and measures.

**Exact where exact is possible.** A cubic's extent, its enclosed area and its centroid all
have closed forms, and this module computes them rather than sampling. Sampling is the
tempting shortcut and it fails in the direction that hides: a flattened curve is always
*inside* the true shape, so a sampled bounding box is always slightly too small, an overlap
check built on it reports clearance that is not there, and nothing about the number looks
wrong.

Length is the exception -- a cubic's arc length has no elementary closed form -- so it is
computed by adaptive subdivision with a stated tolerance, which is bounded rather than
merely plausible.

Everything here works on scene segment runs (``[["M",x,y],["C",...],["Z"]]``) and knows
nothing about scenes, frames or units. That is deliberate: the unit-carrying layer is
:mod:`lineart_trace.scene.measure`, and geometry that knew about frames could not be tested
without building one.
"""
import math

__all__ = ["points_of", "to_cubics", "bounds", "length", "area", "centroid", "flatten",
           "point_at", "contains", "nearest_point", "segments_intersect", "polys_overlap"]


# --------------------------------------------------------------------- conversion
def points_of(run):
    """Every on- and off-curve point of a run, in order. The cheap, conservative reading."""
    out = []
    for s in run:
        nums = s[1:]
        for i in range(0, len(nums) - 1, 2):
            out.append((float(nums[i]), float(nums[i + 1])))
    return out


def to_cubics(run, close=False):
    """A run as a list of ``(p0, p1, p2, p3)`` cubics. A line becomes a degenerate cubic.

    One representation downstream, so every measure below handles one case. The closing
    segment of a closed run is materialised here rather than special-cased five times.
    """
    out, start, cur = [], None, None
    for s in run:
        verb, n = s[0], [float(x) for x in s[1:]]
        if verb == "M":
            start = cur = (n[0], n[1])
        elif verb == "L":
            p = (n[0], n[1])
            out.append((cur, _lerp(cur, p, 1 / 3), _lerp(cur, p, 2 / 3), p))
            cur = p
        elif verb == "C":
            p = (n[4], n[5])
            out.append((cur, (n[0], n[1]), (n[2], n[3]), p))
            cur = p
        elif verb == "Z":
            if cur and start and _dist(cur, start) > 1e-12:
                out.append((cur, _lerp(cur, start, 1 / 3), _lerp(cur, start, 2 / 3), start))
            cur = start
    if close and out and start and _dist(out[-1][3], start) > 1e-12:
        p, q = out[-1][3], start
        out.append((p, _lerp(p, q, 1 / 3), _lerp(p, q, 2 / 3), q))
    return out


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


# --------------------------------------------------------------------- power basis
def _power(p0, p1, p2, p3):
    """A cubic's coefficients ``(a, b, c, d)`` with ``P(t) = a t³ + b t² + c t + d``."""
    return (-p0 + 3 * p1 - 3 * p2 + p3, 3 * p0 - 6 * p1 + 3 * p2, -3 * p0 + 3 * p1, p0)


def _poly_mul(u, v):
    out = [0.0] * (len(u) + len(v) - 1)
    for i, a in enumerate(u):
        for j, b in enumerate(v):
            out[i + j] += a * b
    return out


def _poly_int01(c):
    """The definite integral of a polynomial (highest power first) over [0, 1]."""
    n = len(c) - 1
    return sum(a / (n - i + 1) for i, a in enumerate(c))


def _deriv(c):
    n = len(c) - 1
    return [a * (n - i) for i, a in enumerate(c[:-1])] or [0.0]


# --------------------------------------------------------------------- extent
def _cubic_bounds(p0, p1, p2, p3):
    """The exact extent of one cubic: its ends, plus any turning point inside (0, 1)."""
    lo = [min(p0[0], p3[0]), min(p0[1], p3[1])]
    hi = [max(p0[0], p3[0]), max(p0[1], p3[1])]
    for ax in (0, 1):
        a, b, c, _d = _power(p0[ax], p1[ax], p2[ax], p3[ax])
        # P'(t) = 3a t² + 2b t + c
        qa, qb, qc = 3 * a, 2 * b, c
        ts = []
        if abs(qa) < 1e-12:
            if abs(qb) > 1e-12:
                ts = [-qc / qb]
        else:
            disc = qb * qb - 4 * qa * qc
            if disc >= 0:
                r = math.sqrt(disc)
                ts = [(-qb + r) / (2 * qa), (-qb - r) / (2 * qa)]
        for t in ts:
            if 0.0 < t < 1.0:
                v = _at(p0[ax], p1[ax], p2[ax], p3[ax], t)
                lo[ax] = min(lo[ax], v)
                hi[ax] = max(hi[ax], v)
    return lo[0], lo[1], hi[0], hi[1]


def _at(a, b, c, d, t):
    mt = 1 - t
    return (mt ** 3) * a + 3 * (mt ** 2) * t * b + 3 * mt * (t ** 2) * c + (t ** 3) * d


def bounds(runs):
    """The TIGHT extent of one or more runs, as ``(x0, y0, x1, y1)``, or None if empty.

    Tight means the curve's own extent, not its control points'. A cubic lies inside the
    convex hull of its controls and generally does not touch it, so the hull is a bound that
    can be wrong by as much as the curvature -- fine as a rejection test, useless as an
    answer to "how big is this".
    """
    box = None
    for run in runs:
        for c in to_cubics(run):
            b = _cubic_bounds(*c)
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                         max(box[2], b[2]), max(box[3], b[3]))
        if not to_cubics(run):
            pts = points_of(run)
            for x, y in pts:
                b = (x, y, x, y)
                box = b if box is None else (min(box[0], x), min(box[1], y),
                                             max(box[2], x), max(box[3], y))
    return box


# --------------------------------------------------------------------- length
def _cubic_length(p0, p1, p2, p3, tol=1e-6, depth=0):
    """Arc length by adaptive subdivision, to `tol` relative.

    The control polygon bounds the arc from above and the chord from below, so the gap
    between them bounds the error; when it is small enough, Richardson's ``(2·chord +
    polygon) / 3`` is third-order accurate. A depth cap keeps a pathological cusp from
    recursing forever -- it returns the best estimate it has rather than raising, because a
    length that is slightly wrong beats a measurement tool that throws on a real curve.
    """
    chord = _dist(p0, p3)
    poly = _dist(p0, p1) + _dist(p1, p2) + _dist(p2, p3)
    if poly < 1e-15:
        return 0.0
    if depth >= 24 or (poly - chord) <= tol * poly:
        return (2.0 * chord + poly) / 3.0
    (l0, l1, l2, l3), (r0, r1, r2, r3) = _split(p0, p1, p2, p3, 0.5)
    return (_cubic_length(l0, l1, l2, l3, tol, depth + 1)
            + _cubic_length(r0, r1, r2, r3, tol, depth + 1))


def _split(p0, p1, p2, p3, t):
    a = _lerp(p0, p1, t)
    b = _lerp(p1, p2, t)
    c = _lerp(p2, p3, t)
    d = _lerp(a, b, t)
    e = _lerp(b, c, t)
    f = _lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def length(runs, tol=1e-6):
    """Total arc length of the runs."""
    return sum(_cubic_length(*c, tol=tol) for run in runs for c in to_cubics(run))


# --------------------------------------------------------------------- area, centroid
def _green(runs):
    """``(2A, 2·Mx, -2·My)`` accumulated exactly over every cubic, by polynomial integration.

    Green's theorem on each segment: the integrands are polynomials in t of degree at most
    8, and integrating a polynomial exactly is arithmetic. Sampling this is what makes an
    area quietly too small.

    With ``A = ½∮(x dy − y dx)``, the first moments are ``Mx = ½∮x² dy`` and
    ``My = −½∮y² dx``, so the centroid is ``(Mx/A, My/A)``.

    **The divisor is 2A, and it was 6A for an hour.** 6A is the POLYGON centroid formula,
    whose integrand is ``(x₀+x₁)(x₀y₁−x₁y₀)`` and not ``x²y'`` -- a different quantity that
    happens to sit beside this one in every reference. The wrong version put a 4x3 rectangle's
    centroid at (0.67, 0.5) instead of (2, 1.5): a third of the way, which on a symmetric
    shape still looks like a point somewhere inside the figure. Caught by measuring a
    rectangle, whose answer can be written down without the code.
    """
    a2 = mx2 = my2 = 0.0
    for run in runs:
        for (p0, p1, p2, p3) in to_cubics(run, close=True):
            x = list(_power(p0[0], p1[0], p2[0], p3[0]))
            y = list(_power(p0[1], p1[1], p2[1], p3[1]))
            dx, dy = _deriv(x), _deriv(y)
            a2 += _poly_int01(_poly_mul(x, dy)) - _poly_int01(_poly_mul(y, dx))
            mx2 += _poly_int01(_poly_mul(_poly_mul(x, x), dy))
            my2 += _poly_int01(_poly_mul(_poly_mul(y, y), dx))
    return a2, mx2, my2


def area(runs):
    """Signed enclosed area. Positive is counter-clockwise in a y-up frame."""
    return _green(runs)[0] / 2.0


def centroid(runs):
    """The centroid of the enclosed region, or of the points when the area is degenerate.

    The fallback is stated rather than silent: a run with no enclosed area -- an open
    stroke, a straight line -- has no region centroid, and returning the mean of its points
    with no word about it would be a different quantity wearing the same name.
    """
    a2, mx2, my2 = _green(runs)
    a = a2 / 2.0
    if abs(a) < 1e-12:
        pts = [p for run in runs for p in points_of(run)]
        if not pts:
            return None, "empty"
        return ((sum(p[0] for p in pts) / len(pts),
                 sum(p[1] for p in pts) / len(pts)), "points")
    return ((mx2 / (2.0 * a), -my2 / (2.0 * a)), "region")


# --------------------------------------------------------------------- flattening
def flatten(runs, tol=0.05):
    """The runs as polylines, no vertex further than `tol` from the true curve.

    For the questions that have no closed form -- is this point inside, do these two shapes
    overlap -- and `tol` is the honest knob: every answer from a flattened curve is exact
    for a shape that differs from the real one by at most this much.
    """
    out = []
    for run in runs:
        poly = []
        for c in to_cubics(run, close=False):
            _flat(c, tol, poly, 0)
            poly.append(c[3])
        if poly:
            out.append(_dedupe(poly))
    return out


def _flat(c, tol, out, depth):
    p0, p1, p2, p3 = c
    if depth >= 20:
        out.append(p0)
        return
    # Distance of the control points from the chord: the standard flatness test.
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    n = math.hypot(dx, dy)
    if n < 1e-12:
        d = max(_dist(p1, p0), _dist(p2, p0))
    else:
        d = max(abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx),
                abs((p2[0] - p0[0]) * dy - (p2[1] - p0[1]) * dx)) / n
    if d <= tol:
        out.append(p0)
        return
    left, right = _split(p0, p1, p2, p3, 0.5)
    _flat(left, tol, out, depth + 1)
    _flat(right, tol, out, depth + 1)


def _dedupe(poly):
    out = [poly[0]]
    for p in poly[1:]:
        if _dist(p, out[-1]) > 1e-12:
            out.append(p)
    return out


def point_at(run, t):
    """The point a fraction `t` of the way along a run, by arc length."""
    cs = to_cubics(run)
    if not cs:
        return None
    lens = [_cubic_length(*c) for c in cs]
    total = sum(lens)
    if total <= 0:
        return cs[0][0]
    want = max(0.0, min(1.0, t)) * total
    for c, l in zip(cs, lens):
        if want <= l or l == 0:
            u = 0.0 if l == 0 else want / l
            return (_at(c[0][0], c[1][0], c[2][0], c[3][0], u),
                    _at(c[0][1], c[1][1], c[2][1], c[3][1], u))
        want -= l
    return cs[-1][3]


# --------------------------------------------------------------------- hit testing
def contains(polys, pt, rule="evenodd"):
    """Is `pt` inside the flattened loops, under `rule`?"""
    x, y = pt
    if rule == "nonzero":
        wind = 0
        for poly in polys:
            n = len(poly)
            for i in range(n):
                x0, y0 = poly[i]
                x1, y1 = poly[(i + 1) % n]
                if y0 <= y < y1 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                    wind += 1
                elif y1 <= y < y0 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
                    wind -= 1
        return wind != 0
    inside = False
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                xx = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if xx > x:
                    inside = not inside
    return inside


def nearest_point(polys, pt):
    """The closest point on the flattened outline, and its distance."""
    best, bd = None, float("inf")
    px, py = pt
    for poly in polys:
        for i in range(len(poly) - 1):
            q = _closest_on_segment(poly[i], poly[i + 1], (px, py))
            d = _dist(q, (px, py))
            if d < bd:
                best, bd = q, d
    return best, bd


def _closest_on_segment(a, b, p):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    if n < 1e-15:
        return a
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / n))
    return (ax + t * dx, ay + t * dy)


def segments_intersect(a, b, c, d):
    """Do segments ab and cd cross?"""
    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    d1, d2 = side(c, d, a), side(c, d, b)
    d3, d4 = side(a, b, c), side(a, b, d)
    if d1 != d2 and d3 != d4:
        return True
    return False


def polys_overlap(pa, pb, rule="evenodd", a_closed=True, b_closed=True):
    """Do two flattened shapes share any area, or cross?

    Three questions in one, and all three are needed: outlines that cross, A inside B, and B
    inside A. Testing only the first reports two nested shapes as clear of each other, which
    is the overlap a figure most often actually has.

    **`a_closed` and `b_closed` are not decoration.** Containment only means anything for a
    shape that encloses something. An OPEN path -- a stroke, a routed connector -- was being
    treated as a closed polygon by the containment test, so a connector whose bounding path
    happened to wrap around a box reported that it overlapped it and the measured clearance
    came back 0. The route was correct; the measure was wrong about what kind of shape it
    had been handed.
    """
    for a in pa:
        for i in range(len(a) - 1):
            for b in pb:
                for j in range(len(b) - 1):
                    if segments_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                        return True
    if b_closed and pa and pa[0] and contains(pb, pa[0][0], rule):
        return True
    if a_closed and pb and pb[0] and contains(pa, pb[0][0], rule):
        return True
    return False
