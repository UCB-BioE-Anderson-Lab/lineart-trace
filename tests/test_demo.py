"""The demo runs, and what it claims at the end is true.

An example in a repository is a claim that the toolkit does what the example says. This runs
it and checks the three claims that matter: the figure it writes is a valid scene, the
verification it ends on is clean, and the layout it solved stays solved.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    r = subprocess.run([sys.executable, "examples/demo_figure.py", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_demo_runs_and_writes_what_it_says_it_does(demo):
    out, _log = demo
    for name in ("pol-entry.json", "pol-entry.svg", "pol-entry-overlay.svg",
                 "pol-entry-overlay.json"):
        assert (out / name).exists() and (out / name).stat().st_size > 0


def test_the_figure_it_produces_is_a_valid_scene_and_passes_its_own_check(demo):
    from lineart_trace.scene import anchors, io, validate, verify
    out, _log = demo
    doc = io.load(str(out / "pol-entry.json"))
    bad, _warn = validate.problems(doc)
    assert bad == []
    solved, report = anchors.solve(doc)
    assert report["settled"] and not report["unsatisfiable"]
    assert report["moved"] == {}, "the exported scene should already be solved"
    got = verify.check(doc, solve_report=report)
    assert got["errors"] == 0, got["findings"]


def test_the_demo_shows_a_refusal_and_a_finding_rather_than_only_successes(demo):
    """An example where nothing ever goes wrong teaches nothing about what happens when it does."""
    _out, log = demo
    assert "REFUSED" in log
    assert "error(s)" in log


@pytest.fixture(scope="module")
def panels(tmp_path_factory):
    out = tmp_path_factory.mktemp("panels")
    r = subprocess.run([sys.executable, "examples/demo_panels.py", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_panel_demo_exports_one_scene_three_ways(panels):
    out, _log = panels
    for name in ("pathway.svg", "pathway-dark.svg", "pathway-column.svg",
                 "pathway-overlay.svg", "pathway.json"):
        assert (out / name).exists() and (out / name).stat().st_size > 0


def test_all_three_exports_verify_clean_at_their_own_size(panels):
    """Light, dark and column are the same scene; each has to be right at its own size."""
    from lineart_trace.scene import anchors, io, layout, style, verify
    out, _log = panels
    doc = io.load(str(out / "pathway.json"))
    guide = style.load("figure-default")
    solved, report = anchors.solve(doc)
    assert verify.check(doc, solve_report=report)["errors"] == 0

    dark, _ = style.apply(doc, guide, "dark")
    assert verify.check(dark, solve_report=report)["errors"] == 0, \
        verify.check(dark, solve_report=report)["findings"]

    column, _ = style.apply(doc, style.load("journal-column"))
    column, flowed = layout.reflow(column, width=88, height=150)
    column, report2 = anchors.solve(column)
    assert verify.check(column, solve_report=report2)["errors"] == 0


def test_the_panel_demo_is_on_guide(panels):
    from lineart_trace.scene import io, style
    out, _log = panels
    doc = io.load(str(out / "pathway.json"))
    got = style.lint(doc, style.load("figure-default"))
    assert got["errors"] == 0 and got["warnings"] == 0, got["findings"]


def test_the_panel_demo_routes_round_the_inhibitor_rather_than_through_it(panels):
    from lineart_trace.scene import io, measure
    out, _log = panels
    doc = io.load(str(out / "pathway.json"))
    gap = measure.clearance(doc, "step-2.line", "panel-b.inhibitor")["value"]
    assert not gap["overlaps"] and gap["gap"] >= 1.5 - 1e-9


@pytest.fixture(scope="module")
def datafig(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    r = subprocess.run([sys.executable, "examples/demo_data.py", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_data_demo_builds_a_panel_from_a_file_and_records_which_file(datafig):
    from lineart_trace.scene import io, model
    out, _log = datafig
    doc = io.load(str(out / "results.json"))
    prov = model.find(doc, "panel-a.dose")["provenance"]
    assert prov["origin"] == "data"
    assert prov["source"].endswith("dose-response.csv")
    assert len(prov["sha256"]) == 64


def test_the_data_figure_verifies_clean_light_and_dark(datafig):
    from lineart_trace.scene import anchors, io, style, verify
    out, _log = datafig
    doc = io.load(str(out / "results.json"))
    _s, report = anchors.solve(doc)
    assert verify.check(doc, solve_report=report)["errors"] == 0
    dark, _ = style.apply(doc, style.load("figure-default"), "dark")
    assert verify.check(dark, solve_report=report)["errors"] == 0


def test_the_data_demo_is_reproducible_from_its_own_data_file(datafig):
    """Same file, same figure: the point of recording the digest at all."""
    out, _log = datafig
    again = subprocess.run([sys.executable, "examples/demo_data.py", "--out", str(out)],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert again.returncode == 0
    assert "slope 0.3742" in again.stdout


@pytest.fixture(scope="module")
def diagramfig(tmp_path_factory):
    out = tmp_path_factory.mktemp("diagram")
    r = subprocess.run([sys.executable, "examples/demo_diagram.py", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_diagram_demo_puts_four_diagrams_on_one_page_without_them_colliding(diagramfig):
    from lineart_trace.scene import anchors, io, verify
    out, _log = diagramfig
    doc = io.load(str(out / "diagrams.json"))
    _s, report = anchors.solve(doc)
    got = verify.check(doc, solve_report=report)
    assert got["errors"] == 0, got["findings"]


def test_each_diagram_stays_in_its_own_frame(diagramfig):
    """A default that resolved to the page frame once put all four at the page origin."""
    from lineart_trace.scene import io, model
    out, _log = diagramfig
    doc = io.load(str(out / "diagrams.json"))
    for group, frame in (("states", "q1"), ("map", "q2"), ("protocol", "q3"),
                         ("check", "q4")):
        for addr, _el, _p in model.walk(doc):
            if addr.startswith(group + "."):
                assert model.frame_of(doc, addr) == frame, addr


@pytest.fixture(scope="module")
def buildfig(tmp_path_factory):
    out = tmp_path_factory.mktemp("build")
    r = subprocess.run([sys.executable, "examples/demo_build.py", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_build_demo_exports_every_stage_as_a_figure(buildfig):
    out, _log = buildfig
    for name in ("stage-duplex", "stage-enzyme", "stage-caption"):
        assert (out / f"{name}.svg").exists()
    assert (out / "lecture.json").exists() and (out / "lecture.svg").exists()
    assert (out / "replication-diff.png").exists()


def test_the_build_demo_reports_clean_and_wrong_for_the_right_reasons(buildfig):
    _out, log = buildfig
    assert "as built        CLEAN" in log
    assert "after the move  WRONG" in log
    assert "no reference    UNESTABLISHED" in log


def test_every_stage_of_the_build_verifies_on_its_own(buildfig):
    from lineart_trace.scene import animate, io, verify
    out, _log = buildfig
    doc = io.load(str(out / "replication.json"))
    tl = io.load(str(out / "lecture.json"))
    for stage in tl["marks"]:
        still = animate.still(doc, tl, stage)
        assert verify.check(still)["errors"] == 0, stage


@pytest.fixture(scope="module")
def showcase(tmp_path_factory):
    out = tmp_path_factory.mktemp("showcase")
    r = subprocess.run([sys.executable, "examples/showcase.py", "--out", str(out),
                        "--html", str(out / "showcase.html")],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:]
    return out, r.stdout


def test_the_showcase_figure_is_clean_on_every_count(showcase):
    """The one claim the page makes at the top of itself."""
    out, log = showcase
    assert "verdict: CLEAN -- 0 error(s), 0 warning(s), 0 unchecked" in log


def test_the_showcase_exports_three_ways_with_no_errors_in_any(showcase):
    _out, log = showcase
    assert "light 0 errors | dark 0 errors | column 0 errors" in log


def test_the_showcase_bypass_really_goes_round_the_inhibitor(showcase):
    from lineart_trace.scene import io, measure
    out, _log = showcase
    doc = io.load(str(out / "showcase.json"))
    gap = measure.clearance(doc, "panel-b.escape.line", "panel-b.inhibitor")["value"]
    assert not gap["overlaps"] and gap["gap"] >= 1.5
    area = measure.bbox(doc, "panel-b.area", "panel-b-frame")["value"]
    box = measure.bbox(doc, "panel-b.escape", "panel-b-frame")["value"]
    assert box["x"] >= area["x"] - 1e-6
    assert box["x"] + box["width"] <= area["x"] + area["width"] + 1e-6


def test_the_showcase_duplex_is_placed_by_a_discovered_anchor(showcase):
    from lineart_trace.scene import anchors, io, measure, model
    out, _log = showcase
    doc = io.load(str(out / "showcase.json"))
    assert model.find(doc, "panel-a.art")["anchors"]["channel"]["how"] == "discovered"
    found, _dir = anchors.derive(doc, "panel-a.art", "concavity")
    stored = model.find(doc, "panel-a.art")["anchors"]["channel"]["at"]
    import math
    assert math.dist(found, stored) < 0.01


def test_the_showcase_page_is_written_and_says_its_verdict(showcase):
    out, _log = showcase
    page = (out / "showcase.html").read_text()
    assert "clean" in page and "<svg" in page
    assert page.count("<svg") >= 8, "figure, dark, column, overlay and four stages"


def test_the_showcase_writes_the_pages_you_steer_it_from(showcase):
    out, log = showcase
    for name in ("showcase-inspector.html", "showcase-contact.html",
                 "showcase-onion.html", "showcase-truesize.html"):
        assert (out / name).exists() and (out / name).stat().st_size > 0, name
    assert "element(s) clickable" in log


def test_the_showcase_describes_itself_in_words(showcase):
    _out, log = showcase
    assert "is 180 by 118 mm" in log
    assert "draws by role, not by literal value" in log


def test_the_inspector_page_it_writes_is_a_view_with_no_io(showcase):
    out, _log = showcase
    page = (out / "showcase-inspector.html").read_text()
    assert "performs no I/O" in page
    assert "fetch(" not in page and "XMLHttpRequest" not in page
    assert page.count('class="hit"') > 50
