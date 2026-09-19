"""Data to graphics: §3.8. Scales, axes, marks and the annotations a panel needs.

**Done when a publication panel can be produced from a data file and remain correct, and
restyleable, after the data is revised.** Two halves, and the second is the one that is
usually missing: a plot here is ordinary scene elements drawn with style ROLES, so it obeys
whatever guide the figure is under and every measurement tool works on it.

A scale is an explicit object -- domain in, range out, ticks on request -- because the thing
that goes wrong in hand-built figures is an axis whose ticks and whose data disagree about
what the domain was. Everything drawn goes through the same scale that drew the axis.

Data binding records the source and its SHA-256 on the plot group, so §4's "regenerates when
the data changes" is a question the figure can answer about itself.
"""
import hashlib
import math
import os

from . import build, model

__all__ = ["Scale", "linear", "log", "categorical", "axis", "points", "line", "area",
           "bars", "band", "errorbars", "boxes", "histogram", "reference", "legend",
           "significance", "fit", "source_digest", "nice_ticks"]

_AXIS = "structure-stroke"
_GRID = "guide-line"
_LABEL = "caption"
_MARK = "accent-fill"
_MARK_LINE = "accent-stroke"


# --------------------------------------------------------------------- scales
class Scale:
    """A mapping from a data domain to a drawing range, with its own ticks.

    **The range's ORDER is its direction, and there is no flag.** ``linear((0, 100),
    (57, 6))`` puts 0 at y=57 and 100 at y=6, which is how a y axis works on a screen whose
    y runs down. There was a `flip` argument as well, and having two ways to say the same
    thing meant they could contradict each other: the first real plot drawn with it put zero
    at the top of the panel and its significance bracket at the bottom, silently, because
    the range was given bottom-first *and* flipped. One way to say it cannot disagree with
    itself.
    """

    def __init__(self, kind, domain, range_, base=10.0, padding=0.1):
        self.kind = kind
        self.domain = tuple(domain) if kind != "categorical" else list(domain)
        self.range = tuple(float(r) for r in range_)
        self.base = base
        self.padding = padding
        if kind == "log":
            if min(self.domain) <= 0:
                raise ValueError(
                    f"a log scale needs a positive domain; got {self.domain}. Clamping "
                    f"silently would draw zero somewhere finite and no reader would know.")

    def _r(self, t):
        lo, hi = self.range
        return lo + (hi - lo) * t

    def map(self, v):
        """One data value into the drawing range."""
        if self.kind == "categorical":
            try:
                i = self.domain.index(v)
            except ValueError:
                raise KeyError(
                    f"{v!r} is not in this scale's domain "
                    f"({', '.join(map(str, self.domain[:6]))}"
                    f"{'...' if len(self.domain) > 6 else ''}); a categorical scale will "
                    f"not invent a position for a category it was not given")
            n = len(self.domain)
            step = 1.0 / n
            return self._r(step * (i + 0.5))
        lo, hi = float(self.domain[0]), float(self.domain[1])
        if self.kind == "log":
            lo, hi = math.log(lo, self.base), math.log(hi, self.base)
            v = math.log(float(v), self.base)
        if hi == lo:
            return self._r(0.5)
        return self._r((float(v) - lo) / (hi - lo))

    def band(self):
        """The width of one categorical band, minus padding. Zero for continuous scales."""
        if self.kind != "categorical":
            return 0.0
        span = abs(self.range[1] - self.range[0])
        return span / max(1, len(self.domain)) * (1.0 - self.padding)

    def ticks(self, n=5):
        """``[(value, position, label)]`` -- the ticks, already placed."""
        if self.kind == "categorical":
            return [(v, self.map(v), str(v)) for v in self.domain]
        lo, hi = float(self.domain[0]), float(self.domain[1])
        if self.kind == "log":
            out = []
            e0 = int(math.floor(math.log(lo, self.base)))
            e1 = int(math.ceil(math.log(hi, self.base)))
            for e in range(e0, e1 + 1):
                v = self.base ** e
                if lo - 1e-12 <= v <= hi + 1e-12:
                    out.append((v, self.map(v), _tidy(v)))
            return out
        return [(v, self.map(v), _tidy(v)) for v in nice_ticks(lo, hi, n)]

    def __repr__(self):
        return f"Scale({self.kind}, {self.domain}, {self.range})"


