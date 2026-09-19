"""Timelines, staged reveals and stills: §3.12.

**Any frame of an animation can be exported as a static figure**, so the tests treat a frame
as a figure: it validates, it measures, it verifies. A draw-on that cannot be measured as
half-drawn is a dash-offset trick with better marketing, so that is checked directly.
"""
import json

import pytest

from lineart_trace.scene import (animate, build, geometry, glyphs, io, measure, model,
                                 style, validate, verify)


def styled():
    d = model.new("a", 100, 60, title="t", background="#ffffff")
    d["description"] = "a scene for testing"
    d, _ = style.apply(d, style.load("figure-default"))
    d = model.add(d, build.circle("one", 20, 20, 8, role="accent-fill"))
    d = model.add(d, build.circle("two", 50, 20, 8, role="surface-fill"))
    d = model.add(d, build.text("three", "label", (10, 50), family=None, size=None,
                                role="caption"))
    return d


def lecture():
    return animate.from_stages("l", [
        {"name": "first", "reveal": ["one"], "hold": 1.0},
        {"name": "second", "reveal": ["two"], "hold": 1.0},
        {"name": "third", "reveal": ["three"], "hold": 1.0}])


# ------------------------------------------------------------------ easing
@pytest.mark.parametrize("kind", animate.EASINGS)
def test_every_easing_starts_at_zero_and_ends_at_one(kind):
    assert animate.ease(kind, 0.0) == 0.0
    assert animate.ease(kind, 1.0) == 1.0


def test_step_holds_the_start_value_until_the_very_end():
    assert animate.ease("step", 0.999) == 0.0


def test_easing_is_monotonic():
    for kind in animate.EASINGS:
        got = [animate.ease(kind, i / 20) for i in range(21)]
        assert all(b >= a for a, b in zip(got, got[1:])), kind


# ------------------------------------------------------------------ sampling
def test_a_track_holds_its_end_values_outside_its_range():
    tr = {"target": "one", "property": "opacity",
          "keys": [{"t": 1.0, "value": 0.0}, {"t": 2.0, "value": 1.0}]}
    assert animate.sample(tr, 0.0) == 0.0
    assert animate.sample(tr, 1.5) == pytest.approx(0.5)
    assert animate.sample(tr, 9.0) == 1.0


def test_colours_interpolate_as_colours():
    tr = {"target": "one", "property": "fill",
          "keys": [{"t": 0, "value": "#000000"}, {"t": 1, "value": "#ffffff"}]}
    assert animate.sample(tr, 0.5) == "#808080"


def test_values_of_different_shapes_are_refused_rather_than_guessed():
    tr = {"target": "one", "property": "translate",
          "keys": [{"t": 0, "value": [0, 0]}, {"t": 1, "value": [1, 2, 3]}]}
    with pytest.raises(animate.Incompatible, match="different lengths"):
        animate.sample(tr, 0.5)


# ------------------------------------------------------------------ stages
def test_a_staged_build_gives_a_mark_per_stage_and_a_timeline_that_conforms():
    jsonschema = pytest.importorskip("jsonschema")
    tl = lecture()
    assert list(tl["marks"]) == ["first", "second", "third"]
    assert tl["duration"] == pytest.approx(3 * (0.4 + 1.0))
    schema = json.load(open("lineart_trace/scene/timeline.schema.json"))
    jsonschema.Draft202012Validator(schema).validate(tl)


def test_a_still_of_a_stage_contains_exactly_what_has_been_revealed():
    d, tl = styled(), lecture()
    for stage, want in (("first", {"one"}), ("second", {"one", "two"}),
                        ("third", {"one", "two", "three"})):
        got = animate.still(d, tl, stage)
        assert {a for a, _e, _p in model.walk(got) if "." not in a} == want, stage


def test_a_still_is_taken_after_the_rise_not_at_the_mark():
    """At the mark itself the thing being revealed is still at zero: you would see the stage before."""
    d, tl = styled(), lecture()
    at_mark = animate.at(d, tl, tl["marks"]["second"], drop_hidden=True)
    after = animate.still(d, tl, "second")
    assert "two" not in model.addresses(at_mark)
    assert "two" in model.addresses(after)


def test_every_still_is_a_figure_that_validates_and_verifies():
    d, tl = styled(), lecture()
    for stage in tl["marks"]:
        got = animate.still(d, tl, stage)
        assert validate.problems(got)[0] == [], stage
        assert verify.check(got)["errors"] == 0, stage
        assert measure.bbox(got, model.addresses(got)[0])["value"]["width"] > 0


def test_an_unknown_stage_names_the_ones_there_are():
    with pytest.raises(KeyError, match="first"):
        animate.still(styled(), lecture(), "fourth")


