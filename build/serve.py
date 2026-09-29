#!/usr/bin/env python3
"""A form in your browser for creating an ATP. No terminal, no JSON.

    python3 build/serve.py

Opens http://127.0.0.1:842 - fill in the form, optionally upload a proposal to
prefill it, review every field, click Build. The .docx downloads.

Binds to localhost only: nothing outside this machine can reach it, and no
client data leaves the machine.
"""
import glob, html, importlib.util, io, json, os, re, shutil, sys, tempfile, threading, webbrowser
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
BUILD_LOCK = threading.Lock()


def presets(prefix, etype=None):
    """Preset names for `prefix`. Scope and work-plan presets are named for their
    engagement type (inclusions.website, workplan.mobile-app-14week); pass etype
    to list only that type's, so an app preset never appears on the website form."""
    names = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{ROOT}/presets/{prefix}.*.json"))
    if etype:
        names = [n for n in names if n.startswith(f"{prefix}.{etype.replace('_', '-')}")]
    return names


def preset_rows(name):
    return json.load(open(f"{ROOT}/presets/{name}.json"))


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "client").lower()).strip("-") or "client"


def record_engagement(eng, slug):
    """Keep the engagement file as the record of what was issued.

    Locally that means writing into engagements/ for you to commit. Hosted, the
    container filesystem does not survive a restart, so with ATP_GITHUB_TOKEN set
    it commits to the repository instead - the same audit trail, next to the
    template version that produced the document.

    Returns (ok, message). Never raises: a contract that has been generated
    should still reach the person who asked for it, but they must be told the
    record did not save.
    """
    blob = json.dumps(eng, indent=1, ensure_ascii=False) + "\n"
    token = os.environ.get("ATP_GITHUB_TOKEN")

    if not token:
        # Hosted, the container's disk is wiped whenever it sleeps, so a file
        # written there is not a record. Say so rather than report success.
        if os.environ.get("ATP_HOST", "127.0.0.1") not in ("127.0.0.1", "localhost"):
            return False, ("this server has no ATP_GITHUB_TOKEN, so there is nowhere permanent "
                           "to keep the record - keep the downloaded contract, and set the token "
                           "so future records are committed")
        try:
            path = os.path.join(os.environ.get("ATP_ENGAGEMENTS", f"{ROOT}/engagements"),
                                f"{slug}.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write(blob)
            return True, f"written to engagements/{slug}.json - commit it"
        except OSError as e:
            return False, f"could not write the engagement record: {e}"

    import base64, urllib.request, urllib.error
    repo = os.environ.get("ATP_GITHUB_REPO", "vapani/encyte-atp")
    branch = os.environ.get("ATP_GITHUB_BRANCH", "main")
    path = f"engagements/{slug}.json"
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "encyte-atp"}

    def call(req):
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")

    try:
        sha = None                                   # updating needs the current sha
        try:
            sha = call(urllib.request.Request(f"{api}?ref={branch}", headers=headers)).get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        payload = {"message": f"Record the {eng['client']['short_name']} engagement "
                              f"({eng['atp']['ref']})",
                   "content": base64.b64encode(blob.encode()).decode(),
                   "branch": branch}
        if sha:
            payload["sha"] = sha
        call(urllib.request.Request(api, data=json.dumps(payload).encode(),
                                    headers={**headers, "Content-Type": "application/json"},
                                    method="PUT"))
        return True, f"committed to {repo} as {path}"
    except Exception as e:
        detail = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = " - " + json.loads(e.read()).get("message", "")
            except Exception:
                pass
        return False, f"NOT recorded: {type(e).__name__}{detail}"


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
#pages tr.guess input{background:var(--warnbg);border-color:#e8c88a}
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
#tasks th{text-align:left;font-size:12px;font-weight:500;color:var(--mut);padding:0 4px 4px 0}
#tasks .resp{width:170px}
#tasks .when{width:130px}
.note{background:var(--warnbg);border:1px solid #f0dcb4;border-radius:8px;padding:11px 13px;margin-top:12px;font-size:13px;color:#6b4a12}
.note ul{margin:6px 0 0 18px;padding:0}
#status{margin-top:14px;font-size:14px}
.ok{color:var(--teal);font-weight:500}
#status .bad{color:var(--err)}
#status .bad ul{margin:6px 0 0 18px;padding:0}
.field.bad input,.field.bad select,tr.bad input{border-color:var(--err);background:#fdf1f0}
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

<div class="card"><h2>What are we building?</h2><div class="grid">
  <div class="field"><label>Contract type</label><select id="engagement_type" onchange="applyType(this.value)">
    <option value="website">Website</option><option value="web_app">Web app</option>
    <option value="mobile_app">Mobile app</option></select><div class="badge">check this</div></div>
</div>
<div id="draftnote" class="note" style="display:none"><strong>Draft only.</strong> The web app and
  mobile app terms have not been legally reviewed yet. This contract will be marked
  <em>DRAFT FOR LEGAL REVIEW &ndash; NOT FOR ISSUE</em> on every page. Do not send it to a client.</div>
</div>

<div class="card"><h2>Client</h2><div class="grid">
  <div class="field full"><label>Legal entity name</label><input id="client.legal_name" placeholder="e.g. Acme Holdings Pty Ltd"><div class="badge">check this</div></div>
  <div class="field"><label>Trading / short name</label><input id="client.short_name" placeholder="e.g. Acme"><div class="badge">check this</div></div>
  <div class="field"><label>ABN</label><input id="client.abn" placeholder="e.g. 51 824 753 556"><div class="badge">check this</div></div>
  <div class="field full"><label>Address</label><input id="client.address" placeholder="e.g. 12 Example St, Richmond VIC 3121"><div class="badge">check this</div></div>
  <div class="field"><label>Contact person</label><input id="client.contact_name" placeholder="e.g. Jane Doe"><div class="badge">check this</div></div>
</div></div>

<div class="card"><h2>References</h2><div class="grid">
  <div class="field"><label>ATP reference</label><input id="atp.ref" placeholder="e.g. 26-ACM-WD-001"><div class="badge">check this</div></div>
  <div class="field"><label>ATP date</label><input id="atp.date"><div class="badge">check this</div></div>
  <div class="field"><label>Proposal reference</label><input id="proposal.ref" placeholder="e.g. 26-ACM-WD-001"><div class="badge">check this</div></div>
  <div class="field"><label>Proposal date</label><input id="proposal.date" placeholder="e.g. 8 September 2026"><div class="badge">check this</div></div>
  <div class="field full"><label>Project name</label><input id="project.name" placeholder="e.g. Acme website"><div class="badge">check this</div></div>
</div></div>

<div class="card"><h2>Scope</h2><div class="grid">
  <div class="field"><label>What's included</label><select id="scope.inclusions"></select></div>
  <div class="field"><label>Platform</label><input id="scope.platform" value="WordPress"><div class="badge">check this</div></div>
  <div class="field full" id="devices-field" style="display:none"><label>Devices and operating systems</label>
    <input id="scope.devices" placeholder="e.g. iPhones running iOS 17 or later and Android phones running Android 10 or later"><div class="badge">check this</div></div>
  <div class="field full"><label>What is <em>not</em> included</label>
    <input id="scope.exclusions" placeholder="leave blank for the standard list"></div>
  <div class="field full"><label>Hosting note</label>
    <input id="hosting.note" placeholder="optional, e.g. Indicatively about USD $14 a month."></div>
</div>
<div style="margin-top:18px">
  <label id="list-label">Pages</label>
  <p class="hint" style="margin:0 0 8px">Every project differs. Edit these rows &mdash; they appear in the contract exactly as written.</p>
  <table id="pages"><tbody></tbody></table>
  <div style="margin-top:8px">
    <button type="button" id="add-item" onclick="addPage('','')">Add page</button>
    <button type="button" onclick="loadPreset()">Reset to standard list</button>
  </div>
</div></div>

<div class="card"><h2>Fee and support</h2><div class="grid">
  <div class="field"><label>Standard price, excluding GST</label><input id="fee.standard" placeholder="e.g. 9500"><div class="badge">check this</div></div>
  <div class="field"><label>Discount, excluding GST</label><input id="fee.discount" value="0"></div>
  <div class="field"><label>Payment split</label><select id="milestones">__MILESTONES__</select></div>
  <div class="field"><label>Included support</label><input id="support.value" value="60"></div>
  <div class="field"><label>Support unit</label><input id="support.unit" value="days"></div>
  <div class="field"><label>Care plan, per month excl GST</label><input id="support.price" value="99"></div>
</div></div>

<div class="card"><h2>Timeline</h2>
<p class="hint">The work plan in section 3.1. Edit the rows to match the proposal &mdash; they appear
  in the contract exactly as written. The plan cannot run past the duration.</p>
<div class="grid">
  <div class="field"><label>Duration</label><input id="timeline.duration" value="Eight weeks"><div class="badge">check this</div></div>
  <div class="field"><label>&nbsp;</label><div id="planend" class="hint" style="margin:9px 0 0"></div></div>
</div>
<div style="margin-top:14px">
  <table id="tasks"><thead><tr><th>Milestone / task</th><th class="resp">Responsibility</th><th class="when">Timeline</th><th></th></tr></thead><tbody></tbody></table>
  <div style="margin-top:8px">
    <button type="button" onclick="addTask('','P','')">Add task</button>
    <button type="button" onclick="loadPlan()">Reset to standard plan</button>
  </div>
</div></div>

<div class="bar"><button class="primary" id="go">Build the ATP</button></div>
<div id="status"></div>
</main>
<script>
// Per contract type: inclusions presets, standard page or feature list, standard plan,
// duration, payment split, platform, labels, and whether the terms are still a draft.
const TYPES = __TYPES__;
let current = 'website';
const $ = id => document.getElementById(id);

// Responsibility is one of three; the contract gets the matching tokens.
const RESP = {P: '{{provider.short_name}}', C: '{{client.short_name}}',
              B: '{{provider.short_name}} / {{client.short_name}}'};
const RESP_LABEL = {P: 'Encyte', C: 'Client', B: 'Encyte / Client'};
function addTask(task, resp, when){
  const code = RESP[resp] ? resp : (Object.keys(RESP).find(k => RESP[k] === resp) || 'P');
  const tr = document.createElement('tr');
  tr.innerHTML = '<td><input class="tn" placeholder="Task"></td>'
    + '<td class="resp"><select class="tr">'
    + Object.keys(RESP).map(k => '<option value="' + k + '">' + RESP_LABEL[k] + '</option>').join('')
    + '</select></td>'
    + '<td class="when"><input class="tw" placeholder="e.g. Week 3"></td>'
    + '<td class="act"><button type="button" class="link">&times;</button></td>';
  tr.querySelector('.tn').value = task || '';
  tr.querySelector('.tr').value = code;
  tr.querySelector('.tw').value = when || '';
  tr.querySelector('button').onclick = () => { tr.remove(); planEnd(); };
  tr.querySelector('.tw').oninput = planEnd;
  $('tasks').querySelector('tbody').appendChild(tr);
  planEnd();
}
function loadPlan(){
  $('tasks').querySelector('tbody').innerHTML = '';
  TYPES[current].plan.forEach(r => addTask(r[0], r[1], r[2]));
}
function planEnd(){
  const weeks = [...document.querySelectorAll('#tasks .tw')]
    .flatMap(i => (i.value.match(/\\d+/g) || []).map(Number));
  $('planend').textContent = weeks.length ? 'The plan runs to week ' + Math.max(...weeks) + '.' : '';
}

function addPage(name, purpose){
  const tr = document.createElement('tr');
  tr.innerHTML = '<td><input class="pn" placeholder="' + TYPES[current].item + '"></td>'
               + '<td><input class="pp" placeholder="' + TYPES[current].desc + '"></td>'
               + '<td class="act"><button type="button" class="link">&times;</button></td>';
  tr.querySelector('.pn').value = name || '';
  tr.querySelector('.pp').value = purpose || '';
  tr.querySelector('button').onclick = () => tr.remove();
  $('pages').querySelector('tbody').appendChild(tr);
}
function loadPreset(){
  $('pages').querySelector('tbody').innerHTML = '';
  TYPES[current].list.forEach(r => addPage(r[0], r[1]));
  markGuess('pages', false);
}
function markGuess(id, on){
  const el = $(id); if(!el) return;
  el.closest('.field')?.classList.toggle('guess', !!on);
}
function listRows(){
  return [...document.querySelectorAll('#pages tbody tr')]
    .map(tr => [tr.querySelector('.pn').value.trim(), tr.querySelector('.pp').value.trim()]);
}
function planRows(){
  return [...document.querySelectorAll('#tasks tbody tr')]
    .map(tr => [tr.querySelector('.tn').value.trim(), RESP[tr.querySelector('.tr').value], tr.querySelector('.tw').value.trim()]);
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Switch the form to a contract type. Anything still at the previous type's
// standard value is swapped for the new one; anything edited is left alone.
function applyType(t, init){
  const prev = TYPES[current], T = TYPES[t];
  const std = {
    list: init || same(listRows(), prev.list),
    plan: init || same(planRows(), prev.plan),
    duration: init || $('timeline.duration').value.trim() === prev.duration,
    split: init || $('milestones').value === prev.split,
    platform: init || $('scope.platform').value.trim() === prev.platform,
  };
  current = t;
  $('engagement_type').value = t;
  $('scope.inclusions').innerHTML = T.inclusions.map(n => '<option value="' + n + '">' + n + '</option>').join('');
  $('list-label').textContent = T.list_label;
  $('add-item').textContent = 'Add ' + T.item.toLowerCase();
  $('devices-field').style.display = t === 'mobile_app' ? '' : 'none';
  $('draftnote').style.display = T.draft ? '' : 'none';
  $('scope.platform').placeholder = T.platform_hint;
  $('project.name').placeholder = T.project_hint;
  if(std.list) loadPreset();
  else document.querySelectorAll('#pages tbody tr').forEach(tr => {
    tr.querySelector('.pn').placeholder = T.item; tr.querySelector('.pp').placeholder = T.desc; });
  if(std.plan) loadPlan();
  if(std.duration) $('timeline.duration').value = T.duration;
  if(std.split) $('milestones').value = T.split;
  if(std.platform) $('scope.platform').value = T.platform;
}
applyType('website', true);
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
  if(j.fields.engagement_type){
    applyType(j.fields.engagement_type.value);
    markGuess('engagement_type', true);
    filled++;
  }
  for(const [k,v] of Object.entries(j.fields)){
    if(k === 'engagement_type') continue;
    if(k === 'scope.pages'){
      $('pages').querySelector('tbody').innerHTML = '';
      v.value.forEach(r => addPage(r[0], r[1]));
      // read from the proposal, so shade them like any other guess
      document.querySelectorAll('#pages tbody tr').forEach(tr => tr.classList.add('guess'));
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
function notBuilt(errors, fields){
  fields.forEach(id => $(id)?.closest('.field')?.classList.add('bad'));
  const box = document.createElement('div');
  box.className = 'bad';
  box.innerHTML = '<strong>Not built.</strong>';
  const ul = document.createElement('ul');
  errors.forEach(e => { const li = document.createElement('li'); li.textContent = e; ul.appendChild(li); });
  box.appendChild(ul);
  $('status').replaceChildren(box);
  $('status').scrollIntoView({behavior:'smooth', block:'center'});
}
$('go').onclick = async () => {
  const ids = ['client.legal_name','client.short_name','client.abn','client.address',
    'client.contact_name','atp.ref','atp.date','proposal.ref','proposal.date',
    'engagement_type','project.name','scope.inclusions','scope.platform','scope.devices',
    'scope.exclusions','hosting.note',
    'fee.standard','fee.discount','milestones','timeline.duration',
    'support.value','support.unit','support.price'];
  const data = {};
  ids.forEach(i => data[i] = $(i).value.trim());
  document.querySelectorAll('.field.bad, #pages tr.bad, #tasks tr.bad').forEach(el => el.classList.remove('bad'));
  // A row with a page but no purpose used to vanish from the contract without a word.
  const rows = [...document.querySelectorAll('#pages tbody tr')];
  const half = rows.filter(tr => !tr.querySelector('.pn').value.trim() !== !tr.querySelector('.pp').value.trim());
  if(half.length){
    half.forEach(tr => tr.classList.add('bad'));
    return notBuilt(['Every ' + TYPES[current].item.toLowerCase() + ' needs a name and a '
                     + TYPES[current].desc.toLowerCase() + ' - ' + half.length
                     + (half.length === 1 ? ' row is' : ' rows are') + ' incomplete'], []);
  }
  data.pages = rows
      .map(tr => [tr.querySelector('.pn').value.trim(), tr.querySelector('.pp').value.trim()])
      .filter(r => r[0] && r[1]);
  const trows = [...document.querySelectorAll('#tasks tbody tr')];
  const thalf = trows.filter(tr => !tr.querySelector('.tn').value.trim() !== !tr.querySelector('.tw').value.trim());
  if(thalf.length){
    thalf.forEach(tr => tr.classList.add('bad'));
    return notBuilt(['Every timeline row needs a task and a week - ' + thalf.length
                     + (thalf.length === 1 ? ' row is' : ' rows are') + ' incomplete'], []);
  }
  data.tasks = trows
      .map(tr => [tr.querySelector('.tn').value.trim(), RESP[tr.querySelector('.tr').value],
                  tr.querySelector('.tw').value.trim()])
      .filter(r => r[0] && r[2]);
  return build(data);
};

async function build(data){
  $('status').innerHTML = 'Building...';
  const r = await fetch('/build', {method:'POST', headers:{'Content-Type':'application/json'},
                                   body: JSON.stringify(data)});
  if(r.headers.get('Content-Type') === 'application/json'){
    const j = await r.json();
    if(j.confirm){
      if(!confirm(j.confirm))
        return notBuilt(['Check the standard price and discount, then build again'], j.fields || []);
      data.confirm_low_price = true;
      return build(data);
    }
    return notBuilt(j.errors, j.fields || []);
  }
  const blob = await r.blob();
  const name = (r.headers.get('X-Filename') || 'ATP.docx');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  $('status').innerHTML = r.headers.get('X-Draft')
    ? '<div class="note"><strong>Built ' + name + ' as a DRAFT for legal review.</strong> '
      + 'It is marked NOT FOR ISSUE on every page. Do not send it to a client.</div>'
    : '<span class="ok">Built ' + name + ' — downloaded. Open it and read it before sending.</span>';
  const rec = r.headers.get('X-Record') || '';
  const bad = rec.startsWith('FAILED');
  if (rec) $('status').innerHTML += '<div class="' + (bad ? 'note' : '') + '"'
    + ' style="margin-top:8px;font-size:13px' + (bad ? '' : ';color:var(--mut)') + '">'
    + (bad ? '<strong>The engagement record did not save.</strong> ' : 'Record: ')
    + rec.replace(/^(ok|FAILED) /, '') + '</div>';
}
</script></body></html>"""


def abn_valid(abn):
    """The ABN check digit: subtract 1 from the first digit, weight, sum, divide by 89."""
    d = [int(c) for c in re.sub(r"\D", "", abn)]
    if len(d) != 11:
        return False
    d[0] -= 1
    return sum(x * w for x, w in zip(d, (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19))) % 89 == 0


DATE = r"^\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"
REF = r"^\d{2}-[A-Z0-9]+-[A-Z]{2}-\d{3}$"


def form_problems(eng):
    """Checks that suit typed input, on top of build.py's own validation.

    Each is (message, [form field ids]) so the form can mark the fields.
    """
    out = []
    abn = eng["client"]["abn"]
    if abn.strip() and not abn_valid(abn):
        out.append((f"The ABN {abn} is not a valid ABN - check for a typo, or look it up at "
                    f"abr.business.gov.au", ["client.abn"]))
    for key, label in (("atp.date", "ATP date"), ("proposal.date", "Proposal date")):
        section, field = key.split(".")
        v = eng[section][field]
        if v and not re.match(DATE, v):
            out.append((f"{label} '{v}' should be written like 8 September 2026 - "
                        f"it is printed in the contract exactly as typed", [key]))
    for key, label in (("atp.ref", "ATP reference"), ("proposal.ref", "Proposal reference")):
        section, field = key.split(".")
        v = eng[section][field]
        if v and not re.match(REF, v):
            out.append((f"{label} '{v}' should look like 26-NGA-WD-062", [key]))
    # Timeline rows. A row with no week number would slip past the check that the
    # plan fits the duration, and the responsibility can only be one of three.
    for row in eng["timeline"]["tasks"]:
        if not (isinstance(row, list) and len(row) == 3):
            out.append(("A timeline row could not be read - reset to the standard plan", []))
            continue
        task, resp, when = row
        if resp not in RESPONSIBLE:
            out.append((f"Timeline row '{task}' has an unknown responsibility", []))
        if not builder.weeks_in(when):
            out.append((f"Timeline row '{task}' should say which week, e.g. Week 3 or Weeks 4-5 "
                        f"(it says '{when}')", []))
    return out


RESPONSIBLE = {"{{provider.short_name}}", "{{client.short_name}}",
               "{{provider.short_name}} / {{client.short_name}}"}


LABELS = {
    "client.legal_name": "Legal entity name", "client.short_name": "Trading / short name",
    "client.abn": "ABN", "client.address": "Address", "client.contact_name": "Contact person",
    "atp.ref": "ATP reference", "atp.date": "ATP date", "proposal.ref": "Proposal reference",
    "proposal.date": "Proposal date", "project.name": "Project name", "scope.platform": "Platform",
    "timeline.duration": "Duration", "scope.devices": "Devices and operating systems",
}


def friendly(err):
    """build.py's validation message -> (message in the form's words, [field ids])."""
    m = re.match(r"missing or empty: ([\w.]+)$", err)
    if m and m.group(1) in LABELS:
        return f"{LABELS[m.group(1)]} is empty", [m.group(1)]
    if "scope.pages is empty" in err:
        return "Add at least one page, with its purpose", []
    if "scope.features is empty" in err:
        return "Add at least one feature, with its description", []
    if "is not a" in err and "preset" in err:
        return "The 'What's included' list does not match the contract type - pick one for this type", ["scope.inclusions"]
    if "discount exceeds" in err:
        return "The discount is more than the standard price", ["fee.standard", "fee.discount"]
    if "price is $0" in err:
        return "The standard price is empty or $0", ["fee.standard"]
    if "timeline.tasks is empty" in err:
        return "Add at least one timeline row", []
    if "work plan runs" in err:
        m = re.search(r"week (\d+) but the timeline says (\d+) weeks", err)
        return (f"The timeline runs to week {m.group(1)} but the duration says {m.group(2)} weeks - "
                f"change the duration or the timeline rows" if m else err), ["timeline.duration"]
    if "timeline.duration" in err:
        return err[0].upper() + err[1:], ["timeline.duration"]
    if "milestone" in err:
        return err[0].upper() + err[1:], ["milestones"]
    return err[0].upper() + err[1:], []


DEFAULT_SPLIT = "milestones.20-40-40"
LOW_PRICE = 500      # below this the form asks before building; see build_in()


NUM_WORDS = {6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve",
             13: "Thirteen", 14: "Fourteen", 15: "Fifteen", 16: "Sixteen", 18: "Eighteen", 20: "Twenty"}
DEFAULT_SPLITS = {"website": DEFAULT_SPLIT, "web_app": "milestones.20-30-30-20",
                  "mobile_app": "milestones.20-30-30-20"}
TYPE_WORDS = {  # list label, item, description, platform default and hint, project name hint
    "website":    ("Pages", "Page", "Purpose", "WordPress", "e.g. WordPress", "e.g. Acme website"),
    "web_app":    ("Features", "Feature", "Description", "", "e.g. Next.js and React", "e.g. Acme client portal"),
    "mobile_app": ("Features", "Feature", "Description", "", "e.g. React Native", "e.g. Acme mobile app"),
}


def type_data():
    """Everything the form switches when the contract type changes, read from presets/."""
    out = {}
    for t in builder.TYPES:
        label, item, desc, platform, platform_hint, project_hint = TYPE_WORDS[t]
        plan = preset_rows(presets("workplan", t)[0])
        weeks = max(builder.weeks_in(r[-1]) for r in plan)
        out[t] = {
            "inclusions": presets("inclusions", t),
            "list": preset_rows(presets(builder.SCOPE_LIST[t], t)[0]),
            "plan": plan,
            "duration": f"{NUM_WORDS.get(weeks, weeks)} weeks",
            "split": DEFAULT_SPLITS[t],
            "platform": platform, "platform_hint": platform_hint, "project_hint": project_hint,
            "list_label": label, "item": item, "desc": desc,
            "draft": t not in builder.REVIEWED,
        }
    return out


def render_page():
    def opts(names, selected=None):
        return "".join(f'<option value="{html.escape(n)}"{" selected" if n == selected else ""}>'
                       f'{html.escape(n)}</option>' for n in names)
    # The form issues websites only: web app and mobile app clauses are still drafts.
    return (PAGE
            .replace("__MILESTONES__", opts(presets("milestones"), DEFAULT_SPLIT))
            .replace("__TYPES__", json.dumps(type_data())))


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

        etype = d.get("engagement_type") or "website"
        if etype not in builder.TYPES:
            return self._send(200, json.dumps({"errors": [f"unknown contract type '{etype}'"]}))
        try:
            eng = {
                "jurisdiction": "AU",
                "engagement_type": etype,
                "atp": {"date": d.get("atp.date", ""), "ref": d.get("atp.ref", "")},
                "proposal": {"ref": d.get("proposal.ref", ""), "date": d.get("proposal.date", "")},
                "client": {k: d.get(f"client.{k}", "") for k in
                           ("legal_name", "abn", "address", "short_name", "contact_name")},
                # a website lists pages in 2.2, an app lists features
                "scope": {"inclusions": f'preset:{d.get("scope.inclusions")}',
                          builder.SCOPE_LIST[etype]: d.get("pages") or [],
                          "platform": d.get("scope.platform") or ("WordPress" if etype == "website" else "")},
                "hosting": {"note": d.get("hosting.note", "")},
                "fee": {"standard": num("fee.standard"), "discount": num("fee.discount")},
                "milestones": f'preset:{d.get("milestones")}',
                "timeline": {"duration": d.get("timeline.duration", ""),
                             "tasks": d.get("tasks") or []},
                "support": {"included": {"value": int(num("support.value", 60)),
                                         "unit": d.get("support.unit") or "days"},
                            "plan": {"price": num("support.price", 99)}},
                "project": {"name": d.get("project.name", "")},
            }
            if d.get("scope.exclusions"):
                eng["scope"]["exclusions"] = d["scope.exclusions"]
            if etype == "mobile_app":
                eng["scope"]["devices"] = d.get("scope.devices", "")
        except Exception as e:
            return self._send(200, json.dumps({"errors": [f"could not read the form: {e}"]}))

        # build from a scratch file first: a rejected build must not leave a
        # half-filled engagement behind in engagements/
        tmpdir = tempfile.mkdtemp()
        try:
            self.build_in(tmpdir, eng, confirmed_low=bool(d.get("confirm_low_price")))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def build_in(self, tmpdir, eng, confirmed_low=False):
        slug = slugify(eng["client"]["short_name"])
        path = os.path.join(tmpdir, f"{slug}.json")
        json.dump(eng, open(path, "w"), indent=1, ensure_ascii=False)
        open(path, "a").write("\n")

        # Check everything first and report it all at once, in the form's own words.
        try:
            problems = form_problems(eng) + [friendly(e) for e in builder.validate(*builder.load(path))]
        except Exception as e:
            problems = [(f"could not read the form: {e}", [])]
        if problems:
            return self._send(200, json.dumps({"errors": [m for m, _ in problems],
                                               "fields": sorted({f for _, fs in problems for f in fs})}))

        # Valid but implausible: a price this low is usually a misread or a typo
        # ('$ 8, 946' read as $8). Ask, rather than refuse - a small job is possible.
        total = eng["fee"]["standard"] - eng["fee"]["discount"]
        if total < LOW_PRICE and not confirmed_low:
            return self._send(200, json.dumps({
                "confirm": f"The price is ${total:,.2f} excluding GST, which is unusually low for a "
                           f"build. Is that right?\n\nOK builds the contract at this price. Cancel "
                           f"goes back to the form.",
                "fields": ["fee.standard"]}))

        # App terms are unreviewed: build them as marked drafts, never as issuable contracts.
        draft = eng["engagement_type"] not in builder.REVIEWED
        name = (f"ATP-{'DRAFT-' if draft else ''}"
                f"{re.sub(r'[^A-Za-z0-9]+', '-', eng['client']['short_name'] or 'Client')}.docx")
        out = os.path.join(tmpdir, name)
        # build() prints its report; capturing stdout is process-wide, so one build at a time
        with BUILD_LOCK:
            buf, real = io.StringIO(), sys.stdout
            sys.stdout = buf
            try:
                builder.build(path, out, draft=draft)
            except SystemExit:
                sys.stdout = real
                errs = [l.strip(" -") for l in buf.getvalue().splitlines() if l.strip().startswith("-")]
                return self._send(200, json.dumps({"errors": errs or ["validation failed"]}))
            except Exception as e:
                sys.stdout = real
                return self._send(200, json.dumps({"errors": [str(e)]}))
            finally:
                sys.stdout = real

        # It built, so record what was issued. A draft is not issued, so it is not recorded.
        if draft:
            recorded, record_msg = True, "draft for legal review - not recorded, because drafts are not issued"
        else:
            recorded, record_msg = record_engagement(eng, slug)
        print(f"  record: {record_msg}")

        data = open(out, "rb").read()
        self._send(200, data,
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   {"X-Filename": os.path.basename(out),
                    "X-Record": ("ok " if recorded else "FAILED ") + record_msg,
                    **({"X-Draft": "1"} if draft else {}),
                    "Content-Disposition": f'attachment; filename="{os.path.basename(out)}"'})


def main():
    # Defaults are the local ones. In a container ATP_HOST=0.0.0.0 binds the
    # published port, and nothing opens a browser.
    host = os.environ.get("ATP_HOST", "127.0.0.1")
    fixed = os.environ.get("ATP_PORT")
    open_browser = os.environ.get("ATP_OPEN_BROWSER", "1") != "0"

    if fixed:                       # a container publishes one known port
        srv, port = ThreadingHTTPServer((host, int(fixed)), Handler), int(fixed)
    else:                           # locally, step past a port already in use
        srv, port = None, PORT
        for port in range(PORT, PORT + 12):
            try:
                srv = ThreadingHTTPServer((host, port), Handler)
                break
            except OSError:
                continue
        if srv is None:
            sys.exit(f"could not bind a port in {PORT}-{PORT + 11}")

    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    print(f"\n  ATP form running at {url}")
    if host in ("127.0.0.1", "localhost"):
        print("  Local only - nothing is reachable from outside this machine.")
    else:
        print(f"  Listening on {host}:{port} - put authentication in front of it.")
    print("  Press Ctrl-C to stop.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("  stopped")


if __name__ == "__main__":
    main()
