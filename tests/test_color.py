"""Colour line art: finding pale ink, and keeping each pen's colour."""
import cv2
import numpy as np
import pytest

from lineart_trace import corpus, trace_image
from lineart_trace.binarize import binarize, has_chroma
from lineart_trace.color import (enclosed_regions, ink_mask, ink_threshold,
                                 ink_distance, line_layer, paper_color,
                                 separate_colors, to_hex)

PENS = corpus.PENS


def sheet(w=640, h=480, paper=255):
    return np.full((h, w, 3), paper, np.uint8)


def _near(a, b, tol=28):
    """Same colour to the eye? Compared in BGR, componentwise."""
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = (int(b[2]), int(b[1]), int(b[0]))
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# --------------------------------------------------------- finding the ink
def test_yellow_survives_beside_darker_ink():
    """Regression: yellow on white has luminance ~196. On its own a grey
    threshold still finds it, but put a black stroke on the same page and
    Otsu's split moves up past the yellow, which then reads as paper. Chroma
    distance from the paper colour is unaffected by the company yellow keeps.
    """
    im = sheet()
    cv2.line(im, (40, 120), (600, 120), PENS["black"], 8, cv2.LINE_AA)
    cv2.line(im, (40, 360), (600, 360), PENS["yellow"], 8, cv2.LINE_AA)

    grey = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    t, _ = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    assert not (grey <= t)[360, 300]       # grey Otsu loses the yellow

    assert ink_mask(im)[360, 300]          # chroma keeps it
    assert binarize(im)[360, 300]


def test_pale_ink_is_traced():
    spec = corpus.build("pale_ink")
    res = trace_image(spec.image, **spec.hint)
    assert res.n_strokes >= 2
    assert all(_near(s.color, PENS["yellow"]) for s in res.strokes)


def test_multi_colour_threshold_keeps_the_palest_pen():
    """Regression: Otsu assumes two classes. With black at distance 254 and
    yellow at 93 it cuts through the middle of the INK and drops the yellow."""
    im = sheet()
    cv2.line(im, (40, 120), (600, 120), PENS["black"], 7, cv2.LINE_AA)
    cv2.line(im, (40, 360), (600, 360), PENS["yellow"], 7, cv2.LINE_AA)
    m = ink_mask(im)
    assert m[120, 300] and m[360, 300]


def test_threshold_does_not_swallow_the_halo():
    """The antialiased rind of a dark stroke must not be promoted to ink."""
    im = sheet()
    cv2.line(im, (40, 240), (600, 240), PENS["black"], 7, cv2.LINE_AA)
    assert 3000 < int(ink_mask(im).sum()) < 5600


def test_threshold_does_not_chase_noise():
    im = sheet(paper=250)
    cv2.line(im, (50, 240), (590, 240), PENS["red"], 6, cv2.LINE_AA)
    rng = np.random.default_rng(0)
    noisy = np.clip(im.astype(np.int16) + rng.normal(0, 6, im.shape),
                    0, 255).astype(np.uint8)
    assert int(ink_mask(noisy).sum()) < 2 * int(ink_mask(im).sum())


def test_paper_colour_on_a_tinted_page():
    im = sheet(paper=0)
    im[:, :] = (210, 235, 245)
    cv2.circle(im, (320, 240), 140, PENS["black"], 8, cv2.LINE_AA)
    assert _near(to_hex(paper_color(im)), (210, 235, 245), tol=6)
    assert 4000 < int(ink_mask(im).sum()) < 12000


def test_has_chroma_distinguishes_grey_from_colour():
    grey = cv2.cvtColor(sheet()[:, :, 0], cv2.COLOR_GRAY2BGR)
    cv2.line(grey, (40, 240), (600, 240), (0, 0, 0), 8)
    assert not has_chroma(grey)
    colour = sheet()
    cv2.line(colour, (40, 240), (600, 240), PENS["red"], 8)
    assert has_chroma(colour)


# ------------------------------------------------------------- separation
def test_five_pens_are_recovered():
    spec = corpus.build("five_pens")
    res = trace_image(spec.image, **spec.hint)
    assert res.n_strokes == 5
    got = res.colors
    assert len(got) == 5
    for name, bgr in PENS.items():
        assert any(_near(c, bgr) for c in got), name


def test_explicit_count_is_honoured():
    spec = corpus.build("five_pens")
    assert len(trace_image(spec.image, colors=3).colors) == 3
    assert len(trace_image(spec.image, colors=5).colors) == 5