def _tidy(v):
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:g}"


def nice_ticks(lo, hi, n=5):
    """Round tick values covering [lo, hi], at a 1/2/5 step. Deterministic."""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mag * mult:
            step = mag * mult
            break
    else:
        step = mag * 10
    start = math.ceil(lo / step) * step
    out, v = [], start
    while v <= hi + step * 1e-9:
        out.append(round(v, 12))
        v += step
    return out or [lo, hi]


def linear(domain, range_):
    """A linear scale. ``range_`` maps domain-first to range-first, so its order is up/down."""
    return Scale("linear", domain, range_)


def log(domain, range_, base=10.0):
    return Scale("log", domain, range_, base=base)


def categorical(domain, range_, padding=0.25):
    return Scale("categorical", domain, range_, padding=padding)


# --------------------------------------------------------------------- axes
def axis(scale, at, orientation="bottom", ticks=5, label=None, tick_length=1.6,
         grid=None, name="axis"):
    """An axis with ticks, tick labels and an optional label. Returns an element group.

    `at` is the position on the OTHER axis: for a bottom axis, the y it sits at. `grid` is
    the far end of a gridline, or None for no grid.
    """
    kids = []
    vertical = orientation in ("left", "right")
    lo, hi = min(scale.range), max(scale.range)
    if vertical:
        kids.append(build.line("spine", (at, lo), (at, hi), role=_AXIS))
    else:
        kids.append(build.line("spine", (lo, at), (hi, at), role=_AXIS))
    sign = -1 if orientation in ("bottom", "right") else 1
    if orientation == "bottom":
        sign = 1
    elif orientation == "top":
        sign = -1
    elif orientation == "left":
        sign = -1
    else:
        sign = 1

    for i, (_v, pos, text) in enumerate(scale.ticks(ticks), 1):
        if vertical:
            kids.append(build.line(f"tick-{i:02d}", (at, pos),
                                   (at + sign * tick_length, pos), role=_AXIS))
            if grid is not None:
                kids.append(build.line(f"grid-{i:02d}", (at, pos), (grid, pos),
                                       role=_GRID))
            kids.append(build.text(f"tick-{i:02d}-label", text,
                                   (at + sign * (tick_length + 1.0), pos + 0.8),
                                   family=None, size=None,
                                   align="end" if sign < 0 else "start", role=_LABEL))
        else:
            kids.append(build.line(f"tick-{i:02d}", (pos, at),
                                   (pos, at + sign * tick_length), role=_AXIS))
            if grid is not None:
                kids.append(build.line(f"grid-{i:02d}", (pos, at), (pos, grid),
                                       role=_GRID))
            kids.append(build.text(f"tick-{i:02d}-label", text,
                                   (pos, at + sign * (tick_length + 3.0)),
                                   family=None, size=None, align="middle", role=_LABEL))
    if label:
        mid = (lo + hi) / 2
        if vertical:
            kids.append(build.text("label", label,
                                   (at + sign * (tick_length + 9.0), mid), family=None,
                                   size=None, align="middle", role=_LABEL,
                                   transform=None))
            kids[-1]["transform"] = _rotate(-90, at + sign * (tick_length + 9.0), mid)
        else:
            kids.append(build.text("label", label, (mid, at + sign * (tick_length + 8.0)),
                                   family=None, size=None, align="middle", role=_LABEL))
    g = build.group(name, kids)
    g["tags"] = ["axis"]
    g["anchors"] = {"start": {"how": "authored",
                              "at": [at, lo] if vertical else [lo, at]},
                    "end": {"how": "authored",
                            "at": [at, hi] if vertical else [hi, at]}}
    return g


