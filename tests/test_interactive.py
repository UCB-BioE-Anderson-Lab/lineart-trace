"""Human-in-the-loop: §3.15. The inspector, the gallery, the narration and the watcher.

Two rules shape these tests. **The views are pure** -- so each is handed a dict and checked
on its markup, with nothing installed and no file read. And **absence must not look like
emptiness**: a variant that could not be rendered, a layer that could not be gathered, a
check that was not run all have to be visible as themselves.
"""
import json
import os
import threading
import urllib.request

import pytest

from lineart_trace.scene import (animate, build, inspect, io, model, overlay, report,
                                 style, validate, watch)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def styled():
    d = model.new("f", 90, 60, title="A figure", background="#ffffff")
    d["description"] = "for testing"
    d, _ = style.apply(d, style.load("figure-default"))
    d = model.add(d, build.circle("blob", 25, 25, 10, role="accent-fill"))
    d = model.add(d, build.rect("bar", 50, 18, 30, 14, role="surface-fill"))
    d = model.add(d, build.text("cap", "a label", (8, 52), family=None, size=None,
                                role="caption"))
    return d


# ------------------------------------------------------------------ the payload
def test_the_overlay_payload_now_carries_z_order_and_roles():
    """§3.15 lists both; the payload did not have them, so no view could have drawn them."""
    got = overlay.payload(styled(), depth=None)
    boxes = got["boxes"]
    assert all("order" in b and "depth" in b for b in boxes)
    assert [b["order"] for b in boxes] == sorted(b["order"] for b in boxes)
    assert any(b["role"] for b in boxes)
    assert {r["role"] for r in got["roles"]} >= {"accent-fill", "caption"}
    assert all(r["in_guide"] for r in got["roles"])


def test_the_overlay_can_draw_the_order_and_role_layers():
    got = overlay.render(overlay.payload(styled(), depth=None), layers=overlay.LAYERS)
    assert 'id="overlay-order"' in got and 'id="overlay-roles"' in got


def test_a_role_no_guide_defines_is_marked_as_such():
    d = styled()
    d = model.add(d, build.circle("odd", 70, 45, 4, role="invented"))
    got = overlay.payload(d, depth=None)
    assert {r["role"]: r["in_guide"] for r in got["roles"]}["invented"] is False


# ------------------------------------------------------------------ the inspector
def test_the_inspector_needs_nothing_but_its_payload():
    """Purity, checked the only way that means anything: a hand-written dict."""
    hand = {"format": "lineart.overlay/1",
            "canvas": {"width": 40, "height": 20, "unit": "mm"},
            "boxes": [{"address": "a.b", "type": "path", "x": 1, "y": 1, "width": 8,
                       "height": 4, "label": True, "order": 3, "role": "ink",
                       "depth": 2, "style": {"stroke": "#111"}, "tags": ["t"],
                       "anchors": ["tip"]}],
            "anchors": [], "relations": []}
    out = inspect.inspector(hand)
    assert out.startswith("<!doctype html")
    assert 'data-i="0"' in out and "a.b" in out
    assert "performs no I/O" in out


def test_every_element_in_the_payload_is_clickable_and_carries_its_facts():
    got = overlay.payload(styled(), depth=None)
    page = inspect.inspector(got)
    data = json.loads(page.split('id="data">')[1].split("</script>")[0])
    assert len(data["boxes"]) == len(got["boxes"])
    one = [b for b in data["boxes"] if b["address"] == "blob"][0]
    assert one["role"] == "accent-fill" and one["order"] is not None
    assert one["style"].get("fill")
    assert page.count('class="hit"') == len(got["boxes"])


def test_the_inspector_shows_findings_and_says_when_none_were_gathered():
    d = styled()
    with_checks = inspect.inspector(overlay.payload(d, findings=[
        {"severity": "error", "rule": "type-size", "element": "cap",
         "message": "too small"}]))
    assert "type-size" in with_checks and "too small" in with_checks
    without = inspect.inspector(overlay.payload(d))
    assert "no verification was run" in without


def test_the_inspector_offers_a_true_size_view_of_the_real_page():
    got = inspect.inspector(overlay.payload(styled()))
    assert "90mm" in got and "true size" in got


# ------------------------------------------------------------------ the gallery
def test_a_comparison_payload_conforms_to_its_schema():
    jsonschema = pytest.importorskip("jsonschema")
    got = inspect.comparison([("a", "<svg/>", {"verdict": "clean", "findings": 0}),
                              ("b", None, {"why": "no such guide"})],
                             mode="contact", canvas={"width": 10, "height": 5,
                                                     "unit": "mm"})
    schema = json.load(open(os.path.join(ROOT, "lineart_trace/scene/comparison.schema.json")))
    jsonschema.Draft202012Validator(schema).validate(got)
    assert got["items"][1]["unavailable"] == "no such guide"


