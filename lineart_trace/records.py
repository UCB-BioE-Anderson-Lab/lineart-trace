"""Capability records, GENERATED from the docstrings beside the code they describe.

**Why there is a generator at all, and why it is phase-1 work.** A record is this
repository's public claim that a capability exists and behaves a stated way. Written by
hand, it is a second copy of a description whose first copy is the docstring, and the two
diverge the first time somebody edits one -- silently, because nothing compares them. So the
docstring is the source and this is the only writer.

**What a verb must carry.** The summary line of the docstring becomes the description, and a
``C11:`` block carries what a docstring has no other place to put -- the ontology's noun and
verb, the phrases somebody would search with, the schemas in and out, and one example
invocation::

    C11:
      noun: scene
      verb: export
      tags: svg, export, render
      accepts: scene.document
      produces: scene.document
      returns: the SVG, to --out or stdout
      phrases:
        - export a scene to SVG
      requires:
        - lineart_trace/scene/svg.py: the exporter
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null

**A verb with no docstring gets no record, and is NAMED.** Inventing a description from a
function's name puts a confident guess into an index that will return it to somebody who
believes it. The generator prints the offenders and exits non-zero.

**What the examples are and are not.** The generator RUNS each example and records what came
back. That makes the example true when it is written, and it makes `tests/test_sharables.py`
a detector of DRIFT -- code changed, record not regenerated -- rather than an oracle for
correctness. It cannot catch a record that was wrong the moment it was generated, because it
was generated from the behaviour. Said plainly here because a test that looks stronger than
it is does more harm than one that is honestly weak.
"""
import json
import os
import shlex
import subprocess
import sys

__all__ = ["generate", "parse_block", "main"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "sharables")
BIN = os.path.join(ROOT, "bin")

#: Written in this order, which is the order `c11 record --template` prints. A record read by
#: a person is read top to bottom and a stable order is the difference between a diff that
#: shows a change and one that shows a reshuffle.
KEY_ORDER = ["schema", "id", "type", "name", "description", "phrases", "tags", "noun",
             "verb", "entry", "accepts", "produces", "binds", "definition",
             "code_verification", "requires", "returns", "examples", "notes"]

MARKER = "GENERATED from"

LIST_KEYS = ("phrases", "tags", "requires")


def parse_block(doc):
    """The ``C11:`` block of a docstring, as a dict. None when there is no block.

    A deliberately small format -- ``key: value``, and ``key:`` followed by ``- item`` lines
    -- parsed strictly. It is not YAML and does not try to be: a full parser here would
    accept things this generator cannot mean, and the failure would surface as a record with
    a nonsense field rather than as a refusal at the line that caused it.
    """
    if not doc:
        return None
    lines = doc.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == "C11:"), None)
    if start is None:
        return None
    base = len(lines[start]) - len(lines[start].lstrip())
    out, key = {}, None
    for raw in lines[start + 1:]:
        if not raw.strip():
            continue
        ind = len(raw) - len(raw.lstrip())
        if ind <= base:
            break
        line = raw.strip()
        if line.startswith("- "):
            if key is None:
                raise ValueError(f"a list item before any key: {line!r}")
            out.setdefault(key, []).append(line[2:].strip())
            continue
        if ":" not in line:
            raise ValueError(f"not a key: {line!r}")
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value:
            out[key] = value
            key = None
        else:
            out.setdefault(key, [])
    for k in LIST_KEYS:
        if isinstance(out.get(k), str):
            out[k] = [x.strip() for x in out[k].split(",") if x.strip()]
    return out


def _summary(doc):
    """The docstring's first line: what this does, in the words somebody would look for."""
    for line in (doc or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _requires(items):
    out = []
    for item in items or []:
        path, _, note = item.partition(":")
        out.append({"path": path.strip(), "note": note.strip()})
    return out


def _schemas_here():
    got = {}
    for f in sorted(os.listdir(STORE)) if os.path.isdir(STORE) else []:
        if f.endswith(".json"):
            rec = json.load(open(os.path.join(STORE, f)))
            got[rec.get("id", f[:-5])] = rec.get("type", "function")
    return got


def _run_example(entry, arg_text):
    """Run one example the way `tests/test_sharables.py` will, and return what it prints."""
    argv = shlex.split(entry) + shlex.split(arg_text)
    argv[0] = os.path.join(BIN, argv[0])
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=600)
    got = (r.stdout or "").strip() or (r.stderr or "").strip()
    return shlex.split(arg_text), got, r.returncode