def _rotate(deg, cx, cy):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return model.compose([1, 0, 0, 1, cx, cy],
                         model.compose([c, s, -s, c, 0, 0], [1, 0, 0, 1, -cx, -cy]))


# --------------------------------------------------------------------- marks
def points(xs, ys, sx, sy, radius=0.9, name="points", role=_MARK):
    """A scatter of circles."""
    kids = [build.circle(f"p-{i:03d}", sx.map(x), sy.map(y), radius, role=role)
            for i, (x, y) in enumerate(zip(xs, ys), 1)]
    return build.group(name, kids, tags=["mark"])


def line(xs, ys, sx, sy, name="line", role=_MARK_LINE, smooth=False):
    """A line through the points, in the order given."""
    pts = [(sx.map(x), sy.map(y)) for x, y in zip(xs, ys)]
    if len(pts) < 2:
        raise ValueError("a line needs at least two points")
    el = (build.through("path", pts, tension=0.4, role=role) if smooth
          else build.polyline("path", pts, role=role))
    return build.group(name, [el], tags=["mark"])


def area(xs, ys, sx, sy, baseline=None, name="area", role="surface-fill"):
    """A filled area between the series and a baseline."""
    base = sy.map(baseline if baseline is not None else min(sy.domain))
    pts = [(sx.map(x), sy.map(y)) for x, y in zip(xs, ys)]
    loop = [["M", pts[0][0], base]] + [["L", p[0], p[1]] for p in pts] + \
           [["L", pts[-1][0], base], ["Z"]]
    return build.group(name, [build.region("fill", [loop], role=role)], tags=["mark"])


def bars(cats, values, sx, sy, baseline=0.0, name="bars", role=_MARK, radius=0.0):
    """One bar per category, on a categorical scale."""
    w = sx.band()
    base = sy.map(baseline)
    kids = []
    for i, (c, v) in enumerate(zip(cats, values), 1):
        cx = sx.map(c)
        top = sy.map(v)
        y0, y1 = min(top, base), max(top, base)
        kids.append(build.rect(f"bar-{i:02d}", cx - w / 2, y0, w, max(y1 - y0, 1e-6),
                               radius, role=role))
    return build.group(name, kids, tags=["mark"])


def band(xs, los, his, sx, sy, name="band", role="surface-fill"):
    """A confidence band: the region between two series."""
    top = [(sx.map(x), sy.map(v)) for x, v in zip(xs, his)]
    bot = [(sx.map(x), sy.map(v)) for x, v in zip(reversed(list(xs)),
                                                  reversed(list(los)))]
    loop = [["M", top[0][0], top[0][1]]] + [["L", p[0], p[1]] for p in top[1:] + bot] + \
           [["Z"]]
    return build.group(name, [build.region("fill", [loop], role=role)], tags=["mark"])


def errorbars(xs, ys, errs, sx, sy, cap=1.2, name="errors", role=_AXIS, horizontal=False):
    """Error bars with caps. `errs` is a half-width, or ``(low, high)`` pairs."""
    kids = []
    for i, (x, y, e) in enumerate(zip(xs, ys, errs), 1):
        lo, hi = (e, e) if isinstance(e, (int, float)) else (e[0], e[1])
        if horizontal:
            a, b = sx.map(x - lo), sx.map(x + hi)
            yy = sy.map(y)
            kids.append(build.line(f"e-{i:02d}", (a, yy), (b, yy), role=role))
            kids.append(build.line(f"e-{i:02d}-a", (a, yy - cap / 2), (a, yy + cap / 2),
                                   role=role))
            kids.append(build.line(f"e-{i:02d}-b", (b, yy - cap / 2), (b, yy + cap / 2),
                                   role=role))
        else:
            a, b = sy.map(y - lo), sy.map(y + hi)
            xx = sx.map(x)
            kids.append(build.line(f"e-{i:02d}", (xx, a), (xx, b), role=role))
            kids.append(build.line(f"e-{i:02d}-a", (xx - cap / 2, a), (xx + cap / 2, a),
                                   role=role))
            kids.append(build.line(f"e-{i:02d}-b", (xx - cap / 2, b), (xx + cap / 2, b),
                                   role=role))
    return build.group(name, kids, tags=["mark"])