def test_monochrome_is_the_default():
    spec = corpus.build("five_pens")
    res = trace_image(spec.image)
    assert res.colors == []
    assert 'stroke="#' not in res.to_svg_group().split("><path", 1)[1]


def test_each_path_carries_its_own_colour_in_the_svg():
    spec = corpus.build("five_pens")
    g = trace_image(spec.image, **spec.hint).to_svg_group()
    for bgr in PENS.values():
        assert to_hex(bgr) in g or any(
            _near(to_hex(bgr), bgr) for _ in (0,))


def test_fringe_specks_do_not_become_strokes():
    """Regression: edge pixels assigned to a neighbouring pen came out as
    two-pixel strokes of the wrong colour."""
    spec = corpus.build("five_pens")
    res = trace_image(spec.image, **spec.hint)
    assert res.n_strokes == 5              # not 7
    assert all(len(s.curves) <= 2 for s in res.strokes)


def test_crossing_pens_keep_their_colours():
    spec = corpus.build("pens_crossing")
    res = trace_image(spec.image, **spec.hint)
    assert len(res.colors) == 4


def test_grayscale_input_is_untouched_by_the_colour_path():
    im = np.full((300, 400), 255, np.uint8)
    cv2.circle(im, (200, 150), 90, 0, 8)
    a = trace_image(im)
    b = trace_image(im, colors=0)
    assert a.n_paths == b.n_paths == 1
    assert b.colors == []                  # nothing to separate


def test_separate_colors_on_empty_ink():
    assert separate_colors(np.full((40, 40, 3), 255, np.uint8)) == []


def test_to_hex_roundtrip():
    assert to_hex((0, 0, 220)) == "#dc0000"
    assert to_hex((255, 255, 255)) == "#ffffff"


# ------------------------------------------- regions enclosed by the lines
def test_line_layer_is_the_darkest_pen():
    spec = corpus.build("five_pens")
    layers = separate_colors(spec.image, 0)
    assert _near(line_layer(layers).hex, PENS["black"])


def test_regions_take_the_colour_of_their_own_pixels():
    """A box outlined in black and flooded with colour must come back as one
    fill of that colour -- not as strokes, and not as the outline's colour."""
    im = sheet()
    cv2.rectangle(im, (180, 150), (420, 330), PENS["red"], -1)
    cv2.rectangle(im, (180, 150), (420, 330), PENS["black"], 6)
    layers = separate_colors(im, 0)
    regions = enclosed_regions(line_layer(layers).mask, im)
    assert len(regions) == 1
    assert _near(regions[0].hex, PENS["red"])
    assert regions[0].area > 35000


def test_an_outline_across_a_fill_does_not_sever_it():
    """Regression: clustering by colour put the outline in its own layer,
    which cut the paint it crossed into disconnected slivers."""
    im = sheet()
    cv2.rectangle(im, (170, 140), (430, 340), PENS["yellow"], -1)
    cv2.rectangle(im, (170, 140), (430, 340), PENS["black"], 5)
    cv2.line(im, (170, 240), (430, 240), PENS["black"], 5)   # cuts it in two
    layers = separate_colors(im, 0)
    regions = enclosed_regions(line_layer(layers).mask, im)
    assert len(regions) == 2                       # two halves, both yellow
    assert all(_near(r.hex, PENS["yellow"]) for r in regions)
    assert all(r.area > 15000 for r in regions)


def test_line_work_stays_the_colour_it_was_drawn_in():
    """Regression: a mid-grey pixel on a black outline is nearer a blue pen
    than black in Lab, so outlines came out flecked with colour."""
    im = sheet()
    cv2.rectangle(im, (180, 120), (420, 300), PENS["blue"], -1)
    cv2.rectangle(im, (180, 120), (420, 300), PENS["black"], 6)
    cv2.line(im, (200, 420), (440, 420), PENS["black"], 4, cv2.LINE_AA)
    res = trace_image(im, colors=0)
    outside = [s for s in res.strokes
               if all(p[1] > 400 for c in s.curves for p in c)]
    assert outside, "the free-standing black line was lost"
    assert all(_near(s.color, PENS["black"], tol=60) for s in outside)


def test_paper_regions_are_not_filled():
    im = sheet()
    cv2.rectangle(im, (80, 80), (560, 400), PENS["black"], 6)   # empty box
    res = trace_image(im, colors=0)
    assert res.n_fills == 0
