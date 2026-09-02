"""A labelled corpus of line art, with ground truth, for measuring the tracer.

Every specimen is a function returning ``Specimen(name, category, image,
truth, notes)``. `image` is what the tracer is given; `truth` is the ink the
tracer *should* reproduce. For a clean render the two agree, so `truth` is
simply the ink mask. For a degraded specimen -- a photograph of a crumpled
page -- `truth` is the clean drawing put through the SAME geometric warp but
none of the photometric damage, so the score measures what the tracer
recovered rather than how the noise happened to fall.

Nothing here is decoration. Each specimen isolates one thing that can go
wrong, so a regression can be attributed instead of merely noticed.
"""
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np

__all__ = ["Specimen", "SPECIMENS", "build", "build_all", "categories"]

INK, PAPER = 0, 255


@dataclass
class Specimen:
    name: str
    category: str
    image: np.ndarray                       # uint8 grayscale, what we trace
    truth: np.ndarray                       # 0/1 mask, what we should recover
    notes: str = ""
    hint: Dict = field(default_factory=dict)   # tracer kwargs this case needs


def _canvas(w=640, h=480):
    return np.full((h, w), PAPER, np.uint8)


def _mask(img, thresh=128):
    return (img < thresh).astype(np.uint8)


def _spec(name, cat, img, notes="", hint=None, truth=None):
    return Specimen(name, cat, img,
                    _mask(img) if truth is None else truth, notes, hint or {})


# ------------------------------------------------------------- primitives
def line():
    im = _canvas()
    cv2.line(im, (60, 240), (580, 240), INK, 8, cv2.LINE_AA)
    return _spec("line", "primitive", im, "one straight stroke")


def diagonal():
    im = _canvas()
    cv2.line(im, (60, 60), (580, 420), INK, 8, cv2.LINE_AA)
    return _spec("diagonal", "primitive", im, "staircase-quantised stroke")


def circle():
    im = _canvas()
    cv2.circle(im, (320, 240), 160, INK, 8, cv2.LINE_AA)
    return _spec("circle", "primitive", im, "closed loop with no junction")


def ellipse():
    im = _canvas()
    cv2.ellipse(im, (320, 240), (250, 120), 20, 0, 360, INK, 8, cv2.LINE_AA)
    return _spec("ellipse", "primitive", im, "closed loop, varying curvature")


def rectangle():
    im = _canvas()
    cv2.rectangle(im, (80, 80), (560, 400), INK, 8)
    return _spec("rectangle", "corner", im, "four right-angle corners")


def star():
    im = _canvas()
    pts = []
    for i in range(10):
        r = 190 if i % 2 == 0 else 78
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((320 + r * math.cos(a), 240 + r * math.sin(a)))
    cv2.polylines(im, [np.array(pts, np.int32)], True, INK, 8, cv2.LINE_AA)
    return _spec("star", "corner", im, "ten alternating sharp corners")


def zigzag():
    im = _canvas()
    pts = [(60 + i * 65, 150 if i % 2 else 330) for i in range(9)]
    cv2.polylines(im, [np.array(pts, np.int32)], False, INK, 8, cv2.LINE_AA)
    return _spec("zigzag", "corner", im, "repeated cusps")


def wave():
    im = _canvas()
    pts = [(40 + i, 240 + 130 * math.sin(i / 60.0)) for i in range(560)]
    cv2.polylines(im, [np.array(pts, np.int32)], False, INK, 8, cv2.LINE_AA)
    return _spec("wave", "curve", im, "smooth sinusoid, no corners")


def shallow_arc():
    im = _canvas()
    cv2.ellipse(im, (320, 900), (700, 700), 0, 250, 290, INK, 8, cv2.LINE_AA)
    return _spec("shallow_arc", "curve", im, "very low curvature; seam-prone")


def spiral():
    im = _canvas()
    pts = [(320 + (12 + t * 11) * math.cos(t), 240 + (12 + t * 11) * math.sin(t))
           for t in np.linspace(0, 6 * math.pi, 900)]
    cv2.polylines(im, [np.array(pts, np.int32)], False, INK, 7, cv2.LINE_AA)
    return _spec("spiral", "curve", im, "tightening curvature, close neighbours")


