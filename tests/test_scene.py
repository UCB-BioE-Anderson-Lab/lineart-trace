"""The scene: its addressing, its units, its determinism, and what it refuses.

The tests that matter here are not "a good scene passes". They are the ones that would let a
bad scene through quietly: an address that resolves to two things, a rename that leaves a
reference pointing at a name nobody has, a page length that silently means frame pixels, and
a writer whose output depends on the order a dict happened to be built in.
"""
import json
import os
import subprocess
import sys

import pytest

from lineart_trace.scene import io, measure, model, svg, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scene():
    d = model.new("demo", 90, 60, title="A demo")
    d["frames"]["art"] = {"parent": "page", "unit": "px",
                          "transform": [0.0718, 0, 0, 0.0718, 4, 4]}
    d = model.add(d, {"name": "enzyme", "type": "group", "frame": "art",
                      "anchors": {"active-site": {"how": "authored", "at": [612, 388],
                                                  "dir": [0, -1]}},
                      "children": []})
    d = model.add(d, {"name": "outline", "type": "path", "role": "structure-stroke",
                      "style": {"stroke_width": "1.2pt"},
                      "geometry": {"kind": "path", "closed": True,
                                   "d": [["M", 512, 96],
                                         ["C", 640, 96, 720, 176, 720, 304],
                                         ["Z"]]}}, "enzyme")
    return d


# ------------------------------------------------------------------ determinism
def test_writing_is_byte_stable_through_a_round_trip():
    d = scene()
    once = io.dumps(d)
    assert io.dumps(io.loads(once)) == once


def test_key_order_does_not_follow_insertion_order():
    """Two documents equal as data must be equal as bytes, or nothing downstream diffs."""
    a = {"name": "x", "format": "lineart.scene/1", "canvas": {"unit": "mm", "width": 1}}
    b = {"canvas": {"width": 1, "unit": "mm"}, "format": "lineart.scene/1", "name": "x"}
    assert io.dumps(a) == io.dumps(b)


def test_numpy_scalars_and_float_noise_are_written_as_plain_numbers():
    np = pytest.importorskip("numpy")
    text = io.dumps({"d": [["C", np.float64(0.07180000000001), np.int64(3), -0.0]]})
    assert text.strip() == '{\n  "d": [\n    ["C", 0.0718, 3, 0]\n  ]\n}'


def test_a_segment_stays_on_one_line():
    """A diff must be able to name the segment that moved, not the number."""
    text = io.dumps(scene())
    assert '["C", 640, 96, 720, 176, 720, 304]' in text


# ------------------------------------------------------------------ addressing
def test_an_address_resolves_to_an_element_or_an_anchor():
    d = scene()
    assert model.resolve(d, "enzyme.outline")["kind"] == "element"
    assert model.resolve(d, "enzyme.active-site")["kind"] == "anchor"
    with pytest.raises(KeyError):
        model.resolve(d, "enzyme.nothing-here")


def test_an_anchor_that_collides_with_a_child_is_refused():
    """`enzyme.active-site` naming two things is the one way addressing stops being total."""
    d = model.add(scene(), {"name": "active-site", "type": "path",
                            "geometry": {"kind": "path", "d": [["M", 0, 0]]}}, "enzyme")
    bad, _warn = validate.problems(d)
    assert any("both a child and an anchor" in b for b in bad)


def test_duplicate_sibling_names_are_refused_at_the_point_of_the_edit():
    d = scene()
    with pytest.raises(ValueError, match="already has a child"):
        model.add(d, {"name": "outline", "type": "path",
                      "geometry": {"kind": "path", "d": [["M", 0, 0]]}}, "enzyme")


def test_rename_moves_every_address_beneath_it_and_rewrites_references():
    """The cost of identity-by-name, and the test that it is actually paid."""
    d = scene()
    d["elements"][0]["children"].append(
        {"name": "leader", "type": "path",
         "relations": [{"to": "enzyme.active-site", "kind": "attach"}],
         "geometry": {"kind": "path", "d": [["M", 0, 0]]}})
    assert validate.problems(d)[0] == []
    out, n = model.rename(d, "enzyme", "pol")
    assert n == 1
    assert "pol.outline" in model.addresses(out)
    assert model.find(out, "pol.leader")["relations"][0]["to"] == "pol.active-site"


