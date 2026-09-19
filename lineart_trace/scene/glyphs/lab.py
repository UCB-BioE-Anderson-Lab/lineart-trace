"""Laboratory glyphs: the objects a protocol figure is made of. §3.7."""
import math

from .. import build
from . import register

__all__ = ["tube", "plate", "pipette", "gradient"]

_LINE = "structure-stroke"
_FINE = "detail-stroke"
_FILL = "surface-fill"
_ACCENT = "accent-fill"
_LABEL = "caption"


@register("lab.tube", version="1", family="lab",
          height=22.0, width=8.0, fill=0.0, cap=True, label=None, graduations=0)
def tube(height, width, fill, cap, label, graduations):
    """A microcentrifuge tube, optionally filled to a fraction of its body and graduated."""
    r = width / 2
    body_h = height - r
    kids = []
    outline = [["M", 0.0, 0.0], ["L", width, 0.0], ["L", width, body_h]]
    k = r * build.KAPPA
    outline += [["C", width, body_h + k, width - r + k, height, r, height],
                ["C", r - k, height, 0.0, body_h + k, 0.0, body_h], ["Z"]]
    if fill > 0:
        top = height - (body_h + r) * min(1.0, fill)
        clip = [["M", 0.0, max(top, 0.0)], ["L", width, max(top, 0.0)],
                ["L", width, body_h],
                ["C", width, body_h + k, width - r + k, height, r, height],
                ["C", r - k, height, 0.0, body_h + k, 0.0, body_h], ["Z"]]
        kids.append(build.region("contents", [clip], role=_ACCENT))
    kids.insert(0, build.path("body", outline, closed=True, role=_LINE))
    if cap:
        kids.append(build.rect("cap", -0.6, -2.4, width + 1.2, 2.4, radius=0.6,
                               role=_FILL))
    for i in range(1, graduations + 1):
        y = body_h * i / (graduations + 1)
        kids.append(build.line(f"grad-{i}", (width * 0.62, y), (width, y), role=_FINE))
    if label:
        kids.append(build.text("label", label, (width / 2, height + 4.0), family=None,
                               size=None, align="middle", role=_LABEL))
    return kids, {"mouth": {"how": "authored", "at": [width / 2, -2.4], "dir": [0, -1]},
                  "tip": {"how": "authored", "at": [width / 2, height], "dir": [0, 1]},
                  "centre": {"how": "authored", "at": [width / 2, height / 2]}}


@register("lab.plate", version="1", family="lab",
          rows=8, cols=12, pitch=4.5, well=3.4, filled=(), labels=True)
def plate(rows, cols, pitch, well, filled, labels):
    """A microplate. `filled` is a sequence of ``"A1"``-style wells to draw as occupied."""
    pad = 3.0
    w = cols * pitch + 2 * pad
    h = rows * pitch + 2 * pad
    kids = [build.rect("body", 0.0, 0.0, w, h, radius=1.5, role=_FILL)]
    want = {str(f).upper() for f in filled}
    letters = "ABCDEFGHIJKLMNOP"
    for r in range(rows):
        for c in range(cols):
            cx = pad + pitch * (c + 0.5)
            cy = pad + pitch * (r + 0.5)
            name = f"{letters[r]}{c + 1}"
            role = _ACCENT if name in want else _LINE
            kids.append(build.circle(f"well-{name.lower()}", cx, cy, well / 2, role=role))
    if labels:
        for c in range(cols):
            kids.append(build.text(f"col-{c + 1}", str(c + 1),
                                   (pad + pitch * (c + 0.5), -1.2), family=None,
                                   size=None, align="middle", role=_LABEL))
        for r in range(rows):
            kids.append(build.text(f"row-{letters[r].lower()}", letters[r],
                                   (-1.6, pad + pitch * (r + 0.5) + 1.0), family=None,
                                   size=None, align="end", role=_LABEL))
    anchors = {"a1": {"how": "authored", "at": [pad + pitch * 0.5, pad + pitch * 0.5]},
               "centre": {"how": "authored", "at": [w / 2, h / 2]},
               "top-left": {"how": "authored", "at": [0.0, 0.0]}}
    return kids, anchors


@register("lab.pipette", version="1", family="lab",
          length=30.0, width=5.0, tip=6.0, label=None)
def pipette(length, width, tip, label):
    """A pipette with a tip, pointing down."""
    kids = [
        build.polyline("barrel", [(0.0, 0.0), (width, 0.0), (width * 0.62, length),
                                  (width * 0.38, length)], closed=True, role=_LINE),
        build.polyline("tip-cone", [(width * 0.38, length), (width * 0.62, length),
                               (width * 0.54, length + tip), (width * 0.46, length + tip)],
                       closed=True, role=_FILL),
        build.rect("plunger", width * 0.3, -3.0, width * 0.4, 3.0, role=_LINE),
    ]
    if label:
        kids.append(build.text("label", label, (width + 2.0, length / 2), family=None,
                               size=None, role=_LABEL))
    return kids, {"tip": {"how": "authored", "at": [width / 2, length + tip],
                          "dir": [0, 1]},
                  "top": {"how": "authored", "at": [width / 2, -3.0], "dir": [0, -1]}}


@register("lab.gradient", version="1", family="lab",
          width=10.0, height=40.0, steps=6, label_top=None, label_bottom=None)
def gradient(width, height, steps, label_top, label_bottom):
    """A density or concentration gradient drawn as discrete bands, densest at the bottom."""
    kids = [build.rect("column", 0.0, 0.0, width, height, radius=1.0, role=_LINE)]
    for i in range(steps):
        y = height * i / steps
        kids.append(build.rect(f"band-{i + 1}", 0.6, y + 0.4, width - 1.2,
                               height / steps - 0.8,
                               role=_ACCENT if i >= steps - 2 else _FILL))
    # `top-label`/`bottom-label` for the elements: `top` and `bottom` are the anchors, and
    # an element sharing an anchor's name makes the address mean two things.
    if label_top:
        kids.append(build.text("top-label", label_top, (width + 2.0, 3.0), family=None,
                               size=None, role=_LABEL))
    if label_bottom:
        kids.append(build.text("bottom-label", label_bottom, (width + 2.0, height - 1.0),
                               family=None, size=None, role=_LABEL))
    return kids, {"top": {"how": "authored", "at": [width / 2, 0.0], "dir": [0, -1]},
                  "bottom": {"how": "authored", "at": [width / 2, height], "dir": [0, 1]}}
