"""Font metrics read straight out of the font file. No rendering, no dependency.

§1 lists "no text metrics -- extent is unknowable without rendering" as one of the eight
failures this toolkit exists to close, and closing it means reading the tables a font already
carries: `head` for the em square, `hhea` and `OS/2` for the vertical metrics, `hmtx` for
advance widths, `cmap` to get from a character to a glyph, and `glyf` for each glyph's own
ink box.

**Why a parser rather than a library.** Only six tables are needed and none of them require
interpreting an outline -- a glyph's ink box is the first eight bytes of its `glyf` entry. A
dependency would be larger than the problem, and `lineart_trace.scene` staying importable
with nothing installed is what lets a §3.15 view render from a fixture. `fontTools`, when it
happens to be installed, is what the tests check this against.

**Determinism has a specific meaning here and it is not "the same everywhere".** A measured
advance depends on the font FILE, and two machines with different files under the same
family name will measure differently. That cannot be fixed by being careful. So every
measurement names the file it came from and its SHA-256, and a family that cannot be
resolved is a refusal rather than a substitution -- silently falling back to another face is
how a figure passes its legibility check and overflows in print.

**What is NOT measured: kerning.** No `kern` or `GPOS` lookup, so an advance is the sum of
the glyphs' own widths. Kerning only ever pulls pairs closer, so the number is an
over-estimate -- safe for "will this fit", wrong by a little for "exactly where does this
end". Stated rather than discovered.
"""
import hashlib
import os
import struct
import sys

__all__ = ["families", "resolve", "Font", "metrics", "FontNotFound", "font_dirs"]


class FontNotFound(Exception):
    """A family that could not be resolved. Never a silent substitution."""


