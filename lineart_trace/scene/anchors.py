"""Anchors and relations: §3.5, where editing one thing updates everything attached to it.

**Done when editing one element updates everything attached to it, and an unsatisfiable
layout is an explicit error rather than a silent overlap.** Both halves matter, and the
second is the one systems get wrong: a constraint solver that quietly settles for the
nearest thing it can reach produces a figure that is wrong in a way nobody is told about.
:func:`solve` reports every relation it could not satisfy, by name, with the distance it
fell short.

**Three kinds of anchor**, as §2 sets out.

``authored``    a point somebody chose; stored and never recomputed
``derived``     a recipe over the element's own geometry -- ``bbox.ne``, ``centroid``,
                ``path.mid``, ``extreme.top``
``discovered``  found by looking at the shape: ``concavity`` is the deepest inlet of a
                silhouette, which is what turns "seat the duplex in the entry channel" into
                a declaration

A derived or discovered anchor stores BOTH its recipe and its resolved position. The recipe
is what makes it reproducible; the stored position is what lets a §3.15 view render the
scene without recomputing anything. :func:`resolve` refreshes the positions; nothing else
writes them.

**Relations translate, and only translate.** An `attach` moves an element so that one of its
anchors lands on a target point; an `align` moves it so an edge or centre matches; `clear`
pushes it away until a gap is met; `inside` pulls it back within a box. None of them rotate
or scale, because a relation that could scale would silently change a stroke weight, and
because translation is the whole of what §3.5's verbs actually ask for.
"""
import math

from . import geometry, model

__all__ = ["derive", "resolve", "solve", "RECIPES", "KINDS"]

#: The `by` recipes a derived anchor may name.
RECIPES = ("bbox.nw", "bbox.n", "bbox.ne", "bbox.e", "bbox.se", "bbox.s", "bbox.sw",
           "bbox.w", "bbox.centre", "centroid", "path.start", "path.mid", "path.end",
           "extreme.top", "extreme.bottom", "extreme.left", "extreme.right", "concavity")

#: The relation kinds :func:`solve` understands.
KINDS = ("attach", "align", "clear", "inside")

#: The `align` edges. The first six match an edge to the SAME edge; the last four match one
#: edge to the OPPOSITE one, which is what "put this below that" means and what nothing here
#: could say. A caption that has to sit under the last panel, on a page whose panel grid may
#: be re-laid, cannot be positioned any other way without naming a coordinate.
_EDGES = ("left", "right", "top", "bottom", "centre-x", "centre-y",
          "below", "above", "left-of", "right-of")


def _own_runs(doc, address, silhouette=False):
    """Every run beneath `address`, in that element's own PRE-TRANSFORM coordinates.

    That is the space an anchor's `at` is written in. Deriving from post-transform geometry
    and storing the result in that field applies the transform twice, which does not look
    like a bug -- it looks like a label that drifts a little further from its target every
    time the scene is solved.
    """
    from . import measure
    return measure.runs_in_local(doc, address, skip_text=silhouette)


def _hull(points):
    """Andrew's monotone chain. Returns the hull counter-clockwise."""
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) > 0:
                    break
                out.pop()
            out.append(p)
        return out

    return half(pts)[:-1] + half(reversed(pts))[:-1]


def _deepest_concavity(polys):
    """The outline point furthest inside its own convex hull, and how deep it is.

    That is what "the deepest concavity of a silhouette" means operationally: a bay is a
    stretch of outline that the hull bridges, and its deepest point is the one furthest from
    the bridge. A shape with no concavity -- a circle, a convex blob -- has no such point,
    and this says so rather than returning its least-convex vertex as though it were an
    inlet.
    """
    pts = [p for poly in polys for p in poly]
    if len(pts) < 4:
        return None, 0.0
    hull = _hull(pts)
    if len(hull) < 3:
        return None, 0.0
    ring = list(hull) + [hull[0]]
    best, bd = None, 0.0
    for p in pts:
        d = min(_seg_distance(ring[i], ring[i + 1], p) for i in range(len(ring) - 1))
        if d > bd:
            best, bd = p, d
    return best, bd


