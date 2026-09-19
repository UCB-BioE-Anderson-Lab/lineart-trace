# lineart-trace

**A toolkit for making SVG vector art** — scientific figures, diagrams and
animations that are real, editable vector graphics rather than pictures of
them. Aimed at teaching and lecture graphics, publication figures, and
general diagrams.

<img src="docs/beach-recolour.svg" width="100%"
     alt="the traced beach scene, recolouring its sand, ball and ocean on a loop">

*Nothing in that loop is a filter or a repaint. The trace came out as paths
grouped by the pen that drew them, so the sand changing colour is one
attribute on one group — six `<animate>` elements for the whole picture. Try
that on the PNG and you are editing pixels.*

![the source PNG on the left, the traced vectors on the right, visually
identical](docs/lead.png)

## Where this is going

The goal is a suite of composable tools for building figures deliberately:
a **scene** of named elements you can address and revise, **anchors** so one
element can be seated against another without guessed coordinates,
**measurement** so nothing is placed by eye, **style guides** applied by role
so a set of figures stays consistent, reusable **glyph libraries** for
recurring subjects, **layout**, **data-driven panels**, **animation and
staged reveals**, rich **output** at any size or resolution, and **preview
and overlay tools** so a person can see what the design process is doing and
steer it.

The functional scope is specified in **[docs/spec.md](docs/spec.md)**, with a
suggested build order. The target it is measured against: a person and a model
working together should converge on a correct figure in a few deliberate steps
rather than many blind ones.

## What works today

**All twelve phases of [docs/spec.md](docs/spec.md) are built**: a scene you can build,
address, measure, attach, check, style, lay out, populate from a glyph library or a data
file, diagram, animate, and report on. Phases 1–5 are the point the spec names as the minimum
at which this beats writing SVG by hand; everything after is reach.

A scene is one JSON document — a canvas at a physical size, named frames that own their
units, and a tree of named elements. Every element has an address (`panel-b.enzyme.outline`),
every length knows its frame and unit, and every traced element records the file and digest
it came from. Tools hand a scene to the next one as a **path**, never as an object.

```bash
lineart-trace drawing.png --scene --width 180 -o figure.json   # §3.10 trace into a scene
lineart-scene tree      --in figure.json                       # what is in it
lineart-scene measure bbox --in figure.json art --stroke       # tight extent, in mm
lineart-scene anchor    --in figure.json --in-place art cleft --by concavity
lineart-scene attach    --in figure.json --in-place label --to art.cleft --via tip
lineart-scene solve     --in figure.json --in-place                # attached things follow
lineart-scene textbox "active site" --family Helvetica --size 9 --width 24 --height 6
lineart-scene verify    --in figure.json                       # correct at printed size?
lineart-scene render    --in figure.json --out figure.svg
lineart-scene overlay   --in figure.json --out overlay.svg --check

lineart-scene panels    --in fig.json --in-place --rows 1 --cols 3   # lettered A B C
lineart-scene adopt     --in fig.json --in-place --guide figure-default
lineart-scene style     --in fig.json --in-place figure-default --variant dark
lineart-scene connect   --in fig.json --in-place link --from 10,30 --to 90,30 \
                        --avoid wall --avoid hub --clearance 2 --arrow 2
lineart-scene reflow    --in fig.json --in-place --width 88          # reflow, not shrink
lineart-scene lint      --in fig.json --guide figure-default
lineart-scene palette   -n 5                                          # colours anyone can tell apart
lineart-scene glyphs    --family dna                                  # what is in the library
lineart-scene glyph     --in fig.json --in-place dna.plasmid map --at 20,20 \
                        --args '{"name":"pUC19","sites":[["EcoRI",10]]}'
lineart-scene plot      --in fig.json --in-place panel --data results.csv \
                        --x dose --y response --fit --ylabel response
lineart-scene flowchart --in fig.json --in-place --nodes '{"a":"lyse","b":"bind"}' \
                        --edges '[["a","b","then"]]'
lineart-scene build     --in fig.json --out lecture.json show \
                        --stages '[{"name":"one","reveal":["panel"]}]'
lineart-scene still     --in fig.json --out step1.json --timeline lecture.json --stage one
lineart-scene snapshot  --in fig.json --out reference.png
lineart-scene report    --in fig.json --guide figure-default --reference reference.png

lineart-scene inspect   --in fig.json --out inspect.html    # click anything, learn its name
lineart-scene watch     --in fig.json                       # live preview on 127.0.0.1
lineart-scene compare   --in fig.json --out onion.html --variant dark --mode onion
lineart-scene contact   --in fig.json --out sheet.html --variant dark --guide journal-column
lineart-scene truesize  --in fig.json --out truesize.html   # with a ruler
lineart-scene describe  --in fig.json                       # in plain language
```

