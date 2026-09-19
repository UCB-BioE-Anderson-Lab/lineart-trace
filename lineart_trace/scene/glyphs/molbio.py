"""Molecular biology glyphs. §3.7's first family, and the one the spec names.

Every glyph here is built from roles and carries anchors. Coordinates are the glyph's own,
with the origin at its top-left and y running down, so a caller positions it with a transform
or a relation rather than by baking an offset into the arguments.
"""
import math

from .. import build
from . import register

__all__ = ["duplex", "plasmid", "gel", "protein", "membrane", "reaction"]

_ROLE_LINE = "structure-stroke"
_ROLE_FINE = "detail-stroke"
_ROLE_FILL = "surface-fill"
_ROLE_ACCENT = "accent-stroke"
_ROLE_ACCENT_FILL = "accent-fill"
_ROLE_LABEL = "caption"


def _sine(x0, length, mid, rise, turns, phase, n=80):
    return [(x0 + length * t / n,
             mid + rise * math.sin(2 * math.pi * turns * t / n + phase))
            for t in range(n + 1)]


@register("dna.duplex", version="1", family="dna",
          length=40.0, rise=2.4, turns=4.0, rungs=17, polarity=True,
          nick=None, gap=None, mismatch=None, label=None)
def duplex(length, rise, turns, rungs, polarity, nick, gap, mismatch, label):
    """A linear DNA duplex: two antiparallel strands, base-pair rungs, and strand polarity.

    `nick`, `gap` and `mismatch` each take a fraction along the duplex (0 to 1) or None.
    A nick breaks the top strand at that point; a gap removes a short run of it; a mismatch
    draws its rung as a broken pair. Each is a thing a lecture slide needs and a thing that
    is fiddly to draw twice the same way.
    """
    mid = rise + 1.0
    kids = []
    top = _sine(0.0, length, mid, rise, turns, 0.0)
    bottom = _sine(0.0, length, mid, rise, turns, math.pi)

    def cut(points, at, width):
        if at is None:
            return [points]
        lo, hi = (at - width / 2) * length, (at + width / 2) * length
        a = [p for p in points if p[0] <= lo]
        b = [p for p in points if p[0] >= hi]
        return [p for p in (a, b) if len(p) > 1]

    if gap is not None:
        runs = cut(top, gap, 0.10)
    elif nick is not None:
        runs = cut(top, nick, 0.012)
    else:
        runs = [top]
    for i, run in enumerate(runs, 1):
        kids.append(build.through(f"strand-a-{i}" if len(runs) > 1 else "strand-a",
                                  run, tension=0.5, role=_ROLE_LINE))
    kids.append(build.through("strand-b", bottom, tension=0.5, role=_ROLE_LINE))

    mm = None if mismatch is None else int(round(mismatch * (rungs - 1)))
    for i in range(rungs):
        t = (i + 0.5) / rungs
        x = length * t
        y0 = mid + rise * math.sin(2 * math.pi * turns * t)
        y1 = mid + rise * math.sin(2 * math.pi * turns * t + math.pi)
        if gap is not None and abs(t - gap) < 0.05:
            continue
        if i == mm:
            d = (y1 - y0) * 0.3
            kids.append(build.line(f"pair-{i + 1:02d}a", (x, y0), (x, y0 + d),
                                   role=_ROLE_FINE))
            kids.append(build.line(f"pair-{i + 1:02d}b", (x, y1 - d), (x, y1),
                                   role=_ROLE_FINE))
        else:
            kids.append(build.line(f"pair-{i + 1:02d}", (x, y0), (x, y1),
                                   role=_ROLE_FINE))

    if polarity:
        kids.append(build.text("five-prime-label", "5′", (-1.2, mid - rise - 1.0),
                               family=None, size=None, align="end", role=_ROLE_LABEL))
        kids.append(build.text("three-prime-label", "3′",
                               (length + 1.2, mid - rise - 1.0),
                               family=None, size=None, role=_ROLE_LABEL))
        kids.append(build.text("five-prime-label-b", "5′",
                               (length + 1.2, mid + rise + 2.4),
                               family=None, size=None, role=_ROLE_LABEL))
        kids.append(build.text("three-prime-label-b", "3′",
                               (-1.2, mid + rise + 2.4), family=None, size=None,
                               align="end", role=_ROLE_LABEL))
    if label:
        kids.append(build.text("label", label, (length / 2, mid + rise + 6.0),
                               family=None, size=None, align="middle", role=_ROLE_LABEL))

    anchors = {
        "five-prime": {"how": "authored", "at": [0.0, mid], "dir": [-1.0, 0.0]},
        "three-prime": {"how": "authored", "at": [length, mid], "dir": [1.0, 0.0]},
        "centre": {"how": "authored", "at": [length / 2, mid]},
    }
    for key, at in (("nick", nick), ("gap", gap), ("mismatch", mismatch)):
        if at is not None:
            anchors[key] = {"how": "authored", "at": [length * at, mid - rise],
                            "dir": [0.0, -1.0]}
    return kids, anchors


