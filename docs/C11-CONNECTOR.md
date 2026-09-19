# Using this repository as a C11 content world

**This repository is a content world**, and it is also a C11 installation in its own right.
Those are two different things and it is worth knowing which one you want.

| you want | you need |
|---|---|
| to *use* these capabilities from somewhere else | mount this repository — below |
| to *work on* this repository | nothing; it is already an installation. See `CLAUDE.md` |

## How to mount it

Add this repository's path to your installation's mounts file, one path per line:

    ~/cortex/engine/c11-mounts.txt          (or wherever your installation keeps it)

        ~/Documents/GitHub/lineart-trace

That is the whole of it, and it is deliberately the only thing your installation records.
**Your installation names a directory; this repository describes what is in it** — through
`c11-connector.json` at the root here, which names where the records live (`sharables/`), where
the programs live (`bin/`) and which file to read to work with them (this one).

Nothing here is written by a mounting installation. Mounted records are read and run, never
edited: writing a record under one of these ids forks it into your own store, where your
version shadows this one. That is the intended way to disagree with something here.

## What you get

Today: **two records, both hand-written, both for commands.**

| record | what it does |
|---|---|
| `lineart.trace` | turn a raster picture of line art into real vector paths — centrelines for strokes, contours for fills, one colour per pen |
| `lineart.check` | score a trace against the ink it came from: overlap, coverage, spill, and how far the worst-placed ink sits from anything drawn |

That is a small surface on purpose. `docs/spec.md` specifies where this is going — a scene
model and fifteen families of tools that transform it — and those records will be **generated
from the source's own docstrings** rather than written by hand, so a description and the code
it describes cannot drift apart. Until that generator exists, a hand-written record is the only
honest kind here, and there are two of them.

## What this repository expects of you

**Nothing.** It has no opinion about which installation mounts it, does not read your store, and
cannot reach back into it. The dependency runs one way.

## If something does not work

- **The installation reports no toolkit mounted.** The path in the mounts file is wrong, or
  points somewhere without a `sharables/` directory. A mount that cannot be read is named rather
  than skipped, so the message will say which line it could not use.
- **A capability is found but will not run.** The entry needs this package's dependencies —
  numpy and opencv-python — importable by whatever `python3` resolves to. `pip install -e .`
  here once. Without them the entry fails with an ImportError, which is the intended loud
  failure rather than a silent empty result.
- **A record's example no longer matches what the command prints.** That is drift, and
  `pytest tests/test_sharables.py` is what catches it. The fix is to correct the record or the
  code, never to relax the test.