What each piece does, and what it deliberately does not:

| | |
|---|---|
| **Measure** | Tight curve extents, exact area and centroid, arc length, clearance, collisions, hit tests — and **text metrics read out of the font file**, so a label's size is known before it is drawn |
| **Draw** | Lines, rectangles with radii, ellipses, arcs, polygons, stars, curves through points, arrowheads, brackets — all as cubics, one spelling |
| **Fit text** | Wrap, shrink, or **refuse** — a label that will not fit reports by how much rather than overflowing |
| **Attach** | Anchors authored, derived (`bbox.ne`, `centroid`, `path.mid`) or **discovered** (`concavity`); relations `attach` / `align` / `clear` / `inside`, re-solved after any edit, with unsatisfiable layouts reported rather than approximated |
| **Verify** | Type size, stroke weight, feature separation, contrast against the real background, three kinds of colourblind simulation, off-canvas, missing glyphs, unsolved relations — at the size it will print |
| **Style** | Guides with tokens, roles, inheritance and variants; apply one to re-theme a figure without editing it; adopt a traced figure's literals into roles; lint what is off-palette or off-scale; generate palettes that survive all three dichromacies |
| **Lay out** | Panels as frames with automatic lettering, distribute, pack, and **reflow** — a drawing fills the new panel, a 10 pt label is still 10 pt; connectors routed around obstacles with the clearance they achieve reported as a number |
| **Place** | A glyph library: DNA duplex with nicks and mismatches, plasmid maps with features and cut sites, gels with ladders and bands, protein silhouettes with real clefts, membranes, reaction arrows, tubes, plates, pipettes, gradients, stepped processes, timelines — every one styled by role and carrying anchors |
| **Plot** | Linear, log and categorical scales with honest refusals; scatter, line, area, bar, box and histogram marks; error bars, confidence bands, significance brackets, reference lines and legends; a fit that reports slope, intercept and r² with the drawing |
| **Diagram** | Nodes sized to their measured labels, edges that route round obstacles and report the clearance, containers that re-fit, layered flowcharts, trees, swimlanes — and a cycle is named rather than looped on |
| **Animate** | Timelines and staged lecture builds where **any frame is an ordinary scene** you can measure and verify; draw-on that trims real geometry, morphs that refuse an invented correspondence, an animated SVG that names what it could not carry |
| **Report** | One verdict over a figure — clean, questionable, unestablished or wrong — across conformance, layout, print legibility, style, glyph versions and visual regression with a diff image |
| **Steer** | An **interactive inspector** — click anything and it names it, with its role, z-order, box in mm, anchors and resolved style; a **live preview** that re-renders when the file changes; **onion-skin** and side-by-side comparison; a **contact sheet** of variants each with its own verdict; a **true-size** page with a ruler to check the screen against; and the figure **described in plain language**, unwelcome parts included |
| **Show** | An annotated overlay: names, boxes, anchors, relations, **z-order, style roles** and findings, as a `type: view` that performs no I/O |

### See it work

```bash
python3 examples/showcase.py --html docs/showcase.html
```

**One figure that uses everything**, and a page that shows it: traced art with a DNA duplex
seated in a concavity found on the silhouette, a pathway whose bypass routes round an
inhibitor, a scatter with a fit from a CSV, a gel and a plate from the glyph library — styled
by a guide, laid out on a grid, and exported at 180 × 118 mm, as a dark variant, and reflowed
to an 88 mm journal column that **re-grids from 2×2 to 4×1**. All three verify with zero
errors. The page also shows the annotated overlay, the four stages of the lecture build, and
a regression diff — and links to the inspector, the
contact sheet, the onion wipe and the true-size page.