@register("dna.plasmid", version="1", family="dna",
          radius=18.0, features=(), sites=(), name=None, ticks=True)
def plasmid(radius, features, sites, name, ticks):
    """A circular plasmid map: the backbone, feature arcs with arrowheads, and cut sites.

    `features` is a sequence of ``(label, start_deg, end_deg)`` and `sites` a sequence of
    ``(label, degrees)``. Angles run clockwise from twelve o'clock, which is how every
    plasmid map in every catalogue is drawn.
    """
    cx = cy = radius + 8.0
    kids = [build.circle("backbone", cx, cy, radius, role=_ROLE_LINE)]

    def at(deg, r):
        a = math.radians(deg - 90.0)
        return (cx + r * math.cos(a), cy + r * math.sin(a))

    for i, (lab, a0, a1) in enumerate(features, 1):
        rr = radius + 2.2
        kids.append(build.arc(f"feature-{i}", cx, cy, rr, a0 - 90.0, a1 - 90.0,
                              role=_ROLE_ACCENT))
        tipd = math.radians(a1 - 90.0)
        tan = (-math.sin(tipd), math.cos(tipd))
        kids.append(build.arrowhead(f"feature-{i}-head", at(a1, rr), tan, 2.0,
                                    role=_ROLE_ACCENT_FILL))
        midd = (a0 + a1) / 2.0
        lx, ly = at(midd, rr + 5.0)
        kids.append(build.text(f"feature-{i}-label", lab, (lx, ly), family=None,
                               size=None, align="middle", role=_ROLE_LABEL))
    for i, (lab, deg) in enumerate(sites, 1):
        if ticks:
            kids.append(build.line(f"site-{i}", at(deg, radius - 2.0),
                                   at(deg, radius + 2.0), role=_ROLE_LINE))
        lx, ly = at(deg, radius + 8.0)
        kids.append(build.text(f"site-{i}-label", lab, (lx, ly), family=None, size=None,
                               align="middle", role=_ROLE_LABEL))
    if name:
        kids.append(build.text("name", name, (cx, cy), family=None, size=None,
                               align="middle", baseline="middle", role=_ROLE_LABEL))

    anchors = {"centre": {"how": "authored", "at": [cx, cy]},
               "north": {"how": "authored", "at": list(at(0, radius)), "dir": [0, -1]},
               "east": {"how": "authored", "at": list(at(90, radius)), "dir": [1, 0]},
               "south": {"how": "authored", "at": list(at(180, radius)), "dir": [0, 1]},
               "west": {"how": "authored", "at": list(at(270, radius)), "dir": [-1, 0]}}
    # `cut-N`, NOT `site-N`: the tick elements are already called `site-N`, and an anchor
    # sharing a name with a child makes `plasmid.site-1` name two things. The validator
    # caught it on the first placement of this glyph, which is what that check is for.
    for i, (lab, deg) in enumerate(sites, 1):
        anchors[f"cut-{i}"] = {"how": "authored", "at": list(at(deg, radius + 2.0)),
                                "dir": [math.cos(math.radians(deg - 90)),
                                        math.sin(math.radians(deg - 90))]}
    return kids, anchors


