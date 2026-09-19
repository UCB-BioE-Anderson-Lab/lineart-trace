"""Generic glyphs: process axes and stepped sequences. §3.7's third family."""
from .. import build
from . import register

__all__ = ["steps", "timeline", "bracket_set"]

_LINE = "structure-stroke"
_FILL = "surface-fill"
_ACCENT_FILL = "accent-fill"
_LABEL = "caption"


@register("process.steps", version="1", family="process",
          stages=(), width=24.0, height=10.0, gap=6.0, vertical=False, numbered=True)
def steps(stages, width, height, gap, vertical, numbered):
    """A stepped sequence: a box per stage, joined by arrows, numbered if you want.

    `stages` is a sequence of labels. The arrows are drawn here rather than routed, because
    a sequence has nothing to route around -- `connector.route` is for when it does.
    """
    kids = []
    anchors = {}
    for i, label in enumerate(stages):
        x = 0.0 if vertical else i * (width + gap)
        y = i * (height + gap) if vertical else 0.0
        # `box-N` for the element and `stage-N` for the anchor: the anchor is the name a
        # caller addresses, so it gets the good one. Sharing them makes the address ambiguous
        # and `scene.validate` refuses the scene.
        kids.append(build.rect(f"box-{i + 1}", x, y, width, height, radius=1.5,
                               role=_FILL))
        text = f"{i + 1}. {label}" if numbered else str(label)
        kids.append(build.text(f"box-{i + 1}-label", text,
                               (x + width / 2, y + height / 2 + 1.0), family=None,
                               size=None, align="middle", role=_LABEL))
        anchors[f"stage-{i + 1}"] = {"how": "authored",
                                     "at": [x + width / 2, y + height / 2]}
        if i:
            if vertical:
                a = (x + width / 2, y - gap)
                b = (x + width / 2, y)
                d = (0, 1)
            else:
                a = (x - gap, y + height / 2)
                b = (x, y + height / 2)
                d = (1, 0)
            kids.append(build.line(f"link-{i}", a, b, role=_LINE))
            kids.append(build.arrowhead(f"link-{i}-head", b, d, 1.8,
                                        role=_ACCENT_FILL))
    n = max(1, len(stages))
    span_x = width if vertical else n * width + (n - 1) * gap
    span_y = n * height + (n - 1) * gap if vertical else height
    anchors["start"] = {"how": "authored", "at": [0.0, height / 2] if not vertical
                        else [width / 2, 0.0], "dir": [-1, 0] if not vertical else [0, -1]}
    anchors["end"] = {"how": "authored",
                      "at": [span_x, height / 2] if not vertical else [width / 2, span_y],
                      "dir": [1, 0] if not vertical else [0, 1]}
    return kids, anchors


@register("axis.timeline", version="1", family="axis",
          length=70.0, marks=(), title=None, ticks_below=True)
def timeline(length, marks, title, ticks_below):
    """An annotated axis of time or process. `marks` is ``(label, fraction)`` pairs."""
    y = 6.0
    kids = [build.line("axis", (0.0, y), (length, y), role=_LINE),
            build.arrowhead("axis-head", (length, y), (1, 0), 2.0, role=_ACCENT_FILL)]
    anchors = {"start": {"how": "authored", "at": [0.0, y], "dir": [-1, 0]},
               "end": {"how": "authored", "at": [length, y], "dir": [1, 0]}}
    for i, (label, t) in enumerate(marks, 1):
        x = length * float(t)
        dy = 2.0 if ticks_below else -2.0
        kids.append(build.line(f"tick-{i}", (x, y), (x, y + dy), role=_LINE))
        kids.append(build.text(f"tick-{i}-label", label,
                               (x, y + (5.6 if ticks_below else -3.6)), family=None,
                               size=None, align="middle", role=_LABEL))
        anchors[f"mark-{i}"] = {"how": "authored", "at": [x, y], "dir": [0, -1]}
    if title:
        kids.append(build.text("title", title, (length / 2, y - 4.0), family=None,
                               size=None, align="middle", role=_LABEL))
    return kids, anchors


@register("process.bracket", version="1", family="process",
          span=30.0, depth=3.0, label=None, side="top")
def bracket_set(span, depth, label, side):
    """A bracket spanning a run of things, with a label on it."""
    sign = -1 if side == "top" else 1
    y = 4.0
    kids = [build.bracket("bracket", (0.0, y), (span, y), depth * sign, role=_LINE)]
    if label:
        kids.append(build.text("label", label, (span / 2, y + sign * (depth + 2.0)),
                               family=None, size=None, align="middle", role=_LABEL))
    return kids, {"centre": {"how": "authored", "at": [span / 2, y + sign * depth],
                             "dir": [0, sign]},
                  "start": {"how": "authored", "at": [0.0, y]},
                  "end": {"how": "authored", "at": [span, y]}}