```bash
python3 examples/demo_figure.py --out out
```

Ten steps building one figure: trace, find the entry channel by **looking at the shape**,
seat a DNA duplex in it by declaration, refuse a caption that will not fit, check the figure
at print size and fix what the check finds, then **move and enlarge the enzyme** — and watch
the duplex, the leader and the caption follow, be re-checked, and come back clean.

```bash
python3 examples/demo_panels.py --out out
```

A three-panel figure, exported three times from one scene: house style, dark variant, and an
88 mm journal column. The panel letters are automatic, the boxes are sized to text measured
before anything is drawn, the arrows route around the inhibitor, and each export is verified
at its own size.

```bash
python3 examples/demo_data.py --out out
```

A publication figure built from a CSV: a scatter with a least-squares fit and its confidence
band, bars with error bars and a significance bracket, a log-log decay with a legend on a
backing plate. The figure records the data file's digest, and is verified at print size in
both themes.

```bash
python3 examples/demo_diagram.py --out out
python3 examples/demo_build.py --out out
```

Four diagram constructs on one page — a cyclic state machine, a tree of gene names, swimlanes
with a container that re-fits, a flowchart whose arrow goes round an obstacle. Then a lecture
build where **every stage is exported as a figure and verified on its own**, a draw-on that
measures as half-drawn, and one report that distinguishes *clean* from *unestablished*.

The format, every decision behind it and what is deliberately not built are in
**[docs/scene-format.md](docs/scene-format.md)**.

## Tracing

Ask ChatGPT — or any image generator — for line art and you get back a *photo*
of a drawing: a grid of pixels that looks like pen work but contains no pen
work. There are no paths in it. You cannot recolour a line, change its weight,
put it on a dark background, dash it, animate it, or print it larger than it
was generated. It is a picture of vector art, not vector art.

The tracer turns it back into the real thing: **1.2 MB of pixels in, 130 KB of
SVG out** — filled regions and stroked centrelines in four inks the tool worked
out for itself, every one of them a curve you can edit.

```bash
pip install git+https://github.com/UCB-BioE-Anderson-Lab/lineart-trace
lineart-trace beach.png --colors 0 --svg -o beach.svg
```

```python
from lineart_trace import trace_file
r = trace_file("beach.png", colors=0)
print(r.n_strokes, r.n_fills, r.colors)
svg = r.to_svg_group(scale=0.5)
```

A second worked example, one closed contour rather than a whole scene:
`polymerase.png` goes in as 777 KB and comes out as
[**3.8 KB**](docs/polymerase.svg) — a single path of 97 cubic Béziers.

### Centrelines, not outlines

The other half of "real vector art" is what shape the paths are. An outline
tracer (potrace, `cv2.findContours`) returns a closed loop *around* every
stroke, so a pen line becomes a long thin sausage: set its width to 8 and you
get a fatter sausage, not a fatter line. **lineart-trace recovers the
centreline**, so a stroke is one open path down the middle of the ink, with a
width you can change. Shapes that are genuinely filled — a solid ball, a band
of sea — are detected and emitted as filled contours instead, because a
centreline cannot represent them.

### What the tracer does

| | |
|---|---|
| **Centrelines** | one open path per stroke, not an outline loop |
| **Per-path stroke width** | recovered from the distance transform, so a drawing with mixed weights stays mixed |
| **Junctions** | every arm of a crossing routes through one shared point, so crossings do not show gaps |
| **Corners** | high-curvature points become segment boundaries, so a square stays square |
| **Filled regions** | shapes too solid to have a centreline are emitted as filled contours, holes included |
| **Colour** | ink is found by distance from the paper *colour*, and can be split into one layer per pen, each path keeping its own colour |
| **Photographs** | uneven lighting is divided out before thresholding, so a phone shot of a crumpled page still works |

### Pipeline

1. **Binarize.** Otsu, after dividing out a blurred estimate of the page when
   the lighting is uneven (`--method`, `--flatten`, `--denoise`). Colour input
   is measured against the paper colour instead of its brightness.
2. **Split fills from strokes.** Regions that are compact rather than
   elongated become contours; everything else goes on to be thinned.
3. **Thin** to a 1-pixel skeleton: Zhang–Suen, then a sequential
   simple-point cleanup.