# -------------------------------------------------------------- junctions
def cross():
    im = _canvas()
    cv2.line(im, (60, 240), (580, 240), INK, 8, cv2.LINE_AA)
    cv2.line(im, (320, 40), (320, 440), INK, 8, cv2.LINE_AA)
    return _spec("cross", "junction", im, "perpendicular crossing")


def acute_cross():
    im = _canvas()
    cv2.line(im, (60, 240), (580, 240), INK, 8, cv2.LINE_AA)
    cv2.line(im, (60, 310), (580, 170), INK, 8, cv2.LINE_AA)
    return _spec("acute_cross", "junction", im, "~15 degree crossing")


def tee():
    im = _canvas()
    cv2.line(im, (320, 40), (320, 440), INK, 8, cv2.LINE_AA)
    cv2.line(im, (320, 240), (580, 240), INK, 8, cv2.LINE_AA)
    return _spec("tee", "junction", im, "T junction")


def hub():
    im = _canvas()
    cv2.circle(im, (320, 240), 150, INK, 8, cv2.LINE_AA)
    for a in range(0, 360, 45):
        p = (int(320 + 190 * math.cos(math.radians(a))),
             int(240 + 190 * math.sin(math.radians(a))))
        cv2.line(im, (320, 240), p, INK, 8, cv2.LINE_AA)
    return _spec("hub", "junction", im,
                 "eight spokes meeting at one point, each crossing a ring")


def tangent():
    im = _canvas()
    cv2.circle(im, (320, 200), 130, INK, 8, cv2.LINE_AA)
    cv2.line(im, (40, 330), (600, 330), INK, 8, cv2.LINE_AA)
    return _spec("tangent", "junction", im, "circle touching a line")


# ------------------------------------------------------------------ fills
def solid_triangle():
    im = _canvas()
    cv2.fillPoly(im, [np.array([(120, 100), (500, 240), (120, 380)], np.int32)],
                 INK, cv2.LINE_AA)
    return _spec("solid_triangle", "fill", im,
                 "a centreline cannot represent this; must become a contour")


def arrow():
    im = _canvas()
    cv2.line(im, (60, 240), (420, 240), INK, 10, cv2.LINE_AA)
    cv2.fillPoly(im, [np.array([(560, 240), (410, 185), (410, 295)], np.int32)],
                 INK, cv2.LINE_AA)
    return _spec("arrow", "fill", im, "solid head welded to a stroke")


def ring_fill():
    im = _canvas()
    cv2.circle(im, (320, 240), 170, INK, -1, cv2.LINE_AA)
    cv2.circle(im, (320, 240), 80, PAPER, -1, cv2.LINE_AA)
    return _spec("ring_fill", "fill", im, "filled region with a hole")


def bold_stroke():
    im = _canvas()
    cv2.line(im, (60, 160), (580, 160), INK, 6, cv2.LINE_AA)
    cv2.line(im, (60, 320), (580, 320), INK, 26, cv2.LINE_AA)
    return _spec("bold_stroke", "fill", im,
                 "a heavy stroke is still a stroke, not a fill")


# --------------------------------------------------------------- patterns
def hatching():
    im = _canvas()
    for i in range(14):
        cv2.line(im, (40 + i * 34, 100), (160 + i * 34, 380), INK, 5, cv2.LINE_AA)
        cv2.line(im, (40 + i * 34, 380), (160 + i * 34, 100), INK, 5, cv2.LINE_AA)
    return _spec("hatching", "pattern", im, "dense cross-hatching")


def parallels():
    im = _canvas()
    for i, gap in enumerate((7, 14, 28)):
        y = 110 + i * 120
        cv2.line(im, (60, y), (580, y), INK, 7, cv2.LINE_AA)
        cv2.line(im, (60, y + gap), (580, y + gap), INK, 7, cv2.LINE_AA)
    return _spec("parallels", "pattern", im,
                 "pairs 1x / 2x / 4x a stroke width apart")


def concentric():
    im = _canvas()
    for r in (60, 95, 135, 180):
        cv2.circle(im, (320, 240), r, INK, 7, cv2.LINE_AA)
    return _spec("concentric", "pattern", im, "nested loops")


