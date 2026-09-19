# Design log

Why this code is shaped the way it is, and — more usefully — **what was tried
and abandoned**. The README says what the tool does; the docstrings say how a
given function works. This file is for the decisions, so that nobody (the
author included) spends another afternoon rediscovering that a plausible idea
does not survive contact with a real drawing.

Every claim here is a measurement that was actually taken. Where a number
appears, it came from running the thing.

---

## The premise

Recover stroke **centrelines**, not outlines. An outline tracer returns a
closed loop around each stroke, so a pen line becomes a long thin sausage and
its "width" is not editable. A centreline is one open path down the middle,
with a width attribute you can change. Shapes that are genuinely filled cannot
be represented that way and are emitted as filled contours instead.

---

## Decisions

### Thinning must finish before topology is read
Parallel Zhang–Suen leaves two-pixel-wide diagonal bands, and **every pixel
inside such a band has crossing number 2**. An eight-spoke hub therefore read
as ordinary line pixels and no junction was found at all. A sequential
simple-point cleanup pass fixes it.

The test has to use 8-connectivity for the neighbours. The textbook
simple-point test (crossing number 1) assumes a 4-connected background and
will **not** cut a staircase — it was tried first and did nothing.

### A crossing is a blob, not a pixel
Thinning an X of 10px strokes leaves a cluster of branch pixels. Treating each
as its own node produced 18 junk 2-pixel chains plus 97 degenerate leftovers
on an eight-spoke test figure. Branch pixels are clustered and every arm
routes through the cluster centroid, so the arms actually meet.

### Delete junction pixels before walking
What remains is components that are simple paths or closed loops, so ordering
is a walk from an end with no cross-component bookkeeping. The original bug —
a plain circle tracing to two paths — was the old walk overrunning its own
start and orphaning the staircase pixels it stepped over. This makes that
class of bug unrepresentable rather than fixed.

### Stroke width comes from the distance-transform *ridge*
The skeleton does not sit exactly on the ridge; on a curve it is up to half a
pixel off, and reading the transform there understates width badly — a 9px
circle measured **7.79**. Taking the 3×3 local maximum reads the ridge itself:
**8.99**. And width is `2d − 1`, not `2d`: the transform reports distance to
the nearest blank pixel, so the centre of an n-wide stroke reads (n+1)/2.
Doubling alone fattens every stroke by a pixel.

### Stroke ends are not extended
Thinning stops about a stroke radius short of a butt end, so extending looked
right in principle. Measured, it is worse: with the default round line caps
the shortfall already cancels out. IoU 0.873 extended against **0.899** not.

### Fill detection is scale-free
The obvious test is "is this much wider than a stroke?" — but stroke width is
measured from the skeleton, and when the picture is mostly fill, the fill sets
that width and the test can never fire. An image of nothing but a solid
triangle scored **0.51**. Thinness `4πA/P²` needs no reference width and took
the same specimen to **0.99**.

### Colour: ask about regions, not pixels
See *Rejected* below for the architecture this replaced. The line work is the
darkest pen; the regions are what it encloses; each takes the median colour of
its own pixels; a region matching the paper is not a fill. Pixels under the
outline go to the nearest region so neighbouring fills meet beneath it. Ink
left over once fills are removed is line work in its own colour — which is how
a drawing of five coloured pens and no fills still works.

A region paints its **ink**, not the whole area it encloses. Filling the area
wholesale paints over the white speckles in sand: spill **0.085 → 0.001**.

### Ink is found by distance from the paper colour
Not by brightness. Yellow on white has luminance ~196 of 255, so a brightness
threshold keeps every smudge darker than that and drops the strokes.

---

## Rejected

Each of these was implemented and measured before being backed out.

### Elongation `A / r_max²` for fill detection
Roughness-proof, which thinness is not — a beach's sand, with a wiggly
coastline and holes punched by the objects on it, scores 0.033 on thinness
despite being 274,000 pixels of solid fill.

**Why it failed:** `r_max` comes from the fattest point. An arrowhead on a
leader line is one component, so the head's radius applied to the whole thing
and the shaft was swallowed. Caught by an existing test.

### A majority vote to clean up mis-coloured specks
Reassign each pixel to the most common pen in its neighbourhood.

**Why it failed:** a three-pixel window around a black outline drawn across
sand is mostly sand, so the vote ate the line work. Stray components went
**266 → 455**. Only small islands *with another pen around them* should move; a
small black mark surrounded by paper is a bird.

### A histogram valley test to find a pale pen
Accept a lower threshold when there is a dip between the paper peak and the
next mode.