def boxes(cats, stats, sx, sy, name="boxes", role="surface-fill", line_role=_AXIS):
    """Box plots. `stats` is ``(min, q1, median, q3, max)`` per category."""
    w = sx.band()
    kids = []
    for i, (c, s) in enumerate(zip(cats, stats), 1):
        lo, q1, med, q3, hi = s
        cx = sx.map(c)
        ylo, yq1, ymed, yq3, yhi = (sy.map(v) for v in (lo, q1, med, q3, hi))
        kids.append(build.line(f"whisker-{i:02d}", (cx, ylo), (cx, yhi), role=line_role))
        kids.append(build.line(f"cap-{i:02d}-lo", (cx - w / 4, ylo), (cx + w / 4, ylo),
                               role=line_role))
        kids.append(build.line(f"cap-{i:02d}-hi", (cx - w / 4, yhi), (cx + w / 4, yhi),
                               role=line_role))
        top, bot = min(yq1, yq3), max(yq1, yq3)
        kids.append(build.rect(f"box-{i:02d}", cx - w / 2, top, w, bot - top, role=role))
        kids.append(build.line(f"median-{i:02d}", (cx - w / 2, ymed), (cx + w / 2, ymed),
                               role=line_role))
    return build.group(name, kids, tags=["mark"])


def histogram(values, sx, sy, bins=10, name="histogram", role=_MARK):
    """A histogram of `values`, binned over the x scale's domain. Returns ``(group, counts)``."""
    lo, hi = float(sx.domain[0]), float(sx.domain[1])
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        if v < lo or v > hi:
            continue
        k = min(bins - 1, int((v - lo) / width))
        counts[k] += 1
    kids = []
    base = sy.map(0)
    for i, c in enumerate(counts, 1):
        x0, x1 = sx.map(lo + width * (i - 1)), sx.map(lo + width * i)
        top = sy.map(c)
        y0, y1 = min(top, base), max(top, base)
        kids.append(build.rect(f"bin-{i:02d}", min(x0, x1), y0, abs(x1 - x0),
                               max(y1 - y0, 1e-6), role=role))
    return build.group(name, kids, tags=["mark"]), counts


def reference(value, scale, other, orientation="horizontal", label=None,
              name="reference", role=_GRID):
    """A reference line across the plot, with an optional label at its end."""
    pos = scale.map(value)
    lo, hi = min(other), max(other)
    if orientation == "horizontal":
        el = build.line("line", (lo, pos), (hi, pos), role=role)
        at = (hi, pos - 1.0)
    else:
        el = build.line("line", (pos, lo), (pos, hi), role=role)
        at = (pos, lo - 1.0)
    kids = [el]
    if label:
        kids.append(build.text("label", label, at, family=None, size=None, align="end",
                               role=_LABEL))
    return build.group(name, kids, tags=["annotation"])


def significance(a, b, y, scale, label="*", drop=1.6, name="significance", role=_AXIS):
    """A significance bracket between two categories, with its label above."""
    xa, xb = scale.map(a), scale.map(b)
    kids = [build.polyline("bracket", [(xa, y + drop), (xa, y), (xb, y), (xb, y + drop)],
                           role=role),
            build.text("label", label, ((xa + xb) / 2, y - 1.0), family=None, size=None,
                       align="middle", role=_LABEL)]
    return build.group(name, kids, tags=["annotation"])


