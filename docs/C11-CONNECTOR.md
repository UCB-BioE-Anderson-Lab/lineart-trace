# Using this repository as a C11 content world

**This repository is a content world**, and it is also a C11 installation in its own right.
Those are two different things and it is worth knowing which one you want.

| you want | you need |
|---|---|
| to *use* these capabilities from somewhere else | mount this repository — below |
| to *work on* this repository | nothing; it is already an installation. See `CLAUDE.md` |

## How to mount it

Add this repository's path to your installation's mounts file, one path per line:

    ~/cortex/engine/c11-mounts.txt          (or wherever your installation keeps it)

        ~/Documents/GitHub/lineart-trace

That is the whole of it, and it is deliberately the only thing your installation records.
**Your installation names a directory; this repository describes what is in it** — through
`c11-connector.json` at the root here, which names where the records live (`sharables/`), where
the programs live (`bin/`) and which file to read to work with them (this one).

Nothing here is written by a mounting installation. Mounted records are read and run, never
edited: writing a record under one of these ids forks it into your own store, where your
version shadows this one. That is the intended way to disagree with something here.

## What you get

**60 records: two hand-written commands, and 58 generated.**

| record | type | what it does |
|---|---|---|
| `scene.comparison` | **schema** | two or more renderings of a figure and what to do with them -- an onion... |
| `scene.document` | **schema** | the document a figure is made of -- a canvas at a physical size, named... |
| `scene.measurement` | **schema** | one measurement taken from a scene -- what was measured, of which element,... |
| `scene.overlay-payload` | **schema** | everything an annotated overlay draws, measured already -- the boxes,... |
| `scene.timeline` | **schema** | how a figure changes over time -- named marks, staged reveals, and tracks... |
| `style.guide` | **schema** | a named set of tokens -- palette, stroke scale, type scale, spacing -- and... |
| `scene.view.gallery` | **view** | Two or more renderings, looked at together. A pure function of `payload` |
| `scene.view.inspector` | **view** | The figure, clickable. A pure function of `payload`; performs no I/O |
| `scene.view.overlay` | **view** | The payload as an annotated SVG document. A pure function; it performs no I/O |
| `anchor.declare` | function | Give an element a named anchor, either a point you choose or a recipe over... |
| `animation.export` | function | Export one self-contained animated SVG, saying what it could not carry |
| `build.stage` | function | Turn a staged reveal into a timeline, with a mark at every stage |
| `connector.route` | function | Draw a connector between two points that routes around whatever is in the way |
| `container.fit` | function | Draw a box that fits around the elements it names, and re-fit it when they... |
| `diagram.lay` | function | Lay out a whole diagram: nodes sized to their labels, then edges routed... |
| `edge.join` | function | Join two nodes with an edge that goes round whatever is between them |
| `element.distribute` | function | Space elements evenly along an axis |
| `element.draw` | function | Add a primitive to a scene: a rectangle, ellipse, polygon, line, star or... |
| `element.pack` | function | Lay elements into another element's area, wrapping to new rows, refusing... |
| `figure.compare` | function | Say whether a figure has changed since its reference, and where |
| `figure.compare-visually` | function | Two versions of a figure together: wiped over each other, or side by side |
| `figure.describe` | function | Say what is in this figure, what styles it uses and what is wrong with it,... |
| `figure.inspect` | function | An interactive page: click anything in the figure and it tells you what it is |
| `figure.preview` | function | A preview at the figure's real printed size, with a ruler to check the... |
| `figure.reflow` | function | Retarget a figure to a different page: re-lay the panels, keep the... |
| `figure.report` | function | Run every check over a figure and give one verdict: clean, questionable,... |
| `figure.sheet` | function | A contact sheet: every variant, guide or build stage of a figure on one page |
| `figure.snapshot` | function | Write the reference image a later regression check compares against |
| `figure.verify` | function | Check a figure at its printed size: type too small, rules too fine, things... |
| `figure.watch` | function | Serve a live preview on loopback that re-renders whenever the scene file... |
| `font.list` | function | List the font families this installation can measure, and where they came from |
| `glyph.capture` | function | Capture part of a scene as a reusable glyph definition |
| `glyph.list` | function | List the glyph library, or say what one glyph takes |
| `glyph.place` | function | Place a reusable glyph -- a DNA duplex, a plasmid map, a gel, a plate --... |
| `guide.list` | function | List the style guides this installation can reach, and what each one is for |
| `lineart.check` | function | measure how faithfully a trace reproduced the ink it came from — rasterise... |
| `lineart.trace` | function | turn a raster picture of line art into real vector paths — open... |
| `node.add` | function | Add a diagram node, sized to hold its label in the font the guide supplies |
| `palette.choose` | function | Generate colours any reader can tell apart, or check a set you already have |
| `panel.lay` | function | Lay a grid of panel frames over the page, each with its own coordinates... |
| `plot.draw` | function | Build a plot panel from a data file: axes, ticks, marks and an optional fit |
| `relation.attach` | function | Declare that an element is positioned relative to another, and solve for where |
| `scene.annotate` | function | Draw the figure with its structure on top: names, boxes, anchors and relations |
| `scene.collide` | function | Find every pair of elements whose ink overlaps |
| `scene.create` | function | Start a new empty scene: a canvas at a physical size, and nothing on it yet |
| `scene.export` | function | Export a scene to SVG, sized in its own physical units |
| `scene.gap` | function | Measure the gap between two elements: zero when they touch, otherwise how... |
| `scene.inventory` | function | Say what is in a scene: how many of each type, which roles, colours, fonts... |
| `scene.measure` | function | Measure an element: its bounding box, in a frame you name and the unit... |
| `scene.probe` | function | Say what is at a coordinate: every element whose ink covers it, innermost last |
| `scene.remove` | function | Remove an element from a scene, and everything beneath it |
| `scene.rename` | function | Rename an element, and rewrite every reference that named it or anything... |
| `scene.solve` | function | Re-solve every relation in the scene, and report what moved and what could not |
| `scene.tree` | function | List what is in a scene: every element by name, indented, with its type... |
| `scene.validate` | function | Check that a file really is a scene, and say what is wrong with it if it... |
| `still.take` | function | The scene at one stage of a build, as an ordinary scene you can measure... |
| `style.adopt` | function | Convert a scene's literal colours and widths into named roles it can be... |
| `style.apply` | function | Apply a style guide to a scene, so every element drawn by role changes at once |
| `style.lint` | function | Say what in this scene is off-guide: literal styles, off-palette colours,... |
| `text.measure` | function | Measure text without drawing it, and say whether it fits a box you name |

