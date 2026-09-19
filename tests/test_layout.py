"""Panels, reflow, arranging and connector routing: §3.6.

The claim worth testing is not that a route exists. It is that the route **clears what it
says it clears** -- checked against an independent measurement, not against the router's own
opinion -- and that a layout which cannot be satisfied is refused rather than drawn wrong.
"""
import pytest

from lineart_trace.scene import build, layout, measure, model, style, validate


def page(w=180.0, h=100.0):
    d = model.new("p", w, h, background="#ffffff")
    d, _ = style.apply(d, style.load("figure-default"))
    return d


def box(doc, addr, frame=None):
    return measure.bbox(doc, addr, frame)["value"]


# ------------------------------------------------------------------ panels
def test_a_panel_grid_fills_the_page_with_the_gutters_and_margins_asked_for():
    d, rep = layout.panels(page(), rows=2, cols=3, gutter=6, margin=4)
    assert rep["created"] == ["panel-a", "panel-b", "panel-c",
                              "panel-d", "panel-e", "panel-f"]
    assert rep["panel"]["width"] == pytest.approx((180 - 8 - 12) / 3)
    assert rep["panel"]["height"] == pytest.approx((100 - 8 - 6) / 2)
    assert validate.problems(d)[0] == []


def test_each_panel_is_its_own_coordinate_space():
    d, _ = layout.panels(page(), rows=1, cols=2, gutter=6, margin=4)
    d = model.add(d, build.rect("r", 0, 0, 10, 10), "panel-b")
    assert box(d, "panel-b.r", "panel-b-frame")["x"] == 0.0        # panel coordinates
    assert box(d, "panel-b.r")["x"] > 90.0                          # page coordinates


def test_panel_letters_are_automatic_and_start_where_asked():
    d, _ = layout.panels(page(), rows=1, cols=3, letters="A")
    assert [model.find(d, f"panel-{c}.letter")["geometry"]["text"]
            for c in "abc"] == ["A", "B", "C"]
    e, _ = layout.panels(page(), rows=1, cols=2, letters="C")
    assert [model.find(e, f"panel-{c}.letter")["geometry"]["text"]
            for c in "ab"] == ["C", "D"]


def test_a_grid_that_cannot_fit_is_refused_with_the_arithmetic():
    with pytest.raises(ValueError, match="does not fit"):
        layout.panels(page(40, 40), rows=4, cols=6, gutter=10, margin=5)


def test_relaying_panels_moves_them_rather_than_adding_more():
    d, _ = layout.panels(page(), rows=1, cols=2)
    d, rep = layout.panels(d, rows=1, cols=2, gutter=20)
    assert rep["created"] == [] and rep["moved"] == ["panel-a", "panel-b"]


# ------------------------------------------------------------------ reflow
def test_reflow_re_lays_the_panels_and_keeps_the_type_the_same_size():
    d, _ = layout.panels(page(180, 80), rows=1, cols=3, gutter=6, margin=4)
    d = model.add(d, build.text("cap", "caption", (2, 20), family=None, size=None,
                                role="caption"), "panel-b")
    before = box(d, "panel-b.cap")
    out, rep = layout.reflow(d, width=88, height=120)
    after = box(out, "panel-b.cap")
    assert rep["to"] == {"width": 88.0, "height": 120.0}
    assert after["width"] == pytest.approx(before["width"], abs=1e-9)   # reflow, not scale
    assert rep["panel"]["width"] < 30


def test_reflow_re_fits_a_drawing_that_was_placed_to_fill_a_panel():
    """The distinction between reflow and scale: a drawing fills the new panel, type does not."""
    d, _ = layout.panels(page(180, 80), rows=1, cols=2, gutter=6, margin=4)
    d = model.add(d, build.circle("art", 0, 0, 30))
    d, _ = layout.into_panel(d, "art", "panel-a", margin=2)
    out, rep = layout.reflow(d, width=80, height=120)
    assert rep["refitted"] and rep["refitted"][0]["element"] == "panel-a.art"
    area = box(out, "panel-a.area", "panel-a-frame")
    art = box(out, "panel-a.art", "panel-a-frame")
    assert art["width"] <= area["width"] + 1e-6
    assert art["height"] <= area["height"] + 1e-6


def test_a_scene_with_no_panel_grid_refuses_to_reflow():
    """Resizing the canvas alone moves the page and not its contents."""
    with pytest.raises(ValueError, match="no panel grid"):
        layout.reflow(page(), width=88)


def test_into_panel_reparents_the_frame_so_the_panel_actually_contains_it():
    """Without re-parenting the move succeeds and means nothing: it renders where it was."""
    d, _ = layout.panels(page(), rows=1, cols=2, gutter=6, margin=4)
    d["frames"]["art"] = {"parent": "page", "unit": "px",
                          "transform": [0.05, 0, 0, 0.05, 0, 0]}
    art = build.rect("art", 0, 0, 400, 400)
    art["frame"] = "art"
    d = model.add(d, art)
    out, _rep = layout.into_panel(d, "art", "panel-b", margin=1)
    assert out["frames"]["art"]["parent"] == "panel-b-frame"
    b, panel = box(out, "panel-b.art"), box(out, "panel-b.area")
    assert b["x"] >= panel["x"] - 1e-6 and b["x"] + b["width"] <= \
        panel["x"] + panel["width"] + 1e-6