def fit(xs, ys, sx, sy, name="fit", role=_MARK_LINE, band_role="surface-fill",
        confidence=True):
    """A least-squares line with an optional confidence band. Returns ``(group, stats)``.

    The statistics come back with the drawing -- slope, intercept, r squared, n -- because a
    fitted line whose numbers live only in the picture is a number nobody can check.
    """
    xs = [float(x) for x in xs]
    ys = [float(y) for y in ys]
    n = len(xs)
    if n < 3:
        raise ValueError(f"a fit needs at least three points, got {n}")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("every x is the same; there is no line to fit")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    ss_res = sum(r * r for r in resid)
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    se = math.sqrt(ss_res / (n - 2)) if n > 2 else 0.0

    lo, hi = min(xs), max(xs)
    steps = 24
    grid = [lo + (hi - lo) * i / steps for i in range(steps + 1)]
    kids = []
    clamped = 0
    if confidence and se:
        t = 2.0                                   # ~95% for moderate n; stated, not exact
        # CLAMPED TO THE Y SCALE'S DOMAIN, and counted. A band on data the line does not
        # describe well runs off the top and bottom of the panel, over the tick labels --
        # which `figure.verify` reports, correctly, as a label with ink through it. There is
        # no clipping in the scene format, so the honest thing is to keep the band inside
        # the axes and SAY how many of its points were held there: a band silently trimmed
        # is a confidence interval drawn narrower than it is.
        ylo, yhi = min(float(v) for v in sy.domain), max(float(v) for v in sy.domain)
        los, his = [], []
        for x in grid:
            half = t * se * math.sqrt(1.0 / n + (x - mx) ** 2 / sxx)
            a_, b_ = slope * x + intercept - half, slope * x + intercept + half
            if a_ < ylo or b_ > yhi:
                clamped += 1
            los.append(min(max(a_, ylo), yhi))
            his.append(min(max(b_, ylo), yhi))
        kids.append(band(grid, los, his, sx, sy, name="band", role=band_role)
                    ["children"][0])
    kids.append(build.line("line", (sx.map(lo), sy.map(slope * lo + intercept)),
                           (sx.map(hi), sy.map(slope * hi + intercept)), role=role))
    g = build.group(name, kids, tags=["annotation"])
    return g, {"slope": slope, "intercept": intercept, "r2": r2, "n": n,
               "residual_se": se, "band_clamped": clamped,
               "confidence": "t=2 approximation of 95%" if confidence else None}


def legend(entries, at, name="legend", swatch=3.2, leading=5.0, role=_LABEL,
           width=None, backing="paper-fill", pad=1.2):
    """A legend: ``[(label, role)]`` as swatches with labels beside them, on a backing plate.

    **The plate is not decoration.** A legend sits inside the plot area, over gridlines, and
    text with a rule running through it is text a reader has to work at. `figure.verify`
    reports exactly that, and it reported it on the first legend this module drew. Pass
    ``backing=None`` to leave it off deliberately.
    """
    kids = []
    if backing:
        w = width if width is not None else swatch + 1.6 + 22.0
        h = leading * max(1, len(entries)) + pad
        kids.append(build.rect("plate", at[0] - pad, at[1] - pad, w + 2 * pad, h + pad,
                               radius=0.8, role=backing))
    for i, (label, r) in enumerate(entries):
        y = at[1] + i * leading
        kids.append(build.rect(f"swatch-{i + 1}", at[0], y, swatch, swatch, radius=0.5,
                               role=r))
        kids.append(build.text(f"label-{i + 1}", label,
                               (at[0] + swatch + 1.6, y + swatch * 0.85), family=None,
                               size=None, role=role))
    g = build.group(name, kids, tags=["legend"])
    g["anchors"] = {"top-left": {"how": "authored", "at": [at[0], at[1]]}}
    return g