def dashes_dots():
    im = _canvas()
    for i in range(14):
        cv2.line(im, (60 + i * 38, 160), (86 + i * 38, 160), INK, 8, cv2.LINE_AA)
    for i in range(12):
        cv2.circle(im, (70 + i * 44, 320), 5, INK, -1, cv2.LINE_AA)
    return _spec("dashes_dots", "pattern", im,
                 "dashes survive; isolated dots have no centreline")


def thin_lines():
    im = _canvas()
    for i in range(6):
        cv2.line(im, (60, 90 + i * 60), (580, 90 + i * 60), INK, 1, cv2.LINE_AA)
    return _spec("thin_lines", "pattern", im, "single-pixel strokes")


def text_like():
    im = _canvas()
    cv2.putText(im, "Line Art", (40, 190), cv2.FONT_HERSHEY_SIMPLEX, 2.6,
                INK, 7, cv2.LINE_AA)
    cv2.putText(im, "Trace 0.2", (40, 360), cv2.FONT_HERSHEY_DUPLEX, 2.2,
                INK, 5, cv2.LINE_AA)
    return _spec("text_like", "pattern", im, "lettering: many short strokes")


# --------------------------------------------------------------- drawings
def _flower(im):
    cv2.line(im, (320, 460), (320, 250), INK, 7, cv2.LINE_AA)
    for s in (-1, 1):
        pts = [(320 + s * 90 * math.sin(t), 400 - 60 * t) for t in
               np.linspace(0, 1.6, 40)]
        cv2.polylines(im, [np.array(pts, np.int32)], False, INK, 6, cv2.LINE_AA)
    for a in range(0, 360, 45):
        c = (int(320 + 78 * math.cos(math.radians(a))),
             int(230 + 78 * math.sin(math.radians(a))))
        cv2.ellipse(im, c, (46, 30), a, 0, 360, INK, 6, cv2.LINE_AA)
    cv2.circle(im, (320, 230), 34, INK, 6, cv2.LINE_AA)
    return im


def flower():
    return _spec("flower", "drawing", _flower(_canvas()),
                 "ordinary line art: loops, junctions, curves together")


def house():
    im = _canvas()
    cv2.polylines(im, [np.array([(120, 420), (120, 220), (320, 90),
                                 (520, 220), (520, 420), (120, 420)],
                                np.int32)], True, INK, 8, cv2.LINE_AA)
    cv2.rectangle(im, (260, 300), (380, 420), INK, 8)
    cv2.rectangle(im, (160, 260), (230, 330), INK, 6)
    cv2.rectangle(im, (410, 260), (480, 330), INK, 6)
    cv2.line(im, (195, 260), (195, 330), INK, 4, cv2.LINE_AA)
    cv2.line(im, (160, 295), (230, 295), INK, 4, cv2.LINE_AA)
    return _spec("house", "drawing", im, "corners, T-junctions, mixed weights")


def face():
    im = _canvas()
    cv2.ellipse(im, (320, 250), (140, 175), 0, 0, 360, INK, 8, cv2.LINE_AA)
    for x in (265, 375):
        cv2.ellipse(im, (x, 215), (30, 18), 0, 0, 360, INK, 6, cv2.LINE_AA)
        cv2.circle(im, (x, 215), 8, INK, -1, cv2.LINE_AA)
    cv2.ellipse(im, (320, 300), (55, 40), 0, 20, 160, INK, 7, cv2.LINE_AA)
    for x, s in ((265, -1), (375, 1)):
        cv2.ellipse(im, (x, 175), (36, 22), 0, 190, 350, INK, 5, cv2.LINE_AA)
    cv2.line(im, (320, 225), (320, 268), INK, 5, cv2.LINE_AA)
    return _spec("face", "drawing", im,
                 "loops, filled pupils and open curves in one figure")


# ---------------------------------------------------------------- shading
def gray_shading():
    im = _canvas()
    _flower(im)
    sh = np.zeros(im.shape, np.uint8)
    cv2.circle(sh, (320, 230), 74, 1, -1)
    im[sh > 0] = np.minimum(im[sh > 0], 165)      # a flat mid-grey wash
    return _spec("gray_shading", "shading", im,
                 "a grey wash is not a line; it binarises to a blob or nothing",
                 truth=_mask(im, 100))