# ------------------------------------------------------------------ arranging
def test_distribute_equalises_the_gaps():
    d = page()
    for i, x in enumerate((0.0, 5.0, 60.0)):
        d = model.add(d, build.rect(f"r{i}", x, 10, 10, 10))
    out, rep = layout.distribute(d, ["r0", "r1", "r2"], "x")
    xs = [box(out, f"r{i}")["x"] for i in range(3)]
    assert round(xs[1] - xs[0], 6) == round(xs[2] - xs[1], 6)
    assert round(xs[0], 6) == 0.0 and round(xs[2], 6) == 60.0    # the span is kept


def test_pack_wraps_and_refuses_what_will_not_fit():
    d = page()
    d = model.add(d, build.rect("area", 0, 0, 40, 30))
    for i in range(4):
        d = model.add(d, build.rect(f"r{i}", 100 + i, 60, 15, 8))
    d = model.add(d, build.rect("huge", 100, 80, 80, 8))
    out, rep = layout.pack(d, [f"r{i}" for i in range(4)] + ["huge"], "area", gap=2)
    assert rep["refused"] == 1 and rep["overflow"][0]["element"] == "huge"
    assert box(out, "huge")["x"] == 100.0        # left exactly where it was
    for i in range(4):
        b = box(out, f"r{i}")
        assert b["x"] >= -1e-6 and b["x"] + b["width"] <= 40 + 1e-6


# ------------------------------------------------------------------ routing
def blocked_scene():
    d = page(100, 60)
    d = model.add(d, build.rect("wall", 45, 0, 10, 42))
    d = model.add(d, build.circle("hub", 70, 48, 8))
    return d


@pytest.mark.parametrize("clearance", [1.0, 1.5, 2.0])
def test_a_route_clears_what_it_says_it_clears(clearance):
    """Checked against an independent measurement, not against the router's own opinion."""
    d = blocked_scene()
    out, rep = layout.connect(d, "link", (10, 30), (92, 30), avoid=["wall", "hub"],
                              clearance=clearance, resolution=0.5)
    assert rep["routed"]
    assert rep["clearance_worst"] >= clearance - 1e-9
    got = measure.clearance(out, "link.line", "wall")["value"]["gap"]
    assert got >= clearance - 1e-9
    assert abs(got - rep["clearance_worst"]) < 0.3


def test_asking_for_more_clearance_than_the_gap_allows_is_refused():
    """The corridor between the wall and the hub is finite; at 4mm there is no route."""
    d = blocked_scene()
    _out, rep = layout.connect(d, "l", (10, 30), (92, 30), avoid=["wall", "hub"],
                               clearance=4.0, resolution=0.5)
    assert rep["routed"] is False


def test_a_route_that_cannot_exist_is_refused_not_drawn_straight_through():
    d = model.new("x", 40, 40)
    d = model.add(d, build.rect("block", 0, 10, 40, 20))
    out, rep = layout.connect(d, "l", (20, 2), (20, 38), avoid=["block"], clearance=2.0,
                              resolution=0.5)
    assert rep["routed"] is False and "Refusing" in rep["why"]
    assert model.find(out, "l") is None


def test_a_connector_may_leave_the_thing_it_is_attached_to():
    """Its endpoint sits inside its own obstacle's clearance; unblocking one cell is not enough."""
    d = page(60, 60)
    d = model.add(d, build.rect("a", 5, 5, 20, 8))
    d = model.add(d, build.rect("b", 5, 45, 20, 8))
    out, rep = layout.connect(d, "l", (25, 9), (25, 49), avoid=["a", "b"],
                              clearance=1.5, resolution=0.5)
    assert rep["routed"], rep
    assert set(rep["attached_to"]) == {"a", "b"}


def test_routing_works_inside_a_panel_frame():
    """The grid was sized from the page canvas, which is a page-frame quantity."""
    d, _ = layout.panels(page(180, 80), rows=1, cols=2, gutter=6, margin=4)
    d = model.add(d, build.rect("wall", 20, 10, 8, 40), "panel-b")
    out, rep = layout.connect(d, "l", (5, 30), (45, 30), avoid=["panel-b.wall"],
                              clearance=1.5, resolution=0.5, frame="panel-b-frame")
    assert rep["routed"], rep
    assert rep["clearance_worst"] >= 1.5 - 1e-9


def test_a_straight_connector_says_it_did_not_route():
    d = blocked_scene()
    _out, rep = layout.connect(d, "l", (10, 30), (92, 30), avoid=["wall"],
                               kind="straight")
    assert rep["routed"] is False and rep["kind"] == "straight"


def test_fewer_bends_are_preferred():
    d = blocked_scene()
    _out, rep = layout.connect(d, "l", (10, 30), (92, 30), avoid=["wall", "hub"],
                               clearance=1.5, resolution=0.5)
    assert rep["corners"] <= 4


def test_a_routed_connector_leaves_a_valid_scene():
    d = blocked_scene()
    out, _rep = layout.connect(d, "l", (10, 30), (92, 30), avoid=["wall", "hub"],
                               clearance=1.5, resolution=0.5, arrow=2.0)
    assert validate.problems(out)[0] == []
    assert model.find(out, "l.head") is not None
