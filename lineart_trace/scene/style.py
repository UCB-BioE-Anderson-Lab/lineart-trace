"""Style guides: §3.11. **Style is a role, not a value.**

An element asks for `emphasis-stroke`; the active guide decides what that means. A guide is
its own document -- tokens (the palette, the stroke scale, the type scale) and role bindings
that reference them -- so a scene can be re-rendered under a different guide, or a dark
variant of the same one, without touching its content.

**Applying a guide RESOLVES it into the scene, and that is deliberate.** The scene ends up
carrying the role table it was drawn with, not a pointer to a file. Two reasons, and the
first is not convenience:

* A `type: view` may not read a store. A scene that resolved its roles by loading a guide at
  render time would not be renderable from a fixture, and §3.15's overlays would stop being
  checkable without the toolkit running.
* A figure exported last year should still say what `emphasis-stroke` meant last year.

The cost is the obvious one -- a resolved copy goes stale when the guide changes -- so the
scene records the guide's name **and its SHA-256**, and `lint` reports a scene whose guide has
moved on since. The same trade, and the same mitigation, as tracing provenance.
"""
import copy
import hashlib
import json
import os
import re

from . import model

__all__ = ["load", "resolve", "apply", "adopt", "lint", "guide_dirs", "GuideNotFound",
           "digest", "SCHEMA_PATH", "STYLE_KEYS"]

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide.schema.json")

#: Every style property a role may bind. Kept here rather than inferred, so that a typo in a
#: guide is a refusal instead of a property nothing will ever read.
STYLE_KEYS = ("stroke", "stroke_width", "stroke_dash", "stroke_cap", "stroke_join",
              "fill", "opacity", "font_family", "font_size", "font_weight")

_REF = re.compile(r"^@([a-z0-9][a-z0-9-]*)\.([a-z0-9][a-z0-9-]*)$")


class GuideNotFound(Exception):
    """A guide that could not be resolved. Never a silent fallback to an unstyled scene."""


def guide_dirs():
    """Where guides are looked for. ``LINEART_GUIDE_PATH`` first, then `guides/` here."""
    out = []
    env = os.environ.get("LINEART_GUIDE_PATH")
    if env:
        out += [p for p in env.split(os.pathsep) if p]
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out.append(os.path.join(here, "guides"))
    return [d for d in out if os.path.isdir(d)]


def _find(name):
    if os.path.exists(name):
        return name
    for d in guide_dirs():
        p = os.path.join(d, f"{name}.json")
        if os.path.exists(p):
            return p
    raise GuideNotFound(
        f"no style guide {name!r} in {', '.join(guide_dirs()) or 'no guide directory'}. "
        f"Refusing to render unstyled: a figure drawn without the guide it asked for is a "
        f"figure that disagrees with every other one in the set.")


