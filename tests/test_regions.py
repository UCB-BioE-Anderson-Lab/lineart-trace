import cv2
import numpy as np

from lineart_trace.regions import (region_contours, split_fills,
                                   stroke_width_of, thinness)


def blank(w=600, h=400):
    return np.full((h, w), 255, np.uint8)


def ink_of(im):
    return (im < 200).astype(np.uint8)


def test_thinness_of_a_disc_is_one():
    assert abs(thinness(np.pi * 100 ** 2, 2 * np.pi * 100) - 1.0) < 1e-9


def test_thinness_of_a_stroke_is_small():
    assert thinness(10 * 500, 2 * 500 + 2 * 10) < 0.1


def test_solid_shape_becomes_a_fill():
    im = blank()
    cv2.fillPoly(im, [np.array([(60, 60), (400, 200), (60, 340)], np.int32)], 0)
    fill, strokes = split_fills(ink_of(im))
    assert fill.sum() > 0.95 * ink_of(im).sum()
    assert strokes.sum() < 0.05 * ink_of(im).sum()


def test_a_picture_that_is_entirely_fill_is_still_detected():
    """Regression: fill detection keyed off the stroke width, but the stroke
    width was measured from a skeleton the fill itself dominated, so a lone
    solid shape could never be recognised."""
    im = blank()
    cv2.fillPoly(im, [np.array([(60, 60), (400, 200), (60, 340)], np.int32)], 0)
    fill, _ = split_fills(ink_of(im), stroke_width=None)
    assert fill.sum() > 0
    assert len(region_contours(fill)) == 1


def test_a_heavy_stroke_stays_a_stroke():
    im = blank()
    cv2.line(im, (40, 120), (560, 120), 0, 6)
    cv2.line(im, (40, 280), (560, 280), 0, 26)
    fill, strokes = split_fills(ink_of(im))
    assert fill.sum() == 0
    assert strokes.sum() == ink_of(im).sum()


def test_blob_welded_to_a_stroke_is_split_off():
    im = blank()
    cv2.line(im, (40, 200), (400, 200), 0, 10)
    cv2.fillPoly(im, [np.array([(540, 200), (390, 145), (390, 255)], np.int32)],
                 0)
    fill, strokes = split_fills(ink_of(im))
    assert fill.sum() > 2000                    # the head
    assert strokes.sum() > 2000                 # the shaft survives
    assert fill[195:205, 60:200].sum() == 0     # the line is not swallowed


def test_holes_are_preserved():
    im = blank()
    cv2.circle(im, (300, 200), 150, 0, -1)
    cv2.circle(im, (300, 200), 70, 255, -1)
    fill, _ = split_fills(ink_of(im))
    regions = region_contours(fill)
    assert len(regions) == 1
    assert len(regions[0]) == 2                 # outer boundary plus one hole


def test_small_regions_are_ignored():
    im = blank()
    cv2.circle(im, (100, 100), 2, 0, -1)
    fill, _ = split_fills(ink_of(im), min_area=64)
    assert fill.sum() == 0


def test_detection_can_be_disabled():
    im = blank()
    cv2.circle(im, (300, 200), 120, 0, -1)
    fill, strokes = split_fills(ink_of(im), thin_limit=0.0, ratio=0.0)
    assert fill.sum() == 0 and strokes.sum() == ink_of(im).sum()


def test_stroke_width_of_reads_the_drawn_weight():
    for t in (5, 9, 13, 21):
        im = blank()
        cv2.line(im, (40, 200), (560, 200), 0, t)
        assert abs(stroke_width_of(ink_of(im)) - (t + 1)) <= 1.0


def test_empty_mask():
    fill, strokes = split_fills(np.zeros((40, 40), np.uint8))
    assert fill.sum() == 0 and strokes.sum() == 0
    assert region_contours(np.zeros((40, 40), np.uint8)) == []