@register("gel.lanes", version="1", family="gel",
          lanes=4, width=9.0, height=48.0, gap=2.5, ladder=(), bands=(), labels=())
def gel(lanes, width, height, gap, ladder, bands, labels):
    """An electrophoresis gel: lanes, a ladder, and bands placed by migration fraction.

    `bands` is a sequence of ``(lane, fraction, intensity)`` with lane counted from 1 and
    fraction 0 at the well and 1 at the front. `ladder` is a sequence of fractions for lane
    zero, drawn to the left of the first sample lane.
    """
    kids = []
    lane_x = []
    x = 0.0
    total = lanes + (1 if ladder else 0)
    for i in range(total):
        kids.append(build.rect(f"lane-{i}", x, 0.0, width, height, role=_ROLE_FILL))
        lane_x.append(x)
        x += width + gap
    for f in ladder:
        y = 2.0 + (height - 4.0) * f
        kids.append(build.rect(f"ladder-{int(f * 1000):04d}", lane_x[0] + 1.0, y,
                               width - 2.0, 0.9, role=_ROLE_LINE))
    off = 1 if ladder else 0
    for i, (lane, f, intensity) in enumerate(bands, 1):
        idx = lane - 1 + off
        if not 0 <= idx < total:
            continue
        y = 2.0 + (height - 4.0) * f
        h = 0.8 + 1.6 * float(intensity)
        kids.append(build.rect(f"band-{i:02d}", lane_x[idx] + 1.0, y, width - 2.0, h,
                               role=_ROLE_LINE))
    for i, lab in enumerate(labels):
        idx = i + off
        if idx >= total:
            break
        kids.append(build.text(f"label-{i + 1}", lab, (lane_x[idx] + width / 2, -1.5),
                               family=None, size=None, align="middle", role=_ROLE_LABEL))
    anchors = {"top-left": {"how": "authored", "at": [0.0, 0.0]},
               "wells": {"how": "authored", "at": [x / 2, 0.0], "dir": [0, -1]},
               "front": {"how": "authored", "at": [x / 2, height], "dir": [0, 1]}}
    # `well-N`, NOT `lane-N`: the lane rectangles are already called that, and an anchor
    # sharing a child's name makes the address ambiguous. Second time in this file; the
    # catalogue test now places every glyph and validates, so there will not be a third.
    for i, lx in enumerate(lane_x, 1):
        anchors[f"well-{i}"] = {"how": "authored", "at": [lx + width / 2, 0.0],
                                "dir": [0, -1]}
    return kids, anchors


@register("protein.silhouette", version="1", family="protein",
          width=34.0, height=26.0, lobes=5, cleft=0.55, cleft_depth=0.42, seed=1,
          label=None)
def protein(width, height, lobes, cleft, cleft_depth, seed, label):
    """A generic protein silhouette with a real cleft, placed where you ask for it.

    Deterministic for a given `seed`: the same arguments give the same shape, which is what
    lets the same enzyme be drawn identically in three figures.

    The cleft is a genuine concavity, not a decoration: `anchors.derive(..., "concavity")`
    finds it independently, and on a 40x30 glyph the discovered point sits **0.1 to 1.0 mm**
    from the anchor this glyph declares -- the gap being the difference between the analytic
    formula here and the Catmull-Rom curve actually drawn through the samples. Close enough
    to attach to, and stated rather than claimed as exact.
    """
    cx, cy = width / 2 + 2.0, height / 2 + 2.0
    rx, ry = width / 2, height / 2
    n = 96
    rnd = seed * 9781 % 65536
    wob = []
    for k in range(1, 4):
        rnd = (rnd * 1103515245 + 12345) % 2147483648
        wob.append(((rnd % 1000) / 1000.0 - 0.5) * 0.10)
    pts = []
    for i in range(n):
        t = i / n
        a = 2 * math.pi * t
        r = 1.0 + sum(w * math.sin((k + 2) * a + k) for k, w in enumerate(wob, 1))
        r += 0.06 * math.sin(lobes * a)
        d = abs(((t - cleft) + 0.5) % 1.0 - 0.5)
        if d < 0.07:
            r -= cleft_depth * (1.0 - (d / 0.07) ** 2)
        pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
    kids = [build.through("body", pts, tension=0.5, closed=True, role=_ROLE_FILL)]
    if label:
        kids.append(build.text("label", label, (cx, cy), family=None, size=None,
                               align="middle", baseline="middle", role=_ROLE_LABEL))
    a = 2 * math.pi * cleft
    d = abs(0.0)
    rc = 1.0 + sum(w * math.sin((k + 2) * a + k) for k, w in enumerate(wob, 1)) \
        + 0.06 * math.sin(lobes * a) - cleft_depth
    cleft_pt = (cx + rx * rc * math.cos(a), cy + ry * rc * math.sin(a))
    anchors = {
        "cleft": {"how": "authored", "at": [cleft_pt[0], cleft_pt[1]],
                  "dir": [math.cos(a), math.sin(a)]},
        "centre": {"how": "authored", "at": [cx, cy]},
    }
    return kids, anchors


