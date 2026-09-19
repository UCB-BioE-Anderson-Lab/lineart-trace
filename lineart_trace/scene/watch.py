"""Live preview: the scene file is watched, and the page re-renders when it changes. §3.15.

**This is the one part of §3.15 that cannot be a view.** A view performs no I/O, and a live
preview is I/O by definition -- it reads a file repeatedly and serves it. So the split stays
honest: the page it serves *is* the pure inspector view, rendered from a payload; this module
only re-renders it when the bytes on disk change, and hands it to a browser over loopback.

It binds to **127.0.0.1 only**. A figure in progress is the author's business, and a preview
server that listens on every interface is a different thing from what was asked for.

The page polls a version stamp rather than holding a socket open: no dependency, no
framework, and a preview that survives the scene file being rewritten by another tool
mid-read -- which is exactly what happens when the thing you are previewing is being edited.
"""
import hashlib
import json
import os
import threading
import time

__all__ = ["render_page", "stamp", "serve"]

_POLL = """
<script>
let last = null;
async function tick() {
  try {
    const r = await fetch('version', {cache: 'no-store'});
    const v = (await r.json()).stamp;
    if (last !== null && v !== last) { location.reload(); return; }
    last = v;
  } catch (e) { /* the server went away; keep trying */ }
  setTimeout(tick, 600);
}
tick();
</script>
<div style="position:fixed;right:10px;bottom:10px;font:11px ui-monospace,monospace;
     background:#16191d;color:#fff;padding:5px 9px;border-radius:99px;opacity:.72">
  live &middot; reloads when the file changes</div>
"""


def stamp(path):
    """A cheap version of a file: size and mtime, or None if it is not there."""
    try:
        st = os.stat(path)
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return None


def render_page(path, guide=None, depth=3, check=True, live=True):
    """The inspector page for the scene at `path`, right now. Returns markup.

    A scene that will not load or will not validate is **shown as that**, rather than as the
    last good render or a blank page: the whole point of a live preview is to see the state
    you are actually in, and "the file is mid-write" is a state.
    """
    from . import anchors, inspect, io, overlay, report, style as style_, validate
    try:
        doc = io.load(path)
    except (OSError, ValueError) as e:
        return _problem(path, f"this file will not load right now: {e}", live)
    bad, _warn = validate.problems(doc)
    if bad:
        return _problem(path, "this is not a scene yet:\n  " + "\n  ".join(bad[:8]), live)
    findings = None
    if check:
        _solved, srep = anchors.solve(doc)
        got = report.full(doc, guide=guide)
        findings = (got["sections"].get("print") or {}).get("findings", [])
    load = overlay.payload(doc, grid=10.0, findings=findings, depth=depth)
    page = inspect.inspector(load)
    return page.replace("</script>\n", "</script>\n" + _POLL, 1) if live else page


def _problem(path, message, live):
    body = (f'<!doctype html><meta charset="utf-8"><title>waiting</title>'
            f'<style>body{{margin:0;padding:40px;font:14px/1.6 ui-monospace,'
            f'SFMono-Regular,Menlo,monospace;background:#16191d;color:#f2f4f7}}'
            f'h1{{font-size:14px;color:#ff9e80;margin:0 0 14px}}'
            f'pre{{white-space:pre-wrap;color:#c9d1d9}}</style>'
            f'<h1>{os.path.basename(path)}</h1><pre>{message}</pre>')
    return body + (_POLL if live else "")


def serve(path, port=8765, guide=None, depth=3, check=True, host="127.0.0.1",
          on_ready=None, stop=None):
    """Serve the live preview until `stop` is set. Returns the bound port.

    `stop` is a `threading.Event`; without one this blocks until interrupted.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass                          # the point is the figure, not a request log

        def do_GET(self):
            route = self.path.split("?")[0].rstrip("/") or "/"
            if route.endswith("version"):
                body = json.dumps({"stamp": stamp(path)}).encode()
                ctype = "application/json"
            elif route == "/":
                body = render_page(path, guide, depth, check).encode()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    bound = server.server_address[1]
    if on_ready:
        on_ready(bound)
    if stop is None:
        try:
            server.serve_forever(poll_interval=0.3)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return bound
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                         daemon=True)
    t.start()
    stop.wait()
    server.shutdown()
    server.server_close()
    return bound