def test_a_reference_to_nothing_is_reported():
    d = scene()
    d["elements"][0]["children"].append(
        {"name": "leader", "type": "path",
         "relations": [{"to": "enzyme.nowhere"}],
         "geometry": {"kind": "path", "d": [["M", 0, 0]]}})
    bad, _warn = validate.problems(d)
    assert any("which is nothing in this scene" in b for b in bad)


def test_a_relation_to_your_own_descendant_is_refused():
    d = scene()
    d["elements"][0]["relations"] = [{"to": "enzyme.outline"}]
    bad, _warn = validate.problems(d)
    assert any("itself or something inside it" in b for b in bad)


def test_a_relation_via_an_anchor_that_is_not_yours_is_refused():
    d = scene()
    d["elements"][0]["children"][0]["relations"] = [
        {"to": "enzyme", "via": "active-site"}]     # that anchor is the parent's, not mine
    bad, _warn = validate.problems(d)
    assert any("not an anchor on this element" in b for b in bad)


# ------------------------------------------------------------------ units
def test_a_page_length_holds_on_paper_however_deeply_it_is_nested():
    """1.2pt is 1.2pt of paper; in a frame of 0.0718 mm pixels that is 5.896 of them."""
    d = scene()
    got = model.resolve_length(d, "1.2pt", "art")
    assert round(got, 3) == 5.896
    assert round(got * 0.0718 / (25.4 / 72), 4) == 1.2


def test_a_bare_number_is_already_in_its_frame():
    assert model.resolve_length(scene(), 5.0, "art") == 5.0


def test_the_page_frame_must_use_the_canvas_unit():
    d = scene()
    d["canvas"]["unit"] = "pt"
    bad, _warn = validate.problems(d)
    assert any("must be the canvas unit" in b for b in bad)


def test_a_frame_cycle_is_named_rather_than_looped():
    d = scene()
    d["frames"]["art"]["parent"] = "art"
    bad, _warn = validate.problems(d)
    assert any("frame cycle" in b or "no parent" in b for b in bad)


# ------------------------------------------------------------------ geometry
@pytest.mark.parametrize("segs,expect", [
    ([["C", 1, 2]], "a run must open with M"),
    ([["M", 0, 0], ["C", 1, 2]], "C takes 6 numbers"),
    ([["M", 0, 0], ["Z"], ["L", 1, 1]], "must be its last segment"),
    ([["M", 0, 0], ["M", 1, 1]], "a path element holds ONE run"),
])
def test_a_malformed_run_is_refused(segs, expect):
    """JSON Schema can bound the array; only this can tie its length to its verb."""
    d = model.add(scene(), {"name": "bad", "type": "path",
                            "geometry": {"kind": "path", "d": segs}})
    bad, _warn = validate.problems(d)
    assert any(expect in b for b in bad), bad


def test_a_group_with_geometry_and_a_path_with_children_are_both_refused():
    d = scene()
    d["elements"][0]["geometry"] = {"kind": "path", "d": [["M", 0, 0]]}
    bad, _warn = validate.problems(d)
    assert any("a group has children, not geometry" in b for b in bad)


def test_an_anisotropic_frame_warns_and_does_not_fail():
    d = scene()
    d["frames"]["art"]["transform"] = [0.0718, 0, 0, 0.09, 4, 4]
    bad, warn = validate.problems(d)
    assert not bad
    assert any("anisotropic" in w for w in warn)


# ------------------------------------------------------------------ export
def test_export_converts_a_page_stroke_into_the_frame_it_is_drawn_in():
    out = svg.render(scene())
    assert 'stroke-width="5.896"' in out
    assert 'width="90mm"' in out and 'viewBox="0 0 90 60"' in out


def test_export_carries_the_address_as_the_id_and_can_be_prefixed():
    out = svg.render(scene(), standalone=False, prefix="fig1-")
    assert 'id="fig1-enzyme.outline"' in out


