"""Drawings in tests/fixtures, scored against their own ink.

There is no independent ground truth for a real drawing, so the target is the
binarised ink: these say how faithfully the vectors reproduce what was on the
page, not how well the page was thresholded.

`stress.png` (rebuild it with `examples/make_stress.py`), `beach.png` and
`polymerase.png` ship. Drop your own drawings in beside them -- name them in FLOOR and they
are covered too; anything absent is skipped, so the suite passes on a clean
checkout.
"""
import os

import cv2
import pytest

from lineart_trace import binarize, compare, rasterize, trace_file

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# name -> (min coverage, max spill, max paths, max d95, trace options)
#
# The options are part of the expectation. beach.png is a colour drawing and
# has to be traced as one: in monochrome its four inks collapse into a single
# mask, the flat regions stop being recognisable as fills, and coverage drops
# from 0.993 to 0.953 with spill going from 0.001 to 0.075.
FLOOR = {
    # beach.png's flat regions have ragged, hole-punched boundaries, which the
    # DEFAULT thinness threshold reads as stroke-like -- at defaults its sand
    # and sea trace as centrelines and coverage is 0.907. Lowering the
    # threshold is a setting, not a different algorithm, and is part of this
    # drawing's expectation the same way --colors is.
    "beach":       (0.96, 0.02, 1200, 3.0,
                    {"colors": 0, "thin_limit": 0.05, "close": 5}),
    "polymerase":  (0.97, 0.02, 5, 2.0, {}),
    "stress":      (0.96, 0.02, 400, 2.0, {}),
    "fingerprint": (0.96, 0.02, 200, 2.0, {}),
    "crimescene":  (0.95, 0.02, 900, 2.0, {}),
}


@pytest.mark.parametrize("name", sorted(FLOOR))
def test_real_drawing_round_trips(name):
    path = os.path.join(FIX, name + ".png")
    if not os.path.exists(path):
        pytest.skip(f"{name}.png not present")
    lo_cov, hi_spill, max_paths, hi_d95, opts = FLOOR[name]
    res = trace_file(path, **opts)
    ink = binarize(cv2.imread(path, cv2.IMREAD_UNCHANGED))
    m = compare(ink, rasterize(res, res.size))
    assert m["coverage"] >= lo_cov, f"{name}: coverage {m['coverage']:.3f}"
    assert m["spill"] <= hi_spill, f"{name}: spill {m['spill']:.3f}"
    assert m["d95"] <= hi_d95, f"{name}: d95 {m['d95']:.1f}px"
    assert res.n_paths <= max_paths, f"{name}: {res.n_paths} paths"


def test_output_is_much_smaller_than_the_raster():
    path = os.path.join(FIX, "stress.png")
    svg = trace_file(path).to_svg()
    assert len(svg) < os.path.getsize(path)


def test_a_drawing_keeps_its_fills():
    """The filled triangle in the stress pattern must not become a spine."""
    assert trace_file(os.path.join(FIX, "stress.png")).n_fills >= 1


def test_a_scalloped_outline_is_one_closed_path():
    """polymerase.png is a single closed contour with about sixty scallops:
    it must not come apart, and the loop must close."""
    res = trace_file(os.path.join(FIX, "polymerase.png"))
    assert res.n_strokes == 1
    assert res.strokes[0].closed
    assert res.to_svg_paths()[0].endswith("Z")


def test_a_colour_scene_separates_into_pens_and_fills():
    """beach.png is four inks under black line work. The pens must separate.

    Its flat regions need --thin-limit lowered: at defaults their ragged
    boundaries read as stroke-like and they trace as centrelines."""
    res = trace_file(os.path.join(FIX, "beach.png"), colors=0,
                     thin_limit=0.05, close=5)
    assert len(res.colors) == 4
    assert res.n_strokes > 200
    assert res.n_fills >= 10          # sand, sea and ball are regions
    fill_px = sum(len(l) for f in res.fills for l in f.loops)
    assert fill_px > 0


def test_colour_is_recovered_from_a_real_drawing():
    res = trace_file(os.path.join(FIX, "polymerase.png"), colors=0)
    assert len(res.colors) == 1
    r, g, b = (int(res.colors[0][i:i + 2], 16) for i in (1, 3, 5))
    assert b > 150 and b > r + 80 and b > g + 60      # it is blue
