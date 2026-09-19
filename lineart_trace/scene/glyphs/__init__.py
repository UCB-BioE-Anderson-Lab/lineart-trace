"""Parameterised reusable figures: §3.7. A glyph is a function, not a drawing.

**A glyph is INSTANTIATED into real elements, not kept as a reference.** The alternative --
leaving a `{"kind": "glyph"}` node in the scene and expanding it at render time -- was
rejected for the same reason a style guide is resolved into the scene: a `type: view` may not
read a library, so a symbolic glyph would make every overlay unrenderable from a fixture, and
every measurement would need the library loaded to know how big anything is.

So placing a glyph adds a group of ordinary paths and regions, and the group's `provenance`
records the glyph's id, its VERSION and the arguments it was given. That is what makes
re-instantiation possible when the library moves on, and it is what `glyph.check` compares
to tell you a figure was drawn with a version that no longer exists.

**Every glyph draws with style ROLES and no literals.** That is the whole of what makes a
library styleable: a duplex placed in a figure obeys whatever guide the figure is under,
because it never says what colour it is. A glyph that wrote a literal would be a hole in
every theme.

**Every glyph carries anchors.** A duplex has a `five-prime` and a `three-prime`; a protein
has a `cleft`. Without them a glyph is a picture you still have to position by hand, which is
the thing §3.5 exists to end.
"""
import copy

from .. import build, measure, model

__all__ = ["register", "glyph", "catalogue", "place", "promote", "Glyph", "GlyphNotFound",
           "describe"]

_REGISTRY = {}


class GlyphNotFound(Exception):
    """A glyph nobody defines. Never a placeholder drawn as though the figure were finished."""


class Glyph:
    """One entry in the catalogue: what it is, what it takes, and how to build it."""

    def __init__(self, gid, fn, version, family, summary, params):
        self.id = gid
        self.fn = fn
        self.version = version
        self.family = family
        self.summary = summary
        self.params = params

    def build(self, element_name, args=None):
        """The group this glyph makes, with its anchors and provenance already on it.

        Arguments arrive as a DICT, not as keywords. As keywords they shared a namespace
        with this method's own parameters, so `dna.plasmid`, which quite reasonably takes a
        `name`, could not be placed at all -- "got multiple values for argument 'name'" from
        a glyph whose author did nothing wrong. A library's parameter names are its own
        business and must not collide with the machinery that calls it.
        """
        args = dict(args or {})
        bad = [k for k in args if k not in self.params]
        if bad:
            raise TypeError(
                f"{self.id} has no parameter {', '.join(sorted(bad))}; it takes "
                f"{', '.join(sorted(self.params))}")
        full = dict(self.params)
        full.update(args)
        children, anchors = self.fn(**full)
        g = build.group(element_name, children)
        g["anchors"] = {k: (v if isinstance(v, dict) else
                            {"how": "authored", "at": [float(v[0]), float(v[1])]})
                        for k, v in anchors.items()}
        g["tags"] = ["glyph", self.family]
        g["provenance"] = {"origin": "glyph", "tool": self.id,
                           "tool_version": self.version,
                           "params": {k: v for k, v in sorted(full.items())}}
        return g


def register(gid, version, family, summary=None, **defaults):
    """Decorate a builder to put it in the catalogue.

    The defaults ARE the parameter list: a glyph takes exactly what is declared here, and an
    argument that is not one of them is a refusal rather than a silently ignored keyword.
    """
    def wrap(fn):
        _REGISTRY[gid] = Glyph(gid, fn, version, family,
                               summary or (fn.__doc__ or "").strip().splitlines()[0],
                               defaults)
        return fn
    return wrap


def glyph(gid):
    """One glyph by id, or a refusal naming what the catalogue does have."""
    if gid not in _REGISTRY:
        near = sorted(g for g in _REGISTRY if g.split(".")[0] == gid.split(".")[0])
        raise GlyphNotFound(
            f"no glyph {gid!r} in the catalogue"
            + (f"; {gid.split('.')[0]} has {', '.join(near)}" if near else
               f"; the families are {', '.join(sorted({g.split('.')[0] for g in _REGISTRY}))}"))
    return _REGISTRY[gid]


def catalogue():
    """Every glyph, as ``{id: Glyph}``. §4's introspection requirement for the library."""
    return dict(sorted(_REGISTRY.items()))


def describe(gid):
    """What a glyph is and what it takes, as plain data."""
    g = glyph(gid)
    return {"id": g.id, "version": g.version, "family": g.family, "summary": g.summary,
            "parameters": {k: v for k, v in sorted(g.params.items())}}


