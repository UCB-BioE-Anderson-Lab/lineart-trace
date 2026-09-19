# The scene format

**A scene is one JSON document.** It is the source of truth for a figure; SVG is an export
and nothing in this toolkit reads one back. This file says what is in a scene, how one tool
hands a scene to the next, and — the part worth reading twice — what each decision costs.

The shape is in [`lineart_trace/scene/scene.schema.json`](../lineart_trace/scene/scene.schema.json),
which is its single source: the validator reads it, and the `scene.document` record's
`definition` is generated from it rather than retyped.

---

## A scene, whole

```json
{
  "format": "lineart.scene/1",
  "name": "pol-entry",
  "title": "Polymerase entry channel",
  "canvas": { "width": 90, "height": 60, "unit": "mm", "background": "none" },

  "frames": {
    "page": { "unit": "mm" },
    "art":  { "parent": "page", "unit": "px",
              "transform": [0.0718, 0, 0, 0.0718, 4, 4] }
  },

  "style": { "guide": "figure-default", "roles": {} },

  "elements": [
    {
      "name": "enzyme",
      "type": "group",
      "frame": "art",
      "provenance": { "origin": "trace", "source": "docs/lead.png",
                      "sha256": "9f2c…", "tool": "lineart.trace",
                      "tool_version": "0.2.0", "params": { "colors": 0 } },
      "anchors": {
        "active-site": { "how": "authored", "at": [612, 388], "dir": [0, -1] },
        "cleft":       { "how": "discovered", "by": "concavity",
                         "params": { "depth": 0.25 }, "at": [640, 402] }
      },
      "children": [
        { "name": "outline", "type": "path", "role": "structure-stroke",
          "style": { "stroke_width": "1.2pt" },
          "geometry": { "kind": "path", "closed": true,
            "d": [ ["M", 512, 96],
                   ["C", 640, 96, 720, 176, 720, 304],
                   ["Z"] ] } }
      ]
    }
  ]
}
```

## Why JSON, and why it was not a choice

Three constraints, none negotiable, and together they leave one answer.

1. **A capability is invoked as a command line with string arguments.** The dispatcher builds
   `shlex.split(entry) + args` and runs it. A numpy array does not cross that boundary and
   an in-memory scene does not either. **A path does.**
2. **`accepts` and `produces` are checked when a record is written**, against a schema record
   whose `definition` is a JSON Schema. Only JSON can be checked by one.
3. **Determinism** (spec §4): the same inputs produce byte-identical output. That rules out
   timestamps in the document, insertion-ordered keys, and whatever `repr` a float happens
   to carry.

So: the scene is JSON, tools hand it along as a path, and every writer goes through
`lineart_trace.scene.io.dumps`.

---

## The five rules

### Names are sibling-scoped; the address is the join

`enzyme.outline`, `panel-b.enzyme.active-site` — the spec's own spelling. A name is unique
among its siblings and matches `[a-z0-9][a-z0-9-]*`, **with no dot**, so an address splits
unambiguously. Anchors share the element's child namespace, which is what lets an anchor
address resolve without a second separator; a child and an anchor of the same name is
refused, so resolution is total.

**The cost, and it is real:** there is no second, stable identity. A rename moves every
address beneath it, and `scene.rename` rewrites every reference and reports the count.

*Rejected: immutable uids alongside names.* A document full of `uid:7f3a2c` is unreadable to
the model that has to edit it, and a second identity kept in sync with the first is the same
two-sources-that-drift failure that keeps records generated rather than written. A reference
that goes stale is a validation error here, not a silent mis-attach.

### A frame owns the unit; coordinates are bare

Wrapping every coordinate as `{"v": 12, "unit": "mm"}` is unbearable for a 400-point path. So
a frame declares its unit, an element's coordinates are in its frame (inherited from the
nearest ancestor that names one), and **a length that must hold on paper regardless of
nesting is a suffixed string**: `"stroke_width": "1.2pt"` is 1.2 pt of paper wherever it sits.

> Bare number → the element's frame. Suffixed string → the page.

The page frame is the one with no parent, and its unit must be the canvas unit — otherwise a
page length would mean two things. `scene.validate` enforces that.

### Geometry has exactly one spelling

`M`, `L`, `C`, `Z`, and nothing else; arcs and quadratics convert at ingest. Every
measurement tool then handles one case instead of seven — the difference between path length
being correct and being correct *for the segment types somebody remembered*. A `path`
element holds **one** run; several runs is what a `region`'s `loops` are for.

