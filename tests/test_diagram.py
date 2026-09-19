"""Diagram constructs: §3.9. Nodes that size themselves, edges that route, boxes that fit.

The claim is that nothing here is a box drawn at a guessed size, so the tests measure: a node
is as wide as its label plus its padding, a container is as wide as what it holds, an edge
clears what it says it clears, and a graph with a cycle is drawn anyway with the cycle named.
"""
import pytest

from lineart_trace.scene import (anchors, build, diagram, layout, measure, model,
                                 style, validate, verify)


def styled(w=180.0, h=160.0):
    d = model.new("d", w, h, background="#ffffff")
    d, _ = style.apply(d, style.load("figure-default"))
    return d


def box(doc, addr, frame=None):
    return measure.bbox(doc, addr, frame)["value"]


# ------------------------------------------------------------------ nodes
def test_a_node_is_as_wide_as_its_label_plus_its_padding():
    d = styled()
    w, _h, laid = diagram.auto_size(d, "lyse cells", pad_x=3.0)
    assert w == pytest.approx(laid["width"] + 6.0, abs=1e-9)
    d, rep = diagram.node(d, "n", "lyse cells", (10, 10), pad_x=3.0)
    assert box(d, "n")["width"] == pytest.approx(w, abs=1e-6)


def test_a_longer_label_makes_a_wider_node():
    d = styled()
    d, a = diagram.node(d, "a", "in", (0, 0))
    d, b = diagram.node(d, "b", "a considerably longer label", (0, 20))
    assert b["width"] > a["width"] * 2


def test_a_node_wraps_when_it_is_given_a_maximum_width():
    d = styled()
    d, rep = diagram.node(d, "n", "a considerably longer label", (0, 0), max_width=30.0)
    assert rep["wrapped"] and len(rep["lines"]) > 1
    assert box(d, "n")["width"] <= 30.0 + 1e-6


def test_a_node_carries_the_anchors_edges_attach_to():
    d = styled()
    d, _rep = diagram.node(d, "n", "x", (10, 10))
    got = model.find(d, "n")["anchors"]
    assert set(got) == {"centre", "n", "s", "e", "w"}
    b = box(d, "n")
    assert got["e"]["at"][0] == pytest.approx(b["x"] + b["width"], abs=1e-6)


def test_a_node_cannot_be_sized_without_a_font_and_says_so():
    """A glyph or a node that writes no literals has nothing to measure until a guide does."""
    d = model.new("d", 100, 100)
    with pytest.raises(measure.Unmeasurable, match="style guide"):
        diagram.node(d, "n", "x", (0, 0))


# ------------------------------------------------------------------ edges
def test_an_edge_between_clear_nodes_is_the_straight_line():
    """Grid snapping put two little jogs in an arrow with nothing in its way."""
    d = styled()
    d, _ = diagram.node(d, "a", "a", (40, 10))
    d, _ = diagram.node(d, "b", "b", (40, 40))
    d, rep = diagram.edge(d, "e", "a", "b")
    assert rep["routed"] and rep["corners"] == 0 and rep["direct"]


def test_an_edge_goes_round_what_is_between_and_says_by_how_much():
    d = styled()
    d, _ = diagram.node(d, "a", "start here", (10, 10))
    d, _ = diagram.node(d, "b", "end here", (10, 60))
    d, _ = diagram.node(d, "mid", "in the way", (8, 33))
    d, rep = diagram.edge(d, "e", "a", "b", clearance=1.5)
    assert rep["routed"] and rep["corners"] > 0
    assert rep["clearance_worst"] >= 1.5 - 1e-9
    assert "mid" in rep["passed"]
    got = measure.clearance(d, "e.line", "mid")["value"]["gap"]
    assert got >= 1.5 - 1e-9


def test_the_second_edge_of_a_pair_is_offset_so_they_do_not_sit_on_each_other():
    d = styled()
    d, _ = diagram.node(d, "a", "a", (40, 10))
    d, _ = diagram.node(d, "b", "b", (40, 50))
    d, r1 = diagram.edge(d, "there", "a", "b", "go")
    d, r2 = diagram.edge(d, "back", "b", "a", "return")
    assert r1["parallel_offset"] == 0 and r2["parallel_offset"] == 1
    assert measure.clearance(d, "there.line", "back.line")["value"]["gap"] > 0.5


def test_an_edge_chooses_the_sides_that_face_each_other():
    d = styled()
    d, _ = diagram.node(d, "a", "a", (10, 40))
    d, _ = diagram.node(d, "b", "b", (80, 40))
    _d, rep = diagram.edge(d, "e", "a", "b")
    assert rep["sides"] == ["e", "w"]


def test_an_edge_stays_in_the_frame_its_nodes_are_in():
    """A default that resolved to the page frame and then stamped it defeated inheritance."""
    d = styled()
    d["frames"]["q"] = {"parent": "page", "unit": "mm", "transform": [1, 0, 0, 1, 50, 60]}
    d = model.add(d, build.group("g", [], frame="q"))
    d, _ = diagram.node(d, "a", "a", (0, 0), parent="g")
    d, _ = diagram.node(d, "b", "b", (0, 20), parent="g")
    d, rep = diagram.edge(d, "e", "g.a", "g.b", parent="g")
    assert model.find(d, "g.a").get("frame") is None
    assert model.frame_of(d, "g.a") == "q"
    assert model.frame_of(d, "g.e") == "q"
    assert box(d, "g.a")["x"] == pytest.approx(50.0, abs=1e-6)
    assert box(d, "g.e")["x"] > 45.0