def _seg_distance(a, b, p):
    q = geometry._closest_on_segment(a, b, p)
    return math.hypot(p[0] - q[0], p[1] - q[1])


def derive(doc, address, by):
    """Compute one anchor from an element's own geometry. Returns ``(point, direction)``.

    The direction is None for recipes that have no meaningful one; `concavity` points out of
    the inlet, and the bbox edges point away from the shape, which is what an attached label
    or leader wants to know.

    **A silhouette is the OUTLINE**, so `concavity` ignores text beneath the element. A
    protein glyph with its name written across the middle had that label's box read as the
    deepest inlet -- 7.7 mm from the cleft the glyph itself declares, and near the centre,
    because a box in the middle of a shape is a long way inside its hull. Every other recipe
    measures everything beneath the address, which is what "how big is this group" means.
    """
    if by == "concavity":
        # Handled first, and fetched with `skip_text`, so a glyph whose label has no font
        # yet -- placed in a scene with no guide -- can still have its silhouette read. The
        # generic fetch below would raise on that label before reaching this branch.
        runs = _own_runs(doc, address, silhouette=True)
        if not runs:
            raise ValueError(f"{address}: nothing with geometry, so no anchor can be "
                             f"derived")
        polys = geometry.flatten(runs, 0.05)
        p, depth = _deepest_concavity(polys)
        if p is None or depth <= 1e-9:
            raise ValueError(
                f"{address}: this silhouette has no concavity to find -- it is convex to "
                f"within the flattening tolerance. Refusing to return its least-convex "
                f"point as though it were an inlet.")
        box = geometry.bounds(runs)
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        d = (p[0] - cx, p[1] - cy)
        n = math.hypot(*d)
        return p, ((d[0] / n, d[1] / n) if n > 1e-12 else None)

    runs = _own_runs(doc, address)
    if not runs:
        raise ValueError(f"{address}: nothing with geometry, so no anchor can be derived")
    if by.startswith("bbox."):
        box = geometry.bounds(runs)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        table = {"nw": ((x0, y0), (-1, -1)), "n": ((cx, y0), (0, -1)),
                 "ne": ((x1, y0), (1, -1)), "e": ((x1, cy), (1, 0)),
                 "se": ((x1, y1), (1, 1)), "s": ((cx, y1), (0, 1)),
                 "sw": ((x0, y1), (-1, 1)), "w": ((x0, cy), (-1, 0)),
                 "centre": ((cx, cy), None)}
        key = by.split(".", 1)[1]
        if key not in table:
            raise ValueError(f"{address}: no anchor recipe called {by!r} -- bbox takes "
                             f"{', '.join(sorted(table))}")
        return table[key]
    if by == "centroid":
        c, _basis = geometry.centroid(runs)
        return c, None
    if by.startswith("path."):
        which = by.split(".", 1)[1]
        run = runs[0]
        t = {"start": 0.0, "mid": 0.5, "end": 1.0}.get(which)
        if t is None:
            raise ValueError(f"{address}: no anchor recipe called {by!r} -- path takes "
                             f"start, mid, end")
        p = geometry.point_at(run, t)
        q = geometry.point_at(run, min(1.0, t + 0.01) if t < 1 else 0.99)
        d = (q[0] - p[0], q[1] - p[1])
        n = math.hypot(*d)
        return p, ((d[0] / n, d[1] / n) if n > 1e-12 else None)
    if by.startswith("extreme."):
        pts = [p for poly in geometry.flatten(runs, 0.02) for p in poly]
        which = by.split(".", 1)[1]
        pick = {"top": lambda p: p[1], "bottom": lambda p: -p[1],
                "left": lambda p: p[0], "right": lambda p: -p[0]}.get(which)
        if pick is None:
            raise ValueError(f"{address}: no anchor recipe called {by!r} -- extreme takes "
                             f"top, bottom, left, right")
        p = min(pts, key=pick)
        d = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}[which]
        return p, d
    raise ValueError(f"{address}: no anchor recipe called {by!r}. "
                     f"Known: {', '.join(RECIPES)}")