# --------------------------------------------------------------------- binding
def source_digest(path):
    """``(sha256, bytes)`` for a data file, or None if it cannot be read.

    What a plot group records so that "regenerate when the data changes" is a question the
    figure can answer about itself rather than something a person has to remember.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        return hashlib.sha256(data).hexdigest(), len(data)
    except OSError:
        return None


def bind(group, path, rows=None, columns=None, note=None):
    """Record on a plot group where its numbers came from. Returns the group."""
    prov = {"origin": "data", "source": path, "tool": "lineart.data",
            "tool_version": "1"}
    got = source_digest(path)
    if got:
        prov["sha256"] = got[0]
    params = {}
    if rows is not None:
        params["rows"] = int(rows)
    if columns:
        params["columns"] = list(columns)
    if note:
        params["note"] = note
    if params:
        prov["params"] = params
    group["provenance"] = prov
    return group


# --------------------------------------------------------------------- whole panels
def read_table(path):
    """A CSV or TSV as ``(columns, rows)`` with numbers parsed where they parse.

    Deliberately small. A figure toolkit that grows a dataframe library has stopped being a
    figure toolkit; anything more than this belongs upstream, in whatever produced the file.
    """
    import csv
    delim = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter=delim)
        rows = [r for r in reader if r]
    if not rows:
        raise ValueError(f"{path} has no rows")
    head = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        rec = {}
        for i, h in enumerate(head):
            v = r[i].strip() if i < len(r) else ""
            try:
                rec[h] = float(v) if v not in ("", "NA", "NaN", "nan") else None
            except ValueError:
                rec[h] = v
        out.append(rec)
    return head, out


def plot(name, x, y, width, height, kind="scatter", x_scale=None, y_scale=None,
         xlabel=None, ylabel=None, title=None, errors=None, ticks=5, grid=True,
         source=None, fit_line=False, categories=None):
    """A whole plot panel: axes, grid, marks and labels, in one group at (0, 0).

    Returns ``(group, report)``; the report carries the scales and, when `fit_line` is
    asked for, the regression's numbers. Plot coordinates run from (0, 0) at the top-left of
    the panel, like everything else in a scene, and the axes are placed inside it.
    """
    pad_l, pad_b, pad_t, pad_r = 14.0, 13.0, 6.0, 4.0
    x0, x1 = pad_l, width - pad_r
    y0, y1 = height - pad_b, pad_t

    if kind in ("bar", "box"):
        cats = list(categories if categories is not None else x)
        sx = x_scale or categorical(cats, (x0, x1))
    else:
        sx = x_scale or linear((min(x), max(x)), (x0, x1))
    flat = [v for v in y if v is not None] if kind != "box" else \
        [v for s in y for v in s]
    if errors:
        for v, e in zip(y, errors):
            half = e if isinstance(e, (int, float)) else max(e)
            flat += [v - half, v + half]
    sy = y_scale or linear((min(flat + [0.0]), max(flat)), (y0, y1))

    kids = [axis(sx, y0, "bottom", ticks, xlabel, grid=(y1 if grid else None),
                 name="x-axis"),
            axis(sy, x0, "left", ticks, ylabel, grid=(x1 if grid else None),
                 name="y-axis")]
    report = {"x": repr(sx), "y": repr(sy), "kind": kind}

    if kind == "scatter":
        kids.append(points(x, y, sx, sy))
    elif kind == "line":
        kids.append(line(x, y, sx, sy))
    elif kind == "area":
        kids.append(area(x, y, sx, sy))
    elif kind == "bar":
        kids.append(bars(cats, y, sx, sy))
    elif kind == "box":
        kids.append(boxes(cats, y, sx, sy))
    else:
        raise ValueError(f"no plot kind called {kind!r}; known: scatter, line, area, "
                         f"bar, box")
    if errors:
        kids.append(errorbars(x, y, errors, sx, sy))
    if fit_line and kind in ("scatter", "line"):
        g, stats = fit(x, y, sx, sy)
        kids.insert(2, g)
        report["fit"] = stats
    if title:
        kids.append(build.text("title", title, (width / 2, pad_t - 1.5), family=None,
                               size=None, align="middle", role=_LABEL))

    group = build.group(name, kids, tags=["plot"])
    group["anchors"] = {
        "origin": {"how": "authored", "at": [x0, y0]},
        "top-left": {"how": "authored", "at": [0.0, 0.0]},
        "plot-area": {"how": "authored", "at": [(x0 + x1) / 2, (y0 + y1) / 2]},
    }
    if source:
        bind(group, source, rows=len(x))
    report["scales"] = {"x": sx, "y": sy}
    return group, report