def gradient_shading():
    im = _canvas()
    _flower(im)
    g = np.tile(np.linspace(255, 120, im.shape[1]), (im.shape[0], 1))
    im = np.minimum(im, g).astype(np.uint8)
    return _spec("gradient_shading", "shading", im,
                 "a tonal ramp across the drawing",
                 truth=_mask(_flower(_canvas())))


def stipple_shading():
    im = _canvas()
    _flower(im)
    rng = np.random.default_rng(7)
    for _ in range(1400):
        x, y = rng.integers(120, 520), rng.integers(340, 460)
        cv2.circle(im, (int(x), int(y)), 2, INK, -1)
    return _spec("stipple_shading", "shading", im,
                 "stipple dots: correct output is many dots, not lines")


# ------------------------------------------------------------- colour
PENS = {"red": (0, 0, 220), "blue": (220, 60, 0), "black": (0, 0, 0),
        "yellow": (0, 215, 235), "green": (40, 150, 40)}       # BGR


def _color_canvas(w=640, h=480):
    return np.full((h, w, 3), PAPER, np.uint8)


def _color_truth(img):
    from .color import ink_mask
    return ink_mask(img)


def five_pens():
    im = _color_canvas()
    for i, bgr in enumerate(PENS.values()):
        cv2.line(im, (50, 60 + i * 90), (590, 60 + i * 90), bgr, 7, cv2.LINE_AA)
    return Specimen("five_pens", "color", im, _color_truth(im),
                    "five pens on white; each must keep its own colour",
                    {"colors": 0})


def pale_ink():
    """Yellow alone. A brightness threshold cannot see this at all."""
    im = _color_canvas()
    cv2.circle(im, (320, 240), 150, PENS["yellow"], 8, cv2.LINE_AA)
    cv2.line(im, (60, 240), (580, 240), PENS["yellow"], 8, cv2.LINE_AA)
    return Specimen("pale_ink", "color", im, _color_truth(im),
                    "yellow on white: luminance ~196, invisible to a grey "
                    "threshold", {"colors": 0})


def pens_crossing():
    im = _color_canvas()
    cv2.circle(im, (220, 240), 140, PENS["red"], 7, cv2.LINE_AA)
    cv2.circle(im, (400, 240), 140, PENS["blue"], 7, cv2.LINE_AA)
    cv2.line(im, (40, 240), (600, 240), PENS["yellow"], 7, cv2.LINE_AA)
    cv2.line(im, (40, 90), (600, 390), PENS["black"], 7, cv2.LINE_AA)
    return Specimen("pens_crossing", "color", im, _color_truth(im),
                    "pens overlap; the covered stroke is genuinely broken",
                    {"colors": 0})


def tinted_paper():
    im = np.full((480, 640, 3), (210, 235, 245), np.uint8)     # cream page
    cv2.circle(im, (320, 240), 150, (90, 40, 30), 8, cv2.LINE_AA)
    cv2.line(im, (60, 400), (580, 400), (40, 40, 170), 8, cv2.LINE_AA)
    return Specimen("tinted_paper", "color", im, _color_truth(im),
                    "ink on a cream page: the paper is not white",
                    {"colors": 0})


