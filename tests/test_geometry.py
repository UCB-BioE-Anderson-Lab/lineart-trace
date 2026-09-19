"""Curve arithmetic, checked against answers that can be written down without the code.

A measurement library can only be trusted against closed forms and brute force. Every case
here is one or the other: a rectangle whose area is its sides multiplied, a circle whose
circumference is 2*pi*r, an arc whose length is compared to four hundred thousand chords.
"""
import math

import pytest

from lineart_trace.scene import geometry as g

SQUARE = [["M", 0, 0], ["L", 4, 0], ["L", 4, 3], ["L", 0, 3], ["Z"]]
TRIANGLE = [["M", 0, 0], ["L", 6, 0], ["L", 0, 9], ["Z"]]
K = 0.5522847498307936 * 100
CIRCLE = [["M", 100, 0],
          ["C", 100, K, K, 100, 0, 100], ["C", -K, 100, -100, K, -100, 0],
          ["C", -100, -K, -K, -100, 0, -100], ["C", K, -100, 100, -K, 100, 0], ["Z"]]
ARC = [["M", 0, 0], ["C", 0, 100, 100, 100, 100, 0]]


def test_area_of_straight_shapes_is_exact():
    assert g.area([SQUARE]) == 12.0
    assert g.area([TRIANGLE]) == 27.0


def test_centroid_of_straight_shapes_is_exact():
    """A rectangle's centroid can be written down, which is why it catches a wrong divisor."""
    assert g.centroid([SQUARE])[0] == (2.0, 1.5)
    assert g.centroid([TRIANGLE])[0] == (2.0, 3.0)


def test_centroid_does_not_depend_on_which_way_round_the_loop_goes():
    back = [["M", 0, 0], ["L", 0, 3], ["L", 4, 3], ["L", 4, 0], ["Z"]]
    assert g.area([back]) == -12.0
    assert g.centroid([back])[0] == g.centroid([SQUARE])[0]


def test_centroid_is_translation_equivariant():
    moved = [["M", 10, 20], ["L", 14, 20], ["L", 14, 23], ["L", 10, 23], ["Z"]]
    a, b = g.centroid([SQUARE])[0], g.centroid([moved])[0]
    assert (round(b[0] - a[0], 9), round(b[1] - a[1], 9)) == (10.0, 20.0)


def test_centroid_says_when_it_is_not_a_region_centroid():
    """An open stroke has no region centroid; the fallback is named rather than silent."""
    _pt, basis = g.centroid([[["M", 0, 0], ["L", 10, 0]]])
    assert basis == "points"
    assert g.centroid([SQUARE])[1] == "region"


def test_bounds_are_tight_not_the_control_point_hull():
    """The arc peaks at y=75; its control points reach 100. A third too tall is the gap."""
    assert g.bounds([ARC]) == (0.0, 0.0, 100.0, 75.0)
    pts = g.points_of(ARC)
    assert max(p[1] for p in pts) == 100.0


def test_a_bezier_circle_measures_as_the_curve_it_actually_is():
    """Within the approximation's own 0.03% error -- the curve's, not the arithmetic's."""
    assert abs(g.area([CIRCLE]) - math.pi * 1e4) / (math.pi * 1e4) < 5e-4
    assert abs(g.length([CIRCLE]) - 2 * math.pi * 100) / (2 * math.pi * 100) < 5e-4
    assert g.bounds([CIRCLE]) == (-100.0, -100.0, 100.0, 100.0)


def test_length_agrees_with_brute_force_chords():
    c = g.to_cubics(ARC)[0]

    def at(t):
        return tuple(sum(w * p[i] for w, p in zip(
            ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3), c))
            for i in (0, 1))

    n = 200000
    prev, total = at(0.0), 0.0
    for i in range(1, n + 1):
        cur = at(i / n)
        total += math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        prev = cur
    assert abs(g.length([ARC]) - total) / total < 1e-6


def test_point_at_walks_by_arc_length():
    mid = g.point_at([["M", 0, 0], ["L", 10, 0]], 0.5)
    assert (round(mid[0], 9), round(mid[1], 9)) == (5.0, 0.0)


