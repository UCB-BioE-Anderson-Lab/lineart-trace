"""The consolidated report and visual regression: §3.14.

The rule these tests exist to hold: **`unchecked` is never folded into a pass.** A figure with
nothing wrong and four things nobody could check is not a figure with nothing wrong, and a
report that shows them the same is how "verified" comes to mean nothing.
"""
import copy

import pytest

from lineart_trace.scene import (build, glyphs, io, model, raster, report, style,
                                 validate)


def styled(title="t", description="d"):
    d = model.new("f", 80, 50, title=title, background="#ffffff")
    if description:
        d["description"] = description
    d, _ = style.apply(d, style.load("figure-default"))
    d = model.add(d, build.circle("blob", 20, 20, 8, role="accent-fill"))
    d = model.add(d, build.rect("bar", 40, 14, 24, 12, role="surface-fill"))
    return d


# ------------------------------------------------------------------ the rasteriser
def test_the_rasteriser_is_deterministic():
    """A regression check against a noisy rasteriser reports differences that are not there."""
    d = styled()
    a, b = raster.rasterize(d, 80), raster.rasterize(d, 80)
    assert raster.compare(a, b)["changed"] == 0


def test_the_rasteriser_sizes_the_image_from_the_page_and_the_dpi():
    d = styled()
    img = raster.rasterize(d, 100)
    assert abs(img.shape[1] - 80 / 25.4 * 100) <= 1
    assert abs(img.shape[0] - 50 / 25.4 * 100) <= 1


def test_moving_something_changes_pixels_where_it_moved():
    d = styled()
    a = raster.rasterize(d, 100)
    moved = copy.deepcopy(d)
    model.find(moved, "blob")["transform"] = [1, 0, 0, 1, 10, 0]
    got = raster.compare(a, raster.rasterize(moved, 100))
    assert got["changed"] > 0
    assert got["region"]["x0"] < got["region"]["x1"]


def test_two_different_sizes_are_a_difference_not_an_error():
    d = styled()
    a = raster.rasterize(d, 100)
    b = raster.rasterize(d, 50)
    got = raster.compare(a, b)
    assert got["same_size"] is False and "that IS the difference" in got["why"]


# ------------------------------------------------------------------ regression
def test_a_missing_reference_is_unavailable_not_a_pass(tmp_path):
    """The first run has nothing to compare against; calling that success protects nothing."""
    got = report.regress(styled(), str(tmp_path / "none.png"))
    assert "unavailable" in got


def test_an_unchanged_figure_matches_its_reference(tmp_path):
    import cv2
    d = styled()
    ref = str(tmp_path / "ref.png")
    cv2.imwrite(ref, raster.rasterize(d, 80))
    got = report.regress(d, ref, dpi=80)
    assert got["changed"] == 0 and not got["changed_beyond_tolerance"]


def test_a_changed_figure_is_reported_with_a_diff_image(tmp_path):
    import cv2
    d = styled()
    ref = str(tmp_path / "ref.png")
    cv2.imwrite(ref, raster.rasterize(d, 80))
    moved = copy.deepcopy(d)
    model.find(moved, "bar")["transform"] = [1, 0, 0, 1, 0, 6]
    diff = str(tmp_path / "diff.png")
    got = report.regress(moved, ref, dpi=80, diff_path=diff)
    assert got["changed_beyond_tolerance"] and got["changed"] > 0
    assert got["diff"] == diff
    assert cv2.imread(diff) is not None


def test_a_tolerance_lets_a_small_change_through_and_still_counts_it(tmp_path):
    import cv2
    d = styled()
    ref = str(tmp_path / "ref.png")
    cv2.imwrite(ref, raster.rasterize(d, 80))
    moved = copy.deepcopy(d)
    model.find(moved, "bar")["transform"] = [1, 0, 0, 1, 0, 0.4]
    got = report.regress(moved, ref, dpi=80, tolerance=1.0)
    assert not got["changed_beyond_tolerance"]
    assert got["changed"] > 0, "the count is still reported, not zeroed"


# ------------------------------------------------------------------ the report
def test_a_clean_figure_with_everything_supplied_is_clean(tmp_path):
    import cv2
    d = styled()
    ref = str(tmp_path / "ref.png")
    cv2.imwrite(ref, raster.rasterize(d, 80))
    got = report.full(d, guide=style.load("figure-default"), reference=ref, dpi=80)
    assert got["verdict"] == "clean", got["totals"]
    assert got["totals"] == {"errors": 0, "warnings": 0, "unchecked": 0}


def test_leaving_out_the_guide_or_the_reference_is_unestablished_not_clean():
    d = styled()
    got = report.full(d)
    assert got["verdict"] == "unestablished"
    assert got["totals"]["errors"] == 0
    assert any("style" in u for u in got["unchecked"])
    assert any("regression" in u for u in got["unchecked"])


def test_a_document_that_is_not_a_scene_stops_the_report_rather_than_cascading():
    d = styled()
    model.find(d, "blob")["geometry"]["d"] = [["C", 1, 2]]
    got = report.full(d)
    assert got["verdict"] == "wrong"
    assert "stopped" in got["sections"]
    assert "print" not in got["sections"]


def test_the_report_notices_a_figure_that_is_not_solved():
    d = styled()
    model.find(d, "bar")["relations"] = [{"kind": "align", "to": "blob", "edge": "left"}]
    got = report.full(d)
    assert got["sections"]["layout"]["moved"] == 1
    assert "not the document as drawn" in got["sections"]["layout"]["note"]


def test_the_report_notices_a_glyph_drawn_with_a_version_that_is_gone():
    d = styled()
    d, _ = glyphs.place(d, "lab.tube", "t", at=(60, 5))
    model.find(d, "t")["provenance"]["tool"] = "lab.beaker"
    got = report.full(d)
    assert got["sections"]["glyphs"]["gone"]
    assert got["verdict"] == "wrong"


@pytest.mark.parametrize("missing", ["title", "description"])
def test_a_figure_with_no_accessible_description_is_a_warning(missing):
    d = styled(**{missing: ""})
    got = report.full(d, guide=style.load("figure-default"))
    rules = {f["rule"] for f in got["sections"]["print"]["findings"]}
    assert "accessibility" in rules


def test_the_verdict_never_calls_unchecked_a_pass():
    assert report.verdict(0, 0, 0) == "clean"
    assert report.verdict(0, 0, 3) == "unestablished"
    assert report.verdict(0, 2, 0) == "questionable"
    assert report.verdict(1, 0, 0) == "wrong"
    assert report.verdict(1, 5, 9) == "wrong"
