"""Font metrics and text fitting: the half of §1 that says extent is unknowable.

The metric reader is checked against `fontTools` where it is installed, because a parser
written from a specification should be compared with the reference implementation of that
specification rather than with itself.
"""
import pytest

from lineart_trace.scene import fonts, model, text as t

FAMILY = "Helvetica"


def have(family=FAMILY):
    try:
        fonts.resolve(family)
        return True
    except fonts.FontNotFound:
        return False


needs_font = pytest.mark.skipif(not have(), reason=f"no {FAMILY} on this machine")


@needs_font
def test_metrics_come_back_with_the_file_they_were_read_from():
    """A metric is reproducible only alongside the face it came from -- so it carries it."""
    m = fonts.metrics("Polymerase", FAMILY, 12)
    assert m["advance"] > 0 and m["ascent"] > 0 and m["line_height"] > m["ascent"]
    assert len(m["font"]["sha256"]) == 64
    assert m["font"]["units_per_em"] > 0
    assert m["kerning"] is False          # stated, not silently assumed


@needs_font
def test_metrics_scale_linearly_with_size():
    a = fonts.metrics("Hamburgefonstiv", FAMILY, 10)["advance"]
    b = fonts.metrics("Hamburgefonstiv", FAMILY, 30)["advance"]
    assert abs(b - 3 * a) < 1e-9


@needs_font
def test_the_ink_box_is_inside_the_advance_and_below_the_ascent():
    m = fonts.metrics("Hxy", FAMILY, 100)
    assert m["ink"] is not None
    assert m["ink"]["x0"] >= -1 and m["ink"]["x1"] <= m["advance"] + 1
    assert m["ink"]["y1"] <= m["ascent"] + 1


def test_a_missing_family_is_refused_not_substituted():
    """Substituting silently is a figure that measures here and overflows where it prints."""
    with pytest.raises(fonts.FontNotFound):
        fonts.metrics("Hello", "No Such Family At All", 10)


@pytest.mark.parametrize("family", ["Helvetica", "Times New Roman", "Courier New",
                                    "Georgia", "Verdana", "Arial"])
def test_this_parser_agrees_with_fonttools(family):
    """The reference implementation of the specification this was written from."""
    ttLib = pytest.importorskip("fontTools.ttLib")
    if not have(family):
        pytest.skip(f"no {family} here")
    path, idx = fonts.resolve(family)
    mine = fonts.Font(path, idx)
    ref = ttLib.TTFont(path, fontNumber=idx, lazy=True)
    cmap, hmtx, order = ref.getBestCmap(), ref["hmtx"], ref.getGlyphOrder()
    assert mine.units_per_em == ref["head"].unitsPerEm
    for s in ["Polymerase", "Hxy 0123", "Wij, AVATAR.", "active site"]:
        want = sum(hmtx[cmap[ord(c)]][0] if ord(c) in cmap else hmtx[order[0]][0]
                   for c in s)
        assert sum(mine.advance(mine.glyph_id(c)) for c in s) == want, (family, s)
    if "glyf" in ref:
        glyf = ref["glyf"]
        for c in "HxagWQ.,":
            if ord(c) not in cmap:
                continue
            gl = glyf[cmap[ord(c)]]
            want = None if gl.numberOfContours == 0 else (gl.xMin, gl.yMin, gl.xMax,
                                                          gl.yMax)
            assert mine.glyph_box(mine.glyph_id(c)) == want, (family, c)


# ------------------------------------------------------------------ fitting
@needs_font
def test_a_type_size_carries_its_own_unit():
    """A bare 7 in a millimetre box is SEVEN MILLIMETRES of type. Found by the first label."""
    fits = t.fit("DNA duplex entering the active site", 40, 8, FAMILY, "7pt", unit="mm")
    assert len(fits["lines"]) == 1 and fits["width"] < 40
    with pytest.raises(t.TooBig):
        t.fit("DNA duplex entering the active site", 40, 8, FAMILY, 7, unit="mm")


@needs_font
def test_wrapping_uses_as_many_lines_as_it_needs():
    got = t.fit("DNA polymerase active site", 80, 40, FAMILY, 9)
    assert len(got["lines"]) > 1
    assert got["width"] <= 80 and got["height"] <= 40
    assert " ".join(got["lines"]) == "DNA polymerase active site"


@needs_font
def test_strict_refuses_rather_than_overflowing():
    with pytest.raises(t.TooBig) as e:
        t.fit("DNA polymerase active site", 40, 30, FAMILY, 9, mode="strict")
    assert e.value.detail["over_width"] > 0
    assert e.value.detail["needs"]["width"] > 40


@needs_font
def test_shrink_stops_at_the_floor_and_says_so():
    with pytest.raises(t.TooBig) as e:
        t.fit("a very long caption indeed, far too long", 10, 4, FAMILY, 9,
              mode="shrink", min_size=6)
    assert "floor" in str(e.value)
    assert e.value.detail["min_size"] == 6


@needs_font
def test_an_unbreakable_word_is_named_and_not_hyphenated():
    with pytest.raises(t.TooBig) as e:
        t.fit("supercalifragilisticexpialidocious", 20, 40, FAMILY, 10)
    assert e.value.detail["unbreakable"]["word"] == "supercalifragilisticexpialidocious"


@needs_font
def test_a_block_reserves_the_box_it_was_given_as_anchors():
    """Whatever attaches to a label later attaches to the box, not to the ink in it."""
    g, laid = t.block("cap", "active site", 2, 50, 30, 8, family=FAMILY, size="6pt",
                      unit="mm")
    assert [k["name"] for k in g["children"]] == ["line-01"]
    assert g["anchors"]["top-left"]["at"] == [2, 50]
    assert g["anchors"]["bottom-right"]["at"] == [32, 58]
    assert "label" in g["tags"]
    assert laid["unit"] == "mm"