**Why it failed:** the antialias levels of a synthetic render form a **comb** —
discrete spikes with gaps between them — which fakes a valley anywhere you
look. The working test is geometric instead: halo *hugs* the ink already
found, noise is *incoherent*, a real pen is coherent and stands apart.

### Triangle thresholding of the colour-distance map
**Why it failed:** far too permissive. 30,057 ink pixels against a true ~24,500,
grabbing the antialias halo. On a noisy page, 5,228 against a true ~3,300.

### Plain Otsu for the ink/paper split on colour art
**Why it failed:** Otsu assumes two classes, but ink in several colours spans a
wide range of distances — black at 254, yellow at 93. It cuts through the
middle of the **ink** and calls the palest pen paper. On a red/blue/yellow/black
figure it cut at 98.6 and lost the yellow by 5.4.

### Cluster seeds chosen by colour distance from paper
"Use the most ink-like pixels to find the pen colours."

**Why it failed:** it discards the palest pen *wholesale* — yellow is the
nearest ink to white, so every yellow pixel was excluded from the seeds and
the yellow stroke was then assigned to whichever other pen was least unlike
it. Seeds are chosen geometrically instead, by depth into the stroke.

### Assigning ink pixels to the nearest pen colour in Lab
**Why it failed:** Lab counts lightness as a full dimension, so a **pure grey**
antialiased pixel on the edge of a black line is nearer a chromatic pen than
black. Measured: grey 80 → ocean, grey 160 and 200 → sand. Every outline in
the drawing came out flecked with colour; a black-and-white lighthouse had
**445** chromatic pixels where the source has 0.

Measuring distance to the *paper-to-pen segment* fixes it — every grey lands
on the paper-to-black segment at distance 0 — but that was only a better
answer to the wrong question. See below.

### The whole pixel-clustering colour architecture
Cluster ink by colour, then rebuild regions from the clusters.

**Why it failed:** two independent problems, both structural. Edge pixels have
no well-defined colour (above). And an outline belongs to a different cluster
than the paint it is drawn across, so it **severs** that paint — a shoreline
cut the sand into disconnected slivers, only the largest survived, and its
boundary had to be rebuilt morphologically, giving a smooth blob where the
coastline should be.

It was propped up with `--thin-limit 0.05` and `--close 5`, which are gone.
Replaced by the region-first architecture; on the same drawing, coverage
0.976 → **0.992**, spill 0.085 → **0.001**, IoU 0.904 → **0.917**.

---

## A note on measurement

**IoU is a poor headline for fine line art.** A half-pixel centreline offset
costs a fixed absolute amount of overlap, which is a large fraction of a 3px
stroke and a small one of a 20px stroke. The same drawing at different
weights, identical geometry, identical settings:

| weight | 2px | 3px | 5px | 8px | 12px | 20px |
|---|---:|---:|---:|---:|---:|---:|
| IoU | 0.819 | 0.883 | 0.908 | 0.936 | 0.931 | 0.951 |
| coverage | 1.000 | 0.995 | 0.999 | 0.997 | 0.990 | 0.984 |

Judge fine work by **coverage** and **spill**; treat IoU as a sub-pixel
registration score. `d95` catches a whole stroke going missing, which an area
measure hides.

**Beware a yardstick that is itself broken.** An early regression test rendered
results by drawing polylines through curve *endpoints*, ignoring the control
points. It reported 0.72 coverage on a figure whose real coverage was
**0.996**, and it had been passing — so it was also capable of hiding a real
regression. Round-trip scoring now goes through the same rasteriser the
metrics use.

**A fix validated by the corpus is not the same as a fix driven by it.** Two
changes were once tuned on a single image, passed all 40 specimens, and were
still backed out: nothing in the corpus had *driven* the thresholds. If a
defect is real, add a specimen for its class first.

---

## Phase 1 — the scene

### JSON was forced, not chosen
Three constraints and one answer: a capability is invoked as `shlex.split(entry) + args`, so
what crosses the boundary is strings and the only scene that fits is a path; `accepts` and
`produces` are checked against a schema record whose definition is a JSON Schema, which only
JSON can be; determinism forbids the timestamps and insertion-ordered keys a richer format
would have made easy. Recorded because "we picked JSON" reads like a preference and it is
not one.

### The document is the model
No `Scene` class mirroring the schema. A class that mirrors a schema is a second declaration
of the format, and the two drift — the same argument that keeps records generated from
docstrings and keeps element identity in names rather than a parallel table of uids. The
generalisation cost nothing and removed a whole category of bug before it could exist.

