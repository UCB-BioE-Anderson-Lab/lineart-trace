"""Measured quality gates over the whole corpus.

These are the numbers the README's capability table is built from. Each floor
sits a little under what the tracer currently achieves, so a real regression
trips it while ordinary noise does not. The cases the tracer genuinely cannot
do well are listed here too, with the floor they actually reach -- an honest
limit, recorded, rather than a specimen quietly left out of the suite.
"""
import numpy as np
import pytest

from lineart_trace import compare, corpus, rasterize, trace_image

# name -> (min IoU, min coverage)
FLOOR = {
    "line": (0.96, 0.98), "diagonal": (0.92, 0.98),
    "circle": (0.87, 0.98), "ellipse": (0.88, 0.98),
    "rectangle": (0.96, 0.98), "star": (0.84, 0.94), "zigzag": (0.84, 0.94),
    "wave": (0.90, 0.98), "shallow_arc": (0.86, 0.98), "spiral": (0.87, 0.98),
    "cross": (0.96, 0.98), "acute_cross": (0.87, 0.96), "tee": (0.93, 0.98),
    "hub": (0.92, 0.98), "tangent": (0.90, 0.97),
    "solid_triangle": (0.96, 0.98), "arrow": (0.94, 0.98),
    "ring_fill": (0.91, 0.94), "bold_stroke": (0.94, 0.97),
    "hatching": (0.82, 0.96), "parallels": (0.94, 0.98),
    "concentric": (0.87, 0.98), "dashes_dots": (0.85, 0.97),
    "thin_lines": (0.97, 0.99), "text_like": (0.77, 0.87),
    "flower": (0.85, 0.97), "house": (0.92, 0.98), "face": (0.87, 0.97),
    "five_pens": (0.97, 0.98), "pale_ink": (0.90, 0.98),
    "pens_crossing": (0.86, 0.97), "tinted_paper": (0.91, 0.98),
    "gray_shading": (0.84, 0.97), "gradient_shading": (0.85, 0.97),
    "stipple_shading": (0.60, 0.76),          # known limit: see below
    "photograph": (0.81, 0.96), "scan": (0.87, 0.98),
    "speckled": (0.85, 0.97), "broken": (0.79, 0.94),
    "low_contrast": (0.92, 0.98),
}

# Categories whose specimens are ordinary line art. The tracer's headline
# claim is about these, so they get a blanket floor as well as per-case ones.
CLEAN = ("primitive", "corner", "curve", "junction", "drawing", "color")


def score(spec):
    res = trace_image(spec.image, **spec.hint)
    return res, compare(spec.truth, rasterize(res, res.size))


@pytest.fixture(scope="module")
def scored():
    return {s.name: (s,) + score(s) for s in corpus.build_all()}


def test_every_specimen_has_a_recorded_floor():
    """A new specimen must come with its measured expectation."""
    assert set(FLOOR) == set(s.name for s in corpus.build_all())


@pytest.mark.parametrize("name", sorted(FLOOR))
def test_specimen_meets_its_floor(scored, name):
    spec, res, m = scored[name]
    lo_iou, lo_cov = FLOOR[name]
    assert m["iou"] >= lo_iou, f"{name}: IoU {m['iou']:.3f} < {lo_iou}"
    assert m["coverage"] >= lo_cov, \
        f"{name}: coverage {m['coverage']:.3f} < {lo_cov}"


@pytest.mark.parametrize("name", sorted(FLOOR))
def test_nothing_is_painted_on_blank_paper(scored, name):
    """Spurious strokes are worse than missing ones: they are visible."""
    assert scored[name][2]["spill"] < 0.06, name


def test_ordinary_line_art_is_reproduced_faithfully(scored):
    rows = [m for (s, _, m) in scored.values() if s.category in CLEAN]
    assert len(rows) >= 19
    assert min(r["coverage"] for r in rows) > 0.95
    assert min(r["iou"] for r in rows) > 0.84
    assert np.mean([r["iou"] for r in rows]) > 0.90


def test_corpus_mean_does_not_regress(scored):
    ious = [m["iou"] for (_, _, m) in scored.values()]
    assert np.mean(ious) > 0.88


def test_output_is_compact(scored):
    """A trace should be far smaller than the raster, and free of the
    thousands of fragments a broken graph walk produces."""
    for name, (spec, res, _) in scored.items():
        ink = float(spec.truth.sum())
        assert res.n_segments < max(60, ink / 25), name


# ------------------------------------------------------- known limitations
def test_stipple_dots_are_not_lines():
    """Stipple shading has no centrelines at all. The honest output is a crowd
    of small filled dots; what must NOT happen is joining them into strokes.

    Dots that touch merge into one blob, so the count is well under the number
    of dots drawn -- that is a real limit of working from a binary mask, and
    `--min-fill-area` trades it against picking up noise.
    """
    spec = corpus.build("stipple_shading")
    res = trace_image(spec.image, **spec.hint)
    assert res.n_fills >= 50
    long_strokes = [s for s in res.strokes if len(s.curves) > 3]
    assert len(long_strokes) < 20
    finer = trace_image(spec.image, min_fill_area=6)
    assert finer.n_fills > res.n_fills


def test_a_grey_wash_is_not_traced_as_line_work():
    """A flat mid-grey wash is tone, not line. It should either binarise away
    or become one filled region -- never a thicket of strokes."""
    plain = corpus.build("flower")
    washed = corpus.build("gray_shading")
    a = trace_image(plain.image)
    b = trace_image(washed.image)
    assert b.n_strokes < a.n_strokes + 12


def test_isolated_dots_survive_as_fills_not_as_strokes():
    """Regression: dots have no centreline and used to be pruned away."""
    spec = corpus.build("dashes_dots")
    res = trace_image(spec.image, **spec.hint)
    assert res.n_fills >= 10