def test_export_refuses_to_draw_a_glyph_it_cannot_draw():
    """A placeholder would look like the figure was finished. §3.7 is not built."""
    d = model.add(scene(), {"name": "dna", "type": "glyph",
                            "geometry": {"kind": "glyph", "glyph": "duplex"}})
    with pytest.raises(NotImplementedError):
        svg.render(d)


def test_a_guide_never_renders():
    d = model.add(scene(), {"name": "axis", "type": "guide",
                            "geometry": {"kind": "path", "d": [["M", 0, 0], ["L", 9, 9]]}})
    assert "axis" not in svg.render(d)


# ------------------------------------------------------------------ measurement
def test_a_measurement_says_which_frame_and_unit_it_is_in():
    d = scene()
    page = measure.bbox(d, "enzyme")
    art = measure.bbox(d, "enzyme", "art")
    assert page["unit"] == "mm" and art["unit"] == "px"
    assert round(art["value"]["width"] * 0.0718, 6) == round(page["value"]["width"], 6)


def test_measuring_something_with_no_geometry_refuses_rather_than_returning_zero():
    d = model.add(model.new("x", 10, 10), {"name": "empty", "type": "group",
                                           "children": []})
    with pytest.raises(ValueError, match="no extent"):
        measure.bbox(d, "empty")


# ------------------------------------------------------------------ the checker
def _run(*args):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-m", "lineart_trace.scene.cli", *args],
                          cwd=ROOT, capture_output=True, text=True, env=env)


def test_the_checker_answers_zero_one_and_two_and_never_confuses_them(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(io.dumps(scene()))
    assert _run("validate", str(good)).returncode == 0

    bad_doc = scene()
    bad_doc["elements"][0]["geometry"] = {"kind": "path", "d": [["M", 0, 0]]}
    bad = tmp_path / "bad.json"
    bad.write_text(io.dumps(bad_doc))
    r = _run("validate", str(bad))
    assert r.returncode == 1 and "not a scene" in r.stdout

    assert _run("validate", str(tmp_path / "absent.json")).returncode == 2
    junk = tmp_path / "junk.json"
    junk.write_text("{not json")
    assert _run("validate", str(junk)).returncode == 2


def test_a_transform_refuses_to_guess_where_to_write(tmp_path):
    src = tmp_path / "s.json"
    src.write_text(io.dumps(scene()))
    r = _run("rename", "--in", str(src), "enzyme", "pol")
    assert r.returncode == 3 and "--out" in r.stderr
    assert io.loads(src.read_text()) == scene()          # and it did not touch the input


# ------------------------------------------------------------------ the records
def test_every_record_still_matches_the_docstring_it_came_from():
    """The drift detector. A generated record nobody regenerated is a hand-written one.

    This is the check that makes generation worth doing: edit a verb's behaviour or its
    description and forget to regenerate, and the store's claim about it is false until
    somebody reads both files side by side. Here, it is a failing test.
    """
    from lineart_trace import records
    assert records.stale() == []


def test_a_verb_with_no_docstring_gets_no_record_and_is_named():
    """Rule: a description invented from a function name is a guess in an index."""
    from lineart_trace import records

    def verb_undocumented(a):
        pass

    got, problems = records.generate({"undocumented": ("lineart-scene", verb_undocumented)},
                                     write=False)
    assert got == [] or all(r["id"] != "scene.undocumented" for r in got)
    assert any("no docstring" in p and "verb_undocumented" in p for p in problems)


def test_a_declaration_naming_a_schema_that_is_not_here_is_refused():
    """The kernel's write-time rule, enforced in a clone with nothing mounted."""
    from lineart_trace import records

    def verb_bogus(a):
        """Do a thing.

        C11:
          noun: scene
          verb: bogus
          accepts: scene.nonexistent
          phrases:
            - a phrase
        """

    _got, problems = records.generate({"bogus": ("lineart-scene", verb_bogus)}, write=False)
    assert any("refusing to write a claim nobody can check" in p for p in problems)
