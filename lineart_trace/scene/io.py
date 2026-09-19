"""Reading and writing a scene document, byte-for-byte the same way every time.

**Determinism is a property of this file or it is not a property of the toolkit.**
Cross-cutting requirement §4 asks that the same inputs produce byte-identical output, and
`json.dumps` does not give that on its own: dict order follows insertion, floats print
whatever repr they carry (``0.07180000000000001``), and numpy scalars -- which the tracer
produces by the thousand -- are not JSON at all.

So every writer in the toolkit goes through :func:`dumps`, which

* orders keys by :data:`KEY_ORDER` rather than by insertion or by chance,
* rounds every number to :data:`PLACES` decimals and drops a trailing ``.0``,
* unwraps numpy scalars into plain Python numbers,
* and keeps arrays of scalars on ONE line while nesting everything else.

That last rule is what makes a scene diffable. ``json.dumps(indent=2)`` puts every number of
every Bezier segment on its own line, so a 3000-curve trace becomes 20000 lines and a moved
control point is unreadable in a diff. Inline scalar arrays give one line per segment:
``["C", 640, 96, 720, 176, 720, 304]`` -- so a diff names the segment that moved.
"""
import json

__all__ = ["dumps", "loads", "load", "dump", "PLACES"]

#: Decimals kept on every number written. Six is below the precision of any real drawing and
#: above the noise floor of the fitting, so a re-run diffs clean instead of jittering.
PLACES = 6

#: Key order for the whole format, flat. A key means the same thing wherever it appears, so
#: one table covers scene, element, geometry, anchor and provenance without a per-node
#: schema of its own -- and a key added to the format but not here still writes, sorted
#: after the known ones, rather than raising in a serializer.
KEY_ORDER = [
    # scene
    "format", "name", "title", "description", "canvas", "frames", "style", "elements",
    # canvas / frame
    "width", "height", "unit", "background", "parent", "transform",
    # element
    "type", "frame", "role", "tags", "locked", "anchors", "provenance", "geometry",
    "children",
    # style
    "stroke", "stroke_width", "stroke_dash", "stroke_cap", "stroke_join", "fill",
    "fill_rule", "opacity", "font_family", "font_size", "font_weight", "guide", "roles",
    # provenance
    "origin", "source", "sha256", "tool", "tool_version", "params",
    # anchor
    "how", "by", "at", "dir",
    # geometry
    "kind", "closed", "text", "align", "baseline", "href", "glyph", "args", "d", "loops",
    # measurement envelope
    "scene", "measure", "target", "value",
]
_RANK = {k: i for i, k in enumerate(KEY_ORDER)}


def _rank(k):
    """Known keys in declared order, unknown keys alphabetically after all of them."""
    return (_RANK.get(k, len(_RANK)), k)


def _number(x):
    """A number as it will be written: rounded, integral floats shortened, no negative zero.

    ``-0.0`` is a real hazard rather than a nicety -- it compares equal to ``0.0`` and prints
    differently, which is exactly the shape of a difference that a determinism test cannot
    see and a diff reports every run.
    """
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    v = round(float(x), PLACES)
    if v == 0:
        v = 0.0
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def _scalar(x):
    """One JSON scalar, or None if `x` is not one. numpy scalars unwrap through ``.item()``."""
    if x is None:
        return "null"
    if isinstance(x, (bool, int, float)):
        return _number(x)
    if isinstance(x, str):
        return json.dumps(x, ensure_ascii=False)
    item = getattr(x, "item", None)
    if item is not None and getattr(x, "ndim", None) == 0:
        return _scalar(item())
    return None


def _emit(o, depth, out):
    pad = "  " * depth
    s = _scalar(o)
    if s is not None:
        out.append(s)
        return
    if isinstance(o, dict):
        if not o:
            out.append("{}")
            return
        items = sorted(o.items(), key=lambda kv: _rank(kv[0]))
        out.append("{\n")
        for i, (k, v) in enumerate(items):
            out.append("  " * (depth + 1) + json.dumps(str(k), ensure_ascii=False) + ": ")
            _emit(v, depth + 1, out)
            out.append(",\n" if i < len(items) - 1 else "\n")
        out.append(pad + "}")
        return
    if isinstance(o, (list, tuple)):
        if not o:
            out.append("[]")
            return
        flat = [_scalar(x) for x in o]
        if all(f is not None for f in flat):
            out.append("[" + ", ".join(flat) + "]")
            return
        out.append("[\n")
        for i, v in enumerate(o):
            out.append("  " * (depth + 1))
            _emit(v, depth + 1, out)
            out.append(",\n" if i < len(o) - 1 else "\n")
        out.append(pad + "]")
        return
    tolist = getattr(o, "tolist", None)
    if tolist is not None:
        _emit(tolist(), depth, out)
        return
    raise TypeError(f"cannot write {type(o).__name__} into a scene: {o!r}")


def dumps(doc) -> str:
    """The document as canonical text, ending in a newline."""
    out = []
    _emit(doc, 0, out)
    out.append("\n")
    return "".join(out)


def loads(text: str):
    """Parse scene text. No normalisation -- what is on disk is what you get."""
    return json.loads(text)


def load(path: str):
    """Read a scene from a file, or from stdin when `path` is ``-``."""
    if path == "-":
        import sys
        return loads(sys.stdin.read())
    with open(path, "r", encoding="utf-8") as fh:
        return loads(fh.read())


def dump(doc, path: str) -> None:
    """Write a scene canonically, to a file or to stdout when `path` is ``-``."""
    text = dumps(doc)
    if path == "-":
        import sys
        sys.stdout.write(text)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
