import os, math
import numpy as np
import cv2
import pytest
from lineart_trace import trace_image, trace_file, skeletonize, fit_curve

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

def canvas(w=400, h=300):
    return np.full((h, w), 255, np.uint8)

def test_straight_line_is_one_segment():
    im = canvas(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    r = trace_image(im)
    assert r.n_paths == 1
    assert r.n_segments == 1

def test_stroke_width_recovered():
    im = canvas(); cv2.line(im, (40, 150), (360, 150), 0, 12)
    r = trace_image(im)
    assert 10 <= r.stroke_width <= 15

def test_circle_is_closed_loop():
    im = canvas(); cv2.circle(im, (200, 150), 90, 0, 8)
    r = trace_image(im)
    assert r.n_paths == 1
    d = r.to_svg_paths()[0]
    head = d.split("C")[0][1:].split()
    tail = d.split("C")[-1].split()[-2:]
    assert math.dist([float(head[0]), float(head[1])],
                     [float(tail[0]), float(tail[1])]) < 6

def test_crossing_splits_at_junction():
    im = canvas(); cv2.line(im, (40,150),(360,150),0,8); cv2.line(im,(200,30),(200,270),0,8)
    r = trace_image(im)
    assert r.n_paths == 4          # four arms off one junction

def test_no_control_point_escapes_bbox():
    """Regression: the least-squares solve used to fling control points far
    outside the data, drawing long spurious lines."""
    r = trace_file(os.path.join(FIX, "stress.png"))
    w, h = r.size
    for curves in r.curves:
        for c in curves:
            for p in c:
                assert -w <= p[0] <= 2*w and -h <= p[1] <= 2*h

def test_crossings_do_not_punch_gaps():
    """Regression: pruning short chains removed structural junction-to-
    junction segments, dashing every line that crossed another."""
    im = canvas(500, 400)
    cv2.circle(im, (250, 200), 140, 0, 8)
    for a in range(0, 360, 45):
        p = (int(250+170*math.cos(math.radians(a))), int(200+170*math.sin(math.radians(a))))
        cv2.line(im, (250, 200), p, 0, 8)
    r = trace_image(im, prune=14)
    ink = float((im < 200).sum())
    render = np.full(im.shape, 255, np.uint8)
    for curves in r.curves:
        pts = [curves[0][0]] + [c[3] for c in curves]
        cv2.polylines(render, [np.array(pts, np.int32)], False, 0, 8)
    covered = float(((render < 200) & (im < 200)).sum())
    assert covered / ink > 0.80      # the ring survives its eight crossings

def test_empty_image_is_safe():
    assert trace_image(canvas()).n_paths == 0

def test_fit_curve_handles_two_points():
    assert len(fit_curve(np.array([[0.0, 0.0], [10.0, 0.0]]))) == 1

def test_skeleton_is_one_pixel_wide():
    im = canvas(); cv2.line(im, (40, 150), (360, 150), 0, 21)
    _, bw = cv2.threshold(im, 200, 255, cv2.THRESH_BINARY_INV)
    sk = skeletonize((bw > 0).astype(np.uint8))
    assert sk.sum(axis=0).max() <= 2
