"""The human-in-the-loop views: §3.15. Look at any intermediate state, and steer it.

**These are views, and being views is what makes them useful rather than a side project.**
A view is a pure function from a payload to markup: it reads no store, calls no capability
and measures nothing. So the interactivity here is entirely client-side, driven by data the
payload already carries -- which means an inspector page opens from `file://` with nothing
running, and an overlay of a figure can be sent to somebody who has none of this installed.

Two views, because two payloads:

:func:`inspector`  binds `scene.overlay-payload`. The figure, every element clickable, and a
                   panel saying what the clicked thing is: its address, role, z-order, box in
                   real units, anchors and resolved style.
:func:`gallery`    binds `scene.comparison`. Two or more renderings side by side, as an
                   onion skin with a wipe, as a contact sheet, or one of them at true
                   physical size with a ruler to check the screen against.

**Nothing here computes a number a reader sees.** Every box, name and measurement in these
pages was produced by `overlay.payload` or `comparison`, which are the measuring half. A view
that measured for itself would be a second answer in the system wearing a picture.
"""
import json
import os

__all__ = ["inspector", "gallery", "comparison", "SCHEMA_PATH"]

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "comparison.schema.json")


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


_CSS = """
:root{--ink:#16191d;--muted:#6b7280;--line:#dde2e8;--bg:#eef1f4;--sel:#2f6fd0;
      --warn:#b8860b;--err:#c22c2c;--ok:#1d6b32}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     color:var(--ink);background:var(--bg)}
header{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;
       padding:12px 16px;background:#fff;border-bottom:1px solid var(--line)}
header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:-.01em}
header .sub{color:var(--muted);font-size:13px}
.toggles{margin-left:auto;display:flex;gap:4px;flex-wrap:wrap}
.toggles button{font:11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.04em;text-transform:uppercase;padding:6px 9px;border-radius:5px;
  border:1px solid var(--line);background:#fff;color:var(--muted);cursor:pointer}
.toggles button[aria-pressed="true"]{background:var(--sel);border-color:var(--sel);
  color:#fff}
main{display:grid;grid-template-columns:1fr 330px;gap:14px;padding:14px;
     align-items:start}
@media (max-width:860px){main{grid-template-columns:1fr}}
.stage{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px;
       position:relative}
.stage svg{display:block;width:100%;height:auto}
.hit{fill:transparent;stroke:none;cursor:pointer}
.hit:hover{fill:rgba(47,111,208,.10)}
.box{fill:none;stroke:#2f6fd0;stroke-width:.35;vector-effect:non-scaling-stroke;
     opacity:.55}
.box.group{stroke-dasharray:1.5 1.5}
.sel{fill:rgba(47,111,208,.14);stroke:#2f6fd0;stroke-width:1;
     vector-effect:non-scaling-stroke}
.anch{fill:#d2521e}
.lbl{font:2.2px ui-monospace,monospace;fill:#1a4a94}
aside{background:#fff;border:1px solid var(--line);border-radius:10px;padding:0;
      overflow:hidden;position:sticky;top:14px}
aside h2{font:11px/1 ui-monospace,monospace;letter-spacing:.07em;text-transform:uppercase;
  color:var(--muted);margin:0;padding:11px 13px;border-bottom:1px solid var(--line)}
.pick{padding:13px;border-bottom:1px solid var(--line)}
.pick .addr{font:13px ui-monospace,monospace;font-weight:600;word-break:break-all}
.pick .none{color:var(--muted)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:5px 13px;font-size:12.5px;border-bottom:1px solid #f0f2f5;
      vertical-align:top}
th{color:var(--muted);font-weight:500;width:96px}
tr:last-child th,tr:last-child td{border-bottom:none}
code{font:12px ui-monospace,monospace;background:#f2f4f7;padding:1px 4px;border-radius:3px}
.tree{max-height:340px;overflow:auto}
.tree button{display:block;width:100%;text-align:left;border:0;background:none;
  font:12px ui-monospace,monospace;padding:3px 13px;cursor:pointer;color:var(--ink);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tree button:hover{background:#f2f6fc}
.tree button[aria-current="true"]{background:var(--sel);color:#fff}
.find{padding:9px 13px;font-size:12.5px;border-bottom:1px solid #f0f2f5}
.find b{font-weight:600}
.find.error b{color:var(--err)} .find.warning b{color:var(--warn)}
.note{padding:11px 13px;color:var(--muted);font-size:12.5px}
footer{padding:4px 16px 24px;color:var(--muted);font-size:12px}
"""


