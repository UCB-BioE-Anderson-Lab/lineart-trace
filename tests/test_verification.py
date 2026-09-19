"""Verification and the overlay view: is the figure right, and can a person see why.

Two rules govern these tests. A check must fire on the defect it names and stay silent on a
correct figure -- a check that fires on everything is one nobody reads. And a view must be a
pure function of its payload, which is testable directly: hand it a dict, get markup.
"""
import pytest

from lineart_trace.scene import (anchors, build, measure, model, overlay, text as t,
                                 verify)


def page(**canvas):
    d = model.new("v", 60, 40, background="#ffffff")
    d["canvas"].update(canvas)
    return d


def rules(report):
    return {f["rule"] for f in report["findings"]}


# ------------------------------------------------------------------ each rule fires
def test_type_below_the_floor_is_an_error():
    d = model.add(page(), build.text("tiny", "caption", (5, 10), size="4pt"))
    got = verify.check(d, rules=["type-size"])
    assert rules(got) == {"type-size"}
    assert got["findings"][0]["measured_pt"] == pytest.approx(4.0, abs=1e-6)
    assert not verify.check(
        model.add(page(), build.text("ok", "caption", (5, 10), size="8pt")),
        rules=["type-size"])["findings"]


def test_a_hairline_rule_is_an_error():
    d = model.add(page(), build.rect("hair", 5, 5, 30, 5,
                                     style={"stroke": "#000000", "fill": "none",
                                            "stroke_width": "0.1pt"}))
    assert rules(verify.check(d, rules=["stroke-weight"])) == {"stroke-weight"}


def test_low_contrast_against_the_ACTUAL_background():
    pale = {"stroke": "#cccccc", "fill": "none", "stroke_width": "1pt"}
    on_white = model.add(page(), build.rect("r", 5, 5, 10, 10, style=pale))
    on_dark = model.add(page(background="#222222"), build.rect("r", 5, 5, 10, 10,
                                                               style=pale))
    assert rules(verify.check(on_white, rules=["contrast"])) == {"contrast"}
    assert not verify.check(on_dark, rules=["contrast"])["findings"]


def test_a_transparent_background_makes_contrast_UNCHECKED_not_passed():
    """Nothing to measure against is not the same as measuring and finding it fine."""
    d = model.add(page(background="none"),
                  build.rect("r", 5, 5, 10, 10, style={"fill": "#cccccc"}))
    got = verify.check(d, rules=["contrast"])
    assert not got["findings"]
    assert any(u["rule"] == "contrast" for u in got["unchecked"])


def test_off_canvas_distinguishes_clipped_from_gone():
    clipped = model.add(page(), build.circle("c", 58, 20, 6))
    gone = model.add(page(), build.circle("c", 200, 20, 6))
    a = verify.check(clipped, rules=["off-canvas"])["findings"][0]
    b = verify.check(gone, rules=["off-canvas"])["findings"][0]
    assert a["severity"] == "warning" and "clipped" in a["message"]
    assert b["severity"] == "error" and "outside" in b["message"]


def test_missing_glyphs_are_found_before_they_print_as_boxes():
    if not _have("Helvetica"):
        pytest.skip("no Helvetica")
    d = model.add(page(), build.text("t", "temperature ℃ \U0001f9ec", (5, 10),
                                     family="Helvetica", size="8pt"))
    got = verify.check(d, rules=["missing-glyphs"])
    assert not got["findings"] or got["findings"][0]["rule"] == "missing-glyphs"


def _have(family):
    from lineart_trace.scene import fonts
    try:
        fonts.resolve(family)
        return True
    except fonts.FontNotFound:
        return False


def test_two_colours_that_look_alike_are_a_warning_and_dichromacy_is_checked():
    d = model.add(page(), build.circle("a", 10, 10, 4, style={"fill": "#3b7dd8"}))
    d = model.add(d, build.circle("b", 30, 10, 4, style={"fill": "#3b7ad8"}))
    assert rules(verify.check(d, rules=["colour-distinguishable"])) == \
        {"colour-distinguishable"}
    assert verify.simulate("#d83b3b", "deuteranopia") != "#d83b3b"
    assert verify.simulate("none") is None