4. **Build the skeleton graph.** Branch pixels cluster into junctions; the
   runs between them become ordered point chains; spurs are pruned and the
   chains re-spliced.
5. **Fit** each chain with cubic Béziers — Schneider (Graphics Gems, 1990)
   with Newton–Raphson reparameterisation, cut at detected corners.

### Colour

```bash
lineart-trace drawing.png --colors 0 --svg -o drawing.svg   # find the pens
lineart-trace drawing.png --colors 5 --svg -o drawing.svg   # exactly five
```

By default (`--colors 1`) every pen is traced as one colour, as before. Above
1, the ink is split into that many pens and **each path carries the colour it
was drawn in**; `--colors 0` picks the number itself. `TraceResult.colors`
lists what it found.

Two things make this work.

**Colour is decided per region, not per pixel.** The obvious approach is to
cluster the ink by colour and rebuild the regions from the clusters. It does
not work, for two reasons that only show up on a real drawing. An antialiased
pixel on the edge of a black outline is a grey blend, and in Lab — where
lightness is a full dimension — a mid-grey is 127 from black but only 73 from
a blue pen, so every outline in the picture comes out flecked with colour: a
black-and-white lighthouse arrived speckled with sand and ocean. And because
the outline belongs to a different cluster than the paint it is drawn across,
it *severs* that paint: a shoreline cut the sand into slivers, and what
survived had to be reassembled morphologically, giving a smooth blob where
the coastline should have been.

Both vanish if the question is asked the other way round. The lines already
say where the boundaries are, so: trace the line work first, take the regions
it encloses, and give each region the median colour of its own pixels. A
region matching the paper is not a fill. Pixels under the outline go to the
nearest region so neighbouring fills meet beneath it. Whatever ink is left
over is line work in its own colour, which is why a drawing of five coloured
pens and no fills still works.

**Ink is found by colour distance from the paper, not by brightness.** Yellow
on white has a luminance around 196 of 255. Convert to grey and it is lighter
than most smudges, so a brightness threshold keeps the smudges and drops the
strokes. Measured in Lab against the paper's own colour, yellow is far away —
and the same measurement still rejects a grey background, because it is a
distance in colour rather than in lightness. This applies even at
`--colors 1`: it is why a yellow stroke is traced at all.

**The ink/paper split cannot be plain Otsu.** Otsu assumes two classes, but
ink in several colours is spread over a wide range of distances — black at
254, yellow at 93 — so Otsu cuts through the middle of the *ink* and calls the
palest pen paper. On a red/blue/yellow/black figure it cut at 98.6 and lost
the yellow. So the threshold is re-examined on whatever was called paper, and
a lower split is accepted when the band it adds looks like a pen. That test is
geometric, not statistical: the antialiased halo of a dark stroke also lives
in that band, and it is recognisable because it *hugs* the ink already found,
while sensor noise is recognisable because it is incoherent. A real pen is
coherent and stands away from the other ink.

Where two pens cross, the upper one covers the lower, so the lower stroke is
genuinely broken in the image and the trace shows the break. `--close 5`
bridges it; the close is applied per layer, because a gap that only exists
after the split cannot be mended before it.

### Four things this gets right that are easy to get wrong

**Thinning must be finished before the topology is read.** Parallel Zhang–Suen
leaves two-pixel-wide diagonal bands, and every pixel inside such a band has
crossing number 2. A hub where eight spokes meet therefore reads as ordinary
line pixels and *no junction is found at all*. The sequential cleanup pass in
`thinning.thin_redundant` removes pixels whose ink neighbours are already
8-connected without them. Note that the textbook simple-point test (crossing
number 1) assumes a 4-connected background and will **not** cut a staircase.

**Branch points come from the crossing number, not the neighbour count.** On a
diagonal staircase an ordinary interior pixel has three 8-neighbours. Counting
neighbours reports false branch points and shatters every curve — a plain
circle traced to 29 separate paths before this was fixed.

**A crossing is a blob, not a pixel.** Thinning an X of 10 px strokes leaves a
cluster of branch pixels. Treating each as its own node emits a fistful of
2-pixel junk chains at every crossing. Branch pixels are clustered and every
arm is routed through the cluster centroid.

