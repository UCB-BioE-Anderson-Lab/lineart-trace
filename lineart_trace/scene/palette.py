"""Palettes that can be told apart: generate, extend, and check. §3.11.

**Distinguishable is a measurement, not a taste.** A palette is usable when every pair of its
colours is far enough apart *for every reader*, which means checking each pair under normal
colour vision and under all three dichromacies, and checking each colour against the
background it will actually sit on. This does all four and reports the worst case, so a
palette is accepted or rejected on a number.

Generation is a deterministic greedy search over a fixed candidate grid: at each step, take
the candidate whose worst-case separation from everything already chosen is largest. No
randomness, so the same request returns the same palette on every machine and a figure
regenerated a year later diffs clean.
"""
import colorsys

from . import verify

__all__ = ["generate", "extend", "check", "candidates", "separation", "VISIONS"]

#: Normal vision and the three dichromacies. A palette must survive all four.
VISIONS = ("normal", "deuteranopia", "protanopia", "tritanopia")


def _hex(rgb):
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, c)) * 255)):02x}" for c in rgb)


def candidates(hue_step=10, lightness=(0.38, 0.55, 0.72), saturation=(0.85, 0.55)):
    """The fixed grid searched over. Ordered, so the search is reproducible."""
    out = []
    for light in lightness:
        for sat in saturation:
            for h in range(0, 360, hue_step):
                out.append(_hex(colorsys.hls_to_rgb(h / 360.0, light, sat)))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def separation(a, b):
    """The WORST Lab distance between two colours across all four kinds of vision.

    The worst, not the average: a pair that is vivid to most readers and identical to some is
    a pair that fails, and averaging is how that gets reported as fine.
    """
    worst = None
    for vision in VISIONS:
        x = a if vision == "normal" else verify.simulate(a, vision)
        y = b if vision == "normal" else verify.simulate(b, vision)
        d = verify._delta_e(x, y)
        if d is None:
            return None
        worst = d if worst is None else min(worst, d)
    return worst


def _ok_against(colour, background, min_contrast):
    if not background or background == "none":
        return True
    r = verify.contrast_ratio(colour, background)
    return r is not None and r >= min_contrast


def extend(existing, n, background="#ffffff", min_contrast=3.0, min_delta_e=20.0,
           pool=None):
    """`n` more colours that stay distinguishable from `existing` and from each other.

    Returns ``(colours, report)``. When the pool cannot supply `n` that clear the
    thresholds, it returns the ones it could and **says how many it could not** rather than
    relaxing the threshold quietly -- a palette that reports success with two
    indistinguishable colours in it is worse than one that reports it came up short.
    """
    pool = pool or candidates()
    chosen = list(existing)
    picked, trace = [], []
    for _ in range(n):
        best, best_score = None, -1.0
        for c in pool:
            if c in chosen or c in picked:
                continue
            if not _ok_against(c, background, min_contrast):
                continue
            others = chosen + picked
            score = min((separation(c, o) or 0.0) for o in others) if others else 999.0
            if score > best_score:
                best, best_score = c, score
        if best is None or best_score < min_delta_e:
            trace.append({"wanted": n, "got": len(picked),
                          "why": (f"nothing left in the pool clears {min_delta_e:g} ΔE "
                                  f"against what is already chosen"
                                  f" (best was {best_score:.1f})" if best else
                                  f"nothing left in the pool clears "
                                  f"{min_contrast:g}:1 against {background}")})
            break
        picked.append(best)
    worst = None
    allc = chosen + picked
    for i in range(len(allc)):
        for j in range(i + 1, len(allc)):
            d = separation(allc[i], allc[j])
            if d is not None and (worst is None or d < worst):
                worst = d
    return picked, {"requested": n, "produced": len(picked),
                    "worst_separation": worst, "short": trace,
                    "background": background, "min_contrast": min_contrast,
                    "min_delta_e": min_delta_e}


def generate(n, background="#ffffff", min_contrast=3.0, min_delta_e=20.0, pool=None):
    """`n` colours that any reader can tell apart, on `background`. ``(colours, report)``."""
    return extend([], n, background, min_contrast, min_delta_e, pool)


def check(colours, background="#ffffff", min_contrast=3.0, min_delta_e=20.0):
    """Every pair, under every vision, plus contrast against the background.

    The report names the worst pair rather than only counting problems, because the fix is
    always to change one of two specific colours.
    """
    pairs, bad = [], []
    for i in range(len(colours)):
        for j in range(i + 1, len(colours)):
            a, b = colours[i], colours[j]
            per = {}
            for vision in VISIONS:
                x = a if vision == "normal" else verify.simulate(a, vision)
                y = b if vision == "normal" else verify.simulate(b, vision)
                per[vision] = verify._delta_e(x, y)
            worst_vision = min(per, key=lambda k: (per[k] if per[k] is not None else 1e9))
            entry = {"a": a, "b": b, "delta_e": per,
                     "worst": worst_vision, "worst_delta_e": per[worst_vision]}
            pairs.append(entry)
            if per[worst_vision] is not None and per[worst_vision] < min_delta_e:
                bad.append(entry)
    contrast = []
    for c in colours:
        r = verify.contrast_ratio(c, background)
        entry = {"colour": c, "background": background, "ratio": r}
        contrast.append(entry)
        if r is not None and r < min_contrast:
            entry["below"] = True
    worst_pair = min(pairs, key=lambda p: p["worst_delta_e"] or 1e9) if pairs else None
    return {"colours": list(colours), "background": background,
            "pairs": pairs, "indistinguishable": bad,
            "worst_pair": worst_pair,
            "contrast": contrast,
            "too_faint": [c for c in contrast if c.get("below")],
            "min_delta_e": min_delta_e, "min_contrast": min_contrast,
            "usable": not bad and not [c for c in contrast if c.get("below")]}