The two `lineart.*` records are hand-written, because a record for a *command* is the only
honest kind to write by hand. **Everything else is GENERATED** — the function and view records
from the docstring of the code that performs them, the schema records from the JSON Schema
files every validator in this repository reads. `python3 -m lineart_trace.records` writes
them, `--check` reports drift, and a test fails on it. Edit the docstring, never the record.

The three **views** are pure functions from a payload to markup: no store, no capability, no
network, and — for the two interactive ones — no server either, because their interactivity is
client-side over data the payload already carries. That is why an inspector page opens from
`file://` and can be sent to somebody with none of this installed.

Every scene tool declares `accepts: scene.document` and most declare `produces`, and those
declarations are checked when a record is written. **Written one at a time they are a cycle
with no first element** — the schema names `scene.validate` as its checker and the checker
accepts the schema — so by hand you break it: the schema without its `code_verification`,
then the checker, then the schema again. → `docs/scene-format.md`

Style guides live in `guides/` and are found by name, or through `LINEART_GUIDE_PATH`. The
glyph library is code, in `lineart_trace/scene/glyphs/`, and every glyph in it is registered
from its own docstring like everything else.

## What this repository expects of you

**Nothing.** It has no opinion about which installation mounts it, does not read your store, and
cannot reach back into it. The dependency runs one way.

## If something does not work

- **The installation reports no toolkit mounted.** The path in the mounts file is wrong, or
  points somewhere without a `sharables/` directory. A mount that cannot be read is named rather
  than skipped, so the message will say which line it could not use.
- **A capability is found but will not run.** The entry needs this package's dependencies —
  numpy and opencv-python — importable by whatever `python3` resolves to. `pip install -e .`
  here once. Without them the entry fails with an ImportError, which is the intended loud
  failure rather than a silent empty result.
- **A record's example no longer matches what the command prints.** That is drift, and
  `pytest tests/test_sharables.py` is what catches it. The fix is to correct the record or the
  code, never to relax the test.
