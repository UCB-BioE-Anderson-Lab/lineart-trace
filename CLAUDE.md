# lineart-trace

**A toolkit for making SVG vector art.** `docs/spec.md` is the plan — the scene / element /
anchor / style model, fifteen tool families with what *done* means for each, and a twelve-phase
build order. Phases 1–5 are the minimum at which the toolkit beats writing SVG by hand. Read it
before building anything; read `docs/design-log.md` before re-attempting anything clever about
fill detection or colour separation, because the approaches that were measured and abandoned
are recorded there with the numbers that killed them.

**What works today** is phase 0: the tracer, its 40-specimen corpus, and the round-trip
measurement. It survives as §3.10 (ingest) and §3.14 (verification).

---

## This repository is a C11 installation

`engine/c11-mounts.txt` is what makes it one. The kernel walks up from the working directory
looking for that file, the way git walks up for `.git`. Because it is here, everything this
project records — capabilities, notes, the router's learning log — lands **here**, and the
worlds named in that file are reachable for searching and running.

    ~/cortex/bin/c11 which "<what you want>"    rank candidates; read the descriptions
    ~/cortex/bin/c11 ontology <noun> <verb>     the exact index; it can answer "nothing is that"
    ~/cortex/bin/c11 show <id>  ·  run <id>     read one · perform it
    ~/cortex/bin/c11 record <file.json>         write one down (`record --template` prints the shape)
    ~/cortex/bin/c11 worlds                     what is mounted, in each world's own words

**Do not use `cortex c11`.** The Cortex dispatcher runs its subcommands with the working
directory forced to its own repository, so every press from in here is logged into *that*
repository's history instead of this one — silently, with the right answers coming back.
Verified 2026-09-19. `~/cortex/bin/c11` is the same program without the wrapper and resolves
this directory correctly.

**What the mount grants.** Mounting a world makes its capabilities yours to search and to
run — including the ones that reach a person. JCA, 2026-09-19: *"it should be able to invoke
things like sending an email that are cortex specific if we have mounted the repo to cortex.
If it's mounted, that is. But it should also behave normally in an unmounted mode."* So
running a mounted `mail.send` from here is intended rather than a transgression. What makes
it safe is not restraint at this end: that verb puts a review dialog in front of him, and the
dialog fires the same way whoever called it.

**Mounted records are read-only; the mounted repository is not.** Writing a record under a
mounted id forks it into this store, where the local copy wins — that is how you disagree
with a world you do not own. But a verb you legitimately run is an ordinary command, and
commands write files in the world they run in. **What is forbidden is committing.** One
checkout is canonical for a world; everything else reads it, runs from it, and leaves its
history alone. Nothing enforces that, which is why it is written here.

**Unmounted is a supported state.** A clone of this repository on a machine with no `~/cortex`
is still a working installation: its own records rank and run, and `c11 worlds` reports the
missing mount under NOT MOUNTED rather than pretending it is healthy. Verified on a real
clone, 2026-09-19.

## And it is a content world

`c11-connector.json` says what is here and `sharables/` holds it, so another installation can
mount this repository and reach these capabilities without copying anything.
→ `docs/C11-CONNECTOR.md`

`pytest tests/test_sharables.py` is the enforcer: every record must name an entry that exists,
`requires` that resolve, and examples that still reproduce. It is self-contained and does not
need any C11 installation to run.

## Four rules for the tools you are about to build

**1. Records are GENERATED from docstrings, not written by hand.** JCA, 2026-09-10, on the
sibling toolkit: *"You should not individually make wrappers that then get manually put into
C11. There is existing jsdoc ... and you should be able to, with code, convert them into the
wrappers that C11 needs."* The description of what a function does belongs beside the function,
in the comment its author already wrote; copying it into a separate file creates a second source
that drifts silently. **A function with no docstring gets no record and is NAMED** — inventing a
description from a function name puts a confident guess into an index that will happily return
it.

Hand-written records are for *commands*, and there are two. Everything else waits for the
generator, and **the generator is phase-1 work, not phase-12** — a suite of hundreds registered
retroactively is the failure this rule exists to prevent.

*The constraint that kills the naive version:* the sibling toolkit's generic invoker passes
arguments as one JSON array, which cannot express a numpy array, so it will not work for the
functions in `lineart_trace/` as they stand. Settle the calling convention together with the
scene format — a `scene → scene` tool takes a path and returns a path, and that **is**
expressible.

**2. Every scene tool declares its types.** A record may carry `accepts` and `produces` naming
the schema its input takes and its output has. Register the scene format first as a
`"type": "schema"` record, then declare both fields on every transform. The names are **checked
when a record is written** — naming a schema that is not in the store is refused — so this is
real, not decoration. What is *not* true: the dispatcher does not read either field at call
time. Nothing coerces or validates an argument. Declare them anyway; a uniformly typed suite is
what makes composition checkable later, and this would be the first real use of those fields
anywhere.

**3. The UI tools in §3.15 are `"type": "view"` records, not functions.** A view is a pure
function from a payload to markup that performs no I/O of its own — no store reads, no
capability calls, no network. Everything it displays arrives in its payload. That is what lets
an overlay be rendered from a fixture and checked without the toolkit running, and it is
exactly the shape of "annotated overlays: element names, bounding boxes, anchors, constraints".

**4. Name things with the nouns you mean.** Retrieval is a ranker, not a classifier, and
vocabulary is shared and rivalrous: a record that grabs generic words takes them from every
record that could have matched them. This suite will want *measure*, *align*, *fit*, *place*,
*render*, *compare* — all of them at once. The spec's own model already supplies the nouns
(scene, element, anchor, style, frame, glyph) and its families supply the verbs, which makes
`ontology` the primary index here and `which` the fallback. Keep the scene's element namespace
(`panel-b.enzyme.active-site`) and the record namespace (`scene.align`) distinct; they will look
alike.

## Development

    pip install -e ".[dev]"
    pytest                                     # 199 tests, plus tests/test_sharables.py
    python3 examples/benchmark.py --md docs/benchmark.md
