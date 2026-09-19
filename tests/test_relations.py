"""Anchors, relations and the solver: §3.5, and the two bugs the first real figure found.

The tests that matter are not that an attachment lands in the right place once. They are
that it lands there again after the thing it is attached to is edited, that solving twice
changes nothing, and that a layout which cannot be satisfied is reported instead of
approximated.
"""
import pytest

from lineart_trace.scene import anchors, build, measure, model


def scene():
    d = model.new("t", 200, 120)
    d = model.add(d, build.circle("blob", 30, 30, 20))
    d = model.add(d, build.rect("label", 0, 0, 30, 8))
    model.find(d, "blob")["anchors"] = {"east": {"how": "derived", "by": "bbox.e"}}
    model.find(d, "label")["anchors"] = {"tip": {"how": "derived", "by": "bbox.w"}}
    model.find(d, "label")["relations"] = [
        {"kind": "attach", "to": "blob.east", "via": "tip", "offset": [4, 0]}]
    return d


def box(doc, addr, frame=None):
    return measure.bbox(doc, addr, frame)["value"]


# ------------------------------------------------------------------ recipes
@pytest.mark.parametrize("by,want", [
    ("bbox.nw", (10.0, 20.0)), ("bbox.ne", (30.0, 20.0)), ("bbox.se", (30.0, 26.0)),
    ("bbox.centre", (20.0, 23.0)), ("bbox.w", (10.0, 23.0)), ("bbox.s", (20.0, 26.0)),
])
def test_bbox_recipes(by, want):
    d = model.add(model.new("t", 100, 100), build.rect("r", 10, 20, 20, 6))
    pt, _dir = anchors.derive(d, "r", by)
    assert (round(pt[0], 9), round(pt[1], 9)) == want


def test_a_derived_anchor_knows_which_way_it_faces():
    d = model.add(model.new("t", 100, 100), build.rect("r", 10, 20, 20, 6))
    _pt, direction = anchors.derive(d, "r", "bbox.e")
    assert direction == (1, 0)


def test_concavity_finds_the_inlet_and_refuses_a_convex_shape():
    """A circle has no bay. Returning its least-convex vertex would be an invented anchor."""
    d = model.new("t", 100, 100)
    d = model.add(d, build.polyline("cee", [(10, 10), (90, 10), (90, 30), (40, 30),
                                            (40, 70), (90, 70), (90, 90), (10, 90)],
                                    closed=True))
    d = model.add(d, build.circle("round", 50, 50, 20))
    pt, _dir = anchors.derive(d, "cee", "concavity")
    assert 40 <= pt[0] <= 92 and 25 <= pt[1] <= 75
    with pytest.raises(ValueError, match="no concavity"):
        anchors.derive(d, "round", "concavity")


def test_an_unknown_recipe_is_named_with_the_ones_that_exist():
    d = model.add(model.new("t", 100, 100), build.rect("r", 0, 0, 10, 10))
    with pytest.raises(ValueError, match="no anchor recipe"):
        anchors.derive(d, "r", "bbox.northwest")


# ------------------------------------------------------------------ solving
def test_an_attachment_lands_where_it_was_declared_to():
    out, _rep = anchors.solve(scene())
    blob, label = box(out, "blob"), box(out, "label")
    assert round(label["x"], 6) == round(blob["x"] + blob["width"] + 4, 6)
    assert round(label["y"] + label["height"] / 2, 6) == \
        round(blob["y"] + blob["height"] / 2, 6)


def test_the_attachment_follows_when_the_thing_it_points_at_is_edited():
    """§3.5's whole promise: editing one element updates everything attached to it."""
    out, _ = anchors.solve(scene())
    out["elements"][0] = build.circle("blob", 120, 90, 35)
    out["elements"][0]["anchors"] = {"east": {"how": "derived", "by": "bbox.e"}}
    again, _ = anchors.solve(out)
    blob, label = box(again, "blob"), box(again, "label")
    assert round(label["x"], 6) == round(blob["x"] + blob["width"] + 4, 6)


def test_solving_twice_changes_nothing():
    out, _ = anchors.solve(scene())
    assert anchors.solve(out)[1]["moved"] == {}


def test_a_relation_moves_an_element_by_the_right_amount_in_its_own_frame():
    """The delta is solved in millimetres and written into a transform applied in pixels.

    This is the bug the first real figure found: a traced element lives in an image-pixel
    frame, and composing a millimetre translation into its transform moved it by a fortieth
    of what was asked. Everything that worked before was in the page frame, where the two
    units happen to be the same one.
    """
    d = model.new("t", 200, 120)
    d["frames"]["art"] = {"parent": "page", "unit": "px",
                          "transform": [0.025, 0, 0, 0.025, 0, 0]}
    d = model.add(d, build.rect("target", 100, 40, 20, 10))
    art = build.rect("moving", 0, 0, 400, 200)      # 10 x 5 mm once the frame is applied
    art["frame"] = "art"
    art["relations"] = [{"kind": "align", "to": "target", "edge": "left"}]
    d = model.add(d, art)
    out, rep = anchors.solve(d)
    assert rep["settled"], rep
    assert round(box(out, "moving")["x"], 6) == 100.0
    assert rep["passes"] <= 3, "it should not need to creep there over many passes"


def test_a_group_transform_moves_its_children_in_measurement_as_it_does_in_the_drawing():
    d = model.new("g", 100, 100)
    d = model.add(d, build.group("box", [build.rect("r", 0, 0, 10, 10)],
                                 transform=[1, 0, 0, 1, 25, 40]))
    assert (box(d, "box.r")["x"], box(d, "box.r")["y"]) == (25.0, 40.0)