def test_frames_span_the_whole_timeline():
    d, tl = styled(), lecture()
    got = animate.frames(d, tl, 5)
    assert [t for t, _s in got] == pytest.approx(
        [0.0, tl["duration"] / 4, tl["duration"] / 2, 3 * tl["duration"] / 4,
         tl["duration"]])


# ------------------------------------------------------------------ draw-on
def test_a_half_drawn_stroke_measures_as_half_drawn():
    """Real geometry, not a dash-offset trick -- which is the whole point of doing it here."""
    d = styled()
    d = model.add(d, build.through("curve", [(5, 5), (30, 15), (60, 5), (90, 15)],
                                   role="structure-stroke"))
    full = geometry.length([model.find(d, "curve")["geometry"]["d"]])
    tl = {"format": "lineart.timeline/1", "name": "d", "duration": 1.0,
          "tracks": [{"target": "curve", "property": "draw",
                      "keys": [{"t": 0, "value": 0.0}, {"t": 1, "value": 1.0}]}]}
    for t, want in ((0.25, 0.25), (0.5, 0.5), (0.75, 0.75), (1.0, 1.0)):
        got = geometry.length([model.find(animate.at(d, tl, t),
                                          "curve")["geometry"]["d"]])
        assert got / full == pytest.approx(want, abs=0.01), t


def test_a_stroke_drawn_to_zero_still_leaves_a_valid_scene():
    d = styled()
    d = model.add(d, build.line("l", (5, 5), (90, 5), role="structure-stroke"))
    tl = {"format": "lineart.timeline/1", "name": "d", "duration": 1.0,
          "tracks": [{"target": "l", "property": "draw",
                      "keys": [{"t": 0, "value": 0.0}, {"t": 1, "value": 1.0}]}]}
    got = animate.at(d, tl, 0.0)
    assert validate.problems(got)[0] == []


# ------------------------------------------------------------------ morph
def test_morphing_needs_a_correspondence_and_refuses_to_invent_one():
    a = [["M", 0, 0], ["C", 1, 1, 2, 2, 3, 3]]
    b = [["M", 0, 0], ["L", 3, 3]]
    with pytest.raises(animate.Incompatible, match="different structures"):
        animate.morph_track("x", a, b, 0, 1)


def test_a_morph_between_matching_paths_interpolates_every_point():
    a = [["M", 0, 0], ["C", 1, 1, 2, 2, 3, 3]]
    b = [["M", 0, 0], ["C", 3, 3, 6, 6, 9, 9]]
    tr = animate.morph_track("x", a, b, 0.0, 1.0, steps=2)
    mid = tr["keys"][1]["value"]
    assert mid[1] == ["C", 2.0, 2.0, 4.0, 4.0, 6.0, 6.0]


# ------------------------------------------------------------------ export
def test_the_svg_carries_what_smil_can_and_names_what_it_cannot():
    """An explainer that silently lost its draw-on is worse than one that refuses to pretend."""
    d, tl = styled(), lecture()
    out = animate.to_svg(d, tl)
    assert "<animate" in out and "attributeName=\"opacity\"" in out
    tl2 = dict(tl)
    tl2["tracks"] = tl["tracks"] + [{"target": "one", "property": "draw",
                                     "keys": [{"t": 0, "value": 0.0},
                                              {"t": 1, "value": 1.0}]}]
    got = animate.to_svg(d, tl2)
    assert "not animated in this file" in got and "one:draw" in got


def test_a_looping_timeline_says_so_in_the_file():
    d = styled()
    tl = animate.from_stages("l", [{"name": "a", "reveal": ["one"]}], loop=True)
    assert 'repeatCount="indefinite"' in animate.to_svg(d, tl)


def test_a_camera_track_moves_the_window_and_leaves_a_valid_scene():
    """It wrote `canvas.viewbox`, the exporter ignored it, and the schema refused it."""
    import re
    from lineart_trace.scene import svg, validate
    d = styled()
    tl = {"format": "lineart.timeline/1", "name": "pan", "duration": 2.0,
          "tracks": [{"target": "(camera)", "property": "camera",
                      "keys": [{"t": 0, "value": [0, 0, 100, 60]},
                               {"t": 2, "value": [20, 10, 40, 24]}]}]}
    for t, want in ((0.0, "0 0 100 60"), (1.0, "10 5 70 42"), (2.0, "20 10 40 24")):
        got = animate.at(d, tl, t)
        assert validate.problems(got)[0] == [], t
        assert re.search(r'viewBox="([^"]+)"', svg.render(got)).group(1) == want, t


def test_a_scene_with_no_camera_still_shows_the_whole_page():
    import re
    from lineart_trace.scene import svg
    got = re.search(r'viewBox="([^"]+)"', svg.render(styled())).group(1)
    assert got == "0 0 100 60"
