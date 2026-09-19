"""Text that fits, or says why it does not. §3.4.

**Done when no label ever overflows, overlaps, or silently changes metrics between preview
and export.** The mechanism is that nothing here guesses: every width comes from
:mod:`lineart_trace.scene.fonts`, measured out of the font file, and a string that will not
fit in the box it was given comes back as a refusal carrying the numbers -- what was asked,
what it needs, by how much it is over.

Three ways to fit, and the caller says which:

``wrap``    break at spaces and use as many lines as it takes, failing if the box is too
            short or a single word is too wide
``shrink``  keep it on the requested number of lines and reduce the size until it fits,
            never below `min_size`
``strict``  do neither; either it fits as written or it is a refusal

The y axis runs DOWN, as it does in SVG and in the pixels every traced scene comes from, so
a baseline sits `ascent` below the top of its line. A frame that wants y up says so with its
own transform -- ``[1, 0, 0, -1, 0, h]`` -- rather than with a flag here.
"""
from . import build, fonts, model

__all__ = ["fit", "block", "TooBig", "as_unit"]


def as_unit(size, unit):
    """A type size as a number in `unit`. A bare number is already in it; ``"7pt"`` is not.

    **The scene format's rule, applied here because the alternative bit immediately.** A box
    in millimetres and a size written as a bare 7 means seven MILLIMETRES of type -- about
    20 pt -- and the failure is not an exception, it is a caption that wraps to three lines
    and reports that it does not fit. Found by the demo, at the first real label.
    """
    if not isinstance(size, str):
        return float(size)
    return model.to_unit(*_split_length(size), unit)


def _split_length(s):
    import re
    m = re.match(r"^(-?\d+(?:\.\d+)?)(mm|pt|px|in)$", s)
    if not m:
        raise ValueError(f"not a length: {s!r} -- a bare number, or a number with "
                         f"mm/pt/px/in")
    return float(m.group(1)), m.group(2)


class TooBig(Exception):
    """Text that will not fit, carrying the measurements that say so.

    An exception rather than a silently clipped string, because §4 is explicit about it:
    a label that will not fit is reported, never absorbed.
    """

    def __init__(self, message, detail):
        super().__init__(message)
        self.detail = detail


def _words(string):
    out, cur = [], ""
    for ch in string:
        if ch == " ":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [w for w in out if w != ""] or [""]


def _wrap(string, width, family, size, weight, style):
    """Greedy word wrap on measured advances. Returns ``(lines, widest, overflowing word)``."""
    lines, cur = [], ""
    widest = 0.0
    too_long = None
    for w in _words(string):
        trial = f"{cur} {w}" if cur else w
        adv = fonts.metrics(trial, family, size, weight, style)["advance"]
        if adv <= width or not cur:
            if adv > width and not cur:
                own = fonts.metrics(w, family, size, weight, style)["advance"]
                if own > width:
                    too_long = (w, own)
            cur = trial
            widest = max(widest, adv)
        else:
            lines.append(cur)
            widest = max(widest, fonts.metrics(cur, family, size, weight,
                                               style)["advance"])
            cur = w
            widest = max(widest, fonts.metrics(w, family, size, weight, style)["advance"])
    if cur:
        lines.append(cur)
    return lines, widest, too_long


