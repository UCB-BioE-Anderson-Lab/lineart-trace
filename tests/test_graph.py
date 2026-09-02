import math

import cv2
import numpy as np

from lineart_trace.graph import (build_graph, chain_length, prune_and_merge,
                                 skeleton_chains)
from lineart_trace.thinning import skeletonize


def blank(w=400, h=300):
    return np.full((h, w), 255, np.uint8)


def skel_of(im):
    return skeletonize((im < 200).astype(np.uint8))


def test_circle_is_one_closed_chain():
    """Regression: the walk used to overrun its own start and abandon the
    staircase pixels it stepped over, which came back as a stray loop."""
    im = blank(); cv2.circle(im, (200, 150), 90, 0, 8)
    chains, junctions = build_graph(skel_of(im), 4)
    assert junctions == {}
    assert len(chains) == 1
    c = chains[0]
    assert c.closed and c.pts[0] == c.pts[-1]
    assert c.length > 2 * math.pi * 85


def test_no_stray_fragments_anywhere_in_the_corpus():
    """Every chain must be long enough to be a stroke, not walk leftovers."""
    from lineart_trace import corpus
    from lineart_trace.binarize import binarize
    for spec in corpus.build_all():
        skel = skeletonize(binarize(spec.image))
        if skel.sum() == 0:
            continue
        chains = prune_and_merge(build_graph(skel, 2)[0], 6.0)
        assert all(len(c.pts) >= 2 for c in chains), spec.name
        tiny = [c for c in chains if c.closed and c.length < 4]
        assert not tiny, f"{spec.name}: {len(tiny)} degenerate loops"


def test_crossing_yields_four_arms_through_one_point():
    im = blank()
    cv2.line(im, (40, 150), (360, 150), 0, 8)
    cv2.line(im, (200, 30), (200, 270), 0, 8)
    chains, junctions = build_graph(skel_of(im), 4)
    chains = prune_and_merge(chains, 14)
    assert len(junctions) == 1
    assert len(chains) == 4
    # every arm ends at the junction centroid, so the crossing has no gap
    hub = junctions[1]
    for c in chains:
        assert hub in (c.pts[0], c.pts[-1])


def test_eight_spokes_do_not_shatter():
    """A hub used to emit a fistful of 2-pixel chains, one per branch pixel."""
    im = blank(500, 400)
    for a in range(0, 360, 45):
        p = (int(250 + 150 * math.cos(math.radians(a))),
             int(200 + 150 * math.sin(math.radians(a))))
        cv2.line(im, (250, 200), p, 0, 8)
    chains = prune_and_merge(build_graph(skel_of(im), 4)[0], 14)
    assert len(chains) <= 8
    assert min(c.length for c in chains) > 100


def test_spurs_are_pruned_but_junction_segments_are_kept():
    im = blank(600, 300)
    cv2.line(im, (40, 150), (560, 150), 0, 9)
    for x in (200, 240):                       # two crossings close together
        cv2.line(im, (x, 60), (x, 240), 0, 9)
    chains = prune_and_merge(build_graph(skel_of(im), 5)[0], 20)
    mid = [c for c in chains
           if c.a is not None and c.b is not None and c.length < 60]
    assert mid, "the piece of line between the two crossings was dropped"


def test_merge_splices_a_false_junction():
    """A stray branch pixel on a smooth curve must not leave a visible seam."""
    im = blank(); cv2.ellipse(im, (200, 150), (150, 90), 0, 0, 360, 0, 8)
    chains = prune_and_merge(build_graph(skel_of(im), 4)[0], 14)
    assert len(chains) == 1


def test_skeleton_chains_is_ordered_and_contiguous():
    im = blank(); cv2.line(im, (40, 40), (360, 260), 0, 8)
    for ch in skeleton_chains(skel_of(im), 14):
        for (y0, x0), (y1, x1) in zip(ch, ch[1:]):
            assert max(abs(y1 - y0), abs(x1 - x0)) <= 2


def test_chain_length_matches_geometry():
    assert abs(chain_length([(0, 0), (0, 30), (40, 30)]) - 70) < 1e-9


def test_empty_skeleton():
    assert build_graph(np.zeros((20, 20), np.uint8)) == ([], {})