def generate(sources, write=True):
    """Build a record for every verb in `sources`, and the schema records. ``(records, problems)``.

    `sources` maps a subcommand name to ``(entry_command, function)``.

    **References resolve against what this pass will write, not only against what is on
    disk.** A schema names its checker and the checker declares the schema it accepts, so
    written one at a time they are a cycle with no first element. Resolving the whole pass
    at once is the only order that exists. An installation writing these through
    `c11 record` one file at a time has to break the cycle by hand -- schema without its
    `code_verification`, then the checker, then the schema again -- and
    `docs/scene-format.md` says so.
    """
    schemas = schema_records()
    known = _schemas_here()
    known.update({r["id"]: r["type"] for r in schemas})
    views, view_problems = _view_records(known)
    records, problems = [], []
    for sub, (entry_cmd, fn) in sorted(sources.items()):
        where = f"{fn.__module__}.{fn.__name__}"
        doc = fn.__doc__
        if not doc or not doc.strip():
            problems.append(f"{where}: no docstring, so no record. A description guessed "
                            f"from the name would be a guess in an index that returns it.")
            continue
        try:
            block = parse_block(doc)
        except ValueError as e:
            problems.append(f"{where}: bad C11 block: {e}")
            continue
        if block is None:
            problems.append(f"{where}: docstring has no C11: block, so the ontology has "
                            f"nothing to index it by and no record is written")
            continue
        missing = [k for k in ("noun", "verb", "phrases") if not block.get(k)]
        if missing:
            problems.append(f"{where}: C11 block is missing {', '.join(missing)}")
            continue

        rid = f"{block['noun']}.{block['verb']}"
        entry = f"{entry_cmd} {sub}"
        rec = {
            "schema": "clotho.sharable/1",
            "id": rid,
            "type": "function",
            "description": _summary(doc),
            "phrases": list(block["phrases"]),
            "noun": block["noun"],
            "verb": block["verb"],
            "entry": entry,
        }
        if block.get("tags"):
            rec["tags"] = list(block["tags"])
        for field in ("accepts", "produces"):
            ref = block.get(field)
            if not ref:
                continue
            # The kernel refuses a record naming a schema that is not in the store. This is
            # that rule, applied here, because an UNMOUNTED clone is a supported state and
            # must still be stopped from writing a claim nobody can check.
            if known.get(ref) != "schema":
                problems.append(
                    f"{where}: {field} names {ref!r}, which is "
                    f"{'not in sharables/' if ref not in known else 'a ' + known[ref]}, "
                    f"not a schema -- refusing to write a claim nobody can check")
                rec = None
                break
            rec[field] = ref
        if rec is None:
            continue
        if block.get("requires"):
            rec["requires"] = _requires(block["requires"])
        if block.get("returns"):
            rec["returns"] = block["returns"]
        if block.get("example"):
            argv, got, code = _run_example(entry, block["example"])
            ex = {"input": argv, "output": got}
            if code:
                ex["exit"] = code
            rec["examples"] = [ex]
        rec["notes"] = (f"{MARKER} `{where}` by `python3 -m lineart_trace.records`. "
                        f"Edit that docstring, not this file: a record written by hand is a "
                        f"second copy of a description that already exists beside the code, "
                        f"and the two drift silently.")
        records.append(rec)

    records = schemas + views + records
    problems += view_problems
    ids = {r["id"] for r in records}
    for r in records:
        cv = r.get("code_verification")
        if cv and cv not in ids and cv not in _schemas_here():
            problems.append(f"{r['id']}: code_verification names {cv!r}, which nothing "
                            f"here writes and which is not in the store")
    if write:
        for rec in records:
            path = os.path.join(STORE, rec["id"] + ".json")
            if os.path.exists(path):
                old = json.load(open(path))
                if MARKER not in (old.get("notes") or ""):
                    problems.append(f"{rec['id']}: a hand-written record is already here; "
                                    f"refusing to overwrite it")
                    continue
            ordered = {k: rec[k] for k in KEY_ORDER if k in rec}
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(ordered, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
    return records, problems


#: The schema records, whose SHAPE is read from the schema file beside the code and whose
#: prose is written here, once. A schema record is not generated from a docstring because it
#: does not describe a function -- but the same rule applies to the part that could drift:
#: the `definition` is never retyped, it is read from the file that every validator uses.
SCHEMAS = [
    {
        "id": "scene.document",
        "type": "schema",
        "name": "A scene",
        "description": "the document a figure is made of -- a canvas at a physical size, "
                       "named frames with units, and a tree of named elements carrying "
                       "geometry, style roles, anchors and provenance",
        "phrases": ["the shape of a scene", "what a scene file contains",
                    "the lineart scene format", "how a figure is represented",
                    "what a scene tool takes and returns"],
        "tags": ["scene", "svg", "figure", "format"],
        "noun": "scene",
        "verb": "define",
        "definition_path": "lineart_trace/scene/scene.schema.json",
        "code_verification": "scene.validate",
        "notes": "ONE JSON DOCUMENT, and the format is forced rather than chosen. A "
                 "capability is invoked as a command line with string arguments, so a tool "
                 "hands a scene to the next one as a PATH; and `accepts`/`produces` are "
                 "checked against a schema record whose definition is a JSON Schema, which "
                 "only JSON can be. Three consequences worth knowing before writing one: "
                 "element identity is the NAME PATH and nothing else, so a rename rewrites "
                 "every reference and reports the count; a frame owns the unit and "
                 "coordinates are bare within it, while a length that must hold on paper "
                 "whatever the nesting is written as a suffixed string like \"1.2pt\"; and "
                 "provenance carries the source, its digest, the tool and its parameters "
                 "but NO timestamp, because a clock in the document would break the "
                 "byte-identical re-run that determinism means. What a JSON Schema cannot "
                 "state -- unique sibling names, an anchor that collides with a child, a C "
                 "segment carrying six numbers -- is checked by `scene.validate`, which is "
                 "why this schema names one.",
    },
    {
        "id": "style.guide",
        "type": "schema",
        "name": "A style guide",
        "description": "a named set of tokens -- palette, stroke scale, type scale, spacing "
                       "-- and the role bindings that decide what `emphasis-stroke` means",
        "phrases": ["the shape of a style guide", "what a house style records",
                    "how a figure's roles are bound to values",
                    "the format of a theme"],
        "tags": ["style", "guide", "theme", "palette", "format"],
        "noun": "style",
        "verb": "define",
        "definition_path": "lineart_trace/scene/guide.schema.json",
        "notes": "A GUIDE IS ITS OWN DOCUMENT, and applying it RESOLVES it into the scene "
                 "rather than leaving a pointer. Two reasons, and the first is not "
                 "convenience: a `type: view` may not read a store, so a scene that "
                 "resolved its roles by loading a guide at render time could not be "
                 "rendered from a fixture and the overlays would stop being checkable "
                 "without the toolkit running; and a figure exported last year should still "
                 "say what `emphasis-stroke` meant last year. The cost is that the resolved "
                 "copy goes stale, so the scene records the guide's name AND its SHA-256, "
                 "and `style.lint` reports a scene whose guide has moved on. Same trade, "
                 "same mitigation, as tracing provenance. Tokens are referenced as "
                 "`@group.name`; a reference to a token that does not exist is refused "
                 "rather than left as a literal string, because `@colour.inkk` reaches a "
                 "renderer as a colour name nobody knows and draws in black.",
    },
    {
        "id": "scene.comparison",
        "type": "schema",
        "name": "Renderings to look at together",
        "description": "two or more renderings of a figure and what to do with them -- an "
                       "onion skin, side by side, a contact sheet of variants, or one at "
                       "true printed size",
        "phrases": ["the shape of a comparison", "what the gallery view is given",
                    "how two versions of a figure are shown together",
                    "the payload behind a contact sheet"],
        "tags": ["compare", "contact-sheet", "onion", "view", "format"],
        "noun": "comparison",
        "verb": "define",
        "definition_path": "lineart_trace/scene/comparison.schema.json",
        "notes": "AN ITEM MAY BE `unavailable` INSTEAD OF RENDERED, for the same reason "
                 "every section of an overlay payload may be: a variant that could not be "
                 "produced, shown as a blank panel in a contact sheet, reads as a variant "
                 "that produces nothing. The markup is carried IN the payload rather than "
                 "referenced, because the view that renders it may perform no I/O -- it "
                 "cannot go and fetch an SVG, so the producer hands it over.",
    },
    {
        "id": "scene.timeline",
        "type": "schema",
        "name": "A timeline over a scene",
        "description": "how a figure changes over time -- named marks, staged reveals, and "
                       "tracks animating opacity, colour, transform, draw-on or a camera",
        "phrases": ["the shape of a timeline", "what a staged build records",
                    "how an animation over a figure is described",
                    "the format of a lecture build"],
        "tags": ["animation", "timeline", "stages", "reveal", "format"],
        "noun": "timeline",
        "verb": "define",
        "definition_path": "lineart_trace/scene/timeline.schema.json",
        "notes": "A TIMELINE IS A SEPARATE DOCUMENT THAT SAYS HOW A SCENE CHANGES, and "
                 "sampling it returns A SCENE -- an ordinary `scene.document` with the "
                 "properties applied. That is what makes every other tool work on any "
                 "frame: measure it, check it at printed size, draw an overlay of it, "
                 "export it. Animation done in the exporter instead would have made frame "
                 "12 of a build unmeasurable, which is the state §3.15 exists to end for "
                 "static figures. A staged build is not a different kind of thing: "
                 "`stages` generates the tracks and a mark per stage, so a still of stage 3 "
                 "is the scene at that mark plus its rise -- at the mark itself the thing "
                 "being revealed is still at zero opacity and the still would show stage 2.",
    },
    {
        "id": "scene.overlay-payload",
        "type": "schema",
        "name": "An overlay payload",
        "description": "everything an annotated overlay draws, measured already -- the "
                       "boxes, anchors, relations and findings of one scene, in page "
                       "coordinates",
        "phrases": ["the shape of an overlay payload",
                    "what the annotated view is given",
                    "the data behind a scene overlay"],
        "tags": ["overlay", "view", "format", "annotation"],
        "noun": "overlay",
        "verb": "define",
        "definition_path": "lineart_trace/scene/overlay.schema.json",
        "notes": "EVERY SECTION MAY BE ABSENT INSTEAD OF EMPTY, and that is the whole "
                 "reason this payload exists rather than the view measuring the scene "
                 "itself. A view may not compute: a number a reader takes off the overlay "
                 "has to have been computed by whatever produced the payload, or there are "
                 "two answers in the system and a picture is one of them. So a section is "
                 "either its data or `{\"unavailable\": \"why\"}`, and the view draws the "
                 "reason -- because a layer that could not be gathered, rendered as a layer "
                 "with nothing in it, looks exactly like good news.",
    },
    {
        "id": "scene.measurement",
        "type": "schema",
        "name": "A measurement of a scene",
        "description": "one measurement taken from a scene -- what was measured, of which "
                       "element, in which frame and what unit, and the value",
        "phrases": ["the shape of a measurement", "what a measure tool returns",
                    "a measurement of a figure element",
                    "how a scene measurement is reported"],
        "tags": ["measurement", "scene", "format", "geometry"],
        "noun": "scene",
        "verb": "define",
        "definition_path": "lineart_trace/scene/measurement.schema.json",
        "notes": "THE ENVELOPE IS TYPED AND THE VALUE IS NOT, deliberately and for now. A "
                 "bounding box, a path length and a text metric do not share a payload "
                 "shape, and the choice was between one permissive `value` and a union that "
                 "would have to be edited for every measure §3.2 adds. `additionalProperties` "
                 "is NOT set to false here, and that is load-bearing rather than an "
                 "oversight: a schema that forbids extra properties rejects every field a "
                 "subclass adds, so setting it would make `superclass` unusable and this is "
                 "the record intended to be subclassed once the individual measures exist.",
    },
]


def _view_records(known):
    """Records for the views, from their own docstrings. ``(records, problems)``."""
    out, problems = [], []
    for rid, fn in sorted(view_sources().items()):
        where = f"{fn.__module__}.{fn.__name__}"
        doc = fn.__doc__
        if not doc or not doc.strip():
            problems.append(f"{where}: no docstring, so no record")
            continue
        block = parse_block(doc)
        if not block:
            problems.append(f"{where}: docstring has no C11: block")
            continue
        binds = block.get("binds")
        if not binds:
            # § 7.11.2 -- a view that does not say what it renders is the failure one level
            # up: markup produced from an unstated shape, so a producer's dropped key
            # becomes an empty section nobody can trace.
            problems.append(f"{where}: a view must declare `binds`")
            continue
        if "/" not in binds and known.get(binds) != "schema":
            problems.append(f"{where}: binds names {binds!r}, which is not a schema here")
            continue
        rec = {"schema": "clotho.sharable/1", "id": rid, "type": "view",
               "description": _summary(doc), "phrases": list(block.get("phrases") or []),
               "noun": block.get("noun"), "verb": block.get("verb"), "binds": binds}
        if block.get("tags"):
            rec["tags"] = list(block["tags"])
        if block.get("requires"):
            rec["requires"] = _requires(block["requires"])
        if block.get("returns"):
            rec["returns"] = block["returns"]
        missing = [k for k in ("noun", "verb", "phrases") if not rec.get(k)]
        if missing:
            problems.append(f"{where}: C11 block is missing {', '.join(missing)}")
            continue
        rec["notes"] = (f"{MARKER} `{where}` by `python3 -m lineart_trace.records`. "
                        f"A view performs no I/O: it reads no store, calls no capability "
                        f"and measures nothing, so it can be rendered from a fixture and "
                        f"checked without the toolkit running.")
        out.append(rec)
    return out, problems


def schema_records():
    """The schema records, with each definition read from its file rather than retyped."""
    out = []
    for spec in SCHEMAS:
        rec = {k: v for k, v in spec.items() if k != "definition_path"}
        with open(os.path.join(ROOT, spec["definition_path"]), encoding="utf-8") as fh:
            rec["definition"] = json.load(fh)
        rec["schema"] = "clotho.sharable/1"
        rec["notes"] = (rec.get("notes", "") + f" {MARKER} `lineart_trace.records.SCHEMAS` "
                        f"and `{spec['definition_path']}` by "
                        f"`python3 -m lineart_trace.records`; the definition is read from "
                        f"that file, which every validator in this repository uses, so the "
                        f"record and the checker cannot disagree. Edit the schema file or "
                        f"that table, not this record.")
        out.append(rec)
    return out


def sources():
    """Every command this repository generates records from."""
    from .scene import cli as scene_cli
    return {sub: ("lineart-scene", fn) for sub, fn in scene_cli.VERBS.items()}


def view_sources():
    """Every VIEW this repository generates a record from: ``{id: function}``.

    A view is not a command and has no `entry` -- it is a pure function from a payload to
    markup, and its record says what payload it binds to. It is generated from its
    docstring like everything else, because the argument for that has nothing to do with
    being runnable.
    """
    from .scene import inspect, overlay
    return {"scene.view.overlay": overlay.render,
            "scene.view.inspector": inspect.inspector,
            "scene.view.gallery": inspect.gallery}


def stale():
    """Which committed records no longer match the docstrings they came from.

    This is the drift detector, and it is the whole reason generation is worth anything: a
    generated record that nobody regenerated is a hand-written record with extra steps.
    """
    records, problems = generate(sources(), write=False)
    out = list(problems)
    for rec in records:
        path = os.path.join(STORE, rec["id"] + ".json")
        ordered = {k: rec[k] for k in KEY_ORDER if k in rec}
        if not os.path.exists(path):
            out.append(f"{rec['id']}: generated from its docstring and not in sharables/ "
                       f"-- run `python3 -m lineart_trace.records`")
            continue
        with open(path, encoding="utf-8") as fh:
            on_disk = json.load(fh)
        if on_disk != ordered:
            changed = sorted(set(ordered) | set(on_disk))
            differs = [k for k in changed if on_disk.get(k) != ordered.get(k)]
            out.append(f"{rec['id']}: the record and its source disagree on "
                       f"{', '.join(differs)} -- run `python3 -m lineart_trace.records`")
    return out


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if "--check" in args:
        problems = stale()
        for p in problems:
            print(f"records: {p}", file=sys.stderr)
        print(f"{len(problems)} record(s) out of step with their source", file=sys.stderr)
        return 1 if problems else 0
    records, problems = generate(sources(), write=True)
    for p in problems:
        print(f"records: {p}", file=sys.stderr)
    print(f"{len(records)} record(s) written from docstrings; {len(problems)} problem(s)",
          file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
