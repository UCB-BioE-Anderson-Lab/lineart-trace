"""Scales, marks and annotations: §3.8.

A plotting layer is only worth having if its axis and its data agree about what the domain
was. So most of what follows is about the scale: that a value lands where the tick says it
does, that the range's order is the direction, and that a domain a scale cannot represent is
a refusal rather than a clamp.
"""
import math

import pytest

from lineart_trace.scene import anchors, data, measure, model, style, validate, verify


def styled(w=120.0, h=90.0):
    d = model.new("p", w, h, background="#ffffff")
    d, _ = style.apply(d, style.load("figure-default"))
    return d


# ------------------------------------------------------------------ scales
def test_a_linear_scale_maps_the_ends_of_the_domain_to_the_ends_of_the_range():
    s = data.linear((0, 100), (10.0, 90.0))
    assert s.map(0) == 10.0 and s.map(100) == 90.0 and s.map(50) == 50.0


def test_the_ranges_order_is_the_direction_and_there_is_no_flag():
    """Two ways to say which way is up could disagree, and once did: zero at the top."""
    up = data.linear((0, 100), (90.0, 10.0))
    assert up.map(0) == 90.0 and up.map(100) == 10.0
    assert "flip" not in repr(up)


def test_a_log_scale_puts_the_decades_evenly_apart():
    s = data.log((1, 1000), (0.0, 60.0))
    a, b, c = s.map(1), s.map(10), s.map(100)
    assert (a, b, c) == pytest.approx((0.0, 20.0, 40.0), abs=1e-9)
    assert [t for _v, _p, t in s.ticks()] == ["1", "10", "100", "1000"]


def test_a_log_scale_refuses_a_domain_it_cannot_represent():
    """Clamping zero to something finite draws it somewhere, and no reader would know."""
    with pytest.raises(ValueError, match="positive domain"):
        data.log((0, 10), (0.0, 1.0))


def test_a_categorical_scale_centres_its_bands_and_refuses_an_unknown_category():
    s = data.categorical(["a", "b", "c"], (0.0, 60.0))
    assert [s.map(c) for c in "abc"] == pytest.approx([10.0, 30.0, 50.0], abs=1e-9)
    assert s.band() == pytest.approx(20.0 * 0.75)
    with pytest.raises(KeyError, match="not in this scale"):
        s.map("z")


@pytest.mark.parametrize("lo,hi,want_step", [(0, 10, 2), (0, 1, 0.2), (0, 100, 20),
                                             (3, 7, 1)])
def test_ticks_are_round_numbers(lo, hi, want_step):
    got = data.nice_ticks(lo, hi, 5)
    assert len(got) >= 2
    steps = {round(b - a, 9) for a, b in zip(got, got[1:])}
    assert len(steps) == 1
    assert steps.pop() == pytest.approx(want_step, rel=0.51)
    assert all(lo - 1e-9 <= v <= hi + 1e-9 for v in got)


def test_ticks_are_deterministic():
    assert data.nice_ticks(0, 37, 5) == data.nice_ticks(0, 37, 5)


# ------------------------------------------------------------------ axes and marks
def test_an_axis_ticks_where_its_scale_says():
    """The axis and the data must not disagree about what the domain was."""
    s = data.linear((0, 100), (10.0, 90.0))
    d = model.add(styled(), data.axis(s, 60.0, "bottom", ticks=5, name="ax"))
    for i, (_v, pos, _t) in enumerate(s.ticks(5), 1):
        tick = measure.bbox(d, f"ax.tick-{i:02d}")["value"]
        assert tick["x"] == pytest.approx(pos, abs=1e-6)


def test_marks_land_on_the_same_scale_the_axis_was_drawn_from():
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 10), (80.0, 10.0))
    d = model.add(styled(), data.points([0, 5, 10], [0, 5, 10], sx, sy, radius=1.0,
                                        name="pts"))
    first = measure.bbox(d, "pts.p-001")["value"]
    assert first["x"] + first["width"] / 2 == pytest.approx(sx.map(0), abs=1e-6)
    assert first["y"] + first["height"] / 2 == pytest.approx(sy.map(0), abs=1e-6)


def test_bars_sit_on_their_categories_and_start_at_the_baseline():
    sx = data.categorical(["a", "b"], (10.0, 90.0))
    sy = data.linear((0, 10), (80.0, 10.0))
    d = model.add(styled(), data.bars(["a", "b"], [5, 10], sx, sy, name="bars"))
    b1 = measure.bbox(d, "bars.bar-01")["value"]
    assert b1["x"] + b1["width"] / 2 == pytest.approx(sx.map("a"), abs=1e-6)
    assert b1["y"] + b1["height"] == pytest.approx(sy.map(0), abs=1e-6)
    assert b1["y"] == pytest.approx(sy.map(5), abs=1e-6)


def test_error_bars_span_the_error():
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 10), (80.0, 10.0))
    d = model.add(styled(), data.errorbars([5], [5], [2], sx, sy, name="e"))
    box = measure.bbox(d, "e")["value"]
    assert box["y"] == pytest.approx(sy.map(7), abs=1e-6)
    assert box["y"] + box["height"] == pytest.approx(sy.map(3), abs=1e-6)


def test_a_histogram_counts_what_it_draws():
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 5), (80.0, 10.0))
    # Bins are [0,2) [2,4) [4,6) [6,8) [8,10]: the 2 belongs to the SECOND bin.
    _g, counts = data.histogram([1, 1, 2, 7, 9, 9.5], sx, sy, bins=5)
    assert counts == [2, 1, 0, 1, 2]
    assert sum(counts) == 6