def test_contrast_ratio_matches_the_wcag_definition():
    assert verify.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-6)
    assert verify.contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=1e-9)
    assert verify.contrast_ratio("not a colour", "#fff") is None


# ------------------------------------------------------------------ what does NOT fire
def test_a_drawing_that_overlaps_itself_is_not_a_finding():
    """A check that fires on every correct figure hides the one finding that matters."""
    d = page()
    d = model.add(d, build.circle("a", 20, 20, 10, style={"stroke": "#000", "fill": "none",
                                                          "stroke_width": "1pt"}))
    d = model.add(d, build.circle("b", 26, 20, 10, style={"stroke": "#000", "fill": "none",
                                                          "stroke_width": "1pt"}))
    assert not verify.check(d, rules=["label-overlap"])["findings"]


def test_a_label_CROSSING_the_art_is_a_finding():
    """What makes text unreadable is ink running through it -- so the test is crossing."""
    if not _have("Helvetica"):
        pytest.skip("no Helvetica")
    d = page()
    d = model.add(d, build.circle("art", 20, 20, 8, style={"fill": "#dddddd"}))
    d = model.add(d, build.text("lab", "across the art", (8, 20), family="Helvetica",
                                size="8pt", style={"fill": "#000000"}))
    assert rules(verify.check(d, rules=["label-overlap"])) == {"label-overlap"}


def test_a_label_sitting_INSIDE_the_shape_it_labels_is_not_a_finding():
    """A caption inside its own box is the normal case; the first version called it an error."""
    if not _have("Helvetica"):
        pytest.skip("no Helvetica")
    d = page()
    d = model.add(d, build.rect("box", 4, 12, 40, 12, style={"fill": "#dddddd",
                                                             "stroke": "#333333",
                                                             "stroke_width": "0.5pt"}))
    d = model.add(d, build.text("lab", "inside", (16, 20), family="Helvetica",
                                size="6pt", style={"fill": "#000000"}))
    got = verify.check(d, rules=["label-overlap"])
    assert got["findings"] == [], got["findings"]


def test_a_label_crossing_line_work_is_a_finding():
    if not _have("Helvetica"):
        pytest.skip("no Helvetica")
    d = page()
    d = model.add(d, build.line("rule", (2, 20), (55, 20),
                                style={"stroke": "#333333", "fill": "none",
                                       "stroke_width": "0.5pt"}))
    d = model.add(d, build.text("lab", "on the rule", (10, 21), family="Helvetica",
                                size="8pt", style={"fill": "#000000"}))
    assert rules(verify.check(d, rules=["label-overlap"])) == {"label-overlap"}


def test_separation_is_measured_between_objects_not_inside_one():
    inner = build.group("thing", [
        build.line("a", (5, 5), (25, 5), style={"stroke": "#000", "fill": "none",
                                                "stroke_width": "0.5pt"}),
        build.line("b", (5, 5.05), (25, 5.05), style={"stroke": "#000", "fill": "none",
                                                      "stroke_width": "0.5pt"})])
    d = model.add(page(), inner)
    assert not verify.check(d, rules=["separation"])["findings"]
    d = model.add(d, build.line("other", (5, 5.1), (25, 5.1),
                                style={"stroke": "#000", "fill": "none",
                                       "stroke_width": "0.5pt"}))
    assert rules(verify.check(d, rules=["separation"])) == {"separation"}


def test_repeated_findings_collapse_into_one_that_counts_them():
    d = page()
    for i in range(5):
        d = model.add(d, build.rect(f"r-{i}", 2 + i * 5, 5, 4, 4,
                                    style={"stroke": "#cccccc", "fill": "none",
                                           "stroke_width": "1pt"}))
    got = verify.check(d, rules=["contrast"])
    assert len(got["findings"]) == 1
    assert got["findings"][0]["count"] == 5
    assert len(got["findings"][0]["elements"]) == 5