def resolve(doc, only=None):
    """Recompute every derived and discovered anchor's position. ``(scene, report)``.

    Authored anchors are never touched: somebody chose those, and a recipe that overwrote a
    chosen point would make the three kinds of anchor indistinguishable in practice.
    """
    import copy
    out = copy.deepcopy(doc)
    moved, failed = [], []
    for addr, el, _p in model.walk(out):
        if only and not (addr == only or addr.startswith(only + ".")):
            continue
        for name, a in sorted((el.get("anchors") or {}).items()):
            if a.get("how") not in ("derived", "discovered"):
                continue
            try:
                pt, direction = derive(out, addr, a.get("by", ""))
            except ValueError as e:
                failed.append({"anchor": f"{addr}.{name}", "why": str(e)})
                continue
            was = a.get("at")
            a["at"] = [pt[0], pt[1]]
            if direction:
                a["dir"] = [direction[0], direction[1]]
            if was is None or abs(was[0] - pt[0]) > 1e-9 or abs(was[1] - pt[1]) > 1e-9:
                moved.append({"anchor": f"{addr}.{name}",
                              "from": list(was) if was else None,
                              "to": [pt[0], pt[1]]})
    return out, {"resolved": moved, "unresolvable": failed}


# --------------------------------------------------------------------- solving
def _anchor_point_in(doc, owner_addr, anchor_name, frame):
    from . import measure
    el = model.find(doc, owner_addr)
    a = (el.get("anchors") or {}).get(anchor_name)
    if a is None or "at" not in a:
        raise ValueError(f"{owner_addr}.{anchor_name}: no anchor with a resolved position")
    m = model.compose(model.invert(model.frame_to_page(doc, frame)),
                      model.element_to_page(doc, owner_addr))
    return model.apply(m, a["at"][0], a["at"][1])


def _target_point(doc, ref, frame):
    got = model.resolve(doc, ref)
    if got["kind"] == "anchor":
        return _anchor_point_in(doc, got["element_address"], got["name"], frame)
    from . import measure
    box = geometry.bounds(measure.runs_in_frame(doc, ref, frame))
    if box is None:
        raise ValueError(f"{ref}: nothing with geometry to attach to")
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _box_in(doc, address, frame):
    from . import measure
    box = geometry.bounds(measure.runs_in_frame(doc, address, frame))
    if box is None:
        raise ValueError(f"{address}: nothing with geometry to place")
    return box


def _translate(doc, addr, el, dx, dy, frame):
    """Move `el` by (dx, dy) AS MEASURED IN `frame`, writing it into the element's transform.

    **The units have to be converted and it is not optional.** A relation is solved in the
    page frame, in millimetres; an element's own transform is applied in whatever coordinate
    context it sits in, which for anything traced is image pixels. Composing a millimetre
    delta into a pixel transform moved a traced enzyme by 0.1 mm when it asked for 4, so the
    solver kept asking, hit its pass limit, and reported -- correctly -- that the layout
    never settled. Every element in the demo that worked was in the page frame, where the
    two units happen to coincide.

    The conversion: the delta is a VECTOR, so it goes through the linear part of each matrix
    and never the translation. Into page coordinates through the solve frame, then back into
    the element's parent context, which is its own matrix divided out of its place on the
    page.
    """
    t = el.get("transform") or list(model.IDENTITY)
    f = model.frame_to_page(doc, frame)
    px = f[0] * dx + f[2] * dy
    py = f[1] * dx + f[3] * dy
    parent = model.compose(model.element_to_page(doc, addr), model.invert(t))
    pi = model.invert(parent)
    ex = pi[0] * px + pi[2] * py
    ey = pi[1] * px + pi[3] * py
    el["transform"] = model.compose([1, 0, 0, 1, ex, ey], t)


