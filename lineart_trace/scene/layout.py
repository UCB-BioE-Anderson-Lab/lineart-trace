"""Layout and composition: §3.6. Panels, distribution, and connectors that go round things.

**A panel is a frame, not a rectangle drawn at the right place.** Each panel gets its own
coordinate space with a transform onto the page, so a panel's contents are authored at
whatever size suits them and the grid decides where that lands. That is what makes
:func:`reflow` possible: change the page, recompute the transforms, and every panel's
contents move without any of them being edited.

The panel grid is recorded on the scene (`layout.panels`), because a figure that can be
reflowed has to carry what it was laid out to. Nothing else here keeps state.

**Connector routing avoids obstacles by searching, not by hoping.** A route is found by A*
over an occupancy grid built from the bounding boxes of everything in the way, inflated by a
stated clearance, with a penalty on turns so a route with two bends beats one with six. The
result carries the clearance it actually achieved, so "it goes round" is a number.
"""
import heapq
import math

from . import build, geometry, measure, model

__all__ = ["panels", "reflow", "into_panel", "distribute", "pack", "connect",
           "route", "LETTERS"]

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# --------------------------------------------------------------------- panels
def panels(doc, rows=1, cols=2, gutter=4.0, margin=3.0, letters="A", letter_role=None,
           area_guides=True):
    """Lay a grid of panel frames over the page. Returns ``(scene, report)``.

    Each panel becomes a group with its own frame, named `panel-a`, `panel-b`, ... and a
    guide rectangle giving its usable area. Contents added under a panel are authored in that
    panel's own coordinates, with (0, 0) at its top-left corner.

    `letters` is the first label -- ``"A"`` for A, B, C, or ``""`` for none. The lettering is
    automatic because doing it by hand is the thing that silently goes wrong when a panel is
    inserted.

    Re-running this on a scene that already has panels **moves** them rather than adding
    more, which is what makes it the mechanism behind :func:`reflow`.
    """
    import copy
    out = copy.deepcopy(doc)
    canvas = out["canvas"]
    w, h = float(canvas["width"]), float(canvas["height"])
    if rows < 1 or cols < 1:
        raise ValueError(f"a panel grid needs at least one row and column, got {rows}x{cols}")
    pw = (w - 2 * margin - gutter * (cols - 1)) / cols
    ph = (h - 2 * margin - gutter * (rows - 1)) / rows
    if pw <= 0 or ph <= 0:
        raise ValueError(
            f"a {rows}x{cols} grid with {gutter:g} gutters and {margin:g} margins does not "
            f"fit on {w:g}x{h:g}{canvas['unit']}: each panel would be "
            f"{pw:.3g}x{ph:.3g}. Fewer panels, a smaller gutter, or a bigger page.")

    out.setdefault("layout", {})["panels"] = {
        "rows": rows, "cols": cols, "gutter": gutter, "margin": margin,
        "letters": letters, "area_guides": bool(area_guides)}

    made, moved = [], []
    n = 0
    for r in range(rows):
        for c in range(cols):
            name = f"panel-{LETTERS[n].lower()}" if n < len(LETTERS) else f"panel-{n + 1}"
            x = margin + c * (pw + gutter)
            y = margin + r * (ph + gutter)
            frame = f"{name}-frame"
            out["frames"][frame] = {"parent": model._page_frame(out),
                                    "unit": canvas["unit"],
                                    "transform": [1, 0, 0, 1, x, y]}
            existing = model.find(out, name)
            if existing is None:
                group = build.group(name, [], frame=frame)
                group["tags"] = ["panel"]
                group["anchors"] = {
                    "top-left": {"how": "authored", "at": [0.0, 0.0]},
                    "centre": {"how": "authored", "at": [pw / 2, ph / 2]},
                    "bottom-right": {"how": "authored", "at": [pw, ph]}}
                if area_guides:
                    area = build.rect("area", 0, 0, pw, ph)
                    area["type"] = "guide"
                    group["children"].append(area)
                if letters:
                    first = LETTERS.index(letters.upper()) if letters.upper() in LETTERS \
                        else 0
                    label = LETTERS[(first + n) % len(LETTERS)]
                    role = letter_role or "panel-letter"
                    # A LITERAL ONLY IF NOTHING DEFINES THE ROLE. Writing one unconditionally
                    # is worse than it looks: a literal beats a role, so every panel letter
                    # ignored the guide AND showed up in `style.adopt` as its own invented
                    # role. Writing none unconditionally is worse still -- a panel laid out
                    # in a scene with no guide would have an unmeasurable letter on it.
                    defined = role in ((out.get("style") or {}).get("roles") or {})
                    group["children"].append(
                        build.text("letter", label, (0.0, 0.0),
                                   family=None if defined else "Helvetica",
                                   size=None if defined else "10pt",
                                   baseline="hanging", role=role))
                out = model.add(out, group)
                made.append(name)
            else:
                existing["frame"] = frame
                area = model.find(out, f"{name}.area")
                if area is not None:
                    area["geometry"] = build.rect("area", 0, 0, pw, ph)["geometry"]
                for key, at in (("centre", [pw / 2, ph / 2]),
                                ("bottom-right", [pw, ph])):
                    if key in (existing.get("anchors") or {}):
                        existing["anchors"][key]["at"] = at
                moved.append(name)
            n += 1
    return out, {"rows": rows, "cols": cols, "panel": {"width": pw, "height": ph},
                 "gutter": gutter, "margin": margin, "created": made, "moved": moved,
                 "unit": canvas["unit"]}