def place(doc, gid, name, at=(0.0, 0.0), parent="", frame=None, args=None,
          align="top-left"):
    """Instantiate a glyph into a scene. Returns ``(scene, report)``.

    **`at` is where the glyph's TOP-LEFT lands**, not where its internal origin does, and
    that distinction is not pedantry. A duplex puts its 5′ label to the left of x=0 and a
    plate puts its row letters there; placed at the page corner by their internal origin,
    those labels sit off the paper. `align="origin"` asks for the old behaviour explicitly.

    The alignment is MEASURED after placement, because it needs the extent of text the glyph
    does not size itself -- a glyph writes no literals, so its labels have no font until the
    scene's guide supplies one. When the scene cannot measure them, the shift is skipped and
    the report says so rather than guessing at an offset.
    """
    _m = measure
    g = glyph(gid)
    el = g.build(name, args)
    if at and (at[0] or at[1]):
        el["transform"] = [1, 0, 0, 1, float(at[0]), float(at[1])]
    if frame:
        el["frame"] = frame
    out = model.add(doc, el, parent)
    where = f"{parent}.{name}" if parent else name
    # WHICH ROLES THE SCENE CANNOT HONOUR, reported at placement. A glyph writes no literals
    # -- that is what makes it styleable -- so a glyph placed in a scene with no guide has
    # elements with no colour and labels with no font, and the first sign of it is an
    # `Unmeasurable` from somewhere else entirely. Better to say so here.
    aligned, why = False, None
    if align == "top-left":
        try:
            box = _m.bbox(out, f"{parent}.{name}" if parent else name,
                          frame or model.frame_of(out, f"{parent}.{name}" if parent
                                                  else name))["value"]
        except Exception as e:                       # unmeasurable text, no font, no roles
            why = str(e)
        else:
            dx = float(at[0]) - box["x"]
            dy = float(at[1]) - box["y"]
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                node = model.find(out, f"{parent}.{name}" if parent else name)
                node["transform"] = model.compose(
                    [1, 0, 0, 1, dx, dy], node.get("transform") or list(model.IDENTITY))
            aligned = True

    have = set(((out.get("style") or {}).get("roles") or {}))
    wanted = sorted({e["role"] for _a, e, _p in model.walk(out)
                     if e.get("role") and (_a == where or _a.startswith(where + "."))})
    return out, {"glyph": gid, "version": g.version, "element": where,
                 "anchors": sorted(el["anchors"]),
                 "elements": 1 + len(el.get("children") or []),
                 "roles": wanted, "aligned": aligned,
                 "not_aligned_because": why,
                 "roles_not_in_scene": [r for r in wanted if r not in have]}


def promote(doc, address, gid, version="1"):
    """Capture a scene subtree as a glyph definition. Returns the definition, as plain data.

    A **captured** glyph, not a parameterised one: it records geometry, not a construction,
    so it takes no arguments. Saying so matters -- §3.7 asks that a user be able to promote
    any subtree, and pretending the result is the same kind of thing as a built glyph would
    make the catalogue two things under one name.
    """
    el = model.find(doc, address)
    if el is None:
        raise KeyError(address)
    body = copy.deepcopy(el)
    body.pop("relations", None)
    body.pop("fit", None)
    return {"format": "lineart.glyph/1", "id": gid, "version": str(version),
            "family": gid.split(".")[0], "kind": "captured",
            "summary": f"captured from {address}",
            "anchors": body.get("anchors") or {},
            "element": body}


def place_captured(doc, definition, name, at=(0.0, 0.0), parent="", frame=None):
    """Place a captured glyph. The mirror of :func:`promote`."""
    el = copy.deepcopy(definition["element"])
    el["name"] = name
    el["tags"] = sorted(set((el.get("tags") or []) + ["glyph", definition["family"]]))
    el["provenance"] = {"origin": "glyph", "tool": definition["id"],
                        "tool_version": str(definition.get("version", "1"))}
    if at and (at[0] or at[1]):
        el["transform"] = model.compose([1, 0, 0, 1, float(at[0]), float(at[1])],
                                        el.get("transform") or list(model.IDENTITY))
    if frame:
        el["frame"] = frame
    out = model.add(doc, el, parent)
    where = f"{parent}.{name}" if parent else name
    return out, {"glyph": definition["id"], "version": definition.get("version", "1"),
                 "element": where, "captured": True}


def check(doc):
    """Which glyph instances in this scene were drawn with a version the catalogue has moved past.

    The same staleness question a style guide's digest answers, for the same reason: what is
    in the scene is a resolved copy, and a resolved copy goes quietly out of date.
    """
    out = []
    for addr, el, _p in model.walk(doc):
        prov = el.get("provenance") or {}
        if prov.get("origin") != "glyph":
            continue
        gid, was = prov.get("tool"), str(prov.get("tool_version"))
        entry = {"element": addr, "glyph": gid, "version": was}
        if gid not in _REGISTRY:
            entry["status"] = "gone"
            entry["why"] = f"the catalogue has no {gid!r} any more"
        elif str(_REGISTRY[gid].version) != was:
            entry["status"] = "stale"
            entry["now"] = str(_REGISTRY[gid].version)
            entry["why"] = (f"drawn with {gid} v{was}; the catalogue is now "
                            f"v{_REGISTRY[gid].version}")
        else:
            entry["status"] = "current"
        out.append(entry)
    return {"instances": out,
            "stale": [e for e in out if e["status"] == "stale"],
            "gone": [e for e in out if e["status"] == "gone"]}


from . import molbio, lab, generic        # noqa: E402,F401  (registers the catalogue)