def inspector(payload, title=None):
    """The figure, clickable. A pure function of `payload`; performs no I/O.

    C11:
      type: view
      noun: inspector
      verb: show
      tags: inspect, pick, interactive, overlay, names, roles, preview
      binds: scene.overlay-payload
      returns: one self-contained HTML page; no server, no network, no store
      phrases:
        - let me click a figure and see what things are called
        - inspect a figure element by element
        - which element is this one
        - an interactive view of a scene
        - pick an element and learn its name
      requires:
        - lineart_trace/scene/inspect.py: the view; payload in, markup out
    """
    canvas = payload["canvas"]
    w, h, unit = canvas["width"], canvas["height"], canvas.get("unit", "mm")
    boxes = payload.get("boxes")
    boxes = boxes if isinstance(boxes, list) else []
    anchors_ = payload.get("anchors")
    anchors_ = anchors_ if isinstance(anchors_, list) else []
    findings = payload.get("findings")
    findings = findings if isinstance(findings, list) else []
    art = payload.get("art") or {}
    name = title or payload.get("title") or payload.get("scene") or "scene"

    data = json.dumps({"boxes": boxes, "anchors": anchors_, "findings": findings,
                       "unit": unit, "roles": payload.get("roles")
                       if isinstance(payload.get("roles"), list) else []},
                      separators=(",", ":"))
    art_markup = art.get("markup") or ""
    missing = art.get("unavailable")

    hits = "\n".join(
        f'<rect class="hit" data-i="{i}" x="{b["x"]:.4g}" y="{b["y"]:.4g}" '
        f'width="{max(b["width"], 0.2):.4g}" height="{max(b["height"], 0.2):.4g}"/>'
        for i, b in enumerate(boxes))
    outlines = "\n".join(
        f'<rect class="box{" group" if b.get("type") == "group" else ""}" '
        f'data-i="{i}" x="{b["x"]:.4g}" y="{b["y"]:.4g}" '
        f'width="{max(b["width"], 0.2):.4g}" height="{max(b["height"], 0.2):.4g}"/>'
        for i, b in enumerate(boxes))
    marks = "\n".join(
        f'<circle class="anch" cx="{a["x"]:.4g}" cy="{a["y"]:.4g}" r="{max(w, h) / 220:.4g}"/>'
        for a in anchors_ if "x" in a)
    names = "\n".join(
        f'<text class="lbl" x="{b["x"]:.4g}" y="{b["y"] - max(w, h) / 160:.4g}">'
        f'{_esc(b["address"])}</text>'
        for b in boxes if b.get("label") is not False)
    tree = "\n".join(
        f'<button data-i="{i}" style="padding-left:{13 + 11 * (b.get("depth", 1) - 1)}px">'
        f'{_esc(b["address"].rsplit(".", 1)[-1])}</button>'
        for i, b in enumerate(boxes))
    finds = "".join(
        f'<div class="find {_esc(f.get("severity", "note"))}">'
        f'<b>{_esc(f.get("severity", "?"))}</b> {_esc(f.get("rule", ""))} &mdash; '
        f'{_esc(f.get("message", ""))}</div>' for f in findings) or \
        '<div class="note">' + _esc(
            payload["findings"].get("unavailable")
            if isinstance(payload.get("findings"), dict)
            else "nothing found") + "</div>"

    return f"""<!doctype html><meta charset="utf-8">
<title>{_esc(name)} &mdash; inspector</title>
<style>{_CSS}</style>
<header>
  <h1>{_esc(name)}</h1>
  <span class="sub">{w:g} &times; {h:g} {unit} &middot; {len(boxes)} elements
    &middot; {len(anchors_)} anchors</span>
  <div class="toggles">
    <button id="t-art" aria-pressed="true">art</button>
    <button id="t-box" aria-pressed="true">boxes</button>
    <button id="t-name" aria-pressed="false">names</button>
    <button id="t-anch" aria-pressed="false">anchors</button>
    <button id="t-true" aria-pressed="false">true size</button>
  </div>
</header>
<main>
  <div class="stage" id="stage">
    <svg id="fig" viewBox="0 0 {w:g} {h:g}" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="{w:g}" height="{h:g}" fill="#ffffff"/>
      <g id="g-art">{art_markup}</g>
      <g id="g-box">{outlines}</g>
      <g id="g-name" style="display:none">{names}</g>
      <g id="g-anch" style="display:none">{marks}</g>
      <rect id="g-sel" class="sel" style="display:none" x="0" y="0" width="0" height="0"/>
      <g id="g-hit">{hits}</g>
    </svg>
    {'<p class="note">art: ' + _esc(missing) + '</p>' if missing else ''}
  </div>
  <aside>
    <h2>selected</h2>
    <div class="pick" id="pick"><span class="none">click anything in the figure</span></div>
    <h2>elements</h2>
    <div class="tree" id="tree">{tree}</div>
    <h2>findings</h2>
    <div id="finds">{finds}</div>
  </aside>
</main>
<footer>A view: this page performs no I/O. Everything it shows arrived in its payload.</footer>
<script type="application/json" id="data">{data}</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const fig = document.getElementById('fig'), sel = document.getElementById('g-sel');
const pick = document.getElementById('pick'), tree = document.getElementById('tree');
const U = D.unit;
function row(k, v) {{ return '<tr><th>' + k + '</th><td>' + v + '</td></tr>'; }}
function fmt(n) {{ return (Math.round(n * 100) / 100) + ' ' + U; }}
function show(i) {{
  const b = D.boxes[i]; if (!b) return;
  sel.setAttribute('x', b.x); sel.setAttribute('y', b.y);
  sel.setAttribute('width', Math.max(b.width, 0.2));
  sel.setAttribute('height', Math.max(b.height, 0.2));
  sel.style.display = '';
  const anch = (b.anchors || []).map(a => '<code>' + a + '</code>').join(' ') || '&mdash;';
  const st = Object.entries(b.style || {{}})
      .map(([k, v]) => '<code>' + k + '</code> ' + v).join('<br>') || '&mdash;';
  pick.innerHTML = '<div class="addr">' + b.address + '</div><table>'
    + row('type', '<code>' + (b.type || '?') + '</code>')
    + row('role', b.role ? '<code>' + b.role + '</code>' : '&mdash; (literal style)')
    + row('size', fmt(b.width) + ' &times; ' + fmt(b.height))
    + row('at', fmt(b.x) + ', ' + fmt(b.y))
    + row('drawn', '#' + (b.order === null ? '?' : b.order) + ' of ' + D.boxes.length)
    + row('anchors', anch)
    + row('tags', (b.tags || []).join(', ') || '&mdash;')
    + row('style', st)
    + '</table>';
  [...tree.children].forEach((n, j) => n.setAttribute('aria-current', j == i));
  const cur = tree.children[i]; if (cur) cur.scrollIntoView({{block: 'nearest'}});
}}
fig.addEventListener('click', e => {{
  const t = e.target.closest('.hit'); if (t) show(+t.dataset.i);
}});
tree.addEventListener('click', e => {{
  const t = e.target.closest('button'); if (t) show(+t.dataset.i);
}});
function toggle(id, target, on) {{
  const b = document.getElementById(id);
  b.addEventListener('click', () => {{
    const now = b.getAttribute('aria-pressed') !== 'true';
    b.setAttribute('aria-pressed', now);
    if (target) document.getElementById(target).style.display = now ? '' : 'none';
    if (on) on(now);
  }});
}}
toggle('t-art', 'g-art'); toggle('t-box', 'g-box');
toggle('t-name', 'g-name'); toggle('t-anch', 'g-anch');
toggle('t-true', null, on => {{
  const s = document.getElementById('stage');
  s.style.width = on ? 'calc({w:g}mm + 20px)' : '';
  s.style.maxWidth = on ? 'none' : '';
}});
</script>
"""