JSON Schema can bound a segment array and cannot tie its length to its first element, so
`["C", 1, 2]` passes the schema and is not a curve. That check lives in `scene.validate`,
which is why `scene.document` names a `code_verification`.

### Style is a role; literals are legal and lint

An element carries a `role`; the guide decides what it means. A literal override is legal,
because the tracer necessarily produces them — it recovers a colour and has no idea what the
colour *means*. §3.11's job is turning those into roles; linting flags them. Forbidding them
would have made the ingest path impossible.

### Provenance has no clock

`source`, `sha256`, `tool`, `tool_version`, `params`. **No timestamp anywhere in the
document** — a clock would break the byte-identical re-run that determinism means. When a
scene was made belongs in the installation's log, not in the scene. Raster images are
referenced by path and digest, never inlined as base64, for the same reason plus a diff that
stays readable.

---

## How one tool hands a scene to the next

**In process**, every transform is `scene → scene` and every measurement is `scene → data`.
Pure functions returning new documents; no session, nothing that requires a prior call.

**Across the capability boundary**, a path in and a path out:

```
lineart-scene <verb> --in a.json --out b.json [options]
```

- `--in -` and `--out -` are stdin and stdout, so tools compose in a pipe as well as by file.
- **Payload on stdout, human report on stderr** — the convention `lineart-trace` already
  uses, and what lets a record's example check a one-line report rather than a megabyte of
  scene.
- `--out` is required on anything that transforms. In-place is `--in-place`, spelled out: a
  tool that silently overwrites its input is the destructive edit this toolkit exists to end.

### Exit codes, one scheme for the binary

| code | meaning |
|---|---|
| 0 | it worked |
| 1 | the answer is no — `validate` on a document that is not a scene |
| 2 | it could not be established: unreadable, unparseable, absent |
| 3 | refused: well formed, and cannot be satisfied |

2 is the one that earns its place. "Could not check" reported as "wrong" is a fabricated
finding; reported as success it is absence collapsing into success, on the one path whose job
is to catch that. `lineart-trace` already exits 2 on an unreadable source; this is that rule
made general, and it is the three-answer checker contract as a special case rather than an
exception to it.

---

## Anchors and relations

An element may carry **anchors** -- named points, each one `authored` (a point somebody
chose), `derived` (a recipe over the element's own geometry: `bbox.ne`, `centroid`,
`path.mid`, `extreme.top`) or `discovered` (`concavity`, the deepest inlet of a silhouette).
A derived anchor stores **both** its recipe and its resolved position: the recipe is what
makes it reproducible, the position is what lets a view render the scene without recomputing
anything.

It may also carry **relations** -- `attach`, `align`, `clear`, `inside` -- each naming an
address to relate to. `scene.solve` re-solves them all and reports what moved, what could not
be satisfied and what never settled.

Three properties are load-bearing and each has a test:

- **Editing one element updates everything attached to it.** Move the enzyme, re-solve, and
  the duplex and the leader follow.
- **Solving twice changes nothing.** Relations are declarations, not accumulating nudges.
- **An unsatisfiable layout is an explicit error.** A label that cannot fit inside a box
  smaller than itself is reported with the two sizes, never approximated.

**Relations translate, and only translate.** A relation that could scale would silently
change a stroke weight.

**Anchors and geometry live in the same space.** An element's own `transform` maps that space
to its parent's, so an anchor moves with its shape. `model.element_to_page` is the single
definition of where an element is, used by measurement, by the recipes, by the solver and by
the exporter -- see the design log for what happened when it was three definitions.

## Measurement

`scene.measure` takes the **tight** extent of a curve, not the hull of its control points --
on a single quarter-turn arc the cheap version is a third too tall. Area, centroid and length
are computed in closed form by integrating the polynomial exactly, never by sampling, because
a sampled curve is always *inside* the true one and every error runs in the direction that
hides.

Text is measured from the font file: advance, ascent, descent, line height, cap and x-height,
and the glyphs' own ink box. No rendering. Every text measurement names the face it read and
its SHA-256, because a metric is only reproducible alongside the file it came from, and a
family that is not on the machine is a **refusal** -- substituting another face produces a
figure that measures fine here and overflows where it prints. Kerning is not read, so an
advance is an over-estimate: safe for "will it fit", slightly wrong for "where exactly does
it end".

A text element with an unresolvable font raises `Unmeasurable` rather than reporting a zero
extent. Scanning tools record it; single measurements exit 2, "could not be established".

