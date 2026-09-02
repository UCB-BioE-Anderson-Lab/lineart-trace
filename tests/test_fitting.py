import numpy as np
import pytest

from lineart_trace.fitting import corner_indices, fit_curve, smooth_chain
from lineart_trace.raster import flatten_path


def polyline(*corners, n=60):
    pts = []
    for a, b in zip(corners, corners[1:]):
        a, b = np.array(a, float), np.array(b, float)
        pts.extend(a + (b - a) * s for s in np.linspace(0, 1, n, endpoint=False))
    pts.append(np.array(corners[-1], float))
    return np.array(pts)


def max_deviation(pts, curves):
    """Worst distance from an input point to the fitted curve."""
    poly = flatten_path(curves, 0.05)
    d = np.linalg.norm(pts[:, None, :] - poly[None, :, :], axis=2)
    return float(d.min(axis=1).max())


def test_straight_line_is_one_segment():
    pts = polyline((0, 0), (300, 0))
    assert len(fit_curve(pts, 1.0)) == 1


def test_two_points():
    assert len(fit_curve(np.array([[0.0, 0.0], [10.0, 0.0]]))) == 1


def test_degenerate_input():
    assert fit_curve(np.zeros((1, 2))) == []
    assert fit_curve(np.zeros((0, 2))) == []


def test_circle_is_a_handful_of_segments():
    t = np.linspace(0, 2 * np.pi, 400)
    pts = np.stack([200 + 90 * np.cos(t), 150 + 90 * np.sin(t)], 1)
    curves = fit_curve(pts, 1.0, closed=True)
    assert 3 <= len(curves) <= 6
    assert np.allclose(curves[0][0], curves[-1][3], atol=1e-6)


def test_square_is_four_segments():
    """Least squares rounds corners; detection must cut the fit at them."""
    pts = polyline((0, 0), (100, 0), (100, 100), (0, 100), (0, 0))
    assert len(fit_curve(pts, 1.0, closed=True)) == 4


def test_corner_is_kept_sharp():
    pts = polyline((0, 0), (100, 0), (100, 100))
    with_corner = fit_curve(pts, 1.0, corner_angle=75)
    without = fit_curve(pts, 1.0, corner_angle=0)
    assert max_deviation(pts, with_corner) < max_deviation(pts, without)
    assert max_deviation(pts, with_corner) < 1.5


def test_corner_indices_finds_each_turn():
    pts = polyline((0, 0), (100, 0), (100, 100), (0, 100))
    assert len(corner_indices(pts, 75.0)) == 2


def test_corner_indices_ignores_a_smooth_curve():
    t = np.linspace(0, np.pi, 300)
    pts = np.stack([200 * t / np.pi, 100 * np.sin(t)], 1)
    assert corner_indices(pts, 75.0) == []


@pytest.mark.parametrize("error", [0.5, 1.0, 2.0])
def test_tolerance_is_respected(error):
    t = np.linspace(0, 3 * np.pi, 500)
    pts = np.stack([t * 30, 80 * np.sin(t)], 1)
    curves = fit_curve(pts, error, smooth=0, corner_angle=0)
    assert max_deviation(pts, curves) <= error * 1.5


def test_tighter_tolerance_costs_more_segments():
    t = np.linspace(0, 3 * np.pi, 500)
    pts = np.stack([t * 30, 80 * np.sin(t)], 1)
    loose = len(fit_curve(pts, 4.0, smooth=0, corner_angle=0))
    tight = len(fit_curve(pts, 0.3, smooth=0, corner_angle=0))
    assert tight > loose


def test_no_control_point_flies_off():
    """Regression: the least-squares solve could fling a control point far
    outside the data, drawing as a long spurious line."""
    rng = np.random.default_rng(3)
    for _ in range(30):
        pts = np.cumsum(rng.normal(0, 3, (120, 2)), axis=0)
        lo, hi = pts.min(0), pts.max(0)
        span = np.maximum(hi - lo, 1.0)
        for c in fit_curve(pts, 1.0):
            for p in c:
                assert np.all(p > lo - 2 * span) and np.all(p < hi + 2 * span)


def test_smoothing_pins_the_ends():
    pts = np.cumsum(np.ones((40, 2)), axis=0).astype(float)
    out = smooth_chain(pts, 5)
    assert np.allclose(out[0], pts[0]) and np.allclose(out[-1], pts[-1])


def test_smoothing_reduces_jitter():
    rng = np.random.default_rng(1)
    clean = np.stack([np.linspace(0, 200, 200), np.zeros(200)], 1)
    noisy = clean + rng.normal(0, 0.5, clean.shape)
    before = np.abs(noisy[:, 1]).mean()
    after = np.abs(smooth_chain(noisy, 7)[:, 1]).mean()
    assert after < before