# --------------------------------------------------------------------- comparison
def comparison(items, mode="side-by-side", canvas=None, title=None, note=None):
    """A `lineart.comparison/1` payload from ``[(label, markup, extra)]``. The producer half."""
    out = {"format": "lineart.comparison/1", "mode": mode, "items": []}
    if canvas:
        out["canvas"] = {"width": float(canvas["width"]),
                         "height": float(canvas["height"]),
                         "unit": canvas.get("unit", "mm")}
    if title:
        out["title"] = title
    if note:
        out["note"] = note
    for item in items:
        label, markup = item[0], item[1]
        extra = item[2] if len(item) > 2 else {}
        entry = {"label": label}
        if markup is None:
            entry["unavailable"] = extra.get("why", "this one could not be rendered")
        else:
            entry["markup"] = markup
        for k in ("note", "findings", "verdict"):
            if extra.get(k) is not None:
                entry[k] = extra[k]
        out["items"].append(entry)
    return out


_GALLERY_CSS = """
:root{--ink:#16191d;--muted:#6b7280;--line:#dde2e8;--bg:#eef1f4;--sel:#2f6fd0}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     color:var(--ink);background:var(--bg)}
header{padding:12px 16px;background:#fff;border-bottom:1px solid var(--line);
       display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:15px;margin:0;font-weight:650}
header .sub{color:var(--muted);font-size:13px}
main{padding:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px;
      margin-bottom:12px}
.card svg{display:block;width:100%;height:auto}
.cap{font:11px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;
     color:var(--muted);margin:0 0 7px;font-weight:700}
.side{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.sheet{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.stack{position:relative;overflow:hidden}
.stack .a svg{display:block;width:100%;height:auto}
.stack .b{position:absolute;top:0;left:0;height:100%;overflow:hidden;
          border-right:1px solid #2f6fd0}
.stack .b svg{display:block;height:auto}
.wipe{display:flex;gap:10px;align-items:center;margin-top:10px}
.wipe span{font:10px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;
           color:var(--muted);white-space:nowrap}
input[type=range]{width:100%;margin-top:10px}
.gone{color:var(--muted);font-size:13px;padding:16px;text-align:center}
.truesize{display:inline-block;background:#fff;border:1px solid var(--line);
          border-radius:10px;padding:10px}
.ruler{margin-top:10px;position:relative;height:22px}
.ruler div{position:absolute;top:0;width:1px;height:8px;background:#6b7280}
.ruler span{position:absolute;top:9px;font:9px ui-monospace,monospace;color:var(--muted);
            transform:translateX(-50%)}
footer{padding:4px 16px 24px;color:var(--muted);font-size:12px}
"""


