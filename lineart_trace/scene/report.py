"""One report over a whole figure: §3.14, consolidated.

Every check in this toolkit answers a different question, and a person about to send a figure
somewhere wants one answer. This runs them all -- does it conform, does it solve, is it
legible at printed size, is it on style, were its glyphs drawn with a version that still
exists, and has it changed since the reference -- and returns a single structured report with
a verdict at the top.

**The verdict counts `unchecked` separately and never folds it into a pass.** A figure with
no errors and four things nobody could check is not the same as a figure with no errors, and
a report that shows them as the same is how "verified" comes to mean nothing.
"""
import os

from . import anchors, glyphs, model, raster, style as style_, validate, verify

__all__ = ["full", "regress", "verdict"]


def verdict(errors, warnings, unchecked):
    """A one-word headline. `unchecked` is never silently a pass."""
    if errors:
        return "wrong"
    if unchecked:
        return "unestablished"
    if warnings:
        return "questionable"
    return "clean"


def full(doc, guide=None, reference=None, dpi=150.0, rules=None, thresholds=None,
         tolerance=0.0):
    """Every check, in one report. Returns a dict; nothing is printed.

    `guide` adds the style lint, `reference` adds the visual regression. Both are optional
    and their absence is recorded as **unchecked**, not skipped: a report that quietly omits
    the style check reads exactly like one that passed it.
    """
    out = {"figure": doc.get("name"), "title": doc.get("title"),
           "canvas": dict(doc.get("canvas") or {}), "sections": {}}
    errors = warnings = 0
    unchecked = []

    bad, warn = validate.problems(doc)
    out["sections"]["conforms"] = {"problems": bad, "warnings": warn,
                                   "ok": not bad}
    errors += len(bad)
    warnings += len(warn)
    if bad:
        # Everything below assumes a scene. Running it on a document that is not one
        # produces cascades of nonsense rooted in the problems already reported.
        out["verdict"] = "wrong"
        out["totals"] = {"errors": errors, "warnings": warnings, "unchecked": 0}
        out["sections"]["stopped"] = ("the rest was not run: these checks assume a valid "
                                      "scene, and running them on one that is not "
                                      "produces cascades rooted in the problems above")
        return out

    solved, srep = anchors.solve(doc)
    out["sections"]["layout"] = {
        "settled": srep["settled"], "passes": srep["passes"],
        "moved": len(srep["moved"]),
        "unsatisfiable": srep["unsatisfiable"], "unsettled": srep["unsettled"],
        "anchors_unresolvable": srep["anchors"]["unresolvable"],
        "ok": srep["settled"] and not srep["unsatisfiable"]}
    if srep["moved"]:
        warnings += 1
        out["sections"]["layout"]["note"] = (
            f"{len(srep['moved'])} element(s) moved when this was solved, so the document "
            f"as stored is not the document as drawn")

    got = verify.check(doc, rules, thresholds, solve_report=srep)
    out["sections"]["print"] = got
    errors += got["errors"]
    warnings += got["warnings"]
    unchecked += [f"{u['rule']}: {u['element'] or '-'}" for u in got["unchecked"]]

    if guide is not None:
        linted = style_.lint(doc, guide)
        out["sections"]["style"] = linted
        errors += linted.get("errors", 0)
        warnings += linted.get("warnings", 0)
        unchecked += [f"style: {u['why']}" for u in linted.get("unchecked", [])]
    else:
        out["sections"]["style"] = {"unavailable": "no guide was given, so whether this "
                                                   "figure is on style is unknown"}
        unchecked.append("style: no guide given")

    gl = glyphs.check(doc)
    out["sections"]["glyphs"] = gl
    if gl["gone"]:
        errors += len(gl["gone"])
    if gl["stale"]:
        warnings += len(gl["stale"])

    if reference is not None:
        reg = regress(doc, reference, dpi, tolerance)
        out["sections"]["regression"] = reg
        if reg.get("changed_beyond_tolerance"):
            errors += 1
        elif reg.get("unavailable"):
            unchecked.append(f"regression: {reg['unavailable']}")
    else:
        out["sections"]["regression"] = {
            "unavailable": "no reference image was given, so whether this figure has "
                           "changed is unknown"}
        unchecked.append("regression: no reference given")

    out["totals"] = {"errors": errors, "warnings": warnings,
                     "unchecked": len(unchecked)}
    out["unchecked"] = unchecked
    out["verdict"] = verdict(errors, warnings, len(unchecked))
    return out


