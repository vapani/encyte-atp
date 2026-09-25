#!/usr/bin/env python3
"""A form in your browser for creating an ATP. No terminal, no JSON.

    python3 build/serve.py

Opens http://127.0.0.1:842 - fill in the form, optionally upload a proposal to
prefill it, review every field, click Build. The .docx downloads.

Binds to localhost only: nothing outside this machine can reach it, and no
client data leaves the machine.
"""
import glob, html, importlib.util, io, json, os, re, sys, tempfile, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8420          # ports below 1024 need root; these do not


def _load(name):
    spec = importlib.util.spec_from_file_location(name, f"{ROOT}/build/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


builder = _load("build")
extractor = _load("extract")


def presets(prefix):
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{ROOT}/presets/{prefix}.*.json"))


def preset_rows(name):
    return json.load(open(f"{ROOT}/presets/{name}.json"))


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "client").lower()).strip("-") or "client"


def parse_upload(body, content_type):
    """First file part of a multipart body -> (filename, bytes).

    The stdlib `cgi` module this used to rely on was removed in Python 3.13,
    and one file field does not need a general parser.
    """
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or "")
    if not m:
        raise ValueError("malformed upload")
    boundary = (m.group(1) or m.group(2)).strip().encode()
    for part in body.split(b"--" + boundary):
        if not part.strip() or part.strip() == b"--":
            continue
        head, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        fn = re.search(r'filename="([^"]*)"', head.decode("utf8", "replace"))
        if fn and fn.group(1):
            return fn.group(1), data.rstrip(b"\r\n")
    raise ValueError("no file found in the upload")


# --------------------------------------------------------------------------- page
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>New ATP</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--ink:#14181a;--mut:#5d6b73;--line:#dfe5e8;--bg:#f6f8f9;--card:#fff;
      --teal:#0c9476;--warn:#b26a00;--warnbg:#fff8ec;--err:#b3261e;--radius:10px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{background:var(--ink);color:#fff;padding:18px 24px}
