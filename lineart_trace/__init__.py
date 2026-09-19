"""A toolkit for making SVG vector art.

Two things work today. `lineart_trace.scene` is the scene: one JSON document holding a
canvas, named frames that own their units, and a tree of named elements -- the source of
truth a figure is built in, with SVG as an export. The rest of this package is the tracer
that turns raster line art into those elements (§3.10).

See `docs/scene-format.md` for the format and `docs/spec.md` for the toolkit being built on
top of it.
"""
# Above the submodule imports, and that is load-bearing: `scene.ingest` records the tool
# version in a scene's provenance, so it reads this name while this module is still being
# executed. Assigned at the bottom, as it was, importing the package raised a circular
# ImportError -- from one line that looked like tidying up the exports.
__version__ = "0.2.0"

from .binarize import (binarize, despeckle, flatten_background, has_chroma,
                       to_gray)
from .color import (Layer, ink_distance, ink_mask, paper_color,
                    separate_colors, to_hex)
from .fitting import corner_indices, fit_curve, smooth_chain
from .graph import Chain, build_graph, chain_length, prune_and_merge, skeleton_chains
from .metrics import compare, coverage, distance_stats
from .raster import flatten_cubic, flatten_path, rasterize, render
from .regions import region_contours, split_fills, stroke_width_of, thinness
from .thinning import crossing_number, neighbour_count, skeletonize, thin_redundant
from .trace import (FillPath, StrokePath, TraceResult, trace_file, trace_image,
                    trace_mask)
from . import scene

__all__ = [
    "scene",
    "TraceResult", "StrokePath", "FillPath",
    "trace_file", "trace_image", "trace_mask",
    "binarize", "despeckle", "flatten_background", "to_gray", "has_chroma",
    "Layer", "paper_color", "ink_mask", "ink_distance", "separate_colors",
    "to_hex",
    "skeletonize", "thin_redundant", "crossing_number", "neighbour_count",
    "build_graph", "skeleton_chains", "prune_and_merge", "chain_length", "Chain",
    "split_fills", "region_contours", "stroke_width_of", "thinness",
    "fit_curve", "corner_indices", "smooth_chain",
    "rasterize", "render", "flatten_path", "flatten_cubic",
    "compare", "coverage", "distance_stats",
]
