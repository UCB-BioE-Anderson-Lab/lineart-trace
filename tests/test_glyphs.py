"""The glyph library: §3.7. Every glyph, placed, validated and measured.

The tests that matter here are the ones that scale with the catalogue. A library grows, and
the same mistakes recur -- an anchor sharing a child's name, a literal colour that ignores
the guide, a glyph that draws nothing. So the checks below run over **every** registered
glyph rather than over a chosen few.
"""
import pytest

from lineart_trace.scene import (anchors, glyphs, io, measure, model, style, svg,
                                 validate, verify)

CATALOGUE = sorted(glyphs.catalogue())

#: Arguments that exercise the interesting paths, for glyphs whose defaults draw little.
EXERCISE = {
    "dna.duplex": {"length": 40, "nick": 0.3, "mismatch": 0.6, "label": "duplex"},
    "dna.plasmid": {"radius": 14, "name": "pUC19",
                    "features": [("ampR", 30, 140)], "sites": [("EcoRI", 10)]},
    "gel.lanes": {"lanes": 3, "ladder": [0.2, 0.5], "bands": [(1, 0.3, 1.0)],
                  "labels": ["a", "b", "c"]},
    "protein.silhouette": {"label": "Pol"},
    "process.steps": {"stages": ["one", "two", "three"]},
    "axis.timeline": {"marks": [("0", 0.0), ("mid", 0.5), ("end", 1.0)],
                      "title": "time"},
    "process.bracket": {"label": "region"},
    "lab.tube": {"fill": 0.6, "label": "lysate", "graduations": 3},
    "lab.plate": {"rows": 4, "cols": 6, "filled": ["A1", "D6"]},
    "lab.pipette": {"label": "P200"},
    "lab.gradient": {"label_top": "10%", "label_bottom": "60%"},
    "membrane.bilayer": {"curve": 2.0},
    "arrow.reaction": {"above": "ATP", "below": "Mg", "reversible": True},
}


def styled(width=160.0, height=120.0):
    d = model.new("g", width, height, background="#ffffff")
    d, _ = style.apply(d, style.load("figure-default"))
    return d


def placed(gid):
    d, rep = glyphs.place(styled(), gid, "it", args=EXERCISE.get(gid))
    return d, rep


# ------------------------------------------------------------------ every glyph
@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_places_into_a_valid_scene(gid):
    d, _rep = placed(gid)
    bad, _warn = validate.problems(d)
    assert bad == [], bad


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_draws_something_with_a_real_extent(gid):
    d, _rep = placed(gid)
    box = measure.bbox(d, "it")["value"]
    assert box["width"] > 0.5 and box["height"] > 0.5, box


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_carries_anchors(gid):
    """Without them a glyph is a picture you still have to position by hand."""
    _d, rep = placed(gid)
    assert rep["anchors"], gid


@pytest.mark.parametrize("gid", CATALOGUE)
def test_no_glyph_writes_a_literal_colour_or_width(gid):
    """A glyph that wrote a literal would be a hole in every theme."""
    d, _rep = placed(gid)
    offenders = []
    for addr, el, _p in model.walk(d):
        if not addr.startswith("it"):
            continue
        for k, v in (el.get("style") or {}).items():
            if k in ("stroke", "fill", "stroke_width", "font_family", "font_size"):
                offenders.append(f"{addr}.{k}={v!r}")
    assert offenders == [], offenders


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_is_styled_entirely_by_the_shipped_guide(gid):
    _d, rep = placed(gid)
    assert rep["roles_not_in_scene"] == [], rep["roles_not_in_scene"]


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_is_deterministic(gid):
    a, _ = placed(gid)
    b, _ = placed(gid)
    assert io.dumps(a) == io.dumps(b)


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_renders_and_records_where_it_came_from(gid):
    d, _rep = placed(gid)
    prov = model.find(d, "it")["provenance"]
    assert prov["origin"] == "glyph" and prov["tool"] == gid
    assert prov["tool_version"] == glyphs.glyph(gid).version
    out = svg.render(d)
    assert out.startswith("<svg") and f'id="it"' in out