def _wanted(doc, addr, el, rel, frame):
    """The translation this one relation wants, as ``(dx, dy, slack)``.

    `slack` is how far short the relation is right now -- zero when it is already satisfied.
    Returning it rather than a boolean is what lets :func:`solve` report *by how much* a
    layout could not be satisfied instead of merely that it could not.
    """
    kind = rel.get("kind", "attach")
    ref = rel["to"]
    off = rel.get("offset") or [0.0, 0.0]
    if kind == "attach":
        target = _target_point(doc, ref, frame)
        via = rel.get("via")
        if via:
            here = _anchor_point_in(doc, addr, via, frame)
        else:
            box = _box_in(doc, addr, frame)
            here = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
        dx = target[0] + off[0] - here[0]
        dy = target[1] + off[1] - here[1]
        return dx, dy, math.hypot(dx, dy)
    if kind == "align":
        edge = rel.get("edge", "centre-x")
        if edge not in _EDGES:
            raise ValueError(f"{addr}: no alignment edge called {edge!r}; "
                             f"known: {', '.join(_EDGES)}")
        mine = _box_in(doc, addr, frame)
        theirs = _box_in(doc, ref, frame)
        pick = {"left": (0, 0), "right": (2, 2), "top": (1, 1), "bottom": (3, 3),
                "below": (1, 3), "above": (3, 1), "right-of": (0, 2),
                "left-of": (2, 0)}
        if edge in pick:
            i, j = pick[edge]
            delta = theirs[j] - mine[i]
            if edge in ("left", "right", "right-of", "left-of"):
                return delta + off[0], 0.0, abs(delta + off[0])
            return 0.0, delta + off[1], abs(delta + off[1])
        if edge == "centre-x":
            delta = (theirs[0] + theirs[2]) / 2.0 - (mine[0] + mine[2]) / 2.0
            return delta + off[0], 0.0, abs(delta)
        delta = (theirs[1] + theirs[3]) / 2.0 - (mine[1] + mine[3]) / 2.0
        return 0.0, delta + off[1], abs(delta)
    if kind == "clear":
        margin = float(off[0] if off else 0.0)
        from . import measure  # noqa: F811
        mine_runs = measure.runs_in_frame(doc, addr, frame)
        theirs_runs = measure.runs_in_frame(doc, ref, frame)
        pa = geometry.flatten(mine_runs, 0.05)
        pb = geometry.flatten(theirs_runs, 0.05)
        gap = _gap(pa, pb, measure.encloses(doc, addr), measure.encloses(doc, ref))
        if gap >= margin - 1e-9:
            return 0.0, 0.0, 0.0
        mine = geometry.bounds(mine_runs)
        theirs = geometry.bounds(theirs_runs)
        vx = (mine[0] + mine[2]) / 2.0 - (theirs[0] + theirs[2]) / 2.0
        vy = (mine[1] + mine[3]) / 2.0 - (theirs[1] + theirs[3]) / 2.0
        n = math.hypot(vx, vy)
        if n < 1e-12:
            vx, vy, n = 1.0, 0.0, 1.0
        push = margin - gap
        return vx / n * push, vy / n * push, push
    if kind == "inside":
        mine = _box_in(doc, addr, frame)
        theirs = _box_in(doc, ref, frame)
        pad = float(off[0] if off else 0.0)
        dx = dy = 0.0
        if mine[0] < theirs[0] + pad:
            dx = theirs[0] + pad - mine[0]
        elif mine[2] > theirs[2] - pad:
            dx = theirs[2] - pad - mine[2]
        if mine[1] < theirs[1] + pad:
            dy = theirs[1] + pad - mine[1]
        elif mine[3] > theirs[3] - pad:
            dy = theirs[3] - pad - mine[3]
        too_wide = (mine[2] - mine[0]) > (theirs[2] - theirs[0]) - 2 * pad
        too_tall = (mine[3] - mine[1]) > (theirs[3] - theirs[1]) - 2 * pad
        if too_wide or too_tall:
            raise Unsatisfiable(
                f"{addr} is {'wider' if too_wide else 'taller'} than {ref} allows "
                f"({mine[2] - mine[0]:.4g}x{mine[3] - mine[1]:.4g} into "
                f"{theirs[2] - theirs[0] - 2 * pad:.4g}x"
                f"{theirs[3] - theirs[1] - 2 * pad:.4g}); no translation can fix that")
        return dx, dy, math.hypot(dx, dy)
    raise ValueError(f"{addr}: no relation kind called {kind!r}; known: {', '.join(KINDS)}")