@pytest.mark.parametrize("mode,marker", [
    ("side-by-side", 'class="side"'), ("contact", 'class="sheet"'),
    ("onion", 'id="wipe"'), ("true-size", 'class="ruler"')])
def test_each_gallery_mode_renders_its_own_shape(mode, marker):
    got = inspect.gallery(inspect.comparison(
        [("one", "<svg/>", {}), ("two", "<svg/>", {})], mode=mode,
        canvas={"width": 90, "height": 60, "unit": "mm"}))
    assert marker in got


def test_a_variant_that_could_not_be_rendered_is_shown_as_that():
    """A blank panel in a contact sheet reads as a variant that produces nothing."""
    got = inspect.gallery(inspect.comparison(
        [("ok", "<svg/>", {}), ("broken", None, {"why": "the guide is missing"})],
        mode="contact"))
    assert "not shown" in got and "the guide is missing" in got


def test_the_true_size_view_carries_a_ruler_to_check_the_screen_against():
    got = inspect.gallery(inspect.comparison(
        [("f", "<svg/>", {})], mode="true-size",
        canvas={"width": 90, "height": 60, "unit": "mm"}))
    assert "90mm" in got and "hold a ruler" in got
    assert got.count('class="ruler"') == 1


def test_the_gallery_needs_nothing_but_its_payload():
    out = inspect.gallery({"format": "lineart.comparison/1", "mode": "side-by-side",
                           "items": [{"label": "x", "markup": "<svg/>"}]})
    assert out.startswith("<!doctype html") and "performs no I/O" in out


# ------------------------------------------------------------------ narration
def test_the_narration_says_what_is_in_the_figure():
    text, _got = report.narrate(styled(), guide=style.load("figure-default"))
    assert "90 by 60 mm" in text
    assert "draws by role" in text and "accent-fill" in text
    assert "Helvetica" in text


def test_the_narration_says_the_unwelcome_parts_too():
    """A description that only mentions what went well is an advertisement."""
    d = model.new("bare", 40, 30)
    d = model.add(d, build.circle("c", 20, 15, 5, style={"fill": "#eeeeee"}))
    text, got = report.narrate(d)
    assert got["verdict"] != "clean"
    assert "cannot be re-themed" in text
    assert "unchecked" in text


def test_the_narration_counts_unchecked_separately_from_wrong():
    text, _got = report.narrate(styled(), guide=style.load("figure-default"))
    assert "could not be checked at all" in text or "Nothing is wrong" in text


# ------------------------------------------------------------------ the watcher
def test_the_watcher_shows_a_file_mid_write_as_that_rather_than_a_blank_page(tmp_path):
    p = tmp_path / "half.json"
    p.write_text("{not json yet")
    got = watch.render_page(str(p), live=False)
    assert "will not load" in got


def test_the_watcher_shows_an_invalid_scene_as_invalid(tmp_path):
    d = styled()
    model.find(d, "blob")["geometry"]["d"] = [["C", 1, 2]]
    p = tmp_path / "bad.json"
    p.write_text(io.dumps(d))
    got = watch.render_page(str(p), live=False)
    assert "not a scene yet" in got


def test_the_version_stamp_changes_when_the_file_does(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(io.dumps(styled()))
    first = watch.stamp(str(p))
    p.write_text(io.dumps(styled()) + "\n")
    assert watch.stamp(str(p)) != first
    assert watch.stamp(str(tmp_path / "gone.json")) is None


def test_the_live_page_polls_and_the_plain_one_does_not(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(io.dumps(styled()))
    assert "location.reload" in watch.render_page(str(p), check=False, live=True)
    assert "location.reload" not in watch.render_page(str(p), check=False, live=False)


def test_the_server_serves_on_loopback_and_stops(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(io.dumps(styled()))
    stop, ready, got = threading.Event(), threading.Event(), {}

    def on_ready(port):
        got["port"] = port
        ready.set()

    t = threading.Thread(target=watch.serve, args=(str(p),),
                         kwargs={"port": 0, "on_ready": on_ready, "stop": stop,
                                 "check": False}, daemon=True)
    t.start()
    assert ready.wait(10), "the server never came up"
    base = f"http://127.0.0.1:{got['port']}/"
    page = urllib.request.urlopen(base, timeout=10).read().decode()
    assert "inspector" in page and "location.reload" in page
    stamp = json.load(urllib.request.urlopen(base + "version", timeout=10))["stamp"]
    assert stamp == watch.stamp(str(p))
    stop.set()
    t.join(10)
    assert not t.is_alive(), "the server did not stop"