## Verification

`figure.verify` checks a scene at the size it will be **printed**: type below a floor in
points, rules too fine, features too close, contrast against the *actual* background,
colours indistinguishable under each of three kinds of dichromacy, elements off the canvas,
glyphs the font does not have, and relations that never solved.

Findings collapse: thirteen rungs in one colour that fails contrast is **one** defect with
one fix. A check that cannot be substantiated is `unchecked` and never folded into a pass --
a transparent background makes contrast unknown, not fine.

## Views

`scene.view.overlay` is a `type: view` record: a pure function from a payload to markup that
performs no I/O and **computes nothing**. Its payload, `scene.overlay-payload`, is produced
separately and carries every box, anchor and relation already measured, so a number a reader
takes off the overlay is the same number `scene.measure` reports rather than a second answer
from a second code path.

Any section of that payload may be `{"unavailable": "why"}` instead of its data, and the view
draws the reason. **An empty section looks exactly like good news**, so absence and emptiness
must not look the same.

## Style: a role, not a value

A guide is its own document (`style.guide`): **tokens** -- a palette, a stroke scale, a type
scale, spacing -- and **roles** that reference them as `@group.name`. An element asks for
`emphasis-stroke`; the guide decides what that is. Guides inherit (`extends`) and carry
named **variants** (`dark`, `print`) that override tokens, so the same scene exports light
and dark without one element being edited.

**Applying a guide resolves it into the scene**, and that is deliberate. A `type: view` may
not read a store, so a scene that resolved its roles at render time could not be rendered
from a fixture; and a figure exported last year should still say what `emphasis-stroke` meant
last year. The cost is a resolved copy that goes stale, so the scene records the guide's name
**and its SHA-256** and `style.lint` reports a scene whose guide has moved on -- the same
trade, and the same mitigation, as tracing provenance.

Roles the scene already defines and the guide does not are **carried over, not dropped**:
replacing the table wholesale silently unstyles everything the guide has not heard of, which
is exactly what happens the first time somebody adopts a traced figure and then applies a
house style.

`model.effective_style` is the one resolution of role-then-literal, shared by the renderer,
the measurer and the checker. It was three readings of `el["style"]`, which was harmless
while everything carried literals and wrong the moment an element asked for a role instead: a
figure drawn entirely by role measured as having no stroke width, no type size and no colour,
so every check passed. **A style system that makes a figure less checkable is worse than
none.**

### Palettes

`palette.choose` generates colours by a deterministic greedy search, maximising the **worst**
separation across normal vision and all three dichromacies, subject to contrast against the
background. It reports how many it could produce rather than relaxing the threshold quietly.

Two things the shipped guide learned the hard way: a series generated only against *itself*
clashes with the line work it sits beside, so the series is generated against the guide's own
ink, accent, support and muted; and **a palette is relative to its background**, so the dark
variant carries its own series rather than reusing the light one at 2.2:1.

## Layout: panels, arranging, connectors

A **panel is a frame**, not a rectangle drawn in the right place: each gets its own
coordinate space with a transform onto the page, so its contents are authored at whatever
size suits them. The grid is recorded on the scene (`layout.panels`), which is what makes
**reflow** possible -- change the page, recompute the transforms.

`reflow` is reflow and not scale: a drawing placed with `into_panel` is re-fitted to the new
panel, and a 10 pt label is still 10 pt. The distinction is recorded on the element as `fit`;
without it, reflow re-laid the panels and left a 45 mm drawing sitting in a 23 mm one.

`into_panel` **re-parents the element's frame**. An element that declares its own frame --
everything traced does -- has a coordinate context that starts at that frame, not at whatever
group it sits in. Move it under a panel without re-parenting and it renders exactly where it
was: the move succeeds and means nothing.

**Connector routing avoids obstacles by searching.** A* over an occupancy grid built from
obstacle boxes inflated by a stated clearance, with a turn penalty so two bends beat six. The
report carries the clearance actually achieved, measured the way `scene.gap` measures it, and
a route that cannot exist is refused rather than drawn straight through. The grid is bounded
by the page, and a connector is allowed to leave the thing it is attached to.

## Glyphs: a function, not a drawing

A glyph is **instantiated into real elements**, not left as a reference. The alternative --
a `{"kind": "glyph"}` node expanded at render time -- was rejected for the reason a style
guide is resolved into the scene: a `type: view` may not read a library, so a symbolic glyph
would make every overlay unrenderable from a fixture, and every measurement would need the
library loaded to know how big anything is.

