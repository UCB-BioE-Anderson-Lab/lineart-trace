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