def reflow(doc, width=None, height=None, rows=None, cols=None, gutter=None,
           margin=None):
    """Retarget the figure to a different page, re-laying the panel grid. ``(scene, report)``.

    **The grid itself can change**, and for a real retarget it usually must: four panels that
    sit two-by-two on a slide do not fit two-by-two in an 88 mm column, and forcing them to
    produced a figure whose contents ran off both sides. Passing `rows` and `cols` re-lays
    them one-per-row; leaving them out keeps the grid the figure was laid out to.

    **Reflow, not scale.** The panels are re-laid at the new size and their contents keep
    their own dimensions -- a 10 pt label stays 10 pt when a figure goes from a slide to a
    column, which is the whole difference §3.13 asks for between reflowing and shrinking.

    A scene with no recorded panel grid cannot be reflowed and says so, rather than resizing
    the canvas and leaving everything where it was.
    """
    import copy
    out = copy.deepcopy(doc)
    spec = (out.get("layout") or {}).get("panels")
    if not spec:
        raise ValueError(
            "this scene has no panel grid, so there is nothing to reflow -- resizing the "
            "canvas alone would move the page and not its contents. `layout.panels` "
            "records the grid.")
    was = dict(out["canvas"])
    if width:
        out["canvas"]["width"] = float(width)
    if height:
        out["canvas"]["height"] = float(height)
    for key, value in (("rows", rows), ("cols", cols), ("gutter", gutter),
                       ("margin", margin)):
        if value is not None:
            spec[key] = value
    out, report = panels(out, **spec)
    refitted = []
    for addr, el, _p in list(model.walk(out)):
        spec_fit = el.get("fit")
        if not spec_fit:
            continue
        name = addr.rsplit(".", 1)[-1]
        out, r = into_panel(out, addr, spec_fit["panel"], True,
                            spec_fit.get("margin", 0.0),
                            spec_fit.get("align", "centre"))
        refitted.append({"element": r["element"], "scale": r["scale"]})
    report["from"] = {"width": was["width"], "height": was["height"]}
    report["to"] = {"width": out["canvas"]["width"], "height": out["canvas"]["height"]}
    report["refitted"] = refitted
    report["regridded"] = any(v is not None for v in (rows, cols))
    return out, report