So placing a glyph adds ordinary paths and regions, and the group's `provenance` records the
glyph's id, **version** and arguments. `glyph.check` compares that to the catalogue and
reports a figure drawn with a version that has moved on, or one that is gone.

Three properties, each enforced over the **whole catalogue** by a parameterised test rather
than for a chosen few:

- **Every glyph draws with roles and writes no literals.** That is the whole of what makes a
  library styleable; a literal would be a hole in every theme.
- **Every glyph carries anchors.** Without them a glyph is a picture you still have to
  position by hand.
- **`at` is where the glyph's top-left lands**, measured after placement, not where its
  internal origin does. A duplex puts its 5′ label left of x=0; placed by its origin at the
  page corner, that label is off the paper.

## Data: scales, marks, annotations

A scale is an explicit object -- domain in, range out, ticks on request -- because the thing
that goes wrong in hand-built figures is an axis whose ticks and whose data disagree about
what the domain was. Everything drawn goes through the same scale that drew the axis, and a
test asserts that every tick lands where its scale says.

**The range's order is its direction, and there is no flag.** `linear((0, 100), (57, 6))`
puts 0 at y=57. There was a `flip` argument as well; two ways to say the same thing can
contradict each other, and on the first real plot they did -- zero at the top of the panel
and the significance bracket at the bottom, silently.

A log scale refuses a non-positive domain and a categorical scale refuses a category it was
not given, rather than clamping. A fit returns its numbers -- slope, intercept, r², n,
residual standard error -- with the drawing, because a fitted line whose numbers live only in
the picture is a number nobody can check; and a confidence band that runs off the panel is
held inside it and the number of clamped points is reported, because a band silently trimmed
is an interval drawn narrower than it is.

Plot groups carry `provenance` naming the data file and its SHA-256, so "regenerates when the
data changes" is a question the figure can answer about itself.

## Diagrams: nodes that size themselves

**A node is sized to its contents, measured** in the font the guide supplies. That is the
whole difference between this and drawing boxes: a diagram whose boxes were guessed at has to
be nudged every time a label changes.

Edges attach to node anchors, pick the sides that face each other, and route with
`layout.route`, so an edge with something in its way goes round it and reports the clearance
it achieved. **When nothing is in the way it is the straight line** -- the grid snaps a
route's interior while its ends stay exact, so two boxes almost in line got an arrow with two
little jogs in it. A second edge between the same pair is offset sideways and its label
staggered along it, because a state machine is mostly pairs.

Layering is longest-path, and a **cycle is named rather than looped on**: a state machine is
full of cycles and still has to be drawable. Layers are centred on a common axis, because
left-aligning nodes of different widths gives every edge a sideways kink.

Containers fit what they name and **re-fit** when it changes. Tree keys are slugged into
element names and kept as labels -- a tree of `ampR` and `EcoRI` is the obvious use, and
those are not element names.

## Animation: a frame is a figure

A timeline (`scene.timeline`) is a **separate document that says how a scene changes**, and
sampling it returns *a scene* -- an ordinary `lineart.scene/1` with the properties applied.
Every tool then works on any frame: measure it, check it at printed size, draw an overlay of
it, export it. Animation done in the exporter instead would have made frame 12 of a build
unmeasurable, which is the state §3.15 exists to end for static figures.

A staged build is not a different mechanism: `stages` generates the tracks and a mark per
stage. A still of a stage is taken **after its rise**, because at the mark itself the thing
being revealed is still at zero opacity and the still would show the stage before.

`draw` trims real geometry rather than setting a dash offset, so a half-drawn stroke
*measures* as half drawn. A morph needs the two paths to have the same verbs in the same
order; resampling one to match is possible and is not done, because guessing which point
becomes which is exactly the confident guess this toolkit refuses elsewhere.

The SVG export carries what SMIL can carry — opacity, stroke, fill — and **names what it
cannot** in a comment. An explainer that silently lost its draw-on is worse than one that
refuses to pretend.

## Looking at it, and steering it

§3.15 is the interactivity requirement: *the author must be able to see what the design
process is doing, and steer it.* Four pages and a server, and the split between them is the
view rule.

**`scene.view.inspector`** binds the overlay payload: the figure with every element
clickable, and a panel saying what the clicked thing is — address, role, **z-order**, box in
real units, anchors, resolved style. The interactivity is client-side, driven by data the
payload already carries, so the page opens from `file://` with nothing installed and can be
sent to somebody who has none of this.

