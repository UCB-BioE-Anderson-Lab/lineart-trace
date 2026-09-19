# lineart-trace — toolkit specification

A toolkit for **making SVG vector art**, aimed first at scientific figures:
teaching and lecture graphics, publication figures, and general diagrams.
Tracing raster line art is one component of it, not the whole.

This document specifies **function and scope** — what the toolkit must be able
to do. It deliberately says nothing about how any of it is implemented, what
it is written in, or how the pieces are packaged; those are for architectural
review.

---

## 1. The problem this exists to solve

A capable model can already write SVG by hand. The output is unreliable in
specific, repeatable ways, and every one of them is a missing tool rather than
a missing skill:

| Failure | What is missing |
|---|---|
| Elements overlap, misalign, or drift apart | No way to **measure** anything before drawing it |
| Labels overflow their boxes or collide | No **text metrics** — extent is unknowable without rendering |
| "Move the arrow" means rewriting the file, and something else breaks | No **stable identity** for elements |
| Relationships are hardcoded coordinates that shatter on any edit | No **anchors**; nothing to attach to |
| A set of figures drifts out of visual agreement | No **style guide** applied by role |
| The same enzyme is redrawn differently each time it appears | No **reusable parameterised glyphs** |
| Iteration is blind — write, look, guess, rewrite | No **feedback loop** the author or the model can use |
| A figure looks fine on screen and is illegible at column width | No **verification at final physical size** |

The toolkit's job is to close each of those. The measure of success is not
"can it draw a circle" but **can a person and a model, working together,
converge on a correct figure in a few deliberate steps instead of many blind
ones.**

### Principles

1. **The scene is the source of truth; SVG is an export.** Never re-read your
   own output to make the next edit.
2. **Everything is addressable by name.** An operation targets
   `panel-b.enzyme.active-site`, never a coordinate or a path index.
3. **Anchors, not coordinates.** Relationships are declared between named
   points and resolved at layout time, so they survive edits to either side.
4. **Style is a role, not a value.** An element asks for `emphasis-stroke`;
   the active style guide decides what that means.
5. **Measurement is a first-class operation.** Anything you can draw, you can
   interrogate before and after drawing it.
6. **Every figure records how it was made.** Provenance is part of the scene,
   so a figure can be regenerated when its data or source art changes.

---

## 2. The model

### Scene
A document. Canvas extent, physical size and units (mm/pt/px), coordinate
system and origin convention, background, named colour and type contexts,
metadata (title, caption, description, authorship), and a tree of elements.
Scenes can be nested and referenced — a figure panel is a scene.

### Element
A named node. A stable identity, a type, a transform, a style role, optional
tags, optional anchors, and provenance. Types at minimum:

- **path** — stroked centreline, open or closed
- **region** — filled area, with holes
- **group** — a container with its own frame; children addressed beneath it
- **text** — a run with typographic properties, optionally set on a path
- **image** — embedded or referenced raster
- **glyph instance** — a parameterised reusable figure (see §3.7)
- **guide** — construction geometry that never renders

### Anchor
A named point, direction, or frame carried by an element — `tip`, `inlet`,
`baseline-left`, `cleft`. Anchors may be authored, derived (centroid, bbox
corners, path midpoint), or **discovered** (the deepest concavity of a
silhouette). Other elements attach to them. This is what turns "seat the DNA
duplex in the polymerase's entry channel" into a declaration rather than a
pair of guessed numbers.

### Style guide
A named set of tokens — palettes, stroke weights, dash patterns, type scale
and families, marker shapes, spacing units, corner radii — plus rules binding
**roles** to tokens. Guides can inherit, and a scene can be re-rendered under
a different guide without touching its content.

### Frame
A coordinate space with units and a transform to its parent. Data-bearing
elements live in data frames (with scales); page furniture lives in page
frames. Nesting is explicit so that "2 pt" means 2 pt on paper regardless of
how deeply nested the element is.

---

## 3. Tool families

### 3.1 Scene management
Create, open, save, and version scenes. Inspect: list and tree the elements,
filter by type/tag/style/geometry, resolve a name to an element. Mutate: add,
remove, rename, duplicate, reparent, reorder (z), group and ungroup, lock.
Merge one scene into another as a group. Snapshot and restore. Diff two
scenes structurally (what was added, removed, moved, restyled).

**Done when** a figure can be built and revised over many sessions without any
step needing to regenerate the whole document.

### 3.2 Measurement and inspection
The family that most directly closes the gap with free-handed SVG.