### What JSON only costs 8% — and it is not precision
The obvious lever on a 729 KB traced scene is coordinate precision, and it is nearly
worthless. Measured on `examples/beach.png` (806 strokes, 90 fills, 3381 cubics):

| decimals | size | gzipped | worst coordinate error |
|---|---:|---:|---|
| 2 | 675 KB | 72 KB | 0.64 µm on a 180 mm page |
| 3 | 689 KB | 80 KB | 0.064 µm |
| 4 | 702 KB | 88 KB | 0.0064 µm |
| **6** | **729 KB** | **102 KB** | 0.000064 µm |

8% across the whole usable range, because the bytes are JSON structure — braces, quotes, key
names, indentation — and not digits. So precision stayed at 6, which is a decision to change
nothing, taken with a number rather than a shrug. The scene is **4.26x** the tracer's own SVG
for the same drawing; that ratio is the format, not the rounding.

### Copy-per-transform is 0.9% of the trace that produced it
Every scene tool deep-copies rather than mutating, which is what makes "no session, nothing
requires a prior call" true rather than aspirational. On the beach scene: parse 3.1 ms, write
41.5 ms, a full load/transform/write round trip **59 ms** — against **6,746 ms** to trace the
image in the first place. Structural sharing was considered and not built: it would optimise
under 1% of the path a user actually waits on. `examples/scene_cost.py` re-takes all of these.

### One segment per line, and a diff that can name what moved
`json.dumps(indent=2)` puts every number of every Bezier on its own line — a 3381-curve trace
becomes tens of thousands of lines and a moved control point is invisible in the noise. The
writer keeps arrays of scalars inline and nests everything else, so a segment is one line:
`["C", 640, 96, 720, 176, 720, 304]`. Determinism is what makes a regenerated figure diff at
all; this is what makes the diff readable.

### A guarantee about a field nothing may carry
`ADDRESS_FIELDS` was five entries long — `of`, `to`, `from`, `target`, `anchor` — guessed at
what §3.5 might one day add, so that `rename` would "rewrite every reference". **None of them
existed in the schema**, so no scene could legally carry one, so the rewrite maintained
nothing and the test that dangling references are caught could not be written at all. Found
by writing that test.

Fixed by giving relations a real, checked home — an element may carry `relations` with a `to`
address, validated and maintained though nothing solves them until phase 4 — and narrowing
the list to the one field that is genuinely an address. A relation's `via` names an anchor on
the element carrying it, and rewriting that as an address would corrupt a scene rather than
maintain one.

The lesson is not about relations. **A guarantee about a field nothing may carry is not a
weak guarantee, it is the appearance of one** — and it passes every test you think to write,
because the case it fails on cannot be constructed.

### The cheap version of a reference check accepts every dangling reference there can be
The first dangling-reference check asked whether the part before the last dot names an
element, because an address may name an anchor. On a scene with an element `enzyme`, that
accepts `enzyme.nowhere` — which is *every* broken anchor reference. Replaced by calling the
same resolver the tools call. One resolver, used by the code and by the check on the code.

### Records are generated, and the examples are a staleness detector
Every function record comes from its verb's docstring, and the generator RUNS each example
and records what came back. That makes `tests/test_sharables.py` a detector of drift — code
changed, record not regenerated — and **not** an oracle: it cannot catch a record that was
wrong the moment it was generated, because it was generated from the behaviour. Written down
because a test that looks stronger than it is does more harm than one that is honestly weak.

### The store's own test assumed every record runs
`REQUIRED` in `tests/test_sharables.py` was a constant including `entry`, and the first schema
record broke four tests by being exactly what a schema is: something that holds a definition
and does not run. `entry` on a schema is not merely absent, the kernel forbids it. The fix
was to make required fields a function of type — the kernel's own rule — and to add the check
that every `accepts`, `produces` and `code_verification` resolves to a record of the right
type **in this store, with nothing mounted**, since an unmounted clone is a supported state.

---

## Phases 2–5 — measure, draw, attach, check, show

### The centroid divisor is 2A, and it was 6A for an hour
`6A` is the **polygon** centroid formula, whose integrand is `(x₀+x₁)(x₀y₁−x₁y₀)` and not
`x²y′` — a different quantity that sits beside this one in every reference. The wrong version
put a 4×3 rectangle's centroid at **(0.67, 0.5)** instead of **(2, 1.5)**: exactly a third of
the way, which on a symmetric shape still looks like a point somewhere sensible inside the
figure. Caught by measuring a rectangle, whose answer can be written down without the code.

**The lesson is the test, not the formula.** Curve maths has to be checked against closed
forms — a rectangle, a triangle, a circle — because a plausible-looking wrong answer is the
normal failure here, not a crash.