def gallery(payload, title=None):
    """Two or more renderings, looked at together. A pure function of `payload`.

    `mode` decides how: ``side-by-side``, ``onion`` (a wipe between two), ``contact`` (a
    sheet of variants) or ``true-size`` (one at its printed size, with a ruler).

    C11:
      type: view
      noun: comparison
      verb: show
      tags: compare, onion, side-by-side, contact-sheet, true-size, variants, preview
      binds: scene.comparison
      returns: one self-contained HTML page; no server, no network, no store
      phrases:
        - show me these two versions side by side
        - onion skin two versions of a figure
        - a contact sheet of the variants
        - show this at its real printed size
        - compare a figure under two style guides
      requires:
        - lineart_trace/scene/inspect.py: the view; payload in, markup out
    """
    mode = payload.get("mode", "side-by-side")
    items = payload.get("items", [])
    canvas = payload.get("canvas") or {}
    name = title or payload.get("title") or "comparison"
    note = payload.get("note")

    def card(it, klass="card"):
        if it.get("unavailable"):
            return (f'<div class="{klass}"><p class="cap">{_esc(it["label"])}</p>'
                    f'<div class="gone">not shown &mdash; '
                    f'{_esc(it["unavailable"])}</div></div>')
        extra = []
        if it.get("verdict"):
            extra.append(_esc(it["verdict"]))
        if it.get("findings") is not None:
            extra.append(f'{it["findings"]} finding(s)')
        if it.get("note"):
            extra.append(_esc(it["note"]))
        tail = (" &middot; " + " &middot; ".join(extra)) if extra else ""
        return (f'<div class="{klass}"><p class="cap">{_esc(it["label"])}{tail}</p>'
                f'{it.get("markup", "")}</div>')

    if mode == "onion" and len(items) >= 2:
        a, b = items[0], items[1]
        # BOTH LAYERS IN ONE POSITIONING CONTEXT. The wiped layer was inset from the card
        # while the base sat inside the card's padding, so the two were offset by ten pixels
        # and the figure showed its caption twice at the seam -- which reads as a bug in the
        # figure rather than in the page.
        body = f"""<div class="card">
  <p class="cap">{_esc(a['label'])} &nbsp;&#8596;&nbsp; {_esc(b['label'])}</p>
  <div class="stack" id="stack">
    <div class="a" id="base">{a.get('markup', '')}</div>
    <div class="b" id="top" style="width:50%">{b.get('markup', '')}</div>
  </div>
  <div class="wipe"><span>{_esc(b['label'])}</span>
    <input type="range" id="wipe" min="0" max="100" value="50">
    <span>{_esc(a['label'])}</span></div>
</div>
<script>
const wipe = document.getElementById('wipe'), top_ = document.getElementById('top');
const stack = document.getElementById('stack');
function size() {{
  top_.style.width = wipe.value + '%';
  const s = top_.querySelector('svg');
  if (s) s.style.width = stack.clientWidth + 'px';
}}
wipe.addEventListener('input', size);
window.addEventListener('resize', size);
size(); setTimeout(size, 60);
</script>"""
    elif mode == "contact":
        body = '<div class="sheet">' + "".join(card(i) for i in items) + "</div>"
    elif mode == "true-size":
        w = canvas.get("width", 0)
        unit = canvas.get("unit", "mm")
        ticks = ""
        step = 10 if unit == "mm" else 1
        n = int(w // step)
        for k in range(n + 1):
            pct = (k * step) / w * 100 if w else 0
            ticks += (f'<div style="left:{pct:.4g}%"></div>'
                      f'<span style="left:{pct:.4g}%">{k * step}</span>')
        it = items[0] if items else {"label": "?", "unavailable": "nothing to show"}
        body = (f'<div class="truesize" style="width:calc({w:g}{unit} + 22px)">'
                f'<p class="cap">{_esc(it.get("label", ""))} &middot; shown at '
                f'{w:g} {unit}</p>{it.get("markup", "")}'
                f'<div class="ruler">{ticks}</div>'
                f'<p class="cap" style="margin:6px 0 0">hold a ruler against the scale: '
                f'if it does not read {w:g} {unit}, this screen is not reporting its own '
                f'size and no on-screen preview can be trusted for legibility</p></div>')
    else:
        body = '<div class="side">' + "".join(card(i) for i in items) + "</div>"

    return f"""<!doctype html><meta charset="utf-8">
<title>{_esc(name)}</title>
<style>{_GALLERY_CSS}</style>
<header><h1>{_esc(name)}</h1>
<span class="sub">{_esc(mode)} &middot; {len(items)} item(s)
{('&middot; ' + _esc(note)) if note else ''}</span></header>
<main>{body}</main>
<footer>A view: this page performs no I/O. Everything it shows arrived in its payload.</footer>
"""
