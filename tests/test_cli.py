import os
import xml.etree.ElementTree as ET

import pytest

from lineart_trace.cli import main

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SRC = os.path.join(FIX, "simple.png")


def test_group_to_stdout(capsys):
    assert main([SRC, "-q"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("<g ") and "<path" in out


def test_standalone_svg_is_parseable(capsys):
    assert main([SRC, "--svg", "-q"]) == 0
    root = ET.fromstring(capsys.readouterr().out.strip())
    assert root.tag.endswith("svg")


def test_write_to_file(tmp_path):
    dst = tmp_path / "out.svg"
    assert main([SRC, "--svg", "-q", "-o", str(dst)]) == 0
    assert ET.fromstring(dst.read_text()).tag.endswith("svg")


def test_width_scales_the_document(tmp_path, capsys):
    main([SRC, "--svg", "-q", "--width", "300"])
    root = ET.fromstring(capsys.readouterr().out.strip())
    assert root.attrib["width"] == "300"


def test_transparent_background(capsys):
    main([SRC, "--svg", "-q", "--background", "none"])
    assert "<rect" not in capsys.readouterr().out


def test_colour_and_forced_stroke(capsys):
    main([SRC, "-q", "--color", "#3e5c8a", "--stroke", "2.5"])
    out = capsys.readouterr().out
    assert '#3e5c8a' in out and 'stroke-width="2.50"' in out


def test_check_reports_scores(capsys):
    main([SRC, "--check"])
    err = capsys.readouterr().err
    assert "[check]" in err and "iou=" in err


def test_summary_goes_to_stderr_not_stdout(capsys):
    main([SRC, "--svg"])
    cap = capsys.readouterr()
    assert "strokes" in cap.err and "strokes" not in cap.out.split(">")[0]


def test_missing_file_returns_error(capsys):
    assert main(["definitely-not-here.png"]) == 2
    assert "cannot read" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--method", "--corner-angle", "--thin-limit"])
def test_flags_are_wired(flag, capsys):
    val = {"--method": "adaptive", "--corner-angle": "0",
           "--thin-limit": "0"}[flag]
    assert main([SRC, "-q", flag, val]) == 0
    assert capsys.readouterr().out.startswith("<g ")