Bounding box and tight ink extent of any element or selection. Text metrics
for a given string, family, size and weight — advance width, ascent, descent,
line height — **without drawing it**. Path length, area, centroid, principal
axis. Distance and clearance between elements. Overlap and collision queries.
Point-in-element and "what is at this coordinate". Nearest anchor to a point.
Extremal and concavity analysis of a silhouette (anchor discovery). Ink
coverage and density in a region. Colour inventory of a scene.

**Done when** a model never has to guess a coordinate or a size.

### 3.3 Primitives and construction
Lines, polylines, arcs, elliptical and circular segments, rectangles with
optional radii, ellipses, regular polygons, stars. Bézier and B-spline paths;
interpolation through points; smoothing and simplification with a stated
tolerance. Parametric and function-defined curves. Boolean operations (union,
difference, intersection, exclusion). Offset and inset. Stroke-to-outline.
Corner rounding and chamfering. Path splitting, joining, trimming, reversing.
Dashing as geometry. Markers and arrowheads as a catalogue. Brackets, braces,
callout leaders, hatching and stipple fills.

### 3.4 Text and typography
Place text with full control of alignment and baseline. Fit text to a box by
wrapping, by size, or by reporting failure rather than overflowing. Text on a
path. Multi-line blocks with leading and paragraph controls. Mathematical
notation. Subscript/superscript and small caps as first-class (chemistry and
biology need them constantly). Font embedding or outlining decisions at
export. Label placement helpers that avoid collisions.

**Done when** no label ever overflows, overlaps, or silently changes metrics
between preview and export.

### 3.5 Anchors and relations
Declare, derive, and discover anchors. Attach an element to an anchor with an
alignment rule and offset. Constrain: align edges or centres, maintain a
distance or angle, keep clear by a margin, keep inside a region, distribute
evenly. Pin an element so layout will not move it. Re-solve relations after
any edit and report what moved and what could not be satisfied.

**Done when** editing one element updates everything attached to it, and an
unsatisfiable layout is an explicit error rather than a silent overlap.

### 3.6 Layout and composition
Multi-panel figures with consistent panel sizing, gutters, and automatic panel
lettering. Grids and guides with snapping. Align, distribute, pack, and
tile. Connector routing between elements with obstacle avoidance, with
orthogonal, curved, and straight styles. Automatic label leader placement.
Reflow a figure to a different aspect ratio or column width. Insets and
zoom-boxes with a linking frame back to the source region.

### 3.7 Reusable glyphs and libraries
Parameterised figures instantiated by name with arguments, carrying their own
anchors. The lecture/teaching case needs a real library, not a demo:

- Molecular biology: DNA duplex (linear and circular, with strand polarity,
  nicks, gaps, mismatches), plasmid maps with features and cut sites, gel
  lanes and ladders, protein silhouettes, membranes, cells and organelles,
  reaction arrows with conditions
- Laboratory: tubes, plates, gradients, pipettes, instruments
- Generic: annotated axes of time or process, stepped sequences

Libraries are versioned, extensible, and styleable — a glyph is drawn with
style *roles*, so it obeys the active guide. Users can promote any scene
subtree into a glyph.

### 3.8 Data to graphics
Scales (linear, log, categorical, time) with explicit domains and ranges.
Axes, ticks, minor ticks, gridlines, axis breaks. Plot marks: point, line,
area, bar, box, violin, histogram, heatmap, contour. Error representations:
bars, bands, distributions. Legends and colour bars. Statistical annotation:
significance brackets, fitted lines with confidence bands, reference lines.
Faceting. Binding a plot to a data source so the figure regenerates when the
data changes.

**Done when** a publication panel can be produced from a data file and remain
correct, and restyleable, after the data is revised.

### 3.9 Diagram constructs
Nodes with automatic sizing to their contents. Edges with routing, labels,
and arrow semantics. Flowcharts, state machines, process and pathway
diagrams, swimlanes, trees, and simple network layouts. Container/grouping
boxes that resize with their contents. Cross-references between diagram nodes
and other figure elements.

### 3.10 Ingest
Trace raster line art to centrelines and filled regions — the current
capability — emitting **named scene elements**, not a flat SVG. Import SVG
and adopt its geometry into the scene model. Import data. Import and place
raster images with resolution and colour management. Anchor discovery on
imported art, so traced silhouettes become usable glyphs.

### 3.11 Style
Define, inherit, and switch style guides. Apply a guide to a scene or
subtree. Bind roles to tokens. Palette tools: generate, extend, check for
colourblind safety and for contrast against the intended background. Convert
a scene's literal values into roles (adopt an existing figure into a guide).
Theme variants: light/dark, screen/print, per-journal presets. Style linting:
off-palette colours, inconsistent stroke weights, type sizes outside the
scale, non-standard markers.