def font_dirs():
    """Where fonts are looked for, in order. ``LINEART_FONT_PATH`` is searched first.

    The environment variable is the whole answer to reproducibility across machines: point
    it at fonts committed beside the figures and the metrics stop depending on the host.
    """
    out = []
    env = os.environ.get("LINEART_FONT_PATH")
    if env:
        out += [p for p in env.split(os.pathsep) if p]
    if sys.platform == "darwin":
        out += ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
                "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    elif sys.platform.startswith("win"):
        out += [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
    else:
        out += ["/usr/share/fonts", "/usr/local/share/fonts",
                os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")]
    return [d for d in out if os.path.isdir(d)]


# --------------------------------------------------------------------- the file
class Font:
    """One face, opened for metrics. Cheap: it reads tables, never outlines."""

    def __init__(self, path, index=0):
        self.path = path
        self.index = index
        with open(path, "rb") as fh:
            self._data = fh.read()
        self._tables = self._directory(index)
        self._head()
        self._hhea()
        self._os2()
        self._cmap_offset = self._tables.get("cmap", (0, 0))[0]
        self._cmap = None
        self._hmtx_cache = {}
        self._loca = None

    # -- structure
    def _u16(self, o):
        return struct.unpack_from(">H", self._data, o)[0]

    def _i16(self, o):
        return struct.unpack_from(">h", self._data, o)[0]

    def _u32(self, o):
        return struct.unpack_from(">I", self._data, o)[0]

    def _directory(self, index):
        tag = self._data[:4]
        base = 0
        if tag == b"ttcf":
            n = self._u32(8)
            if index >= n:
                raise ValueError(f"{self.path}: face {index} of {n}")
            base = self._u32(12 + 4 * index)
        num = self._u16(base + 4)
        out = {}
        for i in range(num):
            rec = base + 12 + 16 * i
            name = self._data[rec:rec + 4].decode("latin-1").strip()
            out[name] = (self._u32(rec + 8), self._u32(rec + 12))
        return out

    def _head(self):
        o = self._tables.get("head", (None, 0))[0]
        if o is None:
            raise ValueError(f"{self.path}: no head table")
        self.units_per_em = self._u16(o + 18)
        self.index_to_loc = self._i16(o + 50)

    def _hhea(self):
        o = self._tables.get("hhea", (None, 0))[0]
        if o is None:
            raise ValueError(f"{self.path}: no hhea table")
        self.hhea_ascent = self._i16(o + 4)
        self.hhea_descent = self._i16(o + 6)
        self.hhea_line_gap = self._i16(o + 8)
        self.num_h_metrics = self._u16(o + 34)

    def _os2(self):
        o = self._tables.get("OS/2", (None, 0))[0]
        self.cap_height = None
        self.x_height = None
        self.typo_ascent = self.typo_descent = self.typo_line_gap = None
        self.weight_class = None
        if o is None:
            return
        version = self._u16(o)
        self.weight_class = self._u16(o + 4)
        self.typo_ascent = self._i16(o + 68)
        self.typo_descent = self._i16(o + 70)
        self.typo_line_gap = self._i16(o + 72)
        if version >= 2:
            self.x_height = self._i16(o + 86)
            self.cap_height = self._i16(o + 88)

    # -- names
    def names(self):
        """``{nameID: text}`` for the English Windows records, which every face carries."""
        o, _n = self._tables.get("name", (None, 0))
        if o is None:
            return {}
        count = self._u16(o + 2)
        strings = o + self._u16(o + 4)
        out = {}
        for i in range(count):
            rec = o + 6 + 12 * i
            plat, enc, lang, nid = (self._u16(rec), self._u16(rec + 2),
                                    self._u16(rec + 4), self._u16(rec + 6))
            ln, off = self._u16(rec + 8), self._u16(rec + 10)
            raw = self._data[strings + off:strings + off + ln]
            if plat == 3 and enc in (0, 1) and lang in (0x409, 0):
                try:
                    out[nid] = raw.decode("utf-16-be")
                except UnicodeDecodeError:
                    continue
            elif plat == 1 and nid not in out:
                try:
                    out[nid] = raw.decode("mac-roman")
                except (UnicodeDecodeError, LookupError):
                    continue
        return out

    @property
    def family(self):
        n = self.names()
        return n.get(16) or n.get(1) or os.path.basename(self.path)

    @property
    def subfamily(self):
        n = self.names()
        return n.get(17) or n.get(2) or "Regular"

    # -- glyphs
    def _load_cmap(self):
        if self._cmap is not None:
            return self._cmap
        o = self._cmap_offset
        self._cmap = {}
        if not o:
            return self._cmap
        n = self._u16(o + 2)
        best = None
        for i in range(n):
            rec = o + 4 + 8 * i
            plat, enc, off = self._u16(rec), self._u16(rec + 2), self._u32(rec + 4)
            score = {(3, 10): 4, (3, 1): 3, (0, 4): 4, (0, 3): 3, (0, 6): 4}.get(
                (plat, enc), 1)
            if best is None or score > best[0]:
                best = (score, o + off)
        if best is None:
            return self._cmap
        self._cmap = self._read_cmap_subtable(best[1])
        return self._cmap

    def _read_cmap_subtable(self, o):
        fmt = self._u16(o)
        out = {}
        if fmt == 4:
            seg2 = self._u16(o + 6)
            seg = seg2 // 2
            ends = o + 14
            starts = ends + seg2 + 2
            deltas = starts + seg2
            ranges = deltas + seg2
            for i in range(seg):
                end = self._u16(ends + 2 * i)
                start = self._u16(starts + 2 * i)
                delta = self._i16(deltas + 2 * i)
                ro = self._u16(ranges + 2 * i)
                if start > end:
                    continue
                for c in range(start, min(end, 0xFFFF) + 1):
                    if ro == 0:
                        g = (c + delta) & 0xFFFF
                    else:
                        addr = ranges + 2 * i + ro + 2 * (c - start)
                        if addr + 1 >= len(self._data):
                            continue
                        g = self._u16(addr)
                        if g:
                            g = (g + delta) & 0xFFFF
                    if g:
                        out[c] = g
        elif fmt == 12:
            n = self._u32(o + 12)
            for i in range(n):
                rec = o + 16 + 12 * i
                s, e, g = self._u32(rec), self._u32(rec + 4), self._u32(rec + 8)
                if e - s > 0x10000:
                    e = s + 0x10000
                for c in range(s, e + 1):
                    out[c] = g + (c - s)
        elif fmt == 6:
            first, count = self._u16(o + 6), self._u16(o + 8)
            for i in range(count):
                out[first + i] = self._u16(o + 10 + 2 * i)
        elif fmt == 0:
            for c in range(256):
                out[c] = self._data[o + 6 + c]
        return out

    def glyph_id(self, ch):
        return self._load_cmap().get(ord(ch), 0)

    def advance(self, gid):
        """Advance width of a glyph, in font units."""
        if gid in self._hmtx_cache:
            return self._hmtx_cache[gid]
        o = self._tables.get("hmtx", (None, 0))[0]
        if o is None:
            return 0
        i = min(gid, self.num_h_metrics - 1)
        v = self._u16(o + 4 * i)
        self._hmtx_cache[gid] = v
        return v

    def glyph_box(self, gid):
        """A glyph's own ink box in font units, or None when the font has no `glyf` table.

        None is a real answer, not a failure: a CFF/OTF face stores outlines in a form this
        does not read, so the ink box is unknown and the caller is told so rather than given
        the em box as though it were measured.
        """
        glyf = self._tables.get("glyf")
        loca = self._tables.get("loca")
        if not glyf or not loca:
            return None
        if self._loca is None:
            lo, ln = loca
            if self.index_to_loc == 0:
                n = ln // 2
                self._loca = [self._u16(lo + 2 * i) * 2 for i in range(n)]
            else:
                n = ln // 4
                self._loca = [self._u32(lo + 4 * i) for i in range(n)]
        if gid + 1 >= len(self._loca):
            return None
        start, end = self._loca[gid], self._loca[gid + 1]
        if end <= start:
            return None                      # an empty glyph, such as a space
        o = glyf[0] + start
        return (self._i16(o + 2), self._i16(o + 4), self._i16(o + 6), self._i16(o + 8))

    def digest(self):
        return hashlib.sha256(self._data).hexdigest()


# --------------------------------------------------------------------- resolution
_INDEX = None


def families(refresh=False):
    """``{lower-case family: [(path, face index, subfamily)]}`` for every font found."""
    global _INDEX
    if _INDEX is not None and not refresh:
        return _INDEX
    out = {}
    for d in font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                if not f.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
                    continue
                path = os.path.join(root, f)
                for idx in range(8):
                    try:
                        face = Font(path, idx)
                    except Exception:
                        break
                    try:
                        fam, sub = face.family, face.subfamily
                    except Exception:
                        break
                    out.setdefault(fam.lower(), []).append((path, idx, sub))
                    if face._data[:4] != b"ttcf":
                        break
    _INDEX = {k: sorted(set(v)) for k, v in out.items()}
    return _INDEX


_STYLE_RANK = {"regular": 0, "book": 0, "roman": 0, "medium": 1, "italic": 2, "oblique": 2,
               "bold": 3, "bold italic": 4, "bolditalic": 4, "semibold": 5}


def resolve(family, weight="regular", style="normal"):
    """The face for a family, as ``(path, index)``. Raises FontNotFound rather than guessing.

    Falling back to another family when the asked-for one is missing is the failure this
    refuses: it produces a figure that measures fine here and overflows on the machine that
    prints it.
    """
    want = (family or "").strip().lower()
    idx = families()
    if want not in idx:
        raise FontNotFound(
            f"no font family {family!r} among the {len(idx)} found in "
            f"{', '.join(font_dirs()) or 'no font directory'}. Refusing to substitute "
            f"another face: metrics from the wrong font are a figure that overflows "
            f"somewhere else. `lineart-scene fonts` lists what is here, and "
            f"LINEART_FONT_PATH adds a directory.")
    faces = idx[want]
    tag = " ".join(x for x in [
        "bold" if str(weight).lower() in ("bold", "700", "800", "900") else "",
        "italic" if str(style).lower() in ("italic", "oblique") else ""] if x).strip()
    tag = tag or "regular"
    for path, i, sub in faces:
        if sub.strip().lower() == tag:
            return path, i
    for path, i, sub in faces:
        if _STYLE_RANK.get(sub.strip().lower(), 99) == _STYLE_RANK.get(tag, 99):
            return path, i
    if tag != "regular":
        raise FontNotFound(
            f"family {family!r} is here but has no {tag!r} face "
            f"(only {', '.join(sorted(s for _p, _i, s in faces))}). Synthesising one by "
            f"slanting or smearing would measure as something no renderer will draw.")
    return faces[0][0], faces[0][1]


# --------------------------------------------------------------------- metrics
def metrics(text, family, size, weight="regular", style="normal"):
    """Everything measurable about a run of text at a size, without drawing it.

    Sizes come back in the same unit `size` is given in. `ink` is the tight box the glyphs
    actually mark, relative to the text origin with y up; it is None for a face whose
    outlines this cannot read, and that is reported rather than filled in.
    """
    path, index = resolve(family, weight, style)
    f = Font(path, index)
    upm = float(f.units_per_em or 1000)
    k = float(size) / upm

    asc = f.typo_ascent if f.typo_ascent else f.hhea_ascent
    desc = f.typo_descent if f.typo_descent else f.hhea_descent
    gap = f.typo_line_gap if f.typo_line_gap is not None else f.hhea_line_gap

    advance = 0
    ink = None
    missing = []
    for ch in text:
        gid = f.glyph_id(ch)
        if gid == 0 and ch not in ("\u0000",):
            missing.append(ch)
        box = f.glyph_box(gid)
        if box is not None:
            x0, y0, x1, y1 = box
            b = (advance + x0, y0, advance + x1, y1)
            ink = b if ink is None else (min(ink[0], b[0]), min(ink[1], b[1]),
                                         max(ink[2], b[2]), max(ink[3], b[3]))
        advance += f.advance(gid)

    out = {
        "advance": advance * k,
        "ascent": asc * k,
        "descent": abs(desc) * k,
        "line_height": (asc + abs(desc) + gap) * k,
        "cap_height": (f.cap_height * k) if f.cap_height else None,
        "x_height": (f.x_height * k) if f.x_height else None,
        "ink": None if ink is None else {"x0": ink[0] * k, "y0": ink[1] * k,
                                         "x1": ink[2] * k, "y1": ink[3] * k},
        "font": {"family": f.family, "subfamily": f.subfamily, "path": path,
                 "index": index, "units_per_em": f.units_per_em,
                 "sha256": f.digest()},
        "kerning": False,
    }
    if missing:
        out["missing"] = "".join(sorted(set(missing)))
    return out