def digest(guide):
    """The SHA-256 of a guide's content, canonically ordered. What a scene records."""
    return hashlib.sha256(
        json.dumps(guide, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(name, _seen=None):
    """A guide by name or path, with everything it extends already merged in.

    Inheritance is a deep merge of tokens and a shallow one of roles: a child may add a
    token to a group without restating the group, and a role it names REPLACES the parent's
    rather than merging into it -- a half-overridden role is the kind of thing that looks
    applied and is not.
    """
    path = _find(name)
    with open(path, "r", encoding="utf-8") as fh:
        guide = json.load(fh)
    seen = list(_seen or [])
    key = guide.get("name", path)
    if key in seen:
        raise ValueError(f"guide inheritance cycle: {' -> '.join(seen + [key])}")
    parent_name = guide.get("extends")
    if not parent_name:
        return guide
    parent = load(parent_name, seen + [key])
    out = copy.deepcopy(parent)
    out.update({k: v for k, v in guide.items() if k not in ("tokens", "roles", "variants")})
    for group, items in (guide.get("tokens") or {}).items():
        out.setdefault("tokens", {}).setdefault(group, {}).update(items)
    out.setdefault("roles", {}).update(guide.get("roles") or {})
    out.setdefault("variants", {}).update(guide.get("variants") or {})
    return out


def _tokens(guide, variant=None):
    tokens = copy.deepcopy(guide.get("tokens") or {})
    if variant:
        v = (guide.get("variants") or {}).get(variant)
        if v is None:
            raise KeyError(
                f"guide {guide.get('name')!r} has no variant {variant!r}"
                + (f"; it has {', '.join(sorted(guide.get('variants') or {}))}"
                   if guide.get("variants") else " and no variants at all"))
        for group, items in (v.get("tokens") or {}).items():
            tokens.setdefault(group, {}).update(items)
    return tokens


def resolve(guide, variant=None):
    """The guide's roles with every ``@group.name`` replaced by its token. ``(roles, tokens)``.

    A reference to a token that does not exist is a refusal, not a property left as the
    literal string ``@colour.inkk`` -- which would render as a colour name no renderer knows
    and draw in black, silently.
    """
    tokens = _tokens(guide, variant)
    out, bad = {}, []

    def one(value, where):
        if isinstance(value, list):
            return [one(v, where) for v in value]
        if not isinstance(value, str):
            return value
        m = _REF.match(value)
        if not m:
            return value
        group, key = m.group(1), m.group(2)
        if group not in tokens or key not in tokens[group]:
            bad.append(f"{where}: {value} is not a token in this guide")
            return value
        return one(tokens[group][key], where)

    for role, body in sorted((guide.get("roles") or {}).items()):
        got = {}
        for k, v in sorted(body.items()):
            if k not in STYLE_KEYS:
                bad.append(f"roles/{role}: {k!r} is not a style property; "
                           f"known: {', '.join(STYLE_KEYS)}")
                continue
            got[k] = one(v, f"roles/{role}/{k}")
        out[role] = got
    if bad:
        raise ValueError("; ".join(bad))
    return out, tokens


def apply(doc, guide, variant=None):
    """A new scene carrying the guide's resolved roles. ``(scene, report)``.

    Nothing about the elements changes: an element asking for a role it had before now gets
    what this guide says that role is. A role an element asks for and the guide does not
    define is REPORTED -- it will fall through to the element's own literals, and silently
    doing that is how one figure in a set ends up subtly unlike the others.
    """
    roles, _tok = resolve(guide, variant)
    out = copy.deepcopy(doc)
    style = out.setdefault("style", {})
    had = dict(style.get("roles") or {})
    style["guide"] = guide.get("name", "unnamed")
    style["guide_sha256"] = digest(guide)
    if variant:
        style["variant"] = variant
    # ROLES THE SCENE ALREADY DEFINED AND THIS GUIDE DOES NOT ARE CARRIED OVER, not dropped.
    # Replacing the table wholesale looked like the clean reading of "the guide decides", and
    # it silently unstyled every element asking for a role the guide had never heard of --
    # which is exactly what happens the first time somebody adopts a traced figure and then
    # applies a house style. Carried over and REPORTED is the honest version: the figure does
    # not change under you, and you are told which parts are not yet on the guide.
    carried = {r: b for r, b in had.items() if r not in roles}
    style["roles"] = dict(roles)
    style["roles"].update(carried)
    asked = {}
    for addr, el, _p in model.walk(out):
        if el.get("role"):
            asked.setdefault(el["role"], []).append(addr)
    unknown = {r: v for r, v in sorted(asked.items()) if r not in roles}
    v = (guide.get("variants") or {}).get(variant or "", {})
    if v.get("canvas_background"):
        out.setdefault("canvas", {})["background"] = v["canvas_background"]
    return out, {
        "guide": style["guide"], "variant": variant,
        "roles_defined": len(roles),
        "roles_used": {r: len(v_) for r, v_ in sorted(asked.items())},
        "roles_not_in_guide": unknown,
        "roles_carried_over": sorted(carried),
        "elements_styled": sum(len(v_) for r, v_ in asked.items() if r in roles),
    }


def _signature(style):
    return tuple(sorted((k, json.dumps(v, sort_keys=True))
                        for k, v in (style or {}).items() if k in STYLE_KEYS))


def adopt(doc, guide=None, variant=None, prefix="adopted"):
    """Turn a scene's literal styles into roles. ``(scene, report)``.

    §3.11's "adopt an existing figure into a guide", and the path every traced figure has to
    take: the tracer recovers a colour and has no idea what it MEANS, so it can only write a
    literal. This groups elements by the exact style they carry, matches each group against
    the guide's roles where one matches exactly, and names the rest `adopted-01`, `-02`.

    **It does not guess at meaning.** A group that matches no role gets a numbered name, not
    an invented one like `emphasis-stroke` -- a confident guess about intent is the thing
    this repository refuses to put where somebody will read it as a fact.
    """
    out = copy.deepcopy(doc)
    known = {}
    if guide is not None:
        roles, _t = resolve(guide, variant)
        for name, body in roles.items():
            known[_signature(body)] = name
    groups, order = {}, []
    for addr, el, _p in model.walk(out):
        sig = _signature(el.get("style"))
        if not sig:
            continue
        if sig not in groups:
            groups[sig] = []
            order.append(sig)
        groups[sig].append(addr)

    assigned, made, near = {}, 0, {}
    for sig in order:
        if sig in known:
            assigned[sig] = known[sig]
        else:
            made += 1
            name = f"{prefix}-{made:02d}"
            assigned[sig] = name
            if guide is not None:
                near[name] = _nearest(dict(sig), known)

    new_roles = dict((out.get("style") or {}).get("roles") or {})
    converted, kept = [], []
    for addr, el, _p in model.walk(out):
        sig = _signature(el.get("style"))
        if not sig:
            continue
        role = assigned[sig]
        if el.get("role") and el["role"] != role:
            kept.append({"element": addr, "had": el["role"], "would_be": role})
            continue
        el["role"] = role
        if role not in new_roles:
            new_roles[role] = {k: v for k, v in el["style"].items() if k in STYLE_KEYS}
        el.pop("style", None)
        converted.append({"element": addr, "role": role})
    out.setdefault("style", {})["roles"] = new_roles
    return out, {
        "converted": len(converted),
        "roles_created": made,
        "roles_matched": len(order) - made,
        "roles": sorted(set(assigned.values())),
        "nearest": near,
        "left_alone": kept,
        "elements": converted,
    }


def _nearest(sig, known):
    """The guide role closest to this literal style, and which properties differ.

    Reported, never applied. Telling somebody that `adopted-01` differs from
    `structure-stroke` only in `stroke_width` is information they can act on; quietly
    binding it to `structure-stroke` because it is close would change the drawing on a
    guess.
    """
    best, best_diff = None, None
    for other_sig, name in known.items():
        other = dict(other_sig)
        shared = set(sig) | set(other)
        diff = sorted(k for k in shared if sig.get(k) != other.get(k))
        if best_diff is None or len(diff) < len(best_diff):
            best, best_diff = name, diff
    if best is None:
        return None
    return {"role": best, "differs_in": best_diff}


def lint(doc, guide=None, variant=None):
    """What is off-guide in this scene: literals, off-palette colours, off-scale sizes.

    Returns findings in the same shape `figure.verify` uses, so one reporter prints both.
    A scene with no guide is not linted against an imagined one -- that is `unchecked`.
    """
    findings, unchecked = [], []
    style = doc.get("style") or {}

    def add(rule, severity, element, message, **extra):
        findings.append(dict({"rule": rule, "severity": severity, "element": element,
                              "message": message}, **extra))

    if guide is None:
        if not style.get("guide"):
            unchecked.append({"rule": "style", "element": None,
                              "why": "this scene names no style guide, so there is nothing "
                                     "to hold it to"})
            return {"findings": findings, "unchecked": unchecked}
        roles = style.get("roles") or {}
        tokens = None
    else:
        roles, tokens = resolve(guide, variant)
        want = digest(guide)
        got = style.get("guide_sha256")
        if got and got != want:
            add("guide-stale", "warning", None,
                f"this scene was styled with a version of {style.get('guide')!r} that no "
                f"longer matches the guide on disk; re-apply it",
                had=got[:12], now=want[:12])

    palette = set()
    strokes = set()
    sizes = set()
    for body in roles.values():
        for k in ("stroke", "fill"):
            if body.get(k) and body[k] != "none":
                palette.add(body[k])
        if body.get("stroke_width") is not None:
            strokes.add(json.dumps(body["stroke_width"]))
        if body.get("font_size") is not None:
            sizes.add(json.dumps(body["font_size"]))

    for addr, el, _p in model.walk(doc):
        st = el.get("style") or {}          # LITERALS only: that is what lint is about
        if st:
            add("literal-style", "warning", addr,
                f"carries literal {', '.join(sorted(st))} instead of asking for a role; "
                f"`scene.adopt` converts these",
                properties=sorted(st))
        for k in ("stroke", "fill"):
            v = st.get(k)
            if v and v != "none" and palette and v not in palette:
                add("off-palette", "warning", addr,
                    f"{k} {v} is not in the guide's palette", colour=v, property=k)
        if st.get("stroke_width") is not None and strokes:
            if json.dumps(st["stroke_width"]) not in strokes:
                add("off-scale", "warning", addr,
                    f"stroke width {st['stroke_width']!r} is not on the guide's stroke "
                    f"scale", value=st["stroke_width"])
        if st.get("font_size") is not None and sizes:
            if json.dumps(st["font_size"]) not in sizes:
                add("off-scale", "warning", addr,
                    f"type size {st['font_size']!r} is not on the guide's type scale",
                    value=st["font_size"])
        if el.get("role") and el["role"] not in roles:
            add("unknown-role", "error", addr,
                f"asks for role {el['role']!r}, which this guide does not define",
                role=el["role"])

    order = {"error": 0, "warning": 1}
    findings.sort(key=lambda f: (order.get(f["severity"], 2), f["rule"],
                                 f["element"] or ""))
    return {"findings": findings, "unchecked": unchecked,
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            "guide": style.get("guide")}