**Fill detection cannot depend on the stroke width.** The obvious test is "is
this much wider than a stroke?" — but the stroke width is measured from the
skeleton, and when the picture is mostly fill, the fill sets that width and
the test can never fire. An image of nothing but a solid triangle scored 0.51
under that rule. Thinness, `4πA/P²`, is scale-free: 1.0 for a disc, 0.14 for a
heavy rule, and it needs no reference width. It took the same specimen to
0.99.

### Measured behaviour

The measurement discipline below is the standard the rest of the toolkit is
meant to be held to: every claim is a number, and every rejected approach is
recorded with the measurement that killed it.

Quality is a **round trip**: vectorise, render the vectors back to a raster at
the source resolution, and compare with the ink that should have been there.
`lineart_trace.corpus` holds 40 labelled specimens, each isolating one thing
that can go wrong. Drop your own drawings into `tests/fixtures/` and the
benchmark and test suite pick them up automatically, scored against their own
ink.

![three panels per row: source, traced, and the difference between them, for a
synthetic drawing and a simulated photograph](docs/roundtrip.png)

```bash
python examples/benchmark.py --no-fixtures --md docs/benchmark.md
python examples/benchmark.py --gallery docs/gallery.html     # visual report
lineart-trace drawing.png --check                            # one file
```

A second worked example, [docs/polymerase.svg](docs/polymerase.svg), is the
opposite extreme: a ChatGPT drawing that is one closed contour with about
sixty scallops, which comes out as **a single path of 97 curves, 3.8 KB from
777 KB** — two hundred times smaller.

Across the 40 corpus specimens: **mean IoU 0.915, median coverage 0.995,
median spill 0.001.** Full table in [docs/benchmark.md](docs/benchmark.md).

| category | IoU | what it covers |
|---|---:|---|
| primitives (line, circle, ellipse) | 0.90 – 0.99 | closed loops, staircase quantisation |
| corners (rectangle, star, zigzag) | 0.87 – 0.99 | sharp turns kept sharp |
| junctions (cross, T, 8-spoke hub, tangency) | 0.90 – 0.99 | no gaps at crossings |
| fills (solid shape, arrowhead, ring with hole) | 0.94 – 0.99 | contours, not spines |
| patterns (hatching, parallels, lettering) | 0.78 – 1.00 | many short strokes |
| drawings (flower, house, face) | 0.88 – 0.95 | ordinary line art |
| colour (five pens, pale ink, crossing pens, tinted paper) | 0.90 – 0.99 | per-pen layers |
| photo / scan | 0.85 – 0.91 | crumpled page, skew, lamp falloff |
| noise (specks, dropouts, faint ink) | 0.83 – 0.95 | damaged input |
| shading (grey wash, tonal ramp, stipple) | 0.65 – 0.88 | see limitations |

#### Reading these numbers

**IoU punishes thin strokes and says little about them.** A half-pixel
centreline offset costs a fixed *absolute* amount of overlap, which is a large
*fraction* of a 3-pixel stroke and a small one of a 20-pixel stroke. The same
drawing, redrawn at different weights and traced with identical settings:

| stroke weight | 2 px | 3 px | 5 px | 8 px | 12 px | 20 px |
|---|---:|---:|---:|---:|---:|---:|
| IoU | 0.819 | 0.883 | 0.908 | 0.936 | 0.931 | 0.951 |
| coverage | 1.000 | 0.995 | 0.999 | 0.997 | 0.990 | 0.984 |

The geometry is identical in every column. So judge fine line art by
**coverage** (how much of the ink was reproduced) and **spill** (how much
paint landed on blank paper), and treat IoU as a sub-pixel registration score.
`d95` — how far the worst-placed 5 % of the ink is from anything drawn —
catches a whole stroke going missing, which an area measure can hide.

### Limitations

Each of these is a specimen in the corpus with its measured floor recorded in
`tests/test_corpus.py`, not an untested caveat.