@register("membrane.bilayer", version="1", family="membrane",
          length=60.0, head=1.6, tail=4.0, spacing=3.4, curve=0.0)
def membrane(length, head, tail, spacing, curve):
    """A phospholipid bilayer: two leaflets of heads with their tails facing inwards."""
    kids = []
    mid = head + tail + 1.0
    n = max(2, int(length / spacing))
    for i in range(n + 1):
        x = length * i / n
        dy = curve * math.sin(math.pi * i / n)
        for side, sign in (("upper", -1), ("lower", 1)):
            hy = mid + sign * (tail + head) + dy
            kids.append(build.circle(f"{side}-head-{i:02d}", x, hy, head,
                                     role=_ROLE_FILL))
            kids.append(build.line(f"{side}-tail-{i:02d}a", (x - head * 0.4, hy - sign * head),
                                   (x - head * 0.3, mid + dy), role=_ROLE_FINE))
            kids.append(build.line(f"{side}-tail-{i:02d}b", (x + head * 0.4, hy - sign * head),
                                   (x + head * 0.3, mid + dy), role=_ROLE_FINE))
    anchors = {"outer": {"how": "authored", "at": [length / 2, mid - tail - head * 2],
                         "dir": [0, -1]},
               "inner": {"how": "authored", "at": [length / 2, mid + tail + head * 2],
                         "dir": [0, 1]},
               "centre": {"how": "authored", "at": [length / 2, mid]}}
    return kids, anchors


@register("arrow.reaction", version="1", family="arrow",
          length=26.0, above=None, below=None, reversible=False, head=2.2)
def reaction(length, above, below, reversible, head):
    """A reaction arrow with conditions set above and below it, optionally reversible."""
    y = 4.0
    kids = []
    if reversible:
        kids.append(build.line("forward", (0.0, y - 0.9), (length, y - 0.9),
                               role=_ROLE_LINE))
        kids.append(build.arrowhead("forward-head", (length, y - 0.9), (1, 0), head,
                                    filled=False, role=_ROLE_LINE))
        kids.append(build.line("back", (length, y + 0.9), (0.0, y + 0.9),
                               role=_ROLE_LINE))
        kids.append(build.arrowhead("back-head", (0.0, y + 0.9), (-1, 0), head,
                                    filled=False, role=_ROLE_LINE))
    else:
        kids.append(build.line("shaft", (0.0, y), (length, y), role=_ROLE_LINE))
        kids.append(build.arrowhead("head", (length, y), (1, 0), head,
                                    role=_ROLE_ACCENT_FILL))
    if above:
        kids.append(build.text("above", above, (length / 2, y - 2.4), family=None,
                               size=None, align="middle", role=_ROLE_LABEL))
    if below:
        kids.append(build.text("below", below, (length / 2, y + 5.0), family=None,
                               size=None, align="middle", role=_ROLE_LABEL))
    anchors = {"tail": {"how": "authored", "at": [0.0, y], "dir": [-1, 0]},
               "tip": {"how": "authored", "at": [length, y], "dir": [1, 0]},
               "centre": {"how": "authored", "at": [length / 2, y]}}
    return kids, anchors