@pytest.mark.parametrize("gid", CATALOGUE)
def test_every_glyph_passes_verification_on_a_white_page(gid):
    d, _rep = placed(gid)
    got = verify.check(d, rules=["type-size", "stroke-weight", "contrast", "off-canvas",
                                 "missing-glyphs"])
    assert got["errors"] == 0, got["findings"]


# ------------------------------------------------------------------ the registry
def test_an_unknown_glyph_names_what_the_catalogue_does_have():
    with pytest.raises(glyphs.GlyphNotFound, match="dna"):
        glyphs.glyph("dna.triplex")
    with pytest.raises(glyphs.GlyphNotFound, match="famil"):
        glyphs.glyph("nonsense.thing")


def test_an_argument_that_is_not_a_parameter_is_refused():
    """A silently ignored keyword is a figure drawn differently from what was asked."""
    with pytest.raises(TypeError, match="no parameter"):
        glyphs.place(styled(), "dna.duplex", "d", args={"colour": "red"})


def test_a_glyph_may_take_a_parameter_called_name():
    """It could not, while arguments were passed as keywords alongside the element name."""
    d, rep = glyphs.place(styled(), "dna.plasmid", "p", args={"name": "pUC19"})
    assert rep["element"] == "p"
    assert model.find(d, "p.name")["geometry"]["text"] == "pUC19"


def test_the_catalogue_describes_itself():
    got = glyphs.describe("dna.duplex")
    assert got["family"] == "dna" and "length" in got["parameters"]
    assert got["summary"]


# ------------------------------------------------------------------ staleness
def test_a_scene_knows_which_glyph_version_drew_it():
    d, _ = placed("dna.duplex")
    assert glyphs.check(d)["stale"] == [] and glyphs.check(d)["gone"] == []
    model.find(d, "it")["provenance"]["tool_version"] = "0"
    got = glyphs.check(d)
    assert got["stale"] and got["stale"][0]["now"] == glyphs.glyph("dna.duplex").version


def test_a_glyph_the_catalogue_has_dropped_is_reported_as_gone():
    d, _ = placed("dna.duplex")
    model.find(d, "it")["provenance"]["tool"] = "dna.quadruplex"
    assert glyphs.check(d)["gone"]


# ------------------------------------------------------------------ promote
def test_promoting_a_subtree_captures_it_and_says_it_is_captured():
    d, _ = placed("lab.tube")
    got = glyphs.promote(d, "it", "lab.mytube", version="2")
    assert got["kind"] == "captured" and got["id"] == "lab.mytube"
    back, rep = glyphs.place_captured(styled(), got, "again", at=(20, 20))
    assert rep["captured"] and validate.problems(back)[0] == []
    assert measure.bbox(back, "again")["value"]["width"] > 0


# ------------------------------------------------------------------ the claim
def test_the_protein_cleft_anchor_agrees_with_a_discovered_concavity():
    """The glyph declares a cleft; `concavity` finds one independently. They must agree."""
    import math
    for cleft in (0.2, 0.55, 0.8):
        d, _ = glyphs.place(styled(), "protein.silhouette", "p",
                            args={"cleft": cleft, "label": "X"})
        found, _dir = anchors.derive(d, "p", "concavity")
        declared = model.find(d, "p")["anchors"]["cleft"]["at"]
        assert math.dist(found, declared) < 1.5, (cleft, found, declared)


def test_a_silhouette_ignores_the_label_written_across_it():
    """A box in the middle of a shape is a long way inside its hull, and is not an inlet."""
    import math
    with_label, _ = glyphs.place(styled(), "protein.silhouette", "p",
                                 args={"label": "a very long protein name"})
    without, _ = glyphs.place(styled(), "protein.silhouette", "p", args={"label": None})
    a, _ = anchors.derive(with_label, "p", "concavity")
    b, _ = anchors.derive(without, "p", "concavity")
    assert math.dist(a, b) < 0.01