### Sampled geometry fails in the direction that hides
A flattened curve is always *inside* the true one, so a sampled bounding box is always
slightly too small, a sampled area slightly too little, and a clearance built on them
slightly too generous. Every one of those errors makes a figure look *more* correct than it
is. Area, centroid and extent are therefore computed in closed form — the integrands are
polynomials of degree ≤ 8 and integrating a polynomial is arithmetic. Length has no
elementary closed form and uses adaptive subdivision with a stated tolerance; measured
against 200,000 chords, relative error **8.4 × 10⁻⁸**.

### The tight extent is not the control-point hull, and the gap is not small
A cubic lies inside the convex hull of its control points and generally does not touch it.
One quarter-turn arc from (0,0) to (100,0) with controls at y=100 peaks at **y = 75**. The
cheap bound is **33% too tall** on a single segment. Phase 1 shipped the cheap version with a
docstring saying so; phase 2 replaced it.

### A parser written from a specification must be checked against that specification's
### reference implementation
The font metric reader is ~200 lines over six tables and no dependency. It is checked against
`fontTools` where installed: six families × four strings of advance widths, plus every glyph
ink box for eight characters. **Zero mismatches.** Writing it was cheap; the confidence came
entirely from the comparison, and without it this would be 200 lines of hopeful bit-twiddling
in the one module whose whole purpose is to be trusted without looking.

### A bare number in a millimetre box is seven *millimetres* of type
`fit(caption, 40, 8, "Helvetica", 7)` with a box in mm means 7 mm of type — about 20 pt — and
the failure is not an exception. It is a caption that wraps to three lines and reports,
correctly, that it does not fit. Found at the first real label in the demo. Fixed by applying
the scene format's own rule one level down: a bare number is in the box's unit, a suffixed
string carries its own. `"7pt"` is seven points however the box is measured.

### A text element that measures 0 × 0 passes every check there is
`_runs_of` returned the anchor point for a text element, so its bounding box was a point. It
overflowed nothing, collided with nothing and fitted anywhere — in a toolkit whose *first
listed failure* is labels overflowing their boxes. Text now measures its real ink box from
the font, and a font that cannot be resolved raises `Unmeasurable` rather than returning a
degenerate answer. Scanning tools record it; a single measurement exits 2, *could not be
established*.

### One definition of where an element is, after three
`element_to_page` exists because there were three, and they disagreed in two ways a figure
shows and a test did not:

* Measurement composed only an element's **own** transform, never its ancestors'. A group
  transform moved its children in the exported SVG and moved nothing in any measured box — a
  collision check and the drawing it checked disagreeing about where things are.
* Anchor recipes derived a point from post-transform geometry and stored it in a field every
  other reader treats as pre-transform, so the transform was applied twice and an attached
  label drifted further away on every solve.

*Rejected on the way: a second "local" matrix that stopped short of the element's own
transform.* It was written to fix the second bug and made it worse, because it answered a
question with no referent — there is no space in which an element's anchors sit but its
geometry does not.

### The solver moved traced elements by a fortieth of what it asked for
A relation is solved in the page frame, in millimetres; an element's own `transform` is
applied in whatever context it sits in, which for anything traced is **image pixels**.
Composing a millimetre delta into a pixel transform moved the enzyme 0.1 mm when it asked for
4, so the solver kept asking, hit its 24-pass limit, and reported — correctly — that the
layout never settled.

**Everything that worked before was in the page frame, where the two units happen to be the
same one.** The bug was invisible to every test and every demo until a traced element was
given a relation. After the fix the same layout settles in **10 passes**, and `clear` +
`inside` together — which had looked like a genuine oscillation between two fighting
constraints — settle cleanly.

### A check that fires on every correct figure is one nobody reads
The first `overlap` rule reported every overlapping pair in the scene. On the first real
figure — a DNA duplex seated in a traced enzyme — it produced **27 warnings**, every one about
the drawing being a drawing: two strands cross, thirteen rungs meet both strands, the duplex
enters the enzyme because that is the point of the figure. It buried the one finding that
mattered.

Rewritten to say what it means. An overlap is a defect **when a label is involved**;
otherwise it is the drawing. A separation is a layout question **between objects**, so it is
measured between different top-level elements and never inside one. The exhaustive scan still
exists as `scene.collide`, where it is an answer somebody asked for rather than a verdict.

Findings also collapse: thirteen rungs in one colour that fails contrast is **one** defect
with one fix, and it was reported thirteen times.

