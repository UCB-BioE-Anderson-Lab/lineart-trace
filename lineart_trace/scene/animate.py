"""Animation and staged reveal: §3.12.

**Done when a lecture build and a looping explainer are both first-class, and any frame of
either can be exported as a static figure.** That last clause decides the design: a timeline
is a separate document that says how a SCENE changes, and :func:`at` returns *a scene* -- an
ordinary `lineart.scene/1` with the properties applied. Every tool in the toolkit then works
on any frame: measure it, check it at print size, draw an overlay of it, export it.

The alternative -- animation as something the exporter does on its way out -- would have made
frame 12 of a build unmeasurable and unverifiable, which is exactly the state §3.15 exists to
end for static figures.

**A stage is a timeline, not a different thing.** `stages` builds the tracks, so a lecture
build and a looping explainer share one mechanism and one exporter, and a still of stage 3 is
`at(t)` for the t that stage begins at.
"""
import copy
import math
import os

from . import model

__all__ = ["at", "still", "frames", "from_stages", "marks_of", "duration_of", "ease",
           "to_svg", "SCHEMA_PATH", "EASINGS", "PROPERTIES", "Incompatible"]

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "timeline.schema.json")

EASINGS = ("linear", "ease-in", "ease-out", "ease-in-out", "step")
PROPERTIES = ("opacity", "translate", "scale", "rotate", "draw", "stroke", "fill",
              "morph", "camera")


class Incompatible(Exception):
    """Two paths that cannot be morphed between. Named, never approximated."""


def ease(kind, u):
    """An easing curve on [0, 1]. `step` holds the start value until the very end."""
    u = max(0.0, min(1.0, float(u)))
    if kind == "ease-in":
        return u * u
    if kind == "ease-out":
        return 1.0 - (1.0 - u) ** 2
    if kind == "ease-in-out":
        return 2 * u * u if u < 0.5 else 1.0 - (-2 * u + 2) ** 2 / 2
    if kind == "step":
        return 0.0 if u < 1.0 else 1.0
    return u


def duration_of(tl):
    """The timeline's own duration, or the last key if it does not say."""
    if tl.get("duration"):
        return float(tl["duration"])
    return max((k["t"] for tr in tl.get("tracks", []) for k in tr["keys"]), default=0.0)


def marks_of(tl):
    """``{name: t}`` for the named marks, including one per stage."""
    return dict(sorted((tl.get("marks") or {}).items()))


# --------------------------------------------------------------------- sampling
def _interp(a, b, u):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * u
    if isinstance(a, str) and isinstance(b, str) and a.startswith("#"):
        return _mix(a, b, u)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            raise Incompatible(
                f"cannot interpolate between values of different lengths: {len(a)} and "
                f"{len(b)}")
        return [_interp(x, y, u) for x, y in zip(a, b)]
    return a if u < 1.0 else b


def _rgb(c):
    h = c[1:]
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, u):
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{int(round(x + (y - x) * u)):02x}" for x, y in zip(ra, rb))


