# lineart-trace

Centreline vectorisation of black-on-white line art into SVG cubic Béziers.

Unlike an outline tracer (potrace, `cv2.findContours`), which returns a closed
loop *around* each stroke, this recovers the **centreline** — so the output is
real lines you can restyle: change weight, colour, dash, or animate.

```bash
lineart-trace art.png --width 1180 --svg > art.svg
```

```python
from lineart_trace import trace_file
r = trace_file("art.png", error=1.0, prune=14)
print(r.n_paths, r.n_segments, r.stroke_width)
svg = r.to_svg_group(scale=0.5, color="#3e5c8a")
```

## Pipeline

1. **Binarize** to an ink mask.
2. **Zhang–Suen thinning** (1984) → 1px-wide skeleton.
3. **Skeleton graph walk** → one ordered point chain per stroke, split at
   endpoints and junctions.
4. **Schneider fitting** (Graphics Gems, 1990) → cubic Béziers per chain.

Stroke width is recovered from the distance transform, so traced art keeps the
weight it was drawn at (`--stroke` overrides).

## Two non-obvious things this gets right

**Branch points are found by crossing number, not neighbour count.** On a
diagonal staircase an ordinary interior pixel has three 8-neighbours. Counting
neighbours reports false branch points and shatters every curve into fragments
— a plain circle traced to 29 separate paths before this was fixed.

**Short junction-to-junction chains are structural.** Pruning every short chain
removes the piece of a line *between* two crossings, so every crossing punches
a visible gap. Only chains with a free end are treated as thinning spurs.

## Known limitations

Verified against `tests/fixtures/stress.png` (regenerate with
`python examples/make_stress.py`):

| Case | Behaviour |
|---|---|
| Filled black regions | **Destroyed.** A filled arrowhead skeletonises to a spine. Outline your shapes. |
| Varying stroke width | **Flattened.** One median width is emitted for the whole drawing. |
| Isolated dots | **Dropped** by pruning. |
| Small closed shapes with sharp corners | Corners round off; short edges can be lost. |
| Crossings, T-junctions, tangency | Handled. |
| Parallel lines ≥1× stroke apart | Resolved separately. |
| Dense hatching | Handled, but generates many short paths. |
| Long shallow curves | Occasional seams; `--close 3` bridges antialias breaks. |

## Open bug

A plain circle yields **2 paths, not 1**: one closed chain of the full ring
plus a stray ~4px closed fragment. The skeleton is clean (all 565 pixels have
crossing number 2, no endpoints, no branch points), so the walk is leaving a
few pixels behind and they form their own degenerate loop. `merge_chains`
skips closed chains, so it never absorbs it. See
`tests/test_trace.py::test_circle_is_closed_loop`.

## License

MIT