### A view may not compute, and the first one did
§7.7: a number shown to a person must have been computed by whatever produced the payload, so
that one answer exists rather than two. The first overlay drew the right picture and measured
every bounding box itself — a second source of truth wearing a picture. Split into a producer
that measures and a view that draws, the view now renders from a hand-written dict, which is
how its purity is actually tested.

The same split fixed the readability problem underneath it: whether a label *fits its box*
needs text metrics, metrics need the font file, and a view may not open one. The producer
decides and marks each box; the view obeys and reports how many it hid.

### An inspection tool nobody can read has failed at the only thing it does
The first overlay annotated every element at every depth: thirteen base-pair rungs put
thirteen labels on the same line of the picture, over each other, over the art. Now it draws
two levels by default, hides labels wider than their boxes — and **says both**, because a
filtered overlay that does not admit it is a wrong one.

---

## Phases 6–7 — style guides and layout

### A style system that makes a figure less checkable is worse than none
Reading `el["style"]` directly was harmless while every element carried literals, and wrong
the moment one asked for a role instead. A figure drawn entirely by role measured as having
**no stroke width, no type size and no colour** — so every check passed, the colour inventory
was empty, and every text element was unmeasurable. Fixed by one `model.effective_style`,
shared by the renderer, the measurer and the checker, so that what is drawn, what is measured
and what is checked cannot be three different things.

### `"6pt"` is not the number 6
`_text_runs` resolved a type size to **points** and then handed the resulting advance back as
**frame units**. Every label in a millimetre frame came back about three times too wide:
"substrate" measured 24.2 mm instead of 8.5 mm. It was found only because the overlap check
started complaining that captions crossed the boxes they sit inside. The fix is the format's
own rule, applied one level down — `model.resolve_length` against the element's frame — and
it is the second time the same rule has had to be applied somewhere it was assumed.

### A check that fires on every correct figure, twice more
Both of these called a correct figure wrong on the first real multi-panel figure:

* **Contrast on fills.** A pale surface tint behind a label, outlined with a stroke that
  passes on its own, was four errors. Contrast asks whether a reader can *see* the thing; an
  outlined shape is seen by its outline. A fill is now checked only when nothing else makes
  the shape visible.
* **Label overlap by containment.** A caption sitting *inside* the box it labels is the
  normal case, and the containment test called every one an error. What makes text unreadable
  is ink running **through** it, so the rule now asks whether the outlines cross. A label
  wholly inside a filled shape does not; half-on-half-off does; over line work does.

Once both were fixed, the same check found two things that were genuinely wrong and easy to
miss: a panel letter touching the first box by 0.27 mm, and the word "inhibitor" 0.4 mm wider
than the box holding it.

### An open path is not a closed one, and the containment test did not know
`polys_overlap` ran its inside-ness test on whatever it was handed. A routed connector whose
path happened to wrap around a box was reported as overlapping it, and the measured clearance
came back **0.0** on a route that clears by 2 mm. The route was right; the measure was wrong
about what kind of shape it had. `measure.encloses` now decides, and closedness is threaded
through clearance, collision, probing, verification and the relation solver.

### The router measured its own work by sampling, a week after writing down not to
`route` reported the clearance it achieved by scanning the route's **corners**. On a route
whose closest approach along a straight segment was 2.0 mm it reported **5.85 mm** — the
identical sampling error this log warns about under *Sampled geometry fails in the direction
that hides*, committed in new code by the person who wrote the warning. A vertex scan misses
every closest approach between two vertices, and misses it flatteringly. Now densified and
measured the way `scene.gap` measures, and the test asserts the router's claim against an
independent measurement at three tolerances.

### Two ways the router was right and the figure was wrong
Worth separating, because both looked like router bugs:

* **A 3 mm gap cannot hold 1.5 mm of clearance on both sides.** The refusal was correct and
  the demo's geometry was not.
* **A connector starts on the edge of the thing it leaves**, so its endpoint sits inside that
  obstacle's own inflated region. Unblocking the single cell left the route walled in by its
  neighbours and every sensible request came back "no route". The thing a connector is
  attached to may not block it where it attaches.

And one way the router was simply wrong: **the padding that gives a route room around an
obstacle also gave it room outside the canvas**, so a wall spanning the whole page was
cheerfully routed around through the margin — a connector that leaves the paper, reported as
a success. Routing is now bounded by the page.

### A palette is relative to its background, and to the ink beside it
The shipped guide's series was generated against itself, on white. Two consequences, both
found by the checks rather than by looking:

* Against the guide's own `support` colour it produced a pair that is one colour under
  protanopia (9.7 ΔE). The series is now generated against ink, accent, support and muted.