def sample(track, t):
    """The value of one track at time `t`, with the track's easing applied."""
    keys = sorted(track["keys"], key=lambda k: k["t"])
    if not keys:
        return None
    if t <= keys[0]["t"]:
        return keys[0].get("value")
    if t >= keys[-1]["t"]:
        return keys[-1].get("value")
    for a, b in zip(keys, keys[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            u = 0.0 if span <= 0 else (t - a["t"]) / span
            kind = a.get("easing") or track.get("easing") or "linear"
            return _interp(a.get("value"), b.get("value"), ease(kind, u))
    return keys[-1].get("value")


# --------------------------------------------------------------------- applying
def at(doc, tl, t, drop_hidden=False):
    """The scene as it stands at time `t`. Returns an ordinary scene document.

    With `drop_hidden`, elements at zero opacity are REMOVED rather than drawn transparent.
    That is what a still of a lecture build wants -- a slide that has not revealed something
    yet does not contain it, so measuring the slide measures what is on it.
    """
    out = copy.deepcopy(doc)
    camera = None
    for track in tl.get("tracks", []):
        value = sample(track, float(t))
        if value is None:
            continue
        prop = track["property"]
        if prop == "camera":
            camera = value
            continue
        el = model.find(out, track["target"])
        if el is None:
            continue
        _apply(out, track["target"], el, prop, value)
    if camera:
        out.setdefault("canvas", {})
        out["canvas"]["viewbox"] = list(camera)
    if drop_hidden:
        for addr in [a for a, e, _p in model.walk(out)
                     if float((e.get("style") or {}).get("opacity", 1.0)) <= 1e-6]:
            if model.find(out, addr) is not None:
                out = model.remove(out, addr)
    return out


def _apply(doc, addr, el, prop, value):
    if prop == "opacity":
        el.setdefault("style", {})["opacity"] = max(0.0, min(1.0, float(value)))
    elif prop == "stroke":
        el.setdefault("style", {})["stroke"] = value
    elif prop == "fill":
        el.setdefault("style", {})["fill"] = value
    elif prop == "translate":
        el["transform"] = model.compose([1, 0, 0, 1, float(value[0]), float(value[1])],
                                        el.get("transform") or list(model.IDENTITY))
    elif prop == "scale":
        k = float(value) if isinstance(value, (int, float)) else float(value[0])
        ky = k if isinstance(value, (int, float)) else float(value[1])
        from . import measure
        box = measure.bbox(doc, addr, model.frame_of(doc, addr))["value"]
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        m = model.compose([1, 0, 0, 1, cx, cy],
                          model.compose([k, 0, 0, ky, 0, 0], [1, 0, 0, 1, -cx, -cy]))
        el["transform"] = model.compose(m, el.get("transform") or list(model.IDENTITY))
    elif prop == "rotate":
        from . import measure
        box = measure.bbox(doc, addr, model.frame_of(doc, addr))["value"]
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        a = math.radians(float(value))
        c, s = math.cos(a), math.sin(a)
        m = model.compose([1, 0, 0, 1, cx, cy],
                          model.compose([c, s, -s, c, 0, 0], [1, 0, 0, 1, -cx, -cy]))
        el["transform"] = model.compose(m, el.get("transform") or list(model.IDENTITY))
    elif prop == "draw":
        _draw_to(doc, addr, el, float(value))
    elif prop == "morph":
        _morph_to(el, value)


def _draw_to(doc, addr, el, fraction):
    """Trim every path beneath `addr` to a fraction of its length: the draw-on reveal.

    Real geometry, not a dash-offset trick, so a half-drawn stroke MEASURES as half drawn.
    An animation whose frames cannot be measured is the thing this module exists not to be.
    """
    from . import geometry, measure
    fraction = max(0.0, min(1.0, fraction))
    for a, e in measure._subtree(doc, addr):
        g = e.get("geometry") or {}
        if g.get("kind") != "path":
            continue
        run = g.get("d") or []
        cs = geometry.to_cubics(run)
        if not cs:
            continue
        if fraction >= 1.0:
            continue
        lens = [geometry._cubic_length(*c) for c in cs]
        total = sum(lens)
        if total <= 0:
            continue
        want = total * fraction
        kept, acc = [], 0.0
        for c, l in zip(cs, lens):
            if acc + l <= want or l == 0:
                kept.append(c)
                acc += l
                continue
            u = (want - acc) / l
            left, _right = geometry._split(*c, u)
            if u > 1e-9:
                kept.append(left)
            break
        if not kept:
            p0 = cs[0][0]
            g["d"] = [["M", p0[0], p0[1]]]
            g.pop("closed", None)
            continue
        segs = [["M", kept[0][0][0], kept[0][0][1]]]
        for c in kept:
            segs.append(["C", c[1][0], c[1][1], c[2][0], c[2][1], c[3][0], c[3][1]])
        g["d"] = segs
        g.pop("closed", None)


def _morph_to(el, value):
    g = el.get("geometry") or {}
    if g.get("kind") != "path":
        raise Incompatible(f"only a path can morph; this is a {g.get('kind')!r}")
    g["d"] = [list(seg) for seg in value]


def morph_track(target, a_run, b_run, t0, t1, easing="ease-in-out", steps=12):
    """A morph track between two path runs, or a refusal naming why they cannot morph.

    Two paths morph when they have the same verbs in the same order. Resampling one to match
    the other is possible and is not done here: a morph between shapes that do not correspond
    is an animation that looks like a mistake, and guessing the correspondence is exactly the
    kind of confident guess this toolkit refuses elsewhere.
    """
    va = [s[0] for s in a_run]
    vb = [s[0] for s in b_run]
    if va != vb:
        raise Incompatible(
            f"these paths have different structures, so there is no correspondence to "
            f"morph along: {''.join(va)} against {''.join(vb)}. Make them the same shape of "
            f"path first -- nothing here will guess which point becomes which.")
    keys = []
    for i in range(steps + 1):
        u = i / steps
        blended = []
        for sa, sb in zip(a_run, b_run):
            blended.append([sa[0]] + [x + (y - x) * u for x, y in zip(sa[1:], sb[1:])])
        keys.append({"t": t0 + (t1 - t0) * u, "value": blended})
    return {"target": target, "property": "morph", "easing": easing, "keys": keys}


# --------------------------------------------------------------------- stages
def from_stages(name, stages, rise=0.4, hold=1.0, loop=False, scene=None):
    """A timeline from a staged build. Returns a `lineart.timeline/1` document.

    Each stage reveals what it names and hides what it hides, over `rise` seconds, then holds.
    Every stage gets a **mark** at the moment it begins, so a still of any stage is `at` that
    mark -- which is what makes "export any step as a still" a one-liner rather than a
    separate export path.
    """
    tracks, marks, t = {}, {}, 0.0
    revealed = set()
    for st in stages:
        r = float(st.get("rise", rise))
        h = float(st.get("hold", hold))
        marks[st["name"]] = round(t, 6)
        for addr in st.get("reveal", []):
            tr = tracks.setdefault((addr, "opacity"),
                                   {"target": addr, "property": "opacity",
                                    "easing": "ease-out",
                                    "keys": [{"t": 0.0, "value": 0.0}]})
            tr["keys"].append({"t": round(t, 6), "value": 0.0})
            tr["keys"].append({"t": round(t + r, 6), "value": 1.0})
            revealed.add(addr)
        for addr in st.get("hide", []):
            tr = tracks.setdefault((addr, "opacity"),
                                   {"target": addr, "property": "opacity",
                                    "easing": "ease-out",
                                    "keys": [{"t": 0.0, "value": 1.0}]})
            tr["keys"].append({"t": round(t, 6), "value": 1.0})
            tr["keys"].append({"t": round(t + r, 6), "value": 0.0})
        t += r + h
    out = {"format": "lineart.timeline/1", "name": name, "duration": round(t, 6),
           "loop": bool(loop), "marks": marks,
           "stages": [dict(s) for s in stages],
           "tracks": [tracks[k] for k in sorted(tracks)]}
    if scene:
        out["scene"] = scene
    return out


def still(doc, tl, stage, drop_hidden=True):
    """The scene at a named stage or mark. Raises KeyError naming the marks there are."""
    marks = marks_of(tl)
    if stage not in marks:
        raise KeyError(f"no mark or stage called {stage!r}; this timeline has "
                       f"{', '.join(marks) or 'none'}")
    # A STAGE'S STILL IS TAKEN AFTER ITS RISE, not at the instant it begins -- at the mark
    # itself the thing being revealed is still at zero opacity, so a still of stage 3 would
    # show stage 2.
    rise = 0.0
    for st in tl.get("stages", []):
        if st["name"] == stage:
            rise = float(st.get("rise", 0.4))
            break
    return at(doc, tl, marks[stage] + rise, drop_hidden=drop_hidden)


def frames(doc, tl, n=24, drop_hidden=False):
    """`n` evenly spaced scenes over the timeline. Returns ``[(t, scene)]``."""
    d = duration_of(tl)
    return [(round(d * i / max(1, n - 1), 6),
             at(doc, tl, d * i / max(1, n - 1), drop_hidden))
            for i in range(n)]


# --------------------------------------------------------------------- export
_SMIL = {"opacity": "opacity", "stroke": "stroke", "fill": "fill"}


def to_svg(doc, tl, places=3, background=None):
    """One self-contained animated SVG, using SMIL. Returns markup.

    Only the properties SMIL can carry directly -- opacity, stroke, fill -- are animated in
    the file; `draw`, `morph`, `scale`, `rotate` and `camera` change geometry or the document
    itself and are exported as frames instead. **The file says which**, in a comment, rather
    than quietly dropping them: an explainer that silently lost its draw-on is worse than one
    that refuses to pretend.
    """
    from . import svg
    base = svg.render(doc, standalone=True, places=places, background=background)
    dur = duration_of(tl)
    repeat = "indefinite" if tl.get("loop") else "1"
    lines, unsupported = [], []
    for track in tl.get("tracks", []):
        prop = track["property"]
        if prop not in _SMIL:
            unsupported.append(f"{track['target']}:{prop}")
            continue
        keys = sorted(track["keys"], key=lambda k: k["t"])
        if len(keys) < 2 or dur <= 0:
            continue
        times = ";".join(f"{k['t'] / dur:.6g}" for k in keys)
        values = ";".join(str(k.get("value")) for k in keys)
        lines.append(
            f'  <animate xlink:href="#{track["target"]}" attributeName="{_SMIL[prop]}" '
            f'values="{values}" keyTimes="{times}" dur="{dur:g}s" '
            f'repeatCount="{repeat}" fill="freeze"/>')
    note = ""
    if unsupported:
        note = ("  <!-- not animated in this file (geometry or document changes, which "
                "SMIL cannot carry): " + ", ".join(sorted(unsupported)) +
                ". Export these as frames. -->\n")
    if not lines and not note:
        return base
    body = note + "\n".join(lines) + ("\n" if lines else "")
    out = base.replace("</svg>", body + "</svg>")
    if "xmlns:xlink" not in out:
        out = out.replace("<svg xmlns=", '<svg xmlns:xlink="http://www.w3.org/1999/xlink" '
                          "xmlns=", 1)
    return out