def fit(string, width, height, family="Helvetica", size=10.0, mode="wrap", leading=1.2,
        min_size=4.0, weight="regular", style="normal", unit="pt"):
    """Lay `string` out inside a `width` x `height` box. Raises `TooBig` when it cannot.

    `width`, `height` and the returned lengths are all in `unit`. `size` and `min_size` may
    be bare numbers in that unit, or strings carrying their own -- ``"7pt"`` is seven points
    of type however the box is measured, which is almost always what was meant.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"a text box needs a positive size, got {width}x{height}")
    trial = as_unit(size, unit)
    min_size = as_unit(min_size, unit)
    while True:
        m = fonts.metrics(string, family, trial, weight, style)
        line_h = m["line_height"] * (leading / 1.2) if leading else m["line_height"]
        if mode == "strict":
            lines, widest, too_long = [string], m["advance"], None
        else:
            lines, widest, too_long = _wrap(string, width, family, trial, weight, style)
        need_h = line_h * len(lines)
        ok = widest <= width + 1e-9 and need_h <= height + 1e-9 and too_long is None
        if ok:
            return {"lines": lines, "size": trial, "family": family, "weight": weight,
                    "style": style, "leading": leading, "line_height": line_h,
                    "width": widest, "height": need_h,
                    "ascent": m["ascent"], "descent": m["descent"],
                    "slack_width": width - widest, "slack_height": height - need_h,
                    "unit": unit, "font": m["font"],
                    "shrunk": abs(trial - as_unit(size, unit)) > 1e-9}
        if mode == "shrink" and trial > min_size:
            trial = max(min_size, trial - max(0.25, trial * 0.05))
            continue
        detail = {"string": string, "mode": mode, "family": family, "size": trial,
                  "box": {"width": width, "height": height},
                  "needs": {"width": widest, "height": need_h},
                  "over_width": max(0.0, widest - width),
                  "over_height": max(0.0, need_h - height),
                  "lines": len(lines), "min_size": min_size,
                  "font": m["font"]}
        if too_long:
            detail["unbreakable"] = {"word": too_long[0], "width": too_long[1]}
            raise TooBig(
                f"{string!r} will not fit in {width:g}x{height:g}: the word "
                f"{too_long[0]!r} alone is {too_long[1]:.3g} wide at {trial:g}. "
                f"Nothing here hyphenates -- breaking a word is a typographic decision, "
                f"not a fallback.", detail)
        why = []
        if widest > width:
            why.append(f"{widest - width:.3g} too wide")
        if need_h > height:
            why.append(f"{need_h - height:.3g} too tall ({len(lines)} lines)")
        raise TooBig(
            f"{string!r} will not fit in {width:g}x{height:g} at {trial:g}: "
            f"{' and '.join(why)}"
            + (f"; already at the {min_size:g} floor" if mode == "shrink" else ""), detail)


def block(name, string, x, y, width, height, family="Helvetica", size=10.0, mode="wrap",
          align="start", valign="top", leading=1.2, min_size=4.0, role=None, style=None,
          weight="regular", font_style="normal", unit="pt", doc=None):
    """A group of text elements, one per line, laid out inside the box. Raises `TooBig`.

    The box itself is not drawn. Its geometry is recorded on the group as the anchors
    `top-left`, `centre` and `bottom-right`, so whatever is placed against this label later
    attaches to the box that was reserved rather than to the ink that happened to land in it.

    **Give it `doc` with a `role` and it measures with the font the role supplies**, and
    writes no literal family or size. Without that it measures with the `family` and `size`
    passed here and writes them down -- which is a second source for the same fact: the block
    was laid out in one font and drawn in whatever the guide said, and the style lint
    reported the literals it had to write. Measuring with what will actually be drawn is the
    only version of this that cannot drift.
    """
    from_role = False
    if doc is not None and role:
        body = ((doc.get("style") or {}).get("roles") or {}).get(role) or {}
        if body.get("font_family") and body.get("font_size") is not None:
            family = body["font_family"]
            size = body["font_size"]
            from_role = True
    laid = fit(string, width, height, family, size, mode, leading, min_size, weight,
               font_style, unit)
    line_h = laid["line_height"]
    used = laid["height"]
    top = {"top": y, "middle": y + (height - used) / 2.0,
           "bottom": y + (height - used)}.get(valign, y)
    xs = {"start": x, "middle": x + width / 2.0, "end": x + width}
    kids = []
    for i, line in enumerate(laid["lines"]):
        baseline = top + line_h * i + laid["ascent"]
        kids.append(build.text(f"line-{i + 1:02d}", line, (xs.get(align, x), baseline),
                               family=None if from_role else family,
                               size=None if from_role else laid["size"], align=align,
                               role=role, style=style))
    g = build.group(name, kids)
    g["anchors"] = {
        "top-left": {"how": "authored", "at": [x, y]},
        "centre": {"how": "authored", "at": [x + width / 2.0, y + height / 2.0]},
        "bottom-right": {"how": "authored", "at": [x + width, y + height]},
    }
    g["tags"] = ["label"]
    laid["from_role"] = from_role
    return g, laid