def into_panel(doc, address, panel, fit=True, margin=0.0, align="centre"):
    """Move an element into a panel, re-parenting its frame. Returns ``(scene, report)``.

    **Re-parenting the frame is the part that is not obvious and is not optional.** An
    element that declares its own frame -- everything traced does, in image pixels -- has a
    coordinate context that starts at that frame, not at whatever group it happens to sit
    in. Move it under a panel without re-parenting and it renders exactly where it was,
    because the panel's transform is never in its chain. It looks like the move silently
    failed; in fact the move succeeded and meant nothing.

    With `fit`, the element is scaled and centred to sit inside the panel's area. Scaling is
    applied to the FRAME where the element owns one, so lengths written as page-absolute --
    ``"0.6pt"`` -- keep their size on paper while the drawing changes size around them.
    """
    import copy
    out = copy.deepcopy(doc)
    el = model.find(out, address)
    if el is None:
        raise KeyError(address)
    host = model.find(out, panel)
    if host is None:
        raise KeyError(panel)
    panel_frame = host.get("frame")
    if not panel_frame:
        raise ValueError(f"{panel} has no frame of its own, so it is not a panel")

    frame = el.get("frame")
    out = model.remove(out, address)
    el = copy.deepcopy(el)
    if frame and frame != panel_frame:
        out["frames"][frame]["parent"] = panel_frame
    elif not frame:
        el["frame"] = panel_frame
    out = model.add(out, el, panel)
    moved = f"{panel}.{el['name']}"

    if not fit:
        model.find(out, moved).pop("fit", None)
        return out, {"element": moved, "frame": frame, "fitted": False}
    # RECORDED ON THE ELEMENT, because reflow has to know which contents to re-fit and which
    # to leave alone. That distinction IS the difference between reflowing and scaling: a
    # drawing placed to fill a panel should fill the new panel, and a 10pt label should still
    # be 10pt when the figure goes from a slide to a column. Without this, reflow re-laid the
    # panels and left a 45mm drawing sitting in a 23mm one.
    model.find(out, moved)["fit"] = {"panel": panel, "margin": float(margin),
                                     "align": align}

    area = model.find(out, f"{panel}.area")
    if area is None:
        raise ValueError(f"{panel} has no `area` guide to fit into; lay the panels with "
                         f"area guides, or pass fit=False")
    target = measure.bbox(out, f"{panel}.area", panel_frame)["value"]
    have = measure.bbox(out, moved, panel_frame)["value"]
    if have["width"] <= 0 or have["height"] <= 0:
        raise ValueError(f"{moved} has no extent, so it cannot be fitted")
    tw = target["width"] - 2 * margin
    th = target["height"] - 2 * margin
    k = min(tw / have["width"], th / have["height"])
    if frame and frame != panel_frame:
        t = out["frames"][frame].get("transform") or list(model.IDENTITY)
        out["frames"][frame]["transform"] = model.compose([k, 0, 0, k, 0, 0], t)
    else:
        el = model.find(out, moved)
        el["transform"] = model.compose([k, 0, 0, k, 0, 0],
                                        el.get("transform") or list(model.IDENTITY))
    now = measure.bbox(out, moved, panel_frame)["value"]
    if align == "centre":
        dx = target["x"] + (target["width"] - now["width"]) / 2 - now["x"]
        dy = target["y"] + (target["height"] - now["height"]) / 2 - now["y"]
    else:
        dx = target["x"] + margin - now["x"]
        dy = target["y"] + margin - now["y"]
    _shift(out, moved, model.find(out, moved), dx, dy, panel_frame)
    final = measure.bbox(out, moved, panel_frame)["value"]
    return out, {"element": moved, "frame": frame, "fitted": True, "scale": k,
                 "box": final, "area": target}


# --------------------------------------------------------------------- arranging
def _boxes(doc, addresses, frame):
    got = []
    for a in addresses:
        got.append((a, measure.bbox(doc, a, frame)["value"]))
    return got


def distribute(doc, addresses, axis="x", spacing=None, frame=None):
    """Space elements evenly along an axis. Returns ``(scene, report)``.

    With `spacing`, the GAPS between neighbours are made equal to it. Without, the existing
    extent is kept and the gaps within it are equalised -- so distributing something already
    spread across a panel does not collapse it.
    """
    import copy
    out = copy.deepcopy(doc)
    frame = frame or model._page_frame(out)
    i, j = (0, 2) if axis == "x" else (1, 3)
    key = "x" if axis == "x" else "y"
    size = "width" if axis == "x" else "height"
    items = sorted(_boxes(out, addresses, frame), key=lambda kv: kv[1][key])
    if len(items) < 2:
        raise ValueError("distributing needs at least two elements")
    total = sum(b[size] for _a, b in items)
    if spacing is None:
        span = (items[-1][1][key] + items[-1][1][size]) - items[0][1][key]
        gap = (span - total) / (len(items) - 1)
    else:
        gap = float(spacing)
    moved = {}
    cursor = items[0][1][key]
    for addr, box in items:
        delta = cursor - box[key]
        if abs(delta) > 1e-9:
            el = model.find(out, addr)
            dx, dy = (delta, 0.0) if axis == "x" else (0.0, delta)
            _shift(out, addr, el, dx, dy, frame)
            moved[addr] = {"dx": dx, "dy": dy}
        cursor += box[size] + gap
    return out, {"axis": axis, "gap": gap, "moved": moved,
                 "order": [a for a, _b in items]}


