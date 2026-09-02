"""Write the corpus out as PNGs, for looking at or feeding to other tools.

    python examples/make_corpus.py out/
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lineart_trace import corpus                                 # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = argv[0] if argv else "corpus"
    os.makedirs(out, exist_ok=True)
    for spec in corpus.build_all():
        cv2.imwrite(os.path.join(out, f"{spec.name}.png"), spec.image)
        cv2.imwrite(os.path.join(out, f"{spec.name}.truth.png"),
                    spec.truth * 255)
        print(f"{spec.name:20s} {spec.category:10s} {spec.notes}")
    print(f"\n{len(corpus.SPECIMENS)} specimens -> {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