def test_unsolved_is_unchecked_without_a_solve_report_and_an_error_with_a_bad_one():
    d = model.add(page(), build.rect("a", 1, 1, 5, 5))
    assert any(u["rule"] == "unsolved"
               for u in verify.check(d, rules=["unsolved"])["unchecked"])
    bad = {"unsatisfiable": [{"element": "a", "kind": "inside", "to": "b",
                              "why": "too big"}], "unsettled": [], "anchors": {}}
    assert rules(verify.check(d, rules=["unsolved"], solve_report=bad)) == {"unsolved"}


def test_text_with_no_measurable_font_is_UNCHECKED_not_clean():
    """A text element used to measure 0x0 and pass every check there is."""
    d = model.add(page(), build.text("t", "hello", (5, 10), family="No Such Family",
                                     size="8pt"))
    got = verify.check(d, rules=["off-canvas", "label-overlap"])
    assert not got["findings"]
    assert got["unchecked"]
    with pytest.raises(measure.Unmeasurable):
        measure.bbox(d, "t")


# ------------------------------------------------------------------ the view
def demo_payload():
    d = page()
    d = model.add(d, build.circle("blob", 20, 20, 8))
    d = model.add(d, build.rect("tag", 0, 0, 14, 5))
    model.find(d, "blob")["anchors"] = {"east": {"how": "derived", "by": "bbox.e"}}
    model.find(d, "tag")["anchors"] = {"tip": {"how": "derived", "by": "bbox.w"}}
    model.find(d, "tag")["relations"] = [{"kind": "attach", "to": "blob.east",
                                          "via": "tip", "offset": [3, 0]}]
    d, _ = anchors.solve(d)
    return d, overlay.payload(d, findings=verify.check(d)["findings"])


def test_the_payload_carries_the_same_numbers_the_measure_tools_report():
    """One answer in the system. A view that measured for itself would be a second."""
    d, load = demo_payload()
    for b in load["boxes"]:
        want = measure.bbox(d, b["address"])["value"]
        assert (round(b["x"], 9), round(b["width"], 9)) == \
            (round(want["x"], 9), round(want["width"], 9))


def test_the_view_needs_nothing_but_its_payload():
    """Purity, checked the only way that means anything: render a hand-written dict."""
    hand = {"format": "lineart.overlay/1",
            "canvas": {"width": 10, "height": 10, "unit": "mm"},
            "boxes": [{"address": "a", "type": "path", "x": 1, "y": 1,
                       "width": 4, "height": 2, "label": True}],
            "anchors": [], "relations": []}
    out = overlay.render(hand)
    assert out.startswith("<svg") and "overlay-boxes" in out and ">a<" in out


def test_absence_renders_differently_from_emptiness():
    """An empty section looks exactly like good news, so it must not look like one."""
    base = {"format": "lineart.overlay/1",
            "canvas": {"width": 10, "height": 10, "unit": "mm"},
            "boxes": [], "anchors": [], "relations": []}
    empty = overlay.render(dict(base, findings=[]))
    absent = overlay.render(dict(base, findings={"unavailable": "no check was run"}))
    assert "not shown" not in empty
    assert "not shown" in absent and "no check was run" in absent


def test_the_producer_decides_which_labels_fit_and_the_view_obeys():
    d, load = demo_payload()
    narrow = dict(load)
    narrow["boxes"] = [dict(b, label=False) for b in load["boxes"]]
    out = overlay.render(narrow)
    assert "overlay-names" not in out or ">blob<" not in out
    assert "too narrow" in out


def test_the_overlay_says_when_it_is_only_showing_part_of_the_tree():
    d = page()
    d = model.add(d, build.group("outer", [build.group("inner", [
        build.rect("deep", 1, 1, 3, 3)])]))
    shallow = overlay.payload(d, depth=1)
    assert [b["address"] for b in shallow["boxes"]] == ["outer"]
    assert "depth: not shown" in overlay.render(shallow)
    deep = overlay.payload(d, depth=None)
    assert "outer.inner.deep" in [b["address"] for b in deep["boxes"]]
    assert "depth: not shown" not in overlay.render(deep)