* Reused unchanged on the dark variant, two swatches came out at **2.2:1 and 2.3:1** on a
  `#14171c` page. The dark variant now carries its own series, generated against its own
  background and its own ink.

### Applying a guide must not silently unstyle what it has not heard of
Replacing `style.roles` wholesale is the clean reading of "the guide decides", and it blanks
every element asking for a role the guide never defined — which is exactly what happens the
first time somebody adopts a traced figure and then applies a house style. Unknown roles are
carried over and **reported**. `adopt` also reports the nearest guide role and which
properties differ, so `adopted-01 is closest to 'structure-stroke', differing in stroke_width`
is something to act on rather than a guess to be quietly applied.

### A panel letter written with literals ignores the guide it was laid out under
`layout.panels` wrote `font_size: "10pt"` on every letter. A literal beats a role, so the
letters ignored the guide **and** showed up in `style.adopt` as their own invented role.
Writing none unconditionally is worse — a panel laid out in a scene with no guide has an
unmeasurable letter on it — so the letter takes a literal only when nothing defines the role.

### Reflow is not scale, and the difference has to be recorded
Re-laying the panel grid left a 45 mm drawing sitting in a 23 mm panel. The distinction the
spec asks for — a drawing fills the new panel, a 10 pt label is still 10 pt — is a property
of the *element*, so `into_panel` records `fit` on it and `reflow` re-fits exactly those.

### Moving an element into a panel does nothing unless its frame moves with it
An element that declares its own frame has a coordinate context starting at that frame, not
at the group it sits in. Re-parented, it lands in the panel; not re-parented, it renders
exactly where it was — the move succeeds and means nothing, which is the hardest kind of
failure to see.

---

## Phases 8–9 — the glyph library and data to graphics

### A parameterised library must not share a namespace with the machinery that calls it
`Glyph.build(self, name, **args)` meant `dna.plasmid`, which quite reasonably takes a `name`,
**could not be placed at all** — "got multiple values for argument 'name'", from a glyph whose
author did nothing wrong. Arguments now arrive as a dict. A library's parameter names are its
own business.

### The same mistake four times, until a test ran over the whole catalogue
An anchor sharing a child element's name makes an address mean two things, and
`scene.validate` refuses the scene. It happened in `dna.plasmid` (`site-N`), `gel.lanes`
(`lane-N`), `lab.pipette` (`tip`), `process.steps` (`stage-N`) and `lab.gradient`
(`top`/`bottom`) — five glyphs, found one at a time as each was first placed.

**The fix that mattered was not any of those renames.** It was a parameterised test that
places *every* registered glyph and validates it, plus four more over the whole catalogue: no
literals, has anchors, deterministic, verifies clean. A library grows and the same mistakes
recur; a check that scales with it is worth more than five corrections.

### A glyph's own coordinates start where its ink does, and did not
The molbio module's docstring says a glyph's origin is its top-left. Several put labels at
negative coordinates — the duplex's 5′ marks, the plate's row letters — so placing one at the
page corner put those off the paper, and the `off-canvas` check said so for five of thirteen
glyphs. `place` now **measures** the instance and shifts it so `at` is its top-left, and says
when it could not (an unstyled scene has no font for the labels).

### A silhouette is the outline, and a label written across it is not part of it
`concavity` on a protein glyph read its own name label as the deepest inlet — **7.7 mm** from
the cleft the glyph declares, and near the centre, because a box in the middle of a shape is a
long way inside its hull. With text excluded the two agree to **0.1–1.0 mm**, which is the
difference between the analytic formula and the Catmull-Rom curve actually drawn, and is now
what the docstring claims rather than "agrees".

### Two ways to say which way is up can disagree, and did
`Scale` had a `flip` flag *and* took a range whose order also implied direction. The first
real plot drawn with it put zero at the top of the panel and its significance bracket off the
bottom — silently, because both were self-consistently wrong. The flag is gone: the range's
order is the direction, `linear((0, 135), (57, 6))`, and it cannot contradict itself.

### Three checks that were right about a correct figure, and one that was wrong about a fix
The data panels exercised the verification harder than anything before, and it needed
narrowing three more times and widening once:

* **A fill exactly equal to the background is deliberate.** A legend's backing plate is
  *meant* to be invisible; what must be visible is what sits on it. An accident gives a colour
  *close* to the background, not identical at eight bits a channel — so an exact match is the
  one case this can read as intent.
* **The background is not an encoding colour.** Comparing every colour in the scene against
  the paper reported a surface tint as indistinguishable from it, on every figure with a tint.