# ------------------------------------------------------------------ containers
def test_a_container_fits_what_it_holds_and_refits_when_that_changes():
    d = styled()
    d, _ = diagram.node(d, "a", "a", (10, 10))
    d, _ = diagram.node(d, "b", "b", (40, 10))
    d, r1 = diagram.container(d, "c", ["a", "b"], pad=2.0)
    assert r1["refitted"] is False
    d, _ = diagram.node(d, "c2", "c", (90, 10))
    d, r2 = diagram.container(d, "c", ["a", "b", "c2"], pad=2.0)
    assert r2["refitted"] is True and r2["box"]["width"] > r1["box"]["width"]
    got = box(d, "c")
    for m in ("a", "b", "c2"):
        mb = box(d, m)
        assert got["x"] <= mb["x"] and mb["x"] + mb["width"] <= got["x"] + got["width"]


def test_a_container_with_no_members_is_refused():
    with pytest.raises(ValueError, match="at least one member"):
        diagram.container(styled(), "c", [])


# ------------------------------------------------------------------ layering
def test_layering_assigns_the_longest_path():
    layer, info = diagram.layers([("a", "b"), ("b", "c"), ("a", "c")])
    assert layer == {"a": 0, "b": 1, "c": 2}
    assert info["layers"] == 3 and not info["cyclic"]


def test_a_cycle_is_named_and_the_rest_is_still_laid_out():
    """A state machine is full of cycles and still has to be drawable."""
    layer, info = diagram.layers([("a", "b"), ("b", "c"), ("c", "b")])
    assert info["cyclic"] and info["back_edges"]
    assert layer["a"] == 0 and layer["b"] >= 1


def test_a_flowchart_centres_its_layers_so_the_arrows_do_not_kink():
    """Nodes of different widths, left-aligned, give every edge a sideways jog."""
    d = styled()
    d, rep = diagram.flow(d, {"a": "a", "b": "a much longer label"}, [("a", "b")],
                          at=(10, 10))
    ba, bb = box(d, "a"), box(d, "b")
    assert (ba["x"] + ba["width"] / 2) == pytest.approx(bb["x"] + bb["width"] / 2,
                                                       abs=1e-6)
    assert rep["edges"][0]["corners"] == 0


def test_a_whole_flowchart_is_valid_and_verifies_clean():
    d = styled()
    d, rep = diagram.flow(d, {"one": "collect", "two": "wash", "three": "elute"},
                          [("one", "two"), ("two", "three")], at=(20, 10),
                          spacing=(10, 12))
    assert validate.problems(d)[0] == []
    assert rep["unrouted"] == []
    _s, srep = anchors.solve(d)
    assert verify.check(d, solve_report=srep)["errors"] == 0


def test_a_diagram_is_drawn_entirely_by_role():
    d = styled()
    d, _rep = diagram.flow(d, {"a": "a", "b": "b"}, [("a", "b", "then")], at=(20, 10))
    literals = [a for a, el, _p in model.walk(d) if (el.get("style") or {})]
    assert literals == [], literals


# ------------------------------------------------------------------ trees
def test_a_tree_slugs_keys_that_are_not_element_names():
    """A tree of gene names is the obvious use, and `ampR` is not an element name."""
    d = styled()
    d, rep = diagram.tree(d, "plasmid", {"plasmid": ["ampR", "EcoRI"]}, at=(20, 10))
    assert rep["names"]["ampR"] == "ampr" and rep["names"]["EcoRI"] == "ecori"
    assert validate.problems(d)[0] == []
    assert model.find(d, "ampr")["children"][1]["geometry"]["text"] == "ampR"


def test_a_tree_refuses_keys_that_slug_to_the_same_name():
    with pytest.raises(ValueError, match="slug to the same"):
        diagram.tree(styled(), "r", {"r": ["a-b", "a.b"]})


def test_a_tree_puts_a_parent_over_its_children():
    d = styled()
    d, _rep = diagram.tree(d, "root", {"root": ["one", "two", "three"]}, at=(20, 10))
    parent = box(d, "root")
    kids = [box(d, k) for k in ("one", "two", "three")]
    mid = sum(k["x"] + k["width"] / 2 for k in kids) / 3
    assert parent["x"] + parent["width"] / 2 == pytest.approx(mid, abs=0.6)
    for a, b in zip(kids, kids[1:]):
        assert a["x"] + a["width"] <= b["x"] + 1e-6


# ------------------------------------------------------------------ swimlanes
def test_swimlanes_give_an_anchor_per_lane():
    d = styled()
    d, rep = diagram.swimlanes(d, ["prep", "reaction"], at=(4, 4), width=120,
                               lane_height=16)
    assert rep["anchors"] == ["prep", "reaction"]
    got = model.find(d, "swimlanes")["anchors"]
    assert got["reaction"]["at"][1] - got["prep"]["at"][1] == pytest.approx(16.0)
