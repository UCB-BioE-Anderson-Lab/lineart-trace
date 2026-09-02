"""Emit an SVG that recolours the drawing's inks on a loop.

    python examples/make_color_loop.py

The point is not the animation. The point is that it is *possible*: the trace
came out as paths grouped by the pen that drew them, so changing the sand from
ochre to green is one attribute on one group. Do the same to the source PNG
and you are painting pixels.

Paths are binned by colour and each bin becomes a single <g> carrying one
<animate>, so an image with a thousand strokes needs six animations, not a
thousand. SMIL animation plays in an <img>-embedded SVG, which is how GitHub
renders a README image.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lineart_trace import trace_file                              # noqa: E402

SOURCE = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                      "beach.png")
# beach.png's flat regions have ragged, hole-punched boundaries, which the
# default thinness test reads as stroke-like. Lowering the threshold is a
# setting, not a change of algorithm; see the limitations table.
OPTS = {"colors": 0, "thin_limit": 0.05}

# Pen the tracer finds -> the loop it cycles through. The three sequences are
# stepped together, so they must stay distinguishable at EVERY step, not just
# on average. A palette that gave the sand a light green while the ocean took
# a dark green erased the shoreline between them, and the picture read as a
# different shape -- which looks like missing paths and is not.
CYCLES = {                     # sand          ocean          ball
    "#e6ba2c": ["#e6ba2c", "#ff8fab", "#a8dadc", "#c9e265"],
    "#014184": ["#014184", "#2a9d8f", "#6a4c93", "#8c2f39"],
    "#c63b13": ["#c63b13", "#3d348b", "#f4a261", "#1b6ca8"],
}


def _animate(attr, colours, dur):
    values = ";".join(list(colours) + [colours[0]])       # close the loop
    return (f'<animate attributeName="{attr}" dur="{dur}s" '
            f'repeatCount="indefinite" values="{values}"/>')


def build(src=SOURCE, out="docs/beach-recolour.svg", dur=8.0, **opts):
    res = trace_file(src, **{**OPTS, **opts})
    default = res.colors[0] if res.colors else "#111111"
    w, h = res.size

    fills, strokes = {}, {}
    for f, d in zip(res.fills, res.to_fill_paths()):
        fills.setdefault(f.color or default, []).append(d)
    for s, d in zip(res.strokes, res.to_svg_paths()):
        strokes.setdefault(s.color or default, []).append((d, s.width))

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
             f'height="{h}" viewBox="0 0 {w} {h}">'
             f'<rect width="100%" height="100%" fill="#ffffff"/>']
    for pen, ds in fills.items():
        a = _animate("fill", CYCLES[pen], dur) if pen in CYCLES else ""
        parts.append(f'<g fill="{pen}" fill-rule="evenodd" stroke="none">{a}'
                     + "".join(f'<path d="{d}"/>' for d in ds) + "</g>")
    for pen, items in strokes.items():
        a = _animate("stroke", CYCLES[pen], dur) if pen in CYCLES else ""
        body = "".join(f'<path stroke-width="{wid:.2f}" d="{d}"/>'
                       for d, wid in items)
        parts.append(f'<g fill="none" stroke="{pen}" stroke-linecap="round" '
                     f'stroke-linejoin="round">{a}{body}</g>')
    parts.append("</svg>")

    svg = "".join(parts)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as fh:
        fh.write(svg)
    animated = [p for p in CYCLES if p in fills or p in strokes]
    print(f"wrote {out}  {len(svg) // 1024} KB  "
          f"{len(fills) + len(strokes)} groups, {len(animated)} animated")
    print(f"  pens {res.colors}")
    return svg


if __name__ == "__main__":
    build()