| case | behaviour |
|---|---|
| **Stipple / halftone shading** | IoU 0.65. Dots have no centreline. They come out as small filled regions, and touching dots merge into one — so the count is well under the number drawn. Correct output, poor score. `--min-fill-area` trades resolution against picking up noise. |
| **Grey washes and tonal ramps** | A wash is tone, not line. It either binarises away or becomes one filled region. There is no line to recover, and none is invented. |
| **Lettering** | IoU 0.78. Small counters (the hole in an `e`) and thin serifs fall below the resolution the skeleton can carry. |
| **Tiny isolated dots** | Kept as filled regions above `--min-fill-area` (16 px by default), dropped below it. |
| **Very acute crossings** (< ~15°) | The two branch points sit far apart along the line, so the crossing resolves as two junctions with a short piece between them rather than one. |
| **Antialias dropouts** | A shallow curve can break into pieces at the threshold. `--close 5` bridges them, at the cost of slightly fattening the stroke. |
| **Stroke ends** | Thinning stops about a stroke radius short of a butt end. With the default round line caps this cancels out; with butt caps the line reads short. |
| **Colour under uneven lighting** | The paper colour is estimated globally, so a colour photograph with a strong lighting gradient is not handled: `--flatten` works on brightness and does not apply to the colour path. Scans and renders are fine. |
| **Pens of similar colour** | Two pens within about ΔE 20 are treated as one. Force the split with `--colors N`. |
| **A fill covering most of the page** | The paper colour is the image's most common colour, so a flat region covering more of the page than the paper does is mistaken for the paper and the drawing is read inside out. |
| **Colour with no enclosing line work** | A flat area with no outline around it has no region to be found. It falls back to the monochrome fill test, which judges by thinness and is defeated by a ragged boundary; lower `--thin-limit` if so. |

### Command line

```
lineart-trace SRC [-o OUT]

input     --method {auto,fixed,otsu,adaptive}  --thresh N  --flatten/--no-flatten
          --invert  --denoise  --despeckle AREA  --close R
          --colors N  --max-colors N
tracing   --error PX  --prune PX  --corner-angle DEG  --smooth N
          --fill-ratio N  --thin-limit T  --min-fill-area N
output    --width W  --stroke W  --uniform-width  --color C  --background C
          --places N  --svg  --check
```

`--svg` emits a standalone document; without it you get the bare `<g>`, which
is what you want when inlining into a page.

### API

```python
trace_file(path, **kw) -> TraceResult
trace_image(array, **kw) -> TraceResult      # grayscale, BGR or BGRA
trace_mask(mask, **kw) -> TraceResult        # a 0/1 ink mask you made yourself

TraceResult.strokes   -> [StrokePath(curves, width, closed, color), ...]
TraceResult.fills     -> [FillPath(loops, color), ...]  # outer loop, then holes
TraceResult.colors    -> ["#dc0000", ...]               # pens found
TraceResult.to_svg(scale, color, background) -> str
TraceResult.to_svg_group(...) -> str
```

The stages are separately usable: `binarize`, `ink_mask`, `separate_colors`,
`skeletonize`, `build_graph`, `split_fills`, `fit_curve`, `rasterize`,
`compare`.

## Documents

- **[docs/spec.md](docs/spec.md)** — what the toolkit is for, the scene /
  element / anchor / style model, the fifteen tool families and what "done"
  means for each, and a suggested build order.
- **[docs/design-log.md](docs/design-log.md)** — the decisions taken, and the
  approaches implemented, measured and abandoned, with the numbers that killed
  them. Read it before re-attempting anything clever about fill detection or
  colour separation.
- **[docs/scene-format.md](docs/scene-format.md)** — what a scene is, how one tool hands one
  to the next, and what each decision costs.
- **[docs/benchmark.md](docs/benchmark.md)** — per-specimen round-trip scores.
- **[docs/C11-CONNECTOR.md](docs/C11-CONNECTOR.md)** — using this repository as a content
  world, and the eleven capability records in it.

## Development

```bash
pip install -e ".[dev]"
pytest                                     # 866 tests
python3 -m lineart_trace.records           # regenerate records from docstrings
python3 -m lineart_trace.records --check   # ...or just report which have drifted
python3 examples/scene_cost.py             # what the scene format costs, measured
python examples/benchmark.py --gallery docs/gallery.html \
           --artifact docs/atlas.html --md docs/benchmark.md
python examples/make_corpus.py out/        # write the corpus as PNGs
```

## License

MIT