class Unsatisfiable(Exception):
    """A relation that no amount of moving can satisfy. Reported, never approximated."""


def _gap(pa, pb, a_closed=True, b_closed=True):
    if not pa or not pb:
        return float("inf")
    if geometry.polys_overlap(pa, pb, a_closed=a_closed, b_closed=b_closed):
        return 0.0
    best = float("inf")
    for poly in pa:
        for p in poly:
            _q, d = geometry.nearest_point(pb, p)
            best = min(best, d)
    for poly in pb:
        for p in poly:
            _q, d = geometry.nearest_point(pa, p)
            best = min(best, d)
    return best


#: How close counts as satisfied, in the solve frame's units. **It must be coarser than the
#: format's own precision.** `io.PLACES` rounds every coordinate to six decimals, so a scene
#: written out and read back in differs from itself by up to that much, and composing it
#: through a couple of matrices leaves a residual around 1e-4. With a tolerance of 1e-6 the
#: solver chased that noise: a figure re-solved after a round trip through its own file
#: always reported an element as having moved -- by two ten-thousandths of a millimetre --
#: and `figure.report` duly warned that the stored document was not the drawn one.
#:
#: Measured, not guessed: the residual after one round trip through the file and a couple of
#: matrix compositions is about 2e-4 mm, so the threshold is set an order above it. One
#: micron on a 180 mm page is one part in 180,000. Nothing in any figure depends on it.
SETTLED = 1e-3


def solve(doc, frame=None, max_iter=24, tol=SETTLED):
    """Re-solve every relation. Returns ``(scene, report)``; nothing is mutated in place.

    **Relaxation, not a simultaneous solve.** Relations are applied in document order and
    the whole pass repeats until nothing moves. That converges for the chains figures
    actually contain and does not for a genuinely circular one -- so it stops after
    `max_iter` passes and reports what was still moving, rather than iterating forever or
    declaring success on a layout that never settled.
    """
    import copy
    out = copy.deepcopy(doc)
    out, anchor_report = resolve(out)
    frame = frame or model._page_frame(out)
    moved, failed = {}, []
    passes = 0
    for passes in range(1, max_iter + 1):
        biggest = 0.0
        for addr, el, _p in model.walk(out):
            for i, rel in enumerate(el.get("relations") or []):
                try:
                    dx, dy, slack = _wanted(out, addr, el, rel, frame)
                except Unsatisfiable as e:
                    entry = {"element": addr, "relation": i, "kind": rel.get("kind"),
                             "to": rel.get("to"), "why": str(e)}
                    if entry not in failed:
                        failed.append(entry)
                    continue
                except (ValueError, KeyError) as e:
                    entry = {"element": addr, "relation": i, "kind": rel.get("kind"),
                             "to": rel.get("to"), "why": str(e)}
                    if entry not in failed:
                        failed.append(entry)
                    continue
                if abs(dx) > tol or abs(dy) > tol:
                    _translate(out, addr, el, dx, dy, frame)
                    got = moved.setdefault(addr, [0.0, 0.0])
                    got[0] += dx
                    got[1] += dy
                    biggest = max(biggest, slack)
        if biggest <= tol:
            break
    settled = passes < max_iter
    unsettled = []
    if not settled:
        for addr, el, _p in model.walk(out):
            for i, rel in enumerate(el.get("relations") or []):
                try:
                    _dx, _dy, slack = _wanted(out, addr, el, rel, frame)
                except Exception:
                    continue
                if slack > tol:
                    unsettled.append({"element": addr, "relation": i,
                                      "kind": rel.get("kind"), "to": rel.get("to"),
                                      "short_by": slack})
    return out, {
        "passes": passes,
        "settled": settled,
        "moved": {k: {"dx": v[0], "dy": v[1]} for k, v in sorted(moved.items())},
        "unsatisfiable": failed,
        "unsettled": unsettled,
        "anchors": anchor_report,
        "frame": frame,
    }