**`scene.view.gallery`** binds `scene.comparison`: two or more renderings, as an **onion
skin** with a wipe, **side by side**, as a **contact sheet** of variants each with its own
verdict, or **one at true printed size with a ruler** — because a screen reports its own size
only if it is configured to, and an on-screen legibility judgement that cannot be calibrated
is a guess.

**`figure.watch`** is the one part that cannot be a view, because a live preview is I/O by
definition. It serves the *same pure inspector* on **127.0.0.1 only** and re-renders when the
file changes. A file mid-write shows as a file mid-write, and a scene that does not yet
validate shows its problems — the point of a live preview is to see the state you are
actually in, and "half-saved" is a state.

**`figure.describe`** is the inventory in plain language: what the figure is, what it draws
by, where it came from, and what is wrong with it. It says the unwelcome parts — a
description that only mentions what went well is an advertisement.

**What this is not**: there is no direct manipulation. You cannot drag an element in the
inspector. The loop is *look in the inspector, name what you want changed, run one command,
watch it re-render* — which is what the spec asks for, and it is not the same as an editor.

## One report

`figure.report` runs conformance, layout, print legibility, style lint, glyph versions and
visual regression, and returns one verdict: **clean**, **questionable**, **unestablished** or
**wrong**.

`unchecked` is counted apart from passed, always. A figure with nothing wrong and four things
nobody could check is not a figure with nothing wrong, and a report that shows them the same
is how "verified" comes to mean nothing. Leaving out the guide or the reference makes the
report *unestablished*, not clean.

Visual regression rasterises the scene deterministically and compares it to a stored
reference, reporting the changed pixel count, the region and a diff image. A **missing**
reference is unavailable, not a pass: the first run has nothing to compare against, and
calling that success protects nothing.

## What is not built

Said plainly, because a toolkit that implies more than it does is worse than a small one.

- **No grids or snapping**, no insets or zoom-boxes, and no automatic label-leader
  placement. §3.6 lists them; what is built is panels, reflow, distribute, pack and routing.
- **Routing is orthogonal or a smoothed orthogonal route.** There is no true curved router
  and no edge-bundling.
- **Style linting does not check markers or dash patterns**, and there are no per-journal
  presets beyond the one example guide.
- **No crossing minimisation** in the diagram layout, no force-directed or network layout,
  and no edge bundling. §3.9.
- **No camera easing in the exported file**, no video or frame-sequence writers, and no
  sprite sheets. §3.12, §3.13: frames come back as scenes and are exported one at a time.
- **No direct manipulation.** The inspector picks and reports; it does not edit. Nothing
  drags, and there is no undo stack beyond the file.
- **The rasteriser is for comparison, not for looking at.** Text is drawn as its measured ink
  box, not as glyphs, which is enough to catch a label that moved and honest about not being
  a rendering.
- **No clipping in the format**, so anything that would need it -- an inset, a zoom-box, a
  plot mark outside the axes -- is handled by keeping the geometry inside instead, and saying
  when it had to be held there.
- **The glyph library is the three families in `lineart_trace/scene/glyphs/`**, not the whole
  of §3.7's list: no cells or organelles, no instruments beyond a pipette, and captured
  glyphs take no parameters.
- **No faceting, no heatmaps or contours, no violin or distribution marks**, and no colour
  bars. §3.8.
- **No boolean operations, offset, or stroke-to-outline.** §3.3 lists them; the primitives
  here stop at construction.
- **The solver is relaxation, not simultaneous.** It converges for the chains figures
  actually contain, and stops after a pass limit and says so rather than declaring success on
  a layout that never settled.
- **`scene.measurement` types its envelope and not its value.** A bbox, a length and a text
  metric share no payload shape. Its `additionalProperties` is deliberately not `false`,
  because a schema that forbids extra properties rejects every field a subclass adds.

## The records, and the order they have to be written in

Every function and view record is **generated** from its docstring by
`python3 -m lineart_trace.records`; `--check` reports drift and a test fails on it. A verb
with no docstring gets no record and is named. The schema records are generated too -- their
definitions are read from the schema files, never retyped.

**Writing them through `c11 record` one at a time is a cycle with no first element**:
`scene.document` names `scene.validate` as its checker, and `scene.validate` declares
`accepts: scene.document`. The generator resolves the whole pass at once. By hand, break the
cycle: write `scene.document` **without** its `code_verification`, then `scene.validate`,
then `scene.document` again.
