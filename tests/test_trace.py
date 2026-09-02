"""End-to-end behaviour of the tracer, and the shape of its output."""
import math
import os

import cv2
import numpy as np
import pytest

from lineart_trace import (compare, rasterize, trace_file, trace_image,
                           trace_mask)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def blank(w=400, h=300):
    return np.full((h, w), 255, np.uint8)


def roundtrip(im, **kw):
    """Trace, render the vectors back, and score against the source ink."""
    res = trace_image(im, **kw)
    return res, compare((im < 200).astype(np.uint8), rasterize(res, res.size))


# --------------------------------------------------------------- structure
def test_straight_line_is_one_path_one_cubic():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    res = trace_image(im)
    assert res.n_paths == 1 and res.n_segments == 1


def test_circle_is_a_single_closed_path():
    """Regression: a plain circle came out as the ring plus a stray 4px
    fragment, because the walk overran its start and orphaned the pixels it
    stepped over."""
    im = blank(); cv2.circle(im, (200, 150), 90, 0, 8)
    res = trace_image(im)
    assert res.n_paths == 1
    assert res.strokes[0].closed
    d = res.to_svg_paths()[0]
    assert d.endswith("Z")
    start = [float(v) for v in d[1:].split("C")[0].split()]
    end = [float(v) for v in d[:-1].split("C")[-1].split()[-2:]]
    assert math.dist(start, end) < 1e-6      # it closes exactly


def test_crossing_splits_into_four_arms():
    im = blank()
    cv2.line(im, (40, 150), (360, 150), 0, 8)
    cv2.line(im, (200, 30), (200, 270), 0, 8)
    assert trace_image(im).n_paths == 4


def test_crossings_do_not_punch_gaps():
    """Regression: pruning short chains removed the structural piece of line
    *between* two crossings, dashing every line that crossed another."""
    im = blank(500, 400)
    cv2.circle(im, (250, 200), 140, 0, 8)
    for a in range(0, 360, 45):
        p = (int(250 + 170 * math.cos(math.radians(a))),
             int(200 + 170 * math.sin(math.radians(a))))
        cv2.line(im, (250, 200), p, 0, 8)
    _, m = roundtrip(im)
    assert m["coverage"] > 0.97
    assert m["dmax"] < 6


def test_empty_image_is_safe():
    res = trace_image(blank())
    assert res.n_paths == 0 and res.n_segments == 0
    assert res.to_svg_paths() == [] and res.to_svg_group()


def test_size_is_reported_as_width_height():
    assert trace_image(blank(400, 300)).size == (400, 300)


# ------------------------------------------------------------------ widths
@pytest.mark.parametrize("t", [5, 9, 13, 21])
def test_stroke_width_is_recovered(t):
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, t)
    res = trace_image(im)
    assert abs(res.stroke_width - (t + 1)) <= 1.5


def test_mixed_weights_stay_mixed():
    """Regression: one median width for the whole drawing flattened any
    drawing that used more than one weight."""
    im = blank(600, 400)
    for i, t in enumerate((4, 12, 20)):
        cv2.line(im, (50, 100 + i * 100), (550, 100 + i * 100), 0, t)
    res = trace_image(im)
    assert len(res.strokes) == 3
    got = sorted(round(s.width) for s in res.strokes)
    assert got == [5, 13, 21]


def test_uniform_width_can_be_forced():
    im = blank(600, 400)
    for i, t in enumerate((4, 12, 20)):
        cv2.line(im, (50, 100 + i * 100), (550, 100 + i * 100), 0, t)
    g = trace_image(im).to_svg_group(per_path_width=False)
    assert g.count("stroke-width") == 1


# ------------------------------------------------------------------- fills
def test_solid_shape_becomes_a_fill_not_a_spine():
    """A centreline cannot represent a filled shape: it must be a contour."""
    im = blank(600, 400)
    cv2.fillPoly(im, [np.array([(60, 60), (400, 200), (60, 340)], np.int32)], 0)
    res, m = roundtrip(im)
    assert res.n_fills == 1 and res.n_strokes == 0
    assert m["iou"] > 0.95


def test_arrowhead_keeps_its_shaft():
    im = blank(600, 400)
    cv2.line(im, (40, 200), (400, 200), 0, 10)
    cv2.fillPoly(im, [np.array([(540, 200), (390, 145), (390, 255)], np.int32)], 0)
    res, m = roundtrip(im)
    assert res.n_fills == 1 and res.n_strokes >= 1
    assert m["iou"] > 0.9


def test_fill_detection_can_be_turned_off():
    im = blank(600, 400)
    cv2.fillPoly(im, [np.array([(60, 60), (400, 200), (60, 340)], np.int32)], 0)
    res = trace_image(im, thin_limit=0.0, fill_ratio=0.0)
    assert res.n_fills == 0 and res.n_strokes >= 1


def test_hole_survives_the_round_trip():
    im = blank(600, 400)
    cv2.circle(im, (300, 200), 150, 0, -1)
    cv2.circle(im, (300, 200), 70, 255, -1)
    res, m = roundtrip(im)
    assert m["iou"] > 0.9
    assert "evenodd" in res.to_svg_group()


# ------------------------------------------------------------------ output
def test_svg_document_is_well_formed():
    import xml.etree.ElementTree as ET
    im = blank(600, 400)
    cv2.circle(im, (300, 200), 120, 0, 9)
    cv2.fillPoly(im, [np.array([(60, 60), (160, 110), (60, 160)], np.int32)], 0)
    root = ET.fromstring(trace_image(im).to_svg())
    assert root.tag.endswith("svg")
    assert root.attrib["width"] == "600" and root.attrib["height"] == "400"


def test_scale_and_offset_apply():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    res = trace_image(im)
    a = [float(v) for v in res.to_svg_paths()[0][1:].split("C")[0].split()]
    b = [float(v) for v in
         res.to_svg_paths(scale=2.0, dx=10, dy=5)[0][1:].split("C")[0].split()]
    assert abs(b[0] - (a[0] * 2 + 10)) < 0.2
    assert abs(b[1] - (a[1] * 2 + 5)) < 0.2


def test_no_control_point_escapes_the_canvas():
    """Regression: the least-squares solve flung control points far outside
    the data, drawing as long spurious lines."""
    res = trace_file(os.path.join(FIX, "stress.png"))
    w, h = res.size
    for run in res.curves:
        for c in run:
            for p in c:
                assert -w <= p[0] <= 2 * w and -h <= p[1] <= 2 * h


def test_transparent_background_is_optional():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    assert "<rect" not in trace_image(im).to_svg(background=None)


# ------------------------------------------------------------------- input
def test_trace_mask_accepts_a_bare_mask():
    m = np.zeros((300, 400), np.uint8)
    cv2.line(m, (40, 150), (360, 150), 1, 8)
    assert trace_mask(m).n_paths == 1


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        trace_file(os.path.join(FIX, "nope.png"))


def test_colour_input_matches_grayscale():
    im = blank(); cv2.circle(im, (200, 150), 90, 0, 8)
    rgb = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    assert trace_image(rgb).n_paths == trace_image(im).n_paths
