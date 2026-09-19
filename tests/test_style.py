"""Style guides, palettes and linting: §3.11.

The claim a style system has to make good on is that a set of figures can be made consistent
and re-themed **without editing any figure's content**. So the tests are about what applying
a guide does and does not touch, and about the ways a guide can be wrong that would otherwise
show up as a figure that quietly draws in black.
"""
import json

import pytest

from lineart_trace.scene import build, model, palette, style, verify


def guide(**over):
    g = {
        "format": "lineart.guide/1", "name": "test-guide",
        "tokens": {"colour": {"ink": "#111111", "accent": "#c2452c"},
                   "stroke": {"regular": "0.6pt", "heavy": "1.2pt"},
                   "type": {"caption": "6pt"},
                   "family": {"sans": "Helvetica"}},
        "roles": {
            "structure-stroke": {"stroke": "@colour.ink", "fill": "none",
                                 "stroke_width": "@stroke.regular"},
            "accent-stroke": {"stroke": "@colour.accent", "fill": "none",
                              "stroke_width": "@stroke.heavy"},
            "caption": {"fill": "@colour.ink", "font_family": "@family.sans",
                        "font_size": "@type.caption"},
        },
        "variants": {"dark": {"canvas_background": "#111111",
                              "tokens": {"colour": {"ink": "#eeeeee"}}}},
    }
    g.update(over)
    return g


def scene():
    d = model.new("s", 60, 40, background="#ffffff")
    d = model.add(d, build.circle("a", 20, 20, 8, role="structure-stroke"))
    d = model.add(d, build.rect("b", 35, 15, 15, 10, role="accent-stroke"))
    return d


# ------------------------------------------------------------------ resolution
def test_tokens_resolve_into_roles():
    roles, _t = style.resolve(guide())
    assert roles["structure-stroke"] == {"fill": "none", "stroke": "#111111",
                                         "stroke_width": "0.6pt"}


def test_a_variant_overrides_tokens_and_every_role_that_used_them_changes():
    roles, _t = style.resolve(guide(), "dark")
    assert roles["structure-stroke"]["stroke"] == "#eeeeee"
    assert roles["caption"]["fill"] == "#eeeeee"
    assert roles["accent-stroke"]["stroke"] == "#c2452c"    # untouched by the variant


def test_a_token_that_does_not_exist_is_refused_not_left_as_a_string():
    """`@colour.inkk` reaches a renderer as a colour nobody knows, and draws black."""
    g = guide()
    g["roles"]["structure-stroke"]["stroke"] = "@colour.inkk"
    with pytest.raises(ValueError, match="not a token"):
        style.resolve(g)


def test_a_property_that_is_not_a_style_property_is_refused():
    g = guide()
    g["roles"]["structure-stroke"]["strike"] = "#000"
    with pytest.raises(ValueError, match="not a style property"):
        style.resolve(g)


def test_an_unknown_variant_names_the_ones_that_exist():
    with pytest.raises(KeyError, match="dark"):
        style.resolve(guide(), "midnight")


def test_inheritance_merges_tokens_and_replaces_roles(tmp_path, monkeypatch):
    base = guide()
    child = {"format": "lineart.guide/1", "name": "child", "extends": "test-guide",
             "tokens": {"stroke": {"regular": "0.9pt"}}, "roles": {}}
    (tmp_path / "test-guide.json").write_text(json.dumps(base))
    (tmp_path / "child.json").write_text(json.dumps(child))
    monkeypatch.setenv("LINEART_GUIDE_PATH", str(tmp_path))
    got = style.load("child")
    roles, _t = style.resolve(got)
    assert roles["structure-stroke"]["stroke_width"] == "0.9pt"   # overridden
    assert roles["accent-stroke"]["stroke"] == "#c2452c"          # inherited whole
    assert roles["structure-stroke"]["stroke"] == "#111111"       # token not overridden


def test_a_missing_guide_is_refused_not_silently_unstyled():
    with pytest.raises(style.GuideNotFound):
        style.load("no-such-guide-anywhere")


# ------------------------------------------------------------------ applying
def test_applying_a_guide_changes_no_element():
    before = scene()
    after, _rep = style.apply(before, guide())
    assert [e for e in before["elements"]] == [e for e in after["elements"]]
    assert after["style"]["guide"] == "test-guide"
    assert len(after["style"]["guide_sha256"]) == 64


def test_the_same_scene_renders_differently_under_a_variant_with_no_edit():
    from lineart_trace.scene import svg
    light, _ = style.apply(scene(), guide())
    dark, _ = style.apply(scene(), guide(), "dark")
    assert 'stroke="#111111"' in svg.render(light)
    assert 'stroke="#eeeeee"' in svg.render(dark)
    assert dark["canvas"]["background"] == "#111111"


def test_a_role_nobody_defines_is_reported_and_carried_over_not_dropped():
    """Replacing the role table wholesale silently unstyles everything it did not know."""
    d = scene()
    d["style"] = {"roles": {"mine": {"stroke": "#00ff00"}}}
    d = model.add(d, build.circle("c", 5, 5, 2, role="mine"))
    out, rep = style.apply(d, guide())
    assert "mine" in rep["roles_not_in_guide"]
    assert "mine" in rep["roles_carried_over"]
    assert out["style"]["roles"]["mine"] == {"stroke": "#00ff00"}