* **The check could not see occlusion.** A legend on a plate — the standard fix for a legend
  over a grid — was still reported as unreadable. It now walks elements in drawing order and
  recognises an opaque fill drawn between. The first attempt asked whether the plate covered
  the *gridline*, which runs the height of the panel; the box that matters is the **label's**.
* **And then that exemption hid a real defect.** The plate was covering the decay curve, and
  forgiving the label overlap forgave that too — a figure quietly missing a stretch of its own
  data behind the thing meant to explain it. So `occluded` reports what a plate hides, always.
  A finding removed must not take a fact with it.

### A confidence band that runs off the panel is not narrower than it is
There is no clipping in the scene format, so a band on data the line does not describe well
ran over the tick labels. It is now held inside the y domain **and the number of clamped
points is reported** — a band silently trimmed is a confidence interval drawn narrower than it
is, which is the one way a statistical annotation must never fail.

---

## Phases 10–12 — diagrams, animation, and one report

### A default that overrides what the caller already said is worse than no default
`diagram.flow` resolved its `frame` argument to the page frame and then **stamped** it on
every node it created. A node placed under a group with its own frame came out carrying
`frame: page`, so it rendered at the page origin — and four diagrams on one page sat on top of
one another. The opposite mistake followed within the hour: passing no frame at all left the
connector group in the page frame while its geometry had been computed in another one, so a
routed edge drew itself at the page corner. Both are the same error about whose business the
frame is. A frame is now stamped **only when it differs from what the parent already gives**.

### The router was right; the layout was not
Two vertically connected nodes of different widths have different centres, so every edge
between them jogged sideways by 0.88 mm — which reads as a kink in what should be a straight
arrow. Layers are now centred on a common axis. Separately, the grid snaps a route's interior
to `resolution` while its endpoints stay exact, so even aligned boxes got two little jogs:
**when the straight line is clear, there is nothing to route**, and it is taken directly.

### An obstacle in another coordinate space is not in the way
`edge`'s default `avoid` was every element tagged `node` anywhere in the scene. On a page with
four diagrams that included nodes in other frames; measured into this one they land hundreds
of millimetres away, the routing region grows to cover them all, and the search is refused as
too large. Scoped to the diagram.

### The same name for the anchor and the child, five more times
`site-N`, `lane-N`, `tip`, `stage-N`, `top`/`bottom` — the glyph library's lesson repeated in
the diagram module and the library's own second pass. The parameterised catalogue test caught
the glyph ones; `process.steps` and `lab.gradient` were caught by placing every glyph.

### A field the solver reads that the schema forbids
`anchors._wanted` has read an `edge` property on `align` relations since phase 4. **The schema
never allowed it**, so every alignment relation produced an invalid scene. Nothing noticed for
three phases because the tests that exercise alignment call `solve` and the tests that call
`validate` do not use alignment — it took a consolidated report running both over one document
to put them together.

The fix is one schema line. The lesson is the test that now exists: *every relation kind
produces a scene that validates, before and after solving.* A guarantee about a field nothing
may carry and a field nothing may carry that something reads are the same defect seen from
either end.

### A frame of an animation has to be a figure, or it is not checkable
The design decision that made everything else fall out: a timeline is a separate document and
sampling it returns **a scene**. Animation done in the exporter would have made frame 12 of a
build unmeasurable and unverifiable — precisely the state §3.15 exists to end for static
figures. Because a still is an ordinary scene, `verify` runs on it with no new code.

`draw` therefore trims real geometry rather than setting a dash offset: a half-drawn stroke
**measures** as half drawn, which a dash trick cannot do.

### A still of a stage is taken after its rise
At the mark itself the element being revealed is still at zero opacity, so a still of stage 3
showed stage 2. Obvious in hindsight and not at all obvious while writing it.

### `unchecked` is never folded into a pass
The consolidated report counts three things, not two. A figure with no errors and four checks
nobody could run is **unestablished**, not clean; leaving out the style guide or the reference
image says so rather than quietly reporting a pass on the checks that did run. The same rule
governs regression: a **missing** reference is unavailable, because the first run of a
regression suite has nothing to compare against and calling that success protects nothing.

### Three more narrowings of the verification, all from real figures
* **A fill exactly equal to the background is deliberate** — a knockout or a legend plate.
* **The background is not an encoding colour**, so it is excluded from the distinguishability
  comparison.
* **A plate over its own sibling is the standard way to label an edge**, so `occluded` reports
  only a plate covering something from a different part of the figure. Reporting it on every
  labelled edge buried the case that matters.

---

## The showcase — five defects found by building one real figure

A figure that uses every part of a toolkit exercises it differently from five figures that
each use one part. Everything below was found by building `examples/showcase.py`, and every
one of them was in code that had passed its own tests.