def pack(doc, addresses, into, gap=2.0, frame=None):
    """Lay elements left to right inside a target's box, wrapping to new rows.

    Returns ``(scene, report)``. Anything that will not fit is REPORTED and left where it
    was -- packing that silently drops or overlaps the overflow is the failure this exists
    to prevent.
    """
    import copy
    out = copy.deepcopy(doc)
    frame = frame or model._page_frame(out)
    area = measure.bbox(out, into, frame)["value"]
    x, y, row_h = area["x"], area["y"], 0.0
    moved, overflow = {}, []
    for addr in addresses:
        box = measure.bbox(out, addr, frame)["value"]
        if box["width"] > area["width"] + 1e-9:
            overflow.append({"element": addr, "why": f"{box['width']:.4g} wide, the area "
                                                     f"is {area['width']:.4g}"})
            continue
        if x + box["width"] > area["x"] + area["width"] + 1e-9:
            x = area["x"]
            y += row_h + gap
            row_h = 0.0
        if y + box["height"] > area["y"] + area["height"] + 1e-9:
            overflow.append({"element": addr, "why": "no room left in the area"})
            continue
        dx, dy = x - box["x"], y - box["y"]
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            _shift(out, addr, model.find(out, addr), dx, dy, frame)
            moved[addr] = {"dx": dx, "dy": dy}
        x += box["width"] + gap
        row_h = max(row_h, box["height"])
    return out, {"into": into, "gap": gap, "moved": moved, "overflow": overflow,
                 "placed": len(moved), "refused": len(overflow)}


def _shift(doc, addr, el, dx, dy, frame):
    """Move an element by a delta measured in `frame`. Shared with the relation solver."""
    from . import anchors
    anchors._translate(doc, addr, el, dx, dy, frame)