@pytest.mark.parametrize("kind,extra", [
    ("attach", {"to": "anchor-box"}),
    ("align", {"to": "anchor-box", "edge": "left"}),
    ("clear", {"to": "anchor-box", "offset": [2.0, 0.0]}),
    ("inside", {"to": "anchor-box"}),
])
def test_every_relation_kind_makes_a_scene_that_validates(kind, extra):
    """The solver read an `edge` field the schema forbade: every `align` was an invalid scene.

    The tests that exercised alignment solved without validating, so nothing noticed until a
    consolidated report ran both over the same document.
    """
    from lineart_trace.scene import validate
    d = model.new("t", 200, 200)
    d = model.add(d, build.rect("anchor-box", 40, 50, 60, 40))
    d = model.add(d, build.rect("mover", 0, 0, 10, 10))
    model.find(d, "mover")["relations"] = [dict({"kind": kind}, **extra)]
    assert validate.problems(d)[0] == [], kind
    out, rep = anchors.solve(d)
    assert validate.problems(out)[0] == [], kind
    assert not rep["unsatisfiable"], rep


def test_a_relation_kind_the_solver_does_not_know_is_refused_by_the_schema():
    from lineart_trace.scene import validate
    d = model.add(model.new("t", 60, 60), build.rect("a", 0, 0, 10, 10))
    d = model.add(d, build.rect("b", 20, 20, 10, 10))
    model.find(d, "b")["relations"] = [{"kind": "orbit", "to": "a"}]
    assert any("orbit" in p for p in validate.problems(d)[0])


@pytest.mark.parametrize("edge,check", [
    ("left", lambda a, b: round(a["x"], 6) == round(b["x"], 6)),
    ("top", lambda a, b: round(a["y"], 6) == round(b["y"], 6)),
    ("centre-x", lambda a, b: round(a["x"] + a["width"] / 2, 6) ==
                              round(b["x"] + b["width"] / 2, 6)),
])
def test_align(edge, check):
    d = model.new("t", 200, 200)
    d = model.add(d, build.rect("anchor-box", 40, 50, 60, 20))
    d = model.add(d, build.rect("mover", 0, 0, 10, 10))
    model.find(d, "mover")["relations"] = [{"kind": "align", "to": "anchor-box",
                                            "edge": edge}]
    out, _ = anchors.solve(d)
    assert check(box(out, "mover"), box(out, "anchor-box"))


def test_clear_opens_a_gap_and_inside_pulls_things_back_onto_the_page():
    d = model.new("t", 100, 100)
    area = build.rect("page-area", 2, 2, 96, 96)
    area["type"] = "guide"
    d = model.add(d, area)
    d = model.add(d, build.circle("hub", 50, 50, 20))
    d = model.add(d, build.rect("tag", 44, 44, 20, 8))
    model.find(d, "tag")["relations"] = [
        {"kind": "clear", "to": "hub", "offset": [3.0, 0]},
        {"kind": "inside", "to": "page-area"}]
    out, rep = anchors.solve(d)
    assert rep["settled"], rep
    assert measure.clearance(out, "tag", "hub")["value"]["gap"] >= 2.9
    t = box(out, "tag")
    assert t["x"] >= 1.99 and t["x"] + t["width"] <= 98.01


def test_a_guide_can_be_measured_by_name_and_does_not_inflate_its_parent():
    d = model.new("t", 100, 100)
    rule = build.line("rule", (0, 0), (90, 0))
    rule["type"] = "guide"
    d = model.add(d, build.group("g", [build.rect("r", 10, 10, 10, 10), rule]))
    assert box(d, "g")["width"] == 10.0            # the guide does not count
    assert box(d, "rule" if False else "g.rule")["width"] == 90.0   # ...but can be asked for


def test_an_unsatisfiable_relation_is_reported_and_never_approximated():
    d = model.new("u", 100, 100)
    d = model.add(d, build.rect("box", 10, 10, 20, 20))
    d = model.add(d, build.rect("big", 0, 0, 50, 50))
    model.find(d, "big")["relations"] = [{"kind": "inside", "to": "box"}]
    _out, rep = anchors.solve(d)
    assert rep["unsatisfiable"]
    assert "no translation can fix that" in rep["unsatisfiable"][0]["why"]


def test_a_relation_naming_nothing_is_reported_rather_than_ignored():
    d = model.new("u", 100, 100)
    d = model.add(d, build.rect("a", 0, 0, 10, 10))
    model.find(d, "a")["relations"] = [{"kind": "attach", "to": "ghost"}]
    _out, rep = anchors.solve(d)
    assert rep["unsatisfiable"] and "ghost" in str(rep["unsatisfiable"])


def test_resolve_refreshes_derived_anchors_and_leaves_authored_ones_alone():
    d = model.new("t", 100, 100)
    d = model.add(d, build.rect("r", 0, 0, 10, 10))
    model.find(d, "r")["anchors"] = {
        "mine": {"how": "authored", "at": [3, 3]},
        "corner": {"how": "derived", "by": "bbox.ne", "at": [999, 999]}}
    out, rep = anchors.resolve(d)
    assert model.find(out, "r")["anchors"]["mine"]["at"] == [3, 3]
    assert model.find(out, "r")["anchors"]["corner"]["at"] == [10.0, 0.0]
    assert any(x["anchor"] == "r.corner" for x in rep["resolved"])