**Done when** a set of figures can be made visually consistent, and re-themed
for a different venue, without editing any figure's content.

### 3.12 Animation and staged reveal
Timelines with named keyframes. Property animation (transform, colour, path
length for draw-on, opacity). Staged builds for lecture slides — reveal
order, per-step hold, and the ability to export any step as a still. Easing.
Morphing between compatible paths. Camera moves (pan/zoom over a scene).
Coordination of multiple elements on one clock.

**Done when** a lecture build and a looping explainer are both first-class,
and any frame of either can be exported as a static figure.

### 3.13 Output
SVG: full document, or bare fragment for embedding, with control over
background, precision, and id namespacing to avoid collisions when inlined.
Raster at any resolution or physical size, with correct anti-aliasing.
PDF and EPS at exact physical dimensions with embedded or outlined fonts.
Export a subtree. Sprite sheets and frame sequences. Video and animated
formats. Resizing that is *reflow* where asked and *scale* where asked — a
figure retargeted from a slide to a column should be able to re-layout, not
merely shrink. Deterministic output, so a regenerated figure diffs cleanly.

### 3.14 Verification
The quality-measurement work already in the repository generalises here.

Legibility at final physical size: minimum type size, minimum stroke weight,
minimum feature separation. Contrast ratios against the actual background.
Colourblind simulation. Overlap and clipping detection. Off-canvas elements.
Unsatisfied layout constraints. Round-trip fidelity for traced art (existing).
Visual regression against a stored reference, with a diff image. Accessibility
metadata completeness.

**Done when** "is this figure correct" has an answer that is not "look at it".

### 3.15 Human-in-the-loop
The interactivity requirement: the author must be able to see what the design
process is doing, and steer it.

Live preview that updates as the scene changes. Annotated overlays: element
names, bounding boxes, anchors, constraints, z-order, style roles, the grid.
Pick an element visually and learn its name. Side-by-side and onion-skin
comparison of two versions or two style guides. A scene inventory in plain
language — what is in this figure, what styles it uses, what is wrong with it.
Contact sheets of variants. A preview at true physical size for legibility
judgement. Export of the annotated overlay so it can be discussed
asynchronously.

**Done when** a person can look at any intermediate state, name what they want
changed, and have that be a single instruction.

---

## 4. Cross-cutting requirements

- **Determinism.** The same inputs produce byte-identical output.
- **Provenance.** Each element records its origin — traced from a file,
  generated from data, instantiated from a glyph, hand-placed.
- **Composability.** Every operation is usable on its own and in sequence;
  nothing requires a session or hidden state.
- **Introspection.** The toolkit can describe its own capabilities, a glyph
  library's contents, and a style guide's tokens.
- **Failure is explicit.** A constraint that cannot be met, a label that will
  not fit, a colour outside the palette — reported, never silently absorbed.
- **Units are never ambiguous.** Every length carries a frame and a unit.
- **Scale independence.** A figure is authored once and correct at slide,
  column, and poster size, with the differences declared rather than redone.

---

## 5. Suggested build order

Sequenced so that each phase is independently useful.

1. **Scene, elements, naming, output.** The spine: a scene you can build,
   address, and export. Retarget the existing tracer to emit named elements.
2. **Measurement and inspection.** The single largest gain over free-handed
   SVG, and a prerequisite for everything that places things well.
3. **Primitives, text, and typography.** Enough to draw a figure deliberately.
4. **Anchors and relations.** Where iterative editing stops being destructive.
5. **Human-in-the-loop preview and overlays.** Feedback loop; makes every
   later phase faster to develop and to use.
6. **Style guides and linting.** Consistency across a set of figures.
7. **Layout and composition.** Multi-panel figures and connector routing.
8. **Glyph libraries.** Starting with the molecular-biology set.
9. **Data to graphics.** Publication panels from data.
10. **Diagram constructs.**
11. **Animation and staged reveal.**
12. **Verification suite.** Grown throughout; consolidated here.

Phases 1–5 are the minimum at which the toolkit is better than writing SVG by
hand. Everything after that is reach.

---

## 6. What this replaces

The current package is phase 0: a high-quality tracer with round-trip
measurement, a labelled corpus, and a style-free SVG emitter. It survives as
§3.10 (ingest) and §3.14 (verification), and its measurement discipline —
every claim backed by a number, every rejected approach recorded — is the
standard the rest of the toolkit should be held to. See
[design-log.md](design-log.md).