# --------------------------------------------------------------------- connectors
def route(doc, start, end, avoid=None, clearance=1.5, resolution=1.0, frame=None,
          turn_penalty=3.0, bounds=None):
    """An orthogonal route from point to point that clears every obstacle. ``(points, report)``.

    A* over an occupancy grid: obstacles are the bounding boxes of `avoid`, grown by
    `clearance`, and a turn costs `turn_penalty` cells so a route with two bends is preferred
    to one with six. Returns the corner points and the clearance actually achieved.

    **When there is no route it says so.** Returning the straight line through the obstacle
    would be a connector that looks routed and is not.
    """
    frame = frame or model._page_frame(doc)
    obstacles = []
    for addr in (avoid or []):
        try:
            b = measure.bbox(doc, addr, frame)["value"]
        except (ValueError, KeyError, measure.Unmeasurable):
            continue
        obstacles.append((addr, b))

    # THE GRID IS SIZED FROM THE REGION, not from the page. It was the canvas, which is a
    # page-frame quantity: routing inside a panel frame then built a grid in the wrong
    # coordinates and clipped every route to the top-left corner of the panel. Anything that
    # has to hold in an arbitrary frame must be derived in that frame.
    pad = clearance + 4 * resolution
    xs = [start[0], end[0]] + [b["x"] for _a, b in obstacles] \
        + [b["x"] + b["width"] for _a, b in obstacles]
    ys = [start[1], end[1]] + [b["y"] for _a, b in obstacles] \
        + [b["y"] + b["height"] for _a, b in obstacles]
    ox, oy = min(xs) - pad, min(ys) - pad
    hi_x, hi_y = max(xs) + pad, max(ys) + pad
    # BOUNDED BY THE PAGE. The padding that gives a route room around an obstacle also gave
    # it room OUTSIDE the canvas, so a wall spanning the whole page was cheerfully routed
    # around through the margin -- a connector that leaves the paper, reported as a
    # successful route. The default bound is the canvas, expressed in whatever frame the
    # routing is happening in.
    if bounds is None:
        page = model._page_frame(doc)
        c = doc.get("canvas") or {}
        m = model.frame_between(doc, frame, page)
        corners = [model.apply(m, x, y) for x, y in
                   ((0.0, 0.0), (float(c.get("width", 0)), 0.0),
                    (float(c.get("width", 0)), float(c.get("height", 0))),
                    (0.0, float(c.get("height", 0))))]
        bounds = (min(p[0] for p in corners), min(p[1] for p in corners),
                  max(p[0] for p in corners), max(p[1] for p in corners))
    if bounds:
        ox, oy = max(ox, bounds[0]), max(oy, bounds[1])
        hi_x, hi_y = min(hi_x, bounds[2]), min(hi_y, bounds[3])
        ox, oy = min(ox, start[0], end[0]), min(oy, start[1], end[1])
        hi_x = max(hi_x, start[0], end[0])
        hi_y = max(hi_y, start[1], end[1])
    w, h = hi_x - ox, hi_y - oy
    nx, ny = max(2, int(w / resolution) + 1), max(2, int(h / resolution) + 1)
    if nx * ny > 4_000_000:
        return None, {"routed": False,
                      "why": f"a {nx}x{ny} grid at {resolution:g} resolution is too large "
                             f"to search; use a coarser --resolution"}

    blocked = [[False] * ny for _ in range(nx)]
    for _addr, b in obstacles:
        x0 = int(math.floor((b["x"] - clearance - ox) / resolution))
        x1 = int(math.ceil((b["x"] + b["width"] + clearance - ox) / resolution))
        y0 = int(math.floor((b["y"] - clearance - oy) / resolution))
        y1 = int(math.ceil((b["y"] + b["height"] + clearance - oy) / resolution))
        for i in range(max(0, x0), min(nx, x1 + 1)):
            for j in range(max(0, y0), min(ny, y1 + 1)):
                blocked[i][j] = True

    def cell(p):
        return (max(0, min(nx - 1, int(round((p[0] - ox) / resolution)))),
                max(0, min(ny - 1, int(round((p[1] - oy) / resolution)))))

    # THE STRAIGHT LINE FIRST, when it is clear. The grid snaps the route's interior to
    # `resolution` while the ends stay exact, so two boxes almost in line got a connector
    # with two little jogs in it -- geometrically fine, and it reads as a kink in what should
    # be a straight arrow. If nothing is in the way, nothing needs routing.
    straight = [tuple(map(float, start)), tuple(map(float, end))]
    near_end = [addr for addr, b in obstacles
                if any(b["x"] - clearance <= p[0] <= b["x"] + b["width"] + clearance
                       and b["y"] - clearance <= p[1] <= b["y"] + b["height"] + clearance
                       for p in straight)]
    clear = True
    worst_direct = None
    for addr, _b in obstacles:
        if addr in near_end:
            continue
        try:
            poly = geometry.flatten(measure.runs_in_frame(doc, addr, frame), 0.05)
        except measure.Unmeasurable:
            continue
        if not poly:
            continue
        for p in _densify(straight, resolution / 2.0):
            _q, dd = geometry.nearest_point(poly, p)
            worst_direct = dd if worst_direct is None else min(worst_direct, dd)
        if worst_direct is not None and worst_direct < clearance - 1e-9:
            clear = False
            break
    if clear:
        return straight, {"routed": True, "corners": 0, "direct": True,
                          "clearance_asked": clearance,
                          "clearance_worst": worst_direct,
                          "obstacles": [a for a, _b in obstacles],
                          "passed": [a for a, _b in obstacles if a not in near_end],
                          "attached_to": near_end, "resolution": resolution}

    s, t = cell(start), cell(end)
    # A CORRIDOR AT EACH END, not just the one cell. A connector is normally attached to the
    # EDGE of the thing it leaves, so that point sits inside its own obstacle's inflated
    # region -- unblocking the single cell leaves the route walled in by its neighbours and
    # every sensible request comes back "no route". The thing a connector is attached to may
    # not block it where it attaches.
    escape = int(math.ceil((clearance + 2 * resolution) / resolution))
    for c in (s, t):
        for i in range(max(0, c[0] - escape), min(nx, c[0] + escape + 1)):
            for j in range(max(0, c[1] - escape), min(ny, c[1] + escape + 1)):
                if (i - c[0]) ** 2 + (j - c[1]) ** 2 <= escape ** 2:
                    blocked[i][j] = False

    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    seen = {}
    heap = [(0.0, 0.0, s, None)]
    came = {}
    while heap:
        _f, g, cur, came_dir = heapq.heappop(heap)
        if (cur, came_dir) in seen:
            continue
        seen[(cur, came_dir)] = g
        if cur == t:
            break
        for d in dirs:
            nxt = (cur[0] + d[0], cur[1] + d[1])
            if not (0 <= nxt[0] < nx and 0 <= nxt[1] < ny) or blocked[nxt[0]][nxt[1]]:
                continue
            step = 1.0 + (turn_penalty if came_dir is not None and d != came_dir else 0.0)
            ng = g + step
            if (nxt, d) in seen and seen[(nxt, d)] <= ng:
                continue
            came[(nxt, d)] = (cur, came_dir)
            hcost = abs(nxt[0] - t[0]) + abs(nxt[1] - t[1])
            heapq.heappush(heap, (ng + hcost, ng, nxt, d))
    else:
        return None, {"routed": False,
                      "why": f"no orthogonal route from {start} to {end} clears "
                             f"{clearance:g} around {len(obstacles)} obstacle(s) at "
                             f"{resolution:g} resolution. Refusing to draw the straight "
                             f"line through them."}

    key = next((k for k in came if k[0] == t), (t, None))
    if t != s and key[0] != t:
        return None, {"routed": False, "why": "the search ended without reaching the end"}
    path = []
    node = key if t != s else (s, None)
    while node is not None:
        path.append(node[0])
        node = came.get(node)
    path.reverse()

    pts = [(ox + p[0] * resolution, oy + p[1] * resolution) for p in path]
    pts[0], pts[-1] = (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    corners = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        if (round(b[0] - a[0], 9), round(b[1] - a[1], 9)) != \
                (round(c[0] - b[0], 9), round(c[1] - b[1], 9)):
            if not _collinear(a, b, c):
                corners.append(b)
    corners.append(pts[-1])

    # CLEARANCE IS MEASURED AGAINST WHAT THE ROUTE PASSES, not against what it leaves from.
    # A connector normally starts on the edge of a box, so its clearance to THAT box is zero
    # by construction -- reporting it made every correct route look like a failure. The boxes
    # an end sits on are reported separately, under the name that says what they are.
    attached, passed = [], []
    for addr, b in obstacles:
        near = any(b["x"] - clearance <= p[0] <= b["x"] + b["width"] + clearance
                   and b["y"] - clearance <= p[1] <= b["y"] + b["height"] + clearance
                   for p in (corners[0], corners[-1]))
        (attached if near else passed).append(addr)

    # MEASURED THE WAY `scene.gap` measures, and it was not at first. Scanning only the
    # route's CORNERS reported 5.85mm on a route whose closest approach along a straight
    # segment was 2.0mm -- the same sampling error this repository's design log warns about,
    # committed in new code a week after writing it down. A vertex scan misses every closest
    # approach that happens between two vertices, and it misses it in the flattering
    # direction.
    worst = None
    dense = _densify(corners, resolution / 2.0)
    for addr in passed:
        try:
            other = geometry.flatten(measure.runs_in_frame(doc, addr, frame), 0.05)
        except measure.Unmeasurable:
            continue
        if not other:
            continue
        for p in dense:
            _q, d = geometry.nearest_point(other, p)
            worst = d if worst is None else min(worst, d)
        for line in other:
            for p in line:
                _q, d = geometry.nearest_point([dense], p)
                worst = d if worst is None else min(worst, d)
    return corners, {"routed": True, "corners": len(corners) - 2,
                     "clearance_asked": clearance, "clearance_worst": worst,
                     "obstacles": [a for a, _b in obstacles],
                     "passed": passed, "attached_to": attached,
                     "resolution": resolution}


def _densify(points, step):
    """A polyline resampled so no two points are further apart than `step`."""
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        n = max(1, int(math.ceil(math.dist(a, b) / max(step, 1e-9))))
        for i in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return out


def _collinear(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-9


def connect(doc, name, start, end, avoid=None, clearance=1.5, resolution=1.0,
            kind="orthogonal", role=None, style=None, arrow=0.0, frame=None,
            corner_radius=0.0, bounds=None, parent=""):
    """Draw a routed connector between two points. Returns ``(scene, report)``.

    `kind` is ``orthogonal`` (right angles), ``curved`` (the same route, smoothed) or
    ``straight`` (a direct line, which does not route and says so). With `arrow`, an
    arrowhead of that size is added at the end, pointing along the final segment.
    """
    import copy
    out = copy.deepcopy(doc)
    frame = frame or model._page_frame(out)
    if kind == "straight":
        pts, report = [tuple(map(float, start)), tuple(map(float, end))], {
            "routed": False, "kind": "straight",
            "why": "a straight connector does not route; it is a line between two points"}
    else:
        pts, report = route(out, start, end, avoid, clearance, resolution, frame,
                            bounds=bounds)
        if pts is None:
            return doc, report
        report["kind"] = kind

    kids = []
    if kind == "curved" and len(pts) > 2:
        kids.append(build.through("line", pts, tension=0.4, role=role, style=style))
    elif corner_radius and kind == "orthogonal" and len(pts) > 2:
        kids.append(build.path("line", _rounded(pts, corner_radius), role=role,
                               style=style))
    else:
        kids.append(build.polyline("line", pts, role=role, style=style))
    if arrow:
        a, b = pts[-2], pts[-1]
        d = (b[0] - a[0], b[1] - a[1])
        kids.append(build.arrowhead("head", b, d, arrow, role=role, style=style))
    # STAMPED ONLY WHEN IT DIFFERS FROM WHAT THE PARENT ALREADY GIVES. Stamping the working
    # frame unconditionally overrides inheritance; stamping nothing leaves the group in the
    # page frame while its geometry was computed in another one, so a connector inside a
    # panel drew itself at the page origin. Both were wrong in the same afternoon, in
    # opposite directions.
    inherited = model.frame_of(out, parent) if parent else model._page_frame(out)
    g = build.group(name, kids, frame=(frame if frame != inherited else None))
    g["tags"] = ["connector"]
    g["anchors"] = {"start": {"how": "authored", "at": [pts[0][0], pts[0][1]]},
                    "end": {"how": "authored", "at": [pts[-1][0], pts[-1][1]]}}
    out = model.add(out, g, parent)
    report["points"] = len(pts)
    report["element"] = f"{parent}.{name}" if parent else name
    return out, report


def _rounded(pts, r):
    """An orthogonal polyline with its corners cut by quarter-circle cubics."""
    segs = [["M", pts[0][0], pts[0][1]]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ra = min(r, math.dist(a, b) / 2, math.dist(b, c) / 2)
        if ra <= 1e-9:
            segs.append(["L", b[0], b[1]])
            continue
        into = _towards(b, a, ra)
        outof = _towards(b, c, ra)
        k = ra * build.KAPPA
        segs.append(["L", into[0], into[1]])
        segs.append(["C", into[0] + (b[0] - into[0]) * (1 - build.KAPPA) * 0 + k * _u(b, into)[0],
                     into[1] + k * _u(b, into)[1],
                     outof[0] + k * _u(b, outof)[0], outof[1] + k * _u(b, outof)[1],
                     outof[0], outof[1]])
    segs.append(["L", pts[-1][0], pts[-1][1]])
    return segs


def _towards(a, b, d):
    n = math.dist(a, b) or 1.0
    return (a[0] + (b[0] - a[0]) * d / n, a[1] + (b[1] - a[1]) * d / n)


def _u(a, b):
    n = math.dist(a, b) or 1.0
    return ((a[0] - b[0]) / n, (a[1] - b[1]) / n)