# --------------------------------------------------------- degradation
def _warp_field(shape, seed, amp, scale):
    rng = np.random.default_rng(seed)
    h, w = shape
    small = (max(2, h // scale), max(2, w // scale))
    fy = cv2.resize(rng.normal(0, 1, small).astype(np.float32), (w, h),
                    interpolation=cv2.INTER_CUBIC)
    fx = cv2.resize(rng.normal(0, 1, small).astype(np.float32), (w, h),
                    interpolation=cv2.INTER_CUBIC)
    fy = cv2.GaussianBlur(fy, (0, 0), 9) * amp
    fx = cv2.GaussianBlur(fx, (0, 0), 9) * amp
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    return gx + fx, gy + fy, fx, fy


def photograph(base: Optional[Specimen] = None, seed: int = 3,
               name: str = "photograph") -> Specimen:
    """Simulate a phone photo of a drawing on a crumpled sheet.

    The geometric warp is applied to the ground truth as well, so the score
    reflects whether the strokes were recovered through the lighting, blur,
    noise and JPEG damage -- not whether the paper happened to lie flat.
    """
    base = base or flower()
    im = base.image.astype(np.float32)
    truth = base.truth.astype(np.float32)
    h, w = im.shape

    mx, my, fx, fy = _warp_field((h, w), seed, amp=9.0, scale=6)
    im = cv2.remap(im, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    truth = cv2.remap(truth, mx, my, cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_REPLICATE)

    rng = np.random.default_rng(seed + 1)
    # creases: bright ridge on one side of a fold, shadow on the other
    shade = cv2.GaussianBlur(fx + fy, (0, 0), 25)
    shade = shade / (np.abs(shade).max() + 1e-6)
    light = 1.0 + 0.30 * shade
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    light *= 1.0 - 0.34 * r2                       # vignette
    light *= 0.78 + 0.30 * (xx / w)                # light from one side
    im = im * light

    im = cv2.GaussianBlur(im, (0, 0), 1.1)         # soft focus
    im += rng.normal(0, 4.0, im.shape).astype(np.float32)
    grain = cv2.GaussianBlur(rng.normal(0, 1, im.shape).astype(np.float32),
                             (0, 0), 1.5) * 7.0
    im = np.clip(im + grain, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", im, [int(cv2.IMWRITE_JPEG_QUALITY), 62])
    if ok:
        im = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return Specimen(name, "photo", im, (truth > 0.5).astype(np.uint8),
                    "crumpled page, uneven light, blur, grain, JPEG",
                    {"method": "auto", "denoise": True, "despeckle_area": 12})


def scan():
    base = house()
    im = base.image.astype(np.float32)
    h, w = im.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 1.4, 1.0)
    im = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR,
                        borderValue=PAPER)
    truth = cv2.warpAffine(base.truth.astype(np.float32), M, (w, h),
                           flags=cv2.INTER_LINEAR, borderValue=0)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    im *= 0.80 + 0.24 * (yy / h)
    im = cv2.GaussianBlur(im, (0, 0), 0.9)
    rng = np.random.default_rng(11)
    im = np.clip(im + rng.normal(0, 3.0, im.shape), 0, 255).astype(np.uint8)
    return Specimen("scan", "photo", im, (truth > 0.5).astype(np.uint8),
                    "flatbed scan: skew, soft focus, lamp falloff",
                    {"method": "auto", "despeckle_area": 8})


def speckled():
    base = flower()
    im = base.image.copy()
    rng = np.random.default_rng(5)
    n = im.size // 900
    ys = rng.integers(0, im.shape[0], n)
    xs = rng.integers(0, im.shape[1], n)
    im[ys, xs] = INK
    return Specimen("speckled", "noise", im, base.truth,
                    "salt noise; should be despeckled, not traced",
                    {"despeckle_area": 12})


def broken():
    base = circle()
    im = base.image.copy()
    for a in range(0, 360, 40):
        c = (int(320 + 160 * math.cos(math.radians(a))),
             int(240 + 160 * math.sin(math.radians(a))))
        cv2.circle(im, c, 4, PAPER, -1)
    return Specimen("broken", "noise", im, base.truth,
                    "antialias dropouts along a curve; --close bridges them",
                    {"close": 5})


def low_contrast():
    base = house()
    im = (base.image.astype(np.float32) * 0.35 + 150).astype(np.uint8)
    return Specimen("low_contrast", "noise", im, base.truth,
                    "faint grey ink on grey paper", {"method": "auto"})


# ------------------------------------------------------------------ index
SPECIMENS: Dict[str, Callable[[], Specimen]] = {
    f.__name__: f for f in (
        line, diagonal, circle, ellipse, rectangle, star, zigzag, wave,
        shallow_arc, spiral, cross, acute_cross, tee, hub, tangent,
        solid_triangle, arrow, ring_fill, bold_stroke, hatching, parallels,
        concentric, dashes_dots, thin_lines, text_like, flower, house, face,
        five_pens, pale_ink, pens_crossing, tinted_paper,
        gray_shading, gradient_shading, stipple_shading, photograph, scan,
        speckled, broken, low_contrast,
    )
}


def build(name: str) -> Specimen:
    return SPECIMENS[name]()


def build_all() -> List[Specimen]:
    return [f() for f in SPECIMENS.values()]


def categories() -> List[str]:
    seen = []
    for s in build_all():
        if s.category not in seen:
            seen.append(s.category)
    return seen