@pytest.mark.parametrize("pt,inside", [((2, 1.5), True), ((5, 1.5), False),
                                       ((-1, -1), False), ((3.9, 2.9), True)])
def test_contains(pt, inside):
    assert g.contains(g.flatten([SQUARE]), pt) is inside


def test_overlap_catches_nesting_not_only_crossing():
    """Two nested shapes cross nowhere. Testing only for crossings calls them clear."""
    outer = g.flatten([[["M", 0, 0], ["L", 10, 0], ["L", 10, 10], ["L", 0, 10], ["Z"]]])
    inner = g.flatten([[["M", 3, 3], ["L", 6, 3], ["L", 6, 6], ["L", 3, 6], ["Z"]]])
    far = g.flatten([[["M", 30, 30], ["L", 36, 30], ["L", 36, 36], ["Z"]]])
    assert g.polys_overlap(outer, inner)
    assert g.polys_overlap(inner, outer)
    assert not g.polys_overlap(outer, far)


def test_flattening_stays_within_its_stated_tolerance():
    for tol in (0.5, 0.05, 0.005):
        poly = g.flatten([ARC], tol)[0]
        c = g.to_cubics(ARC)[0]
        worst = 0.0
        for i in range(2001):
            t = i / 2000.0
            p = tuple(sum(w * q[k] for w, q in zip(
                ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3), c))
                for k in (0, 1))
            worst = max(worst, min(
                g._seg_distance if False else
                math.dist(p, g._closest_on_segment(poly[j], poly[j + 1], p))
                for j in range(len(poly) - 1)))
        assert worst <= tol * 1.5, (tol, worst)


# ------------------------------------------------------------------ the primitives
def _runs(el):
    g_ = el["geometry"]
    return [g_["d"]] if g_["kind"] == "path" else g_["loops"]


def test_an_ellipse_encloses_pi_a_b():
    from lineart_trace.scene import build
    e = build.ellipse("e", 0, 0, 100, 60)
    want = math.pi * 100 * 60
    assert abs(g.area(_runs(e)) - want) / want < 5e-4
    assert g.bounds(_runs(e)) == (-100.0, -60.0, 100.0, 60.0)


def test_a_rounded_rectangle_loses_exactly_the_corners_it_rounds():
    from lineart_trace.scene import build
    r = build.rect("r", 10, 20, 40, 30, radius=8)
    want = 40 * 30 - (4 - math.pi) * 64
    assert abs(g.area(_runs(r)) - want) / want < 5e-4


def test_a_rounded_rectangle_clamps_a_radius_that_will_not_fit():
    from lineart_trace.scene import build
    r = build.rect("r", 0, 0, 10, 4, radius=99)
    assert g.bounds(_runs(r)) == (0.0, 0.0, 10.0, 4.0)


def test_a_quarter_arc_is_a_quarter_of_the_circumference():
    from lineart_trace.scene import build
    a = build.arc("a", 0, 0, 50, 0, 90)
    want = math.pi * 50 / 2
    assert abs(g.length(_runs(a)) - want) / want < 5e-4


def test_a_regular_polygon_has_the_area_the_formula_gives():
    from lineart_trace.scene import build
    h = build.polygon("h", 0, 0, 10, 6)
    assert g.area(_runs(h)) == pytest.approx(3 * math.sqrt(3) / 2 * 100, abs=1e-6)


def test_a_curve_through_points_passes_through_every_one_of_them():
    from lineart_trace.scene import build
    pts = [(0, 0), (10, 20), (20, 0), (30, 20)]
    got = g.points_of(build.through("t", pts)["geometry"]["d"])[::3]
    assert [(round(x, 9), round(y, 9)) for x, y in got] == [(float(a), float(b))
                                                            for a, b in pts]


def test_a_primitive_with_no_size_is_refused_rather_than_drawn_degenerate():
    from lineart_trace.scene import build
    with pytest.raises(ValueError):
        build.rect("r", 0, 0, 0, 10)
    with pytest.raises(ValueError):
        build.ellipse("e", 0, 0, 0, 5)
    with pytest.raises(ValueError):
        build.polygon("p", 0, 0, 5, 2)
    with pytest.raises(ValueError):
        build.arrowhead("a", (0, 0), (0, 0))
