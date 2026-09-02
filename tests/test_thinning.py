import math

import cv2
import numpy as np
import pytest

from lineart_trace.thinning import (crossing_number, neighbour_count,
                                    skeletonize, thin_redundant)


def blank(w=400, h=300):
    return np.full((h, w), 255, np.uint8)


def ink_of(im):
    return (im < 200).astype(np.uint8)


def test_skeleton_is_one_pixel_wide():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 21)
    assert skeletonize(ink_of(im)).sum(axis=0).max() == 1


def test_skeleton_of_thick_diagonal_is_thin():
    im = blank(); cv2.line(im, (40, 40), (360, 260), 0, 25)
    sk = skeletonize(ink_of(im))
    # A diagonal is the case parallel Zhang-Suen leaves two pixels wide.
    assert neighbour_count(sk).max() <= 4


def test_skeleton_stays_connected():
    im = blank(); cv2.circle(im, (200, 150), 90, 0, 12)
    sk = skeletonize(ink_of(im))
    n, _ = cv2.connectedComponents(sk, connectivity=8)
    assert n == 2                      # background plus one ring


def test_skeletonize_is_idempotent():
    im = blank(); cv2.ellipse(im, (200, 150), (140, 70), 30, 0, 360, 0, 9)
    sk = skeletonize(ink_of(im))
    assert np.array_equal(skeletonize(sk), sk)


def test_crossing_number_classifies():
    im = blank()
    cv2.line(im, (40, 150), (360, 150), 0, 8)
    cv2.line(im, (200, 30), (200, 270), 0, 8)
    sk = skeletonize(ink_of(im))
    cn = crossing_number(sk)
    assert (cn == 1).sum() == 4                 # four free ends
    assert (cn >= 3).sum() >= 1                 # at least one branch pixel


def test_plain_circle_has_no_branch_pixel():
    """Regression: a two-wide band reads as crossing number 2 everywhere, and
    a hub of eight spokes then looks like plain line pixels."""
    im = blank(); cv2.circle(im, (200, 150), 90, 0, 8)
    sk = skeletonize(ink_of(im))
    cn = crossing_number(sk)
    assert (cn == 2).sum() == sk.sum()
    assert ((cn != 2) & (sk > 0)).sum() == 0


def test_hub_of_spokes_is_found_as_a_branch():
    im = blank(500, 400)
    for a in range(0, 360, 45):
        p = (int(250 + 150 * math.cos(math.radians(a))),
             int(200 + 150 * math.sin(math.radians(a))))
        cv2.line(im, (250, 200), p, 0, 8)
    sk = skeletonize(ink_of(im))
    assert (crossing_number(sk) >= 3).sum() >= 1
    assert (crossing_number(sk) == 1).sum() == 8      # eight spoke tips


def test_thin_redundant_never_disconnects():
    rng = np.random.default_rng(0)
    for seed in range(6):
        im = blank(200, 160)
        for _ in range(5):
            a = tuple(rng.integers(10, 150, 2).tolist())
            b = tuple(rng.integers(10, 150, 2).tolist())
            cv2.line(im, a, b, 0, int(rng.integers(3, 14)))
        sk = skeletonize(ink_of(im), cleanup=False)
        before, _ = cv2.connectedComponents(sk, connectivity=8)
        after, _ = cv2.connectedComponents(thin_redundant(sk), connectivity=8)
        assert after == before


def test_thin_redundant_keeps_endpoints():
    im = blank(); cv2.line(im, (40, 150), (360, 150), 0, 3)
    sk = skeletonize(ink_of(im))
    xs = np.nonzero(sk.any(axis=0))[0]
    assert xs.max() - xs.min() > 300          # the line was not eaten away


def test_empty_and_full_masks_are_safe():
    assert skeletonize(np.zeros((20, 20), np.uint8)).sum() == 0
    assert skeletonize(np.ones((20, 20), np.uint8)).sum() > 0