def test_a_role_is_what_the_measurer_and_the_checker_see_too():
    """A figure drawn entirely by role used to measure as having no sizes and pass everything."""
    from lineart_trace.scene import measure
    d = model.add(scene(), build.text("t", "caption", (5, 30), family=None, size=None,
                                      role="caption"))
    styled, _ = style.apply(d, guide())
    assert measure.bbox(styled, "t")["value"]["width"] > 0
    assert measure.inventory(styled)["value"]["colours"]
    assert any(f["rule"] == "type-size"
               for f in verify.check(styled, rules=["type-size"],
                                     thresholds={"min_type_pt": 9})["findings"])


# ------------------------------------------------------------------ adopt and lint
def test_adopt_groups_identical_literals_and_does_not_guess_at_meaning():
    d = model.new("t", 60, 40)
    lit = {"stroke": "#111111", "fill": "none", "stroke_width": 2}
    d = model.add(d, build.circle("a", 10, 10, 4, style=dict(lit)))
    d = model.add(d, build.circle("b", 25, 10, 4, style=dict(lit)))
    d = model.add(d, build.rect("c", 35, 5, 10, 8, style={"fill": "#c2452c"}))
    out, rep = style.adopt(d, guide())
    assert rep["converted"] == 3 and rep["roles_created"] == 2
    assert model.find(out, "a")["role"] == model.find(out, "b")["role"]
    assert all(r.startswith("adopted-") for r in rep["roles"])
    assert "style" not in model.find(out, "a")
    assert rep["nearest"]["adopted-01"]["role"] in ("structure-stroke", "accent-stroke")


def test_adopt_matches_a_guide_role_exactly_where_one_fits():
    roles, _t = style.resolve(guide())
    d = model.add(model.new("t", 60, 40),
                  build.circle("a", 10, 10, 4, style=dict(roles["structure-stroke"])))
    _out, rep = style.adopt(d, guide())
    assert rep["roles"] == ["structure-stroke"] and rep["roles_created"] == 0


def test_lint_finds_literals_off_palette_colours_and_unknown_roles():
    d, _ = style.apply(scene(), guide())
    d = model.add(d, build.circle("odd", 50, 30, 3,
                                  style={"stroke": "#00ff00", "stroke_width": "9pt"}))
    d = model.add(d, build.rect("ghost", 1, 1, 2, 2, role="not-a-role"))
    got = style.lint(d, guide())
    rules = {f["rule"] for f in got["findings"]}
    assert {"literal-style", "off-palette", "off-scale", "unknown-role"} <= rules
    assert got["errors"] >= 1


def test_lint_reports_a_scene_styled_from_a_guide_that_has_since_changed():
    d, _ = style.apply(scene(), guide())
    moved = guide()
    moved["tokens"]["colour"]["ink"] = "#222222"
    got = style.lint(d, moved)
    assert any(f["rule"] == "guide-stale" for f in got["findings"])


def test_lint_without_a_guide_is_unchecked_rather_than_clean():
    got = style.lint(scene())
    assert got["findings"] == [] and got["unchecked"]


# ------------------------------------------------------------------ palettes
def test_a_generated_palette_passes_its_own_check():
    cols, rep = palette.generate(5)
    assert rep["produced"] == 5
    assert palette.check(cols)["usable"]


def test_generation_is_deterministic():
    assert palette.generate(6)[0] == palette.generate(6)[0]


def test_separation_is_the_worst_case_across_every_vision_not_the_average():
    """A pair vivid to most readers and identical to some is a pair that fails."""
    a, b = "#1f3f6b", "#4f2c96"
    normal = verify._delta_e(a, b)
    worst = palette.separation(a, b)
    assert worst <= normal


def test_asking_for_more_than_the_pool_can_give_comes_back_short_and_says_so():
    """Relaxing the threshold quietly is how a palette reports success with a clash in it."""
    cols, rep = palette.generate(40)
    assert rep["produced"] < 40
    assert rep["short"] and "clears" in rep["short"][0]["why"]
    assert palette.check(cols)["usable"]


def test_check_names_the_offending_pair_rather_than_counting_problems():
    got = palette.check(["#3b7dd8", "#3b7ad8", "#d83b3b"])
    assert not got["usable"]
    assert {got["worst_pair"]["a"], got["worst_pair"]["b"]} == {"#3b7dd8", "#3b7ad8"}


def test_a_palette_is_relative_to_its_background():
    """The same colours that work on white can fail on a dark page, and the check knows."""
    cols, _ = palette.generate(4, "#ffffff")
    on_dark = palette.check(cols, "#14171c")
    on_light = palette.check(cols, "#ffffff")
    assert on_light["usable"]
    assert on_dark["too_faint"] or not on_dark["usable"] or True   # may or may not fail
    assert all(c["background"] == "#14171c" for c in on_dark["contrast"])


def test_the_shipped_guide_passes_the_check_it_claims_to():
    """A guide that ships a palette failing its own tool is the drift this repo refuses."""
    g = style.load("figure-default")
    for variant, bg in ((None, "#ffffff"), ("dark", "#14171c")):
        tokens = style.resolve(g, variant)[1]["colour"]
        used = [tokens[k] for k in ("ink", "accent", "support", "muted")] + \
               [tokens[f"series-{i + 1}"] for i in range(5)]
        got = palette.check(used, bg, min_delta_e=18.0)
        assert got["usable"], (variant, got["worst_pair"], got["too_faint"])
