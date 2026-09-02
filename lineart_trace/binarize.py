"""Any image -> a clean 0/1 ink mask.

A clean render needs nothing but a threshold. A photograph of a drawing on
paper needs the page taken out of the picture first: a phone shot of a
crumpled sheet has a brightness gradient far larger than the contrast between
ink and paper, so a single global threshold either loses the shaded half of
the drawing or floods it. Dividing by a blurred estimate of the page turns
that gradient into flat white, after which Otsu is reliable.
"""
from typing import Optional

import cv2
import numpy as np

__all__ = ["to_gray", "flatten_background", "binarize", "despeckle",
           "has_chroma"]


def to_gray(img: np.ndarray) -> np.ndarray:
    img = np.asarray(img)
    if img.ndim == 3:
        n = img.shape[2]
        if n == 4:
            # Composite onto white: a transparent PNG is not black ink.
            a = img[:, :, 3:4].astype(np.float32) / 255.0
            img = (img[:, :, :3].astype(np.float32) * a
                   + 255.0 * (1 - a)).astype(np.uint8)
        elif n != 3:
            img = img[:, :, 0]
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img.astype(np.uint8)


def has_chroma(img: np.ndarray, frac: float = 0.002, spread: int = 25) -> bool:
    """Is this genuinely coloured, or a grey image that happens to have 3 channels?"""
    img = np.asarray(img)
    if img.ndim != 3 or img.shape[2] < 3:
        return False
    bgr = img[:, :, :3].astype(np.int16)
    sep = bgr.max(axis=2) - bgr.min(axis=2)
    return float((sep > spread).mean()) > frac


def flatten_background(gray: np.ndarray, radius: int = 0) -> np.ndarray:
    """Divide out slow illumination change so the page reads as flat white.

    `radius` is the scale of the lighting variation; 0 picks about a
    sixteenth of the short side, which is well above stroke width and well
    below the size of a shadow.
    """
    gray = to_gray(gray)
    if radius <= 0:
        radius = max(15, min(gray.shape[:2]) // 16)
    k = int(radius) | 1
    # A closing keeps the estimate on the PAPER side: it fills the strokes in
    # before blurring, so ink never drags the local background down with it.
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, se)
    bg = cv2.GaussianBlur(bg, (0, 0), k / 3.0)
    bg = np.maximum(bg, 1).astype(np.float32)
    out = np.clip(gray.astype(np.float32) / bg * 255.0, 0, 255)
    return out.astype(np.uint8)


def binarize(img: np.ndarray, method: str = "auto", thresh: int = 200,
             flatten: Optional[bool] = None, denoise: bool = False,
             invert: Optional[bool] = None, block: int = 0,
             chroma: Optional[bool] = None) -> np.ndarray:
    """Return a 0/1 uint8 ink mask (1 = ink).

    method
        ``fixed``     ink is darker than `thresh`; exact and repeatable.
        ``otsu``      global Otsu split.
        ``adaptive``  local Gaussian threshold; for strong shading.
        ``auto``      Otsu, with background flattening when the image needs it.
    flatten
        Force background flattening on/off. ``None`` decides from the spread
        of local background brightness.
    invert
        Force polarity. ``None`` assumes ink is the minority and flips a mask
        that comes out more than half ink.
    chroma
        Find ink by distance from the paper COLOUR rather than by brightness.
        ``None`` turns it on for genuinely coloured input under ``auto``.
        It matters: yellow on white has a luminance around 196 of 255, so a
        brightness threshold drops yellow strokes entirely while keeping every
        smudge that is darker than they are.
    """
    if chroma is None:
        chroma = method == "auto" and has_chroma(img)
    if chroma:
        from .color import ink_mask
        mask = ink_mask(img)
        if invert:
            mask = 1 - mask
        return mask.astype(np.uint8)

    gray = to_gray(img)
    if denoise:
        gray = cv2.medianBlur(gray, 3)

    if method == "fixed":
        mask = (gray < thresh).astype(np.uint8)
    else:
        work = gray
        if flatten is None:
            k = max(15, min(gray.shape[:2]) // 16) | 1
            se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, se)
            flatten = float(bg.max()) - float(np.percentile(bg, 2)) > 40
        if flatten:
            work = flatten_background(gray)
        if method == "adaptive":
            b = block if block > 0 else (max(15, min(gray.shape[:2]) // 24) | 1)
            mask = (cv2.adaptiveThreshold(work, 1, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY_INV, b | 1, 8)
                    ).astype(np.uint8)
        else:
            t, _ = cv2.threshold(work, 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # `<=`, not `<`: on a hard-edged render with only the values 0 and
            # 255 Otsu returns 0, and a strict compare then finds no ink at all.
            mask = (work <= t).astype(np.uint8)

    if invert is None:
        invert = mask.mean() > 0.5
    if invert:
        mask = 1 - mask
    return mask.astype(np.uint8)


def despeckle(mask: np.ndarray, min_area: int = 0,
              close: int = 0) -> np.ndarray:
    """Drop specks and optionally bridge 1px antialias breaks."""
    m = (np.asarray(mask) > 0).astype(np.uint8)
    if close > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close | 1, close | 1))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    if min_area > 1:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        keep = np.zeros(n, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
        keep[0] = False
        m = keep[lab].astype(np.uint8)
    return m