def regress(doc, reference, dpi=150.0, tolerance=0.0, diff_path=None):
    """Compare this figure to a stored reference image. §3.14's visual regression.

    `tolerance` is the fraction of pixels allowed to differ. A missing reference is
    **unavailable**, not a pass -- the first run of a regression check has nothing to compare
    against, and reporting that as success is how a regression suite comes to protect
    nothing.
    """
    import cv2
    if not os.path.exists(reference):
        return {"unavailable": f"no reference at {reference}; write one first, and until "
                               f"then nothing is being compared"}
    want = cv2.imread(reference, cv2.IMREAD_COLOR)
    if want is None:
        return {"unavailable": f"{reference} could not be read as an image"}
    got = raster.rasterize(doc, dpi)
    cmp_ = raster.compare(got, want)
    cmp_["reference"] = reference
    cmp_["dpi"] = dpi
    cmp_["tolerance"] = tolerance
    cmp_["changed_beyond_tolerance"] = (
        not cmp_.get("same_size", False)
        or cmp_.get("fraction", 0.0) > tolerance + 1e-12)
    if diff_path and cmp_.get("same_size"):
        cv2.imwrite(diff_path, raster.diff_image(got, want))
        cmp_["diff"] = diff_path
    return cmp_


# --------------------------------------------------------------------- in words
def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def narrate(doc, guide=None, reference=None, dpi=150.0):
    """What is in this figure, what styles it uses, and what is wrong with it -- in prose.

    §3.15 asks for "a scene inventory in plain language", and the counted one is not that: a
    dict of type frequencies is a thing to read a number out of, not a thing that tells you
    what you are looking at. This says it in sentences, and says the unwelcome parts too --
    a description that only mentions what went well is an advertisement.

    Returns ``(text, report)``; the report is :func:`full`, so nothing here is a second
    measurement of anything.
    """
    from . import measure, model
    got = full(doc, guide=guide, reference=reference, dpi=dpi)
    inv = measure.inventory(doc)["value"]
    canvas = doc.get("canvas") or {}
    unit = canvas.get("unit", "mm")
    lines = []

    what = doc.get("title") or doc.get("name") or "This figure"
    lines.append(
        f"{what} is {canvas.get('width', 0):g} by {canvas.get('height', 0):g} {unit}"
        f"{' on ' + canvas['background'] if canvas.get('background') not in (None, 'none') else ' on a transparent ground'}"
        f", and holds {_plural(inv['elements'], 'element')}.")

    panels = [a for a, el, _p in model.walk(doc) if "panel" in (el.get("tags") or [])]
    if panels:
        grid = (doc.get("layout") or {}).get("panels") or {}
        lines.append(
            f"It is laid out as {_plural(len(panels), 'panel')}"
            + (f" on a {grid.get('rows')} by {grid.get('cols')} grid" if grid else "")
            + f", lettered {', '.join(p.rsplit('-', 1)[-1].upper() for p in panels[:4])}"
            + ("..." if len(panels) > 4 else "") + ".")

    kinds = ", ".join(f"{n} {k}" for k, n in sorted(inv["types"].items())
                      if k != "group")
    if kinds:
        lines.append(f"The drawing is {kinds}.")

    if inv["roles"]:
        top = sorted(inv["roles"].items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        lines.append(
            f"It draws by role, not by literal value: {_plural(len(inv['roles']), 'role')} "
            f"in use, most often "
            + ", ".join(f"{r} ({n} times)" for r, n in top)
            + (f", under the guide {(doc.get('style') or {}).get('guide')!r}"
               if (doc.get("style") or {}).get("guide") else "") + ".")
    else:
        lines.append("Nothing in it asks for a style role, so it cannot be re-themed "
                     "without editing its elements.")

    if inv["colours"]:
        lines.append(f"It uses {_plural(len(inv['colours']), 'colour')}: "
                     + ", ".join(list(inv["colours"])[:6])
                     + ("..." if len(inv["colours"]) > 6 else "") + ".")
    if inv["fonts"]:
        lines.append(f"Type is set in {', '.join(sorted(inv['fonts']))}.")
    if inv["anchors"]:
        lines.append(f"{_plural(inv['anchors'], 'anchor')} are declared on it, so things "
                     f"attached to them move when what they are attached to moves.")

    prov = {}
    for _a, el, _p in model.walk(doc):
        origin = (el.get("provenance") or {}).get("origin")
        if origin:
            prov[origin] = prov.get(origin, 0) + 1
    if prov:
        lines.append("Where it came from: "
                     + ", ".join(f"{n} {k}" for k, n in sorted(prov.items())) + ".")

    t = got["totals"]
    verdict = got["verdict"]
    if verdict == "clean":
        lines.append("Nothing is wrong with it: every check ran and every check passed.")
    else:
        bits = []
        if t["errors"]:
            bits.append(_plural(t["errors"], "error"))
        if t["warnings"]:
            bits.append(_plural(t["warnings"], "warning"))
        if t["unchecked"]:
            bits.append(f"{t['unchecked']} thing(s) that could not be checked at all")
        lines.append(f"It is {verdict}: " + ", ".join(bits) + ".")
        for f in (got["sections"].get("print") or {}).get("findings", [])[:4]:
            lines.append(f"  — {f['severity']}: {f['message']} "
                         f"({f['element'] or 'the figure'})")
        for u in got["unchecked"][:3]:
            lines.append(f"  — unchecked: {u}")
    return "\n".join(lines), got