# ------------------------------------------------------------------ the fit
def test_a_fit_recovers_a_line_it_was_given_exactly():
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 40), (80.0, 10.0))
    xs = list(range(11))
    ys = [3.0 + 2.5 * x for x in xs]
    _g, stats = data.fit(xs, ys, sx, sy)
    assert stats["slope"] == pytest.approx(2.5, abs=1e-9)
    assert stats["intercept"] == pytest.approx(3.0, abs=1e-9)
    assert stats["r2"] == pytest.approx(1.0, abs=1e-12)
    assert stats["n"] == 11


def test_a_band_that_runs_off_the_panel_is_held_inside_it_and_counted():
    """A band silently trimmed is a confidence interval drawn narrower than it is."""
    sx = data.linear((0, 9), (10.0, 90.0))
    sy = data.linear((0, 20), (80.0, 10.0))
    _g, stats = data.fit(list(range(10)), [x * x for x in range(10)], sx, sy)
    assert stats["band_clamped"] > 0


def test_a_fit_reports_its_numbers_so_they_can_be_checked():
    """A fitted line whose numbers live only in the picture is one nobody can check."""
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 40), (80.0, 10.0))
    _g, stats = data.fit(list(range(11)), [3 + 2.5 * x + (x % 3) for x in range(11)],
                         sx, sy)
    assert 0 < stats["r2"] < 1 and stats["residual_se"] > 0
    assert "95%" in stats["confidence"]


def test_a_fit_refuses_what_it_cannot_fit():
    sx = data.linear((0, 10), (10.0, 90.0))
    sy = data.linear((0, 10), (80.0, 10.0))
    with pytest.raises(ValueError, match="at least three"):
        data.fit([1, 2], [1, 2], sx, sy)
    with pytest.raises(ValueError, match="no line to fit"):
        data.fit([5, 5, 5], [1, 2, 3], sx, sy)


# ------------------------------------------------------------------ whole panels
def test_a_plot_panel_is_a_valid_scene_that_verifies_clean():
    d = styled(140.0, 100.0)
    g, rep = data.plot("p", list(range(10)), [3 + 2.5 * x for x in range(10)], 120.0,
                       80.0, xlabel="x", ylabel="y", title="A", fit_line=True)
    assert rep["fit"]["band_clamped"] == 0
    d = model.add(d, g)
    assert validate.problems(d)[0] == []
    _s, srep = anchors.solve(d)
    got = verify.check(d, solve_report=srep)
    assert got["errors"] == 0, got["findings"]


def test_a_plot_is_drawn_entirely_by_role_so_it_restyles():
    d = styled(140.0, 100.0)
    g, _rep = data.plot("p", list(range(10)), list(range(10)), 120.0, 80.0)
    d = model.add(d, g)
    literals = [a for a, el, _p in model.walk(d)
                if a.startswith("p") and (el.get("style") or {})]
    assert literals == [], literals
    dark, _ = style.apply(d, style.load("figure-default"), "dark")
    from lineart_trace.scene import svg
    assert svg.render(dark) != svg.render(d)


def test_a_plot_records_the_file_it_came_from(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("x,y\n1,2\n2,4\n3,6\n")
    cols, rows = data.read_table(str(csv))
    assert cols == ["x", "y"] and len(rows) == 3 and rows[0]["y"] == 2.0
    g, _rep = data.plot("p", [r["x"] for r in rows], [r["y"] for r in rows], 100.0, 60.0,
                        source=str(csv))
    assert g["provenance"]["origin"] == "data"
    assert len(g["provenance"]["sha256"]) == 64
    assert g["provenance"]["params"]["rows"] == 3


def test_an_unknown_plot_kind_names_the_ones_that_exist():
    with pytest.raises(ValueError, match="no plot kind"):
        data.plot("p", [1, 2], [1, 2], 50.0, 50.0, kind="violin")


# ------------------------------------------------------------------ the legend plate
def test_a_legend_gets_a_plate_and_the_check_sees_through_it():
    """A plate is the standard fix for a legend over a grid; the check must recognise it."""
    d = styled(140.0, 100.0)
    g, _rep = data.plot("p", list(range(10)), list(range(10)), 120.0, 80.0)
    g["children"].append(data.legend([("series", "accent-fill")], (30.0, 20.0),
                                     width=16.0))
    d = model.add(d, g)
    got = verify.check(d, rules=["label-overlap"])
    assert got["errors"] == 0, got["findings"]


def test_but_what_the_plate_hides_is_reported_rather_than_forgiven():
    """A plate over a gridline is the fix; a plate over the data is lost data."""
    d = styled(140.0, 100.0)
    g, _rep = data.plot("p", list(range(10)), list(range(10)), 120.0, 80.0)
    g["children"].append(data.legend([("series", "accent-fill")], (30.0, 20.0),
                                     width=16.0))
    d = model.add(d, g)
    got = verify.check(d, rules=["label-overlap", "occluded"])
    assert any(f["rule"] == "occluded" for f in got["findings"]), got["findings"]


def test_a_legend_without_a_plate_is_reported_as_the_overlap_it_is():
    d = styled(140.0, 100.0)
    g, _rep = data.plot("p", list(range(10)), list(range(10)), 120.0, 80.0)
    g["children"].append(data.legend([("series", "accent-fill")], (30.0, 20.0),
                                     backing=None))
    d = model.add(d, g)
    got = verify.check(d, rules=["label-overlap"])
    assert got["errors"] > 0