header h1{margin:0;font-size:18px;font-weight:600;letter-spacing:.2px}
header p{margin:4px 0 0;color:#9fb0b8;font-size:13px}
main{max-width:860px;margin:24px auto 80px;padding:0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px}
.card h2{margin:0 0 4px;font-size:15px;font-weight:600}
.card .hint{margin:0 0 16px;color:var(--mut);font-size:13px}
label{display:block;font-size:13px;font-weight:500;margin-bottom:5px}
input,select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:7px;font:inherit;background:#fff}
input:focus,select:focus{outline:2px solid var(--teal);outline-offset:-1px;border-color:var(--teal)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid .full{grid-column:1/-1}
@media(max-width:620px){.grid{grid-template-columns:1fr}}
.field{margin-bottom:0}
.field.guess input,.field.guess select{background:var(--warnbg);border-color:#e8c88a}
.badge{display:none;font-size:11px;color:var(--warn);margin-top:4px;font-weight:500}
.field.guess .badge{display:block}
button{font:inherit;font-weight:500;border-radius:7px;border:1px solid var(--line);
       background:#fff;padding:9px 14px;cursor:pointer}
button:hover{border-color:var(--mut)}
button.primary{background:var(--teal);border-color:var(--teal);color:#fff;padding:11px 20px;font-size:15px}
button.primary:hover{filter:brightness(.94)}
button.link{border:none;background:none;color:var(--err);padding:4px 8px;font-size:13px}
#drop{border:1.5px dashed #c6d0d5;border-radius:var(--radius);padding:22px;text-align:center;color:var(--mut);cursor:pointer;background:#fbfcfd}
#drop.over{border-color:var(--teal);background:#f0faf7;color:var(--ink)}
table{width:100%;border-collapse:collapse}
td{padding:4px 4px 4px 0;vertical-align:top}
td.act{width:36px}
.note{background:var(--warnbg);border:1px solid #f0dcb4;border-radius:8px;padding:11px 13px;margin-top:12px;font-size:13px;color:#6b4a12}
.note ul{margin:6px 0 0 18px;padding:0}
#status{margin-top:14px;font-size:14px}
.ok{color:var(--teal);font-weight:500}
.bad{color:var(--err);white-space:pre-wrap}
.bar{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 28%);padding:22px 0 10px;text-align:right}
</style></head><body>
<header><h1>New authorisation to proceed</h1>
<p>Fields are checked before anything is built. Nothing leaves this computer.</p></header>
<main>

<div class="card">
  <h2>Start from a proposal <span style="font-weight:400;color:var(--mut)">(optional)</span></h2>
  <p class="hint">Upload the proposal and the form fills in what it can find. It reads patterns,
     not meaning, so <strong>check every field it fills</strong> &mdash; shaded fields are guesses.</p>
  <div id="drop">Drop a .docx or .pdf here, or click to choose</div>
  <input type="file" id="file" accept=".docx,.pdf" hidden>
  <div id="xnotes"></div>
</div>

<div class="card"><h2>Client</h2><div class="grid">
  <div class="field full"><label>Legal entity name</label><input id="client.legal_name" placeholder="Acme Holdings Pty Ltd"><div class="badge">check this</div></div>
  <div class="field"><label>Trading / short name</label><input id="client.short_name" placeholder="Acme"><div class="badge">check this</div></div>
  <div class="field"><label>ABN</label><input id="client.abn" placeholder="51 824 753 556"><div class="badge">check this</div></div>
  <div class="field full"><label>Address</label><input id="client.address" placeholder="12 Example St, Richmond VIC 3121"><div class="badge">check this</div></div>
  <div class="field"><label>Contact person</label><input id="client.contact_name" placeholder="Jane Doe"><div class="badge">check this</div></div>
</div></div>

<div class="card"><h2>References</h2><div class="grid">
  <div class="field"><label>ATP reference</label><input id="atp.ref" placeholder="26-ACM-WD-001"><div class="badge">check this</div></div>
  <div class="field"><label>ATP date</label><input id="atp.date"><div class="badge">check this</div></div>
  <div class="field"><label>Proposal reference</label><input id="proposal.ref" placeholder="26-ACM-WD-001"><div class="badge">check this</div></div>
  <div class="field"><label>Proposal date</label><input id="proposal.date" placeholder="8 September 2026"><div class="badge">check this</div></div>
  <div class="field full"><label>Project name</label><input id="project.name" placeholder="Acme website"><div class="badge">check this</div></div>
</div></div>

<div class="card"><h2>Scope</h2><div class="grid">
  <div class="field"><label>What's included</label><select id="scope.inclusions">__INCLUSIONS__</select></div>
  <div class="field"><label>Platform</label><input id="scope.platform" value="WordPress"><div class="badge">check this</div></div>
  <div class="field full"><label>What is <em>not</em> included</label>
    <input id="scope.exclusions" placeholder="leave blank for the standard list"></div>
  <div class="field full"><label>Hosting note</label>
    <input id="hosting.note" placeholder="optional, e.g. Indicatively about USD $14 a month."></div>
</div>
<div style="margin-top:18px">
  <label>Pages</label>
  <p class="hint" style="margin:0 0 8px">Every project differs. Edit these rows &mdash; they appear in the contract exactly as written.</p>
  <table id="pages"><tbody></tbody></table>
  <div style="margin-top:8px">
    <button type="button" onclick="addPage('','')">Add page</button>
    <button type="button" onclick="loadPreset()">Reset to standard list</button>
  </div>
</div></div>

<div class="card"><h2>Fee and timeline</h2><div class="grid">
  <div class="field"><label>Standard price, excluding GST</label><input id="fee.standard" placeholder="9500"><div class="badge">check this</div></div>
  <div class="field"><label>Discount, excluding GST</label><input id="fee.discount" value="0"></div>
  <div class="field"><label>Payment split</label><select id="milestones">__MILESTONES__</select></div>
  <div class="field"><label>Work plan</label><select id="workplan">__WORKPLAN__</select></div>
  <div class="field"><label>Duration</label><input id="timeline.duration" value="Eight weeks"><div class="badge">check this</div></div>
  <div class="field"><label>Included support</label><input id="support.value" value="60"></div>
  <div class="field"><label>Support unit</label><input id="support.unit" value="days"></div>
  <div class="field"><label>Care plan, per month excl GST</label><input id="support.price" value="99"></div>
</div></div>

<div class="bar"><button class="primary" id="go">Build the ATP</button></div>
<div id="status"></div>
</main>
<script>
const STD = __STDPAGES__;
const $ = id => document.getElementById(id);

function addPage(name, purpose){
  const tr = document.createElement('tr');
  tr.innerHTML = '<td><input class="pn" placeholder="Page"></td>'
               + '<td><input class="pp" placeholder="Purpose"></td>'
               + '<td class="act"><button type="button" class="link">&times;</button></td>';
  tr.querySelector('.pn').value = name || '';
  tr.querySelector('.pp').value = purpose || '';
  tr.querySelector('button').onclick = () => tr.remove();
  $('pages').querySelector('tbody').appendChild(tr);
}
function loadPreset(){
  $('pages').querySelector('tbody').innerHTML = '';
  STD.forEach(r => addPage(r[0], r[1]));
  markGuess('pages', false);
}
function markGuess(id, on){
  const el = $(id); if(!el) return;
  el.closest('.field')?.classList.toggle('guess', !!on);
}
loadPreset();
$('atp.date').value = new Date().toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric'});

// ---- proposal upload
const drop = $('drop'), file = $('file');
drop.onclick = () => file.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over');
                     if(e.dataTransfer.files[0]) send(e.dataTransfer.files[0]); };
file.onchange = () => file.files[0] && send(file.files[0]);

async function send(f){
  drop.textContent = 'Reading ' + f.name + '...';
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch('/extract', {method:'POST', body:fd});
  const j = await r.json();
  if(j.error){ drop.textContent = 'Could not read it: ' + j.error; return; }
  let filled = 0;
  for(const [k,v] of Object.entries(j.fields)){
    if(k === 'scope.pages'){
      $('pages').querySelector('tbody').innerHTML = '';
      v.value.forEach(r => addPage(r[0], r[1]));
      filled++; continue;
    }
    const el = $(k);
    if(el){ el.value = v.value; markGuess(k, v.confidence === 'low'); filled++; }
  }
  drop.textContent = f.name + ' — ' + filled + ' fields filled';
  const notes = j.notes || [];
  $('xnotes').innerHTML = '<div class="note"><strong>Read before you build.</strong> '
    + 'Shaded fields were guessed from patterns in the document and are often wrong.'
    + (notes.length ? '<ul>' + notes.map(n => '<li>' + n + '</li>').join('') + '</ul>' : '')
    + '</div>';
}

// ---- build
$('go').onclick = async () => {
  const ids = ['client.legal_name','client.short_name','client.abn','client.address',
    'client.contact_name','atp.ref','atp.date','proposal.ref','proposal.date',
    'project.name','scope.inclusions','scope.platform','scope.exclusions','hosting.note',
    'fee.standard','fee.discount','milestones','workplan','timeline.duration',
    'support.value','support.unit','support.price'];
  const data = {};
  ids.forEach(i => data[i] = $(i).value.trim());
  data.pages = [...document.querySelectorAll('#pages tbody tr')]
      .map(tr => [tr.querySelector('.pn').value.trim(), tr.querySelector('.pp').value.trim()])
      .filter(r => r[0] && r[1]);
  $('status').innerHTML = 'Building...';
  const r = await fetch('/build', {method:'POST', headers:{'Content-Type':'application/json'},
                                   body: JSON.stringify(data)});
  if(r.headers.get('Content-Type') === 'application/json'){
    const j = await r.json();
    $('status').innerHTML = '<div class="bad"><strong>Not built.</strong>\\n' + j.errors.join('\\n') + '</div>';
    return;
  }
  const blob = await r.blob();
  const name = (r.headers.get('X-Filename') || 'ATP.docx');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  $('status').innerHTML = '<span class="ok">Built ' + name
    + ' — downloaded. Open it and read it before sending.</span>';
};
</script></body></html>"""


def render_page():
    def opts(names):
        return "".join(f'<option value="{html.escape(n)}">{html.escape(n)}</option>' for n in names)
    return (PAGE
            .replace("__INCLUSIONS__", opts(presets("inclusions")))
            .replace("__MILESTONES__", opts(presets("milestones")))
            .replace("__WORKPLAN__", opts(presets("workplan")))
            .replace("__STDPAGES__", json.dumps(preset_rows(presets("pages")[0]))))


# --------------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, render_page(), "text/html; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path == "/extract":
            return self.handle_extract()
        if self.path == "/build":
            return self.handle_build()
        self._send(404, json.dumps({"error": "not found"}))

    def handle_extract(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            name, blob = parse_upload(self.rfile.read(n), self.headers.get("Content-Type"))
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".docx", ".pdf"):
                raise ValueError("upload a .docx or .pdf")
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
                fh.write(blob)
                tmp = fh.name
            try:
                self._send(200, json.dumps(extractor.extract(tmp)))
            finally:
                os.unlink(tmp)
        except Exception as e:
            self._send(200, json.dumps({"error": str(e)}))

    def handle_build(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._send(200, json.dumps({"errors": [f"bad request: {e}"]}))

        def num(key, default=0.0):
            raw = re.sub(r"[$,]", "", str(d.get(key, "")).strip())
            return float(raw) if raw else default

        try:
            eng = {
                "jurisdiction": "AU",
                "engagement_type": "website",
                "atp": {"date": d.get("atp.date", ""), "ref": d.get("atp.ref", "")},
                "proposal": {"ref": d.get("proposal.ref", ""), "date": d.get("proposal.date", "")},
                "client": {k: d.get(f"client.{k}", "") for k in
                           ("legal_name", "abn", "address", "short_name", "contact_name")},
                "scope": {"inclusions": f'preset:{d.get("scope.inclusions")}',
                          "pages": d.get("pages") or [],
                          "platform": d.get("scope.platform") or "WordPress"},
                "hosting": {"note": d.get("hosting.note", "")},
                "fee": {"standard": num("fee.standard"), "discount": num("fee.discount")},
                "milestones": f'preset:{d.get("milestones")}',
                "timeline": {"duration": d.get("timeline.duration", ""),
                             "tasks": f'preset:{d.get("workplan")}'},
                "support": {"included": {"value": int(num("support.value", 60)),
                                         "unit": d.get("support.unit") or "days"},
                            "plan": {"price": num("support.price", 99)}},
                "project": {"name": d.get("project.name", "")},
            }
            if d.get("scope.exclusions"):
                eng["scope"]["exclusions"] = d["scope.exclusions"]
        except Exception as e:
            return self._send(200, json.dumps({"errors": [f"could not read the form: {e}"]}))

        # build from a scratch file first: a rejected build must not leave a
        # half-filled engagement behind in engagements/
        slug = slugify(eng["client"]["short_name"])
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, f"{slug}.json")
        json.dump(eng, open(path, "w"), indent=1, ensure_ascii=False)
        open(path, "a").write("\n")

        out = os.path.join(tempfile.gettempdir(),
                           f"ATP-{re.sub(r'[^A-Za-z0-9]+', '-', eng['client']['short_name'] or 'Client')}.docx")
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            builder.build(path, out)
        except SystemExit:
            sys.stdout = real
            errs = [l.strip(" -") for l in buf.getvalue().splitlines() if l.strip().startswith("-")]
            return self._send(200, json.dumps({"errors": errs or ["validation failed"]}))
        except Exception as e:
            sys.stdout = real
            return self._send(200, json.dumps({"errors": [str(e)]}))
        finally:
            sys.stdout = real

        # it built, so the engagement is worth keeping and committing
        kept = f"{ROOT}/engagements/{slug}.json"
        json.dump(eng, open(kept, "w"), indent=1, ensure_ascii=False)
        open(kept, "a").write("\n")

        data = open(out, "rb").read()
        os.unlink(out)
        self._send(200, data,
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   {"X-Filename": os.path.basename(out),
                    "Content-Disposition": f'attachment; filename="{os.path.basename(out)}"'})


def main():
    port, srv = PORT, None
    for port in range(PORT, PORT + 12):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit(f"could not bind a port in {PORT}-{PORT + 11}")
    url = f"http://127.0.0.1:{port}"
    print(f"\n  ATP form running at {url}")
    print("  Local only - nothing is reachable from outside this machine.")
    print("  Press Ctrl-C to stop.\n")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("  stopped")


if __name__ == "__main__":
    main()
