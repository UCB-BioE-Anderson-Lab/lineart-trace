import cv2
import numpy as np

from lineart_trace import corpus
from lineart_trace.binarize import (binarize, despeckle, flatten_background,
                                    to_gray)


def blank(w=400, h=300):
    return np.full((h, w), 255, np.uint8)


def test_hard_edged_render_is_not_lost():
    """Regression: on an image holding only 0 and 255, Otsu returns 0 and a
    strict `<` comparison finds no ink at all."""
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    for method in ("auto", "otsu", "fixed", "adaptive"):
        assert binarize(im, method=method).sum() > 2000, method


def test_polarity_is_detected():
    im = np.zeros((300, 400), np.uint8)
    cv2.line(im, (40, 150), (360, 150), 255, 8)      # white ink on black
    assert 1000 < binarize(im).sum() < 40000


def test_invert_can_be_forced():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    normal = binarize(im, invert=False).sum()
    flipped = binarize(im, invert=True).sum()
    assert normal + flipped == im.size


def test_rgb_and_rgba_inputs():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    rgb = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    rgba = np.dstack([rgb, np.full(im.shape, 255, np.uint8)])
    base = binarize(im).sum()
    assert binarize(rgb).sum() == base
    assert binarize(rgba).sum() == base


def test_transparent_png_composites_onto_white():
    """A transparent pixel is paper, not ink, whatever colour sits under it."""
    rgba = np.zeros((80, 80, 4), np.uint8)           # black, fully transparent
    rgba[30:50, 10:70, 3] = 255                      # one opaque black bar
    assert 900 < binarize(rgba).sum() < 1500


def test_flatten_removes_a_lighting_gradient():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    ramp = np.tile(np.linspace(1.0, 0.35, im.shape[1]), (im.shape[0], 1))
    lit = (im * ramp).astype(np.uint8)
    flat = flatten_background(lit)
    rows = np.ones(flat.shape[0], bool)
    rows[140:162] = False                         # exclude the stroke itself
    assert flat[rows].std() < 3                   # the page reads as flat now
    assert binarize(lit).sum() > 2000


def _iou(a, b):
    a, b = a > 0, b > 0
    return float((a & b).sum()) / max(float((a | b).sum()), 1.0)


def test_uneven_lighting_needs_the_background_taken_out():
    """A phone shot of a crumpled page has a brightness gradient far larger
    than the ink-to-paper contrast, so no single threshold can work: it either
    loses the shaded half of the drawing or floods the lit half."""
    spec = corpus.build("photograph")
    auto = _iou(binarize(spec.image, denoise=True), spec.truth)
    fixed = _iou(spec.image < 200, spec.truth)
    flat_off = _iou(binarize(spec.image, method="otsu", flatten=False),
                    spec.truth)
    assert auto > 0.85
    assert auto > 3 * max(fixed, flat_off)


def test_despeckle_drops_specks_and_keeps_strokes():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    mask = (im < 200).astype(np.uint8)
    rng = np.random.default_rng(0)
    noisy = mask.copy()
    noisy[rng.integers(0, 300, 400), rng.integers(0, 400, 400)] = 1
    cleaned = despeckle(noisy, min_area=10)
    assert abs(int(cleaned.sum()) - int(mask.sum())) < 60


def test_close_bridges_a_break():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 8)
    mask = (im < 200).astype(np.uint8)
    mask[:, 200:203] = 0
    n_before, _ = cv2.connectedComponents(mask, connectivity=8)
    n_after, _ = cv2.connectedComponents(despeckle(mask, close=7), connectivity=8)
    assert n_before == 3 and n_after == 2


def test_blank_page_has_no_ink():
    assert binarize(blank()).sum() == 0


def test_to_gray_shapes():
    assert to_gray(np.zeros((5, 5), np.uint8)).shape == (5, 5)
    assert to_gray(np.zeros((5, 5, 3), np.uint8)).shape == (5, 5)
    assert to_gray(np.zeros((5, 5, 4), np.uint8)).shape == (5, 5)
