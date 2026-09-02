"""Drawings in tests/fixtures, scored against their own ink.

There is no independent ground truth for a real drawing, so the target is the
binarised ink: these say how faithfully the vectors reproduce what was on the
page, not how well the page was thresholded.

Only `stress.png` ships (rebuild it with `examples/make_stress.py`). Drop your
own drawings in beside it -- name them in FLOOR and they are covered too;
anything absent is skipped, so the suite passes on a clean checkout.
"""
import os

import cv2
import pytest

from lineart_trace import binarize, compare, rasterize, trace_file

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# name -> (min coverage, max spill, max paths)
FLOOR = {
    "stress":      (0.96, 0.02, 400),
    "fingerprint": (0.96, 0.02, 200),
    "crimescene":  (0.95, 0.02, 900),
}


@pytest.mark.parametrize("name", sorted(FLOOR))
def test_real_drawing_round_trips(name):
    path = os.path.join(FIX, name + ".png")
    if not os.path.exists(path):
        pytest.skip(f"{name}.png not present")
    lo_cov, hi_spill, max_paths = FLOOR[name]
    res = trace_file(path)
    ink = binarize(cv2.imread(path, cv2.IMREAD_UNCHANGED))
    m = compare(ink, rasterize(res, res.size))
    assert m["coverage"] >= lo_cov, f"{name}: coverage {m['coverage']:.3f}"
    assert m["spill"] <= hi_spill, f"{name}: spill {m['spill']:.3f}"
    assert m["d95"] <= 2.0, f"{name}: d95 {m['d95']:.1f}px"
    assert res.n_paths <= max_paths, f"{name}: {res.n_paths} paths"


def test_output_is_much_smaller_than_the_raster():
    path = os.path.join(FIX, "stress.png")
    svg = trace_file(path).to_svg()
    assert len(svg) < os.path.getsize(path)


def test_a_drawing_keeps_its_fills():
    """The filled triangle in the stress pattern must not become a spine."""
    assert trace_file(os.path.join(FIX, "stress.png")).n_fills >= 1