### The solver chased noise the format cannot store
`io.PLACES` rounds every coordinate to six decimals, and the solver's tolerance was `1e-6`.
So a scene written out and read back in differed from itself by more than the solver was
willing to accept: **a figure re-solved after a round trip through its own file always
reported an element as having moved**, by 2 × 10⁻⁴ mm, and `figure.report` duly warned that
the stored document was not the drawn one. The measured residual set the new threshold: 1e-3
mm, one part in 180,000 of the page.

A tolerance finer than the precision of the format it is stored in is not strictness. It is a
check that can never pass.

### A text block measured in one font and drew in another
`text.block` took a `family` and `size`, measured with them, wrote them onto the elements as
literals **and** set a role — so the block was laid out in Helvetica 7 pt and drawn in
whatever the guide said `caption` meant. The style lint reported the literals, which is how it
surfaced. `block` now takes the document, reads the font from the role, and writes no literal
at all: measuring with what will actually be drawn is the only version of this that cannot
drift.

### A caption at a fixed y is a caption in the wrong place
Reflowing the figure to a column re-laid the panels and left the caption where the panels used
to be. Positioned by declaration instead — left-aligned with the first panel, **below** the
last — it follows. That needed a new alignment: `align` could match an edge to the *same* edge
and had no way to say "below", which is the one thing a caption needs.

### Retargeting a figure means retargeting its grid
Four panels that sit 2 × 2 on a slide do not fit 2 × 2 in an 88 mm column, and forcing them to
produced contents running off both sides — two errors the check reported and no amount of
re-fitting could have solved. `reflow` now takes `rows` and `cols`.

### An obstacle that obstructs nothing, and a bound that bound half of it
The figure claimed its bypass went round the inhibitor. It did not: the inhibitor sat clear of
every route and the arrow detoured round the extension step instead — **the narration was
false and nothing caught it**, because "there is a route" and "the route goes round *that*"
are different claims. Moving the obstacle into the corridor made the claim true, and the test
now asserts the clearance between those two specific elements.

Bounding that route to its panel then kept the line inside and hung its **label** 3.4 mm off
the panel's left edge — which looks exactly like the bound not working. A bound on a route and
not on its label is half a bound.

---

## §3.15 — the interactivity, and what building it cost

Asked point blank whether any of this was interactive, the honest answer was **no**. The
overlay was a static SVG; everything else ran, wrote a file and stopped. §3.15 was about a
third built and it is the family whose "done when" is the whole point: *a person can look at
any intermediate state, name what they want changed, and have that be a single instruction.*

### The view rule decided the architecture, again
An interactive page **can** be a view: markup with a script in it is still a pure function of
its payload, because the script runs in the reader's browser and not in the view. So the
inspector carries its data as embedded JSON, opens from `file://`, needs no server, and can be
sent to somebody with none of this installed. Only the live preview — which reads a file
repeatedly — is a function rather than a view, and it serves *the same pure inspector*.

That split is not tidiness. It is why an overlay of a figure in progress is a thing you can
email.

### The overlay could not have drawn two of the things §3.15 asks for
The spec lists **z-order and style roles** among what an annotated overlay shows. The payload
carried neither, so no view could have drawn them however it was written. Added to the
producer, where they are measured, and the view draws them — which is the same producer/view
split the whole module rests on, found missing in the one place it was first applied.

### Both layers in one positioning context
The onion wipe inset its top layer from the card while the base sat inside the card's padding.
Ten pixels of offset, and the figure showed its caption twice at the seam — which reads as a
bug in the *figure*, not in the page. A comparison view whose misalignment is indistinguishable
from a real difference is worse than no comparison view.

### A preview at true size has to admit it might be lying
`width: 180mm` in CSS is only 180 mm if the browser knows the display's physical size, and
often it does not. So the true-size page carries a **ruler**, and says in as many words that if
a real ruler disagrees with the scale then no on-screen preview can be trusted for legibility.
The alternative is a page that quietly shows the wrong size to somebody deciding whether 6 pt
is readable.

### Absence, in three more places
A variant that could not be rendered appears in the contact sheet as *not shown, and why* — a
blank panel reads as a variant that produces nothing. A scene the watcher cannot load shows the
loader's error, not the last good render. A figure with no verification run says so where the
findings would be. Same rule as the overlay payload, applied to three new surfaces.

### What it still is not
The inspector **picks and reports; it does not edit.** Nothing drags. The loop is look, name,
run one command, watch it re-render — which is what the spec asked for, and is not an editor.
Worth writing down so the next person does not read "interactive" as more than it is.
