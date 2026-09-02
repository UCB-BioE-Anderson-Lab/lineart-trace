"""Centreline vectorisation of line art into SVG cubic Beziers."""
from .binarize import binarize, despeckle, flatten_background, to_gray
from .fitting import corner_indices, fit_curve, smooth_chain
from .graph import Chain, build_graph, chain_length, prune_and_merge, skeleton_chains
from .metrics import compare, coverage, distance_stats
from .raster import flatten_cubic, flatten_path, rasterize
from .regions import region_contours, split_fills, stroke_width_of, thinness
from .thinning import crossing_number, neighbour_count, skeletonize, thin_redundant
from .trace import (FillPath, StrokePath, TraceResult, trace_file, trace_image,
                    trace_mask)

__all__ = [
    "TraceResult", "StrokePath", "FillPath",
    "trace_file", "trace_image", "trace_mask",
    "binarize", "despeckle", "flatten_background", "to_gray",
    "skeletonize", "thin_redundant", "crossing_number", "neighbour_count",
    "build_graph", "skeleton_chains", "prune_and_merge", "chain_length", "Chain",
    "split_fills", "region_contours", "stroke_width_of", "thinness",
    "fit_curve", "corner_indices", "smooth_chain",
    "rasterize", "flatten_path", "flatten_cubic",
    "compare", "coverage", "distance_stats",
]
__version__ = "0.2.0"
