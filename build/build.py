#!/usr/bin/env python3
"""Build an ATP from a jurisdiction pack + an engagement file."""
import docx, json, sys, re, copy, os
from docx.oxml.ns import qn
from docx.shared import RGBColor, Twips
from docx.enum.text import WD_COLOR_INDEX
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def money(v, symbol="$"):
    q = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{symbol}{q:,.2f}"

def resolve(v):
    """A string like 'preset:milestones.20-40-40' loads presets/<name>.json."""
    if isinstance(v, str) and v.startswith("preset:"):
        return json.load(open(f"{ROOT}/presets/{v.split(':',1)[1]}.json"))
    return v

# Engagement types the one template can build. The type-specific wording lives in
# {{?type}} blocks inside template/atp-website.docx; sections 4 to 14 are shared.
TYPES = ("website", "web_app", "mobile_app", "web_mobile_app")

# Options that switch on extra clauses within a type, set in the engagement's scope
# ("online_store": true). Block names may be a type or an option: {{?online_store}}.
OPTIONS = {"online_store": ("website",)}      # option -> the types it applies to

# Types whose wording has been legally reviewed and can be issued. Anything else
# builds only with --draft, and the header says so on every page. Adding a type
# here is the record that its clauses were reviewed - do it in its own commit.
# A jurisdiction pack with its own template lists its own ("reviewed": [...]).
REVIEWED = {"website"}

def reviewed(jur):
    return set(jur.get("reviewed", REVIEWED))

# A placeholder the template or the jurisdiction pack leaves for a fact still to
# come, such as "[registration number – to confirm]". It is highlighted in the
# output, and a contract carrying one cannot be issued.
PLACEHOLDER = re.compile(r"\[[^\]]*to confirm[^\]]*\]")
DRAFT_MARK = "DRAFT FOR LEGAL REVIEW \u2013 NOT FOR ISSUE  |  "

# The noun the agreement uses for the thing being delivered. Override per engagement
# with a top-level "deliverable" if a project needs its own word.
DELIVERABLE = {
    "website":    "website",
    "web_app":    "web app",
    "mobile_app": "app",
    "web_mobile_app": "web and mobile app",
    "brand":      "brand identity",
}

SUBJECT = {
    "website":    "Website Design and Build",
    "web_app":    "Web App Design and Build",
    "mobile_app": "Mobile App Design and Build",
    "web_mobile_app": "Web and Mobile App Design and Build",
}

# What 3.10 and the developer-accounts item call the part that goes to the app
# stores: the whole deliverable for a mobile app, only the mobile part otherwise.
STORE_APP = {"web_mobile_app": "mobile app"}

# The list in section 2.2: a website lists pages, an app lists features.
SCOPE_LIST = {"website": "pages", "web_app": "features", "mobile_app": "features",
              "web_mobile_app": "features"}

# Types whose 2.3 names phones and operating systems, and whose app goes to the stores.
MOBILE_TYPES = ("mobile_app", "web_mobile_app")

DEFAULTS = {
    "terms.payment_days": 14,
    "hosting.note": "",
}

TYPE_DEFAULTS = {
    "website": {
        "scope.platform": "WordPress",
        "scope.exclusions": "copywriting (you supply the page copy), legal and compliance review, "
                            "SEO campaigns, and a client portal",
    },
    # no platform default for apps: the stack is a decision for every project
    "web_app": {
        "scope.exclusions": "copywriting (you supply the content), legal and compliance review, "
                            "data migration from existing systems, integrations not listed in "
                            "section 2.2, native mobile apps, and marketing or SEO campaigns",
    },
    "mobile_app": {
        "scope.exclusions": "copywriting (you supply the content), legal and compliance review, "
                            "data migration from existing systems, integrations not listed in "
                            "section 2.2, a web version of the app, app store optimisation, and "
                            "marketing campaigns",
    },
    "web_mobile_app": {
        "scope.exclusions": "copywriting (you supply the content), legal and compliance review, "
                            "data migration from existing systems, integrations not listed in "
                            "section 2.2, app store optimisation, and marketing or SEO campaigns",
    },
}

# Presets whose content only makes sense for one engagement type are named for it
# (inclusions.website, workplan.mobile-app-14week). Milestone splits are shared.
TYPED_PRESETS = ("inclusions", "pages", "features", "workplan")

def put(o, path, val):
    ks = path.split("."); cur = o
    for k in ks[:-1]: cur = cur.setdefault(k, {})
    cur.setdefault(ks[-1], val)

def preset_mismatches(eng):
    """Typed presets referenced by an engagement that belong to another type."""
    slug = str(eng.get("engagement_type", "")).replace("_", "-")
    refs = [eng["scope"].get(k) for k in ("inclusions", "pages", "features")]
    refs.append(eng.get("timeline", {}).get("tasks"))
    bad = []
    for ref in refs:
        if isinstance(ref, str) and ref.startswith("preset:"):
            name = ref.split(":", 1)[1]
            base = name.split("/")[-1]                  # lk/workplan.website-8week
            kind = base.split(".", 1)[0]
            if kind in TYPED_PRESETS and not base.startswith(f"{kind}.{slug}"):
                bad.append(name)
    return bad

def load(engagement_file):
    eng = json.load(open(engagement_file))
    jur = json.load(open(f"{ROOT}/jurisdictions/{eng['jurisdiction']}.json"))
    for k, v in {**DEFAULTS, **TYPE_DEFAULTS.get(eng.get("engagement_type"), {}),
                 **jur.get("defaults", {})}.items():
        put(eng, k, v)
    eng["_preset_mismatches"]  = preset_mismatches(eng)   # checked before resolve() erases the names
    eng["milestones"]          = resolve(eng["milestones"])
    for k in ("pages", "features", "inclusions"):
        if k in eng["scope"]:
            eng["scope"][k] = resolve(eng["scope"][k])
    eng["timeline"]["tasks"]   = resolve(eng["timeline"]["tasks"])
    if eng["scope"].get("online_store") and isinstance(eng["scope"].get("inclusions"), list):
        inc = eng["scope"]["inclusions"]        # the store goes in before the last item, which ends with '.'
        eng["scope"]["inclusions"] = inc[:-1] + [jur.get("store_inclusion", STORE_INCLUSION)] + inc[-1:]
    eng.setdefault("proposal", {}).setdefault("ref", eng["atp"]["ref"])          # defaults to the ATP ref
    subject = SUBJECT.get(eng.get("engagement_type"), "Design and Build")
    eng["atp"].setdefault("subject", f'{eng["client"]["short_name"]} \u2013 {subject}')
    return eng, jur


STORE_INCLUSION = ("an online store: your products set up with payments through your payment "
                   "provider, and order notifications;")

def options_on(eng):
    """The options switched on for this engagement, e.g. {'online_store'}."""
    return {o for o in OPTIONS if eng.get("scope", {}).get(o)}


_WEEK_WORDS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
               "eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,
               "fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,
               "nineteen":19,"twenty":20,"twenty-four":24,"twenty-six":26}

def weeks_in(text):
    """Largest week number mentioned in a string, as digits or as a word."""
    best = 0
    for n in re.findall(r"\d+", text or ""):
        best = max(best, int(n))
    for w, n in _WEEK_WORDS.items():
        if re.search(rf"\b{w}\b", (text or "").lower()):
            best = max(best, n)
    return best

# ---------------- validation ----------------
def validate(eng, jur):
    errs = []
    pct = sum(m["percent"] for m in eng["milestones"])
    if pct != 100:
        errs.append(f"milestone percentages sum to {pct}, not 100")
    for m in eng["milestones"]:                       # the Acentura trap
        stated = re.match(r"\s*(\d+)%", m["description"])
        if stated and int(stated.group(1)) != m["percent"]:
            errs.append(f"milestone description says {stated.group(1)}% but percent is {m['percent']}")
    # 11.0 invoices the final milestone on acceptance under 3.6, and 3.5 starts the
    # support clock there too. A final milestone "at launch" contradicts both.
    if eng["milestones"] and not re.search(r"\bacceptance\b", eng["milestones"][-1]["description"]):
        errs.append("the final milestone must be invoiced on acceptance - the acceptance, support "
                    "and delay clauses depend on it")
    if eng["fee"]["discount"] > eng["fee"]["standard"]:
        errs.append("discount exceeds standard price")
    elif eng["fee"]["standard"] - eng["fee"]["discount"] <= 0:
        errs.append("the price is $0 - enter the standard price excluding tax")
    # the work plan must fit inside the stated duration
    dur = weeks_in(eng.get("timeline", {}).get("duration", ""))
    plan = max([weeks_in(t[-1]) for t in eng.get("timeline", {}).get("tasks", []) if t] or [0])
    if plan and not dur and eng.get("timeline", {}).get("duration"):
        errs.append(f"cannot read a number of weeks from timeline.duration "
                    f"'{eng['timeline']['duration']}' - write it as 'Twelve weeks' or '12 weeks'")
    if dur and plan and plan > dur:
        errs.append(f"work plan runs to week {plan} but the timeline says {dur} weeks "
                    f"- pick a matching workplan preset, or change the duration")
    # A milestone that names a week must agree with the plan. 20-40-40 says 'on
    # acceptance (Week 8)', which contradicts a seven- or ten-week timeline.
    if plan:
        last = len(eng["milestones"])
        for i, ms in enumerate(eng["milestones"], 1):
            named = [int(n) for a, b in re.findall(r"\bweeks?\s+(\d+)(?:\s*[–-]\s*(\d+))?",
                                                  ms["description"], re.I) for n in (a, b) if n]
            if not named:
                continue
            wk = max(named)
            if wk > plan or (i == last and wk != plan):
                errs.append(f"payment milestone {i} says week {wk} but the timeline ends in week {plan} "
                            f"- choose a payment split that does not name weeks, or change the timeline")
    etype = eng.get("engagement_type")
    if etype not in TYPES:
        errs.append(f"engagement_type '{etype}' has no template (one of: {', '.join(TYPES)})")
        return errs
    if etype not in jur.get("types", TYPES):           # a country's template may not cover every type
        errs.append(f"the {jur['code']} template has no {etype} contract yet - it builds "
                    f"{', '.join(jur['types'])} only")
    for name in eng.get("_preset_mismatches", []):
        errs.append(f"preset '{name}' is not a {etype} preset - pick one named "
                    f"{name.split('.')[0]}.{etype.replace('_', '-')}...")
    # every field the contract prints: an empty one reads as 'To: - Acme' or 'dated .'
    required = ["project.name","client.legal_name",f"client.{jur.get('client_id', 'abn')}",
                "client.short_name","client.address",
                "client.contact_name","atp.ref","atp.date","proposal.ref","proposal.date",
                "scope.platform","timeline.duration"]
    if etype in MOBILE_TYPES:
        required.append("scope.devices")            # 2.3 names the phones and OS versions
    for opt in options_on(eng):
        if etype not in OPTIONS[opt]:
            errs.append(f"{opt} applies only to {', '.join(OPTIONS[opt])} contracts, not {etype}")
    for path in required:
        cur, ok = eng, True
        for k in path.split("."):
            if isinstance(cur, dict) and k in cur and cur[k] not in ("", None): cur = cur[k]
            else: ok = False; break
        if not ok: errs.append(f"missing or empty: {path}")
    listed = SCOPE_LIST[etype]
    if not eng["scope"].get(listed): errs.append(f"scope.{listed} is empty")
    # A row may carry a level: 1 is a subpage of the row above, 2 a subpage of that.
    # A level can only go one deeper than the row before it.
    prev = -1
    for i, row in enumerate(eng["scope"].get(listed) or []):
        level = row[2] if isinstance(row, (list, tuple)) and len(row) > 2 else 0
        if level not in (0, 1, 2):
            errs.append(f"{listed} row {i + 1} ('{row[0]}') has level {level} - use 0, 1 or 2")
            continue
        if level > prev + 1:
            errs.append(f"{listed} row {i + 1} ('{row[0]}') is a subpage with no "
                        f"{'page' if level == 1 else 'subpage'} above it")
        prev = level
    if not eng["scope"].get("inclusions"): errs.append("scope.inclusions is empty")
    if not eng["timeline"].get("tasks"): errs.append("timeline.tasks is empty")
    return errs

# ---------------- derived ----------------
def derive(eng, jur):
    rate = Decimal(str(jur["tax"]["rate"]))
    std  = Decimal(str(eng["fee"]["standard"]))
    disc = Decimal(str(eng["fee"]["discount"]))
    total = std - disc
    tax   = (total * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sym   = jur.get("currency_symbol", "$")
    cash  = lambda v: money(v, sym)             # $1,000.00 or LKR 1,000.00
    d = {
      "deliverable": eng.get("deliverable") or DELIVERABLE.get(eng.get("engagement_type"), "work"),
      "fee.standard": cash(std), "fee.discount": cash(disc),
      "fee.total": cash(total), "fee.tax": cash(tax), "fee.total_inc": cash(total+tax),
    }
    # "a website" but "an app" - the article has to follow the noun
    d["deliverable.article"] = "an" if d["deliverable"][:1].lower() in "aeiou" else "a"
    d["store_app"] = STORE_APP.get(eng.get("engagement_type"), d["deliverable"])
    # 2.3 lists what the client holds and pays for: photography, domain and hosting,
    # plus the app store accounts and a payment provider account where they apply
    held = 3 + (eng.get("engagement_type") in MOBILE_TYPES) + ("online_store" in options_on(eng))
    d["held.count"] = {3: "Three", 4: "Four", 5: "Five"}[held]

    tx, cl = jur["tax"]["name"], eng["client"]["short_name"]
    d["fee.headline"] = (
        f'The standard build price for this scope is {cash(std)} excluding {tx}. '
        f'{cl} receives a discount of {cash(disc)}, giving a total of {cash(total)} excluding {tx}.'
        if disc > 0 else
        f'The price for this scope is {cash(total)} excluding {tx}.')
    rows, run_ex = [], Decimal("0")
    for i,m in enumerate(eng["milestones"]):
        ex = (total * Decimal(str(m["percent"])) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if i == len(eng["milestones"])-1: ex = total - run_ex      # last absorbs rounding
        run_ex += ex
        inc = (ex * (1+rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append([str(i+1), m["description"], cash(ex), cash(inc)])
    assert run_ex == total, f"milestone amounts {run_ex} != total {total}"
    d["_milestone_rows"] = rows
    inc = eng["support"]["included"]
    d["support.included.period"]   = f'{inc["value"]} {inc["unit"]}'
    d["support.included.sentence"] = f'{inc["value"]} {inc["unit"]} of support'
    if "plan" in eng["support"]:                 # Sri Lankan contracts quote ongoing support separately
        d["support.plan.price"] = cash(eng["support"]["plan"]["price"])
    d["tax.rate_pct"] = f"{rate * 100:.1f}".rstrip("0").rstrip(".") + "%"
    return d

def flatten(prefix, obj, out):
    for k,v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict): flatten(key+".", v, out)
        elif isinstance(v, (str,int,float)): out[key] = str(v)
    return out

# ---------------- fill ----------------
def fill_text(doc, tokens):
    def do(p):
        for r in p.runs:
            for k,v in tokens.items():
                t = "{{"+k+"}}"
                if t in r.text: r.text = r.text.replace(t, v)
    def walk(container):
        for p in container.paragraphs: do(p)
        for t in container.tables:
            for row in t.rows:
                for c in row.cells: walk(c)
    walk(doc)
    for s in doc.sections:                      # headers and footers carry tokens too
        for part in (s.header, s.first_page_header, s.even_page_header,
                     s.footer, s.first_page_footer, s.even_page_footer):
            walk(part)

BLOCK_OPEN  = re.compile(r"^\{\{\?([\w|]+)\}\}$")
BLOCK_CLOSE = re.compile(r"^\{\{/([\w|]+)\}\}$")

def strip_blocks(doc, engagement_type, options=()):
    """{{?website}} ... {{/website}} keeps its contents only for that engagement type.

    A block can name several types: {{?web_app|mobile_app}} ... {{/web_app|mobile_app}}.
    Markers are always removed. Everything between them survives only when a name
    matches. A name that is not a known type is an error, not a silent cut - a typo
    like {{?mobileapp}} would otherwise drop the clause from every build.
    Runs before fill_rows, so a stripped table cannot shift table indices.
    """
    children = list(doc.element.body)
    drop, kept, cut, open_at, name = [], 0, 0, None, None
    for idx, el in enumerate(children):
        if el.tag != qn('w:p'):
            continue
        txt = "".join(t.text or "" for t in el.iter(qn('w:t'))).strip()
        m = BLOCK_OPEN.match(txt)
        if m:
            if open_at is not None:
                raise ValueError(f"nested conditional block {{{{?{m.group(1)}}}}} inside {{{{?{name}}}}}")
            unknown = [n for n in m.group(1).split("|") if n not in TYPES and n not in OPTIONS]
            if unknown:
                raise ValueError(f"conditional block {{{{?{m.group(1)}}}}} names unknown type(s) "
                                 f"{', '.join(unknown)} (known: {', '.join((*TYPES, *OPTIONS))})")
            open_at, name = idx, m.group(1)
            continue
        m = BLOCK_CLOSE.match(txt)
        if m:
            if open_at is None or m.group(1) != name:
                raise ValueError(f"unmatched {{{{/{m.group(1)}}}}}")
            span = children[open_at:idx + 1]
            if engagement_type in name.split("|") or set(options) & set(name.split("|")):
                drop += [span[0], span[-1]]; kept += 1
            else:
                drop += span; cut += 1
            open_at = name = None
    if open_at is not None:
        raise ValueError(f"unclosed conditional block {{{{?{name}}}}}")
    for el in drop:
        el.getparent().remove(el)
    return kept, cut

def find_table(doc, marker):
    """Locate a repeating table by its {{#marker}} rather than by index."""
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                if "{{#" + marker in c.text:
                    return t
    return None

def set_cell(t, r, c, v):
    p = t.rows[r].cells[c].paragraphs[0]
    if p.runs:
        p.runs[0].text = v
        for x in p.runs[1:]: x.text = ""
    else: p.add_run(v)

def indent_subpages(table, first, levels):
    """Show subpages under their page: indented, and led by an en dash."""
    for i, level in enumerate(levels):
        if not level:
            continue
        p = table.rows[first + i].cells[0].paragraphs[0]
        p.paragraph_format.left_indent = Twips(280 * level)
        if p.runs:
            p.runs[0].text = "\u2013 " + p.runs[0].text

def fill_rows(table, marker, data):
    """Clone the row carrying {{#marker...}} once per data item."""
    tpl_idx = None
    for i,row in enumerate(table.rows):
        if any("{{#"+marker in c.text for c in row.cells): tpl_idx = i; break
    if tpl_idx is None: return 0
    tpl_tr = copy.deepcopy(table.rows[tpl_idx]._tr)
    for n,item in enumerate(data):
        if n == 0: target = tpl_idx
        else:
            table.rows[tpl_idx+n-1]._tr.addnext(copy.deepcopy(tpl_tr)); target = tpl_idx+n
        for c,val in enumerate(item): set_cell(table, target, c, str(val))
    return len(data)

def flag_placeholders(doc):
    """Highlight every run holding a placeholder, and return the placeholders found."""
    found = []
    def walk(container):
        for p in container.paragraphs:
            for r in p.runs:
                hits = PLACEHOLDER.findall(r.text)
                if hits:
                    found.extend(hits)
                    r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        for t in container.tables:
            for row in t.rows:
                for c in row.cells: walk(c)
    walk(doc)
    for s in doc.sections:
        for part in (s.header, s.footer):
            walk(part)
    return found

def mark_draft(doc):
    """Put DRAFT_MARK at the front of the running header, in bold red, on every page."""
    marked = 0
    for s in doc.sections:
        for part in (s.header, s.first_page_header, s.even_page_header):
            for p in part.paragraphs:
                if "ATP & TERMS" in p.text and p.runs:
                    first = p.runs[0]._r
                    r = copy.deepcopy(first)
                    first.addprevious(r)
                    run = docx.text.run.Run(r, p)
                    run.text = DRAFT_MARK
                    run.bold = True
                    run.font.color.rgb = RGBColor(0xB3, 0x26, 0x1E)
                    marked += 1
    if not marked:
        raise ValueError("draft build, but no header paragraph found to mark it in")

def build(engagement_file, out_file, draft=False):
    eng, jur = load(engagement_file)
    errs = validate(eng, jur)
    etype = eng.get("engagement_type")
    if etype in TYPES and etype not in reviewed(jur) and not draft:
        errs.append(f"the {etype} clauses have not been legally reviewed, so this cannot be "
                    f"issued - build a review copy with --draft")
    if errs:
        print("VALIDATION FAILED"); [print("  -", e) for e in errs]; sys.exit(1)
    d = derive(eng, jur)

    tokens = {}
    flatten("", jur, tokens)                 # provider.*, governing_law, tax.name, ...
    flatten("", eng, tokens)                 # client.*, atp.*, scope.platform, terms.*
    tokens.update({k:v for k,v in d.items() if not k.startswith("_")})

    doc = docx.Document(f"{ROOT}/template/{jur.get('template', 'atp-website.docx')}")

    # conditional blocks BEFORE anything addresses a table
    kept, cut = strip_blocks(doc, eng.get("engagement_type"), options_on(eng))

    # repeating blocks, located by marker so a stripped table cannot shift indices
    listed = SCOPE_LIST[etype]
    listed_rows = eng["scope"][listed]
    levels = [r[2] if len(r) > 2 else 0 for r in listed_rows]
    for marker, data in ((listed,       [r[:2] for r in listed_rows]),
                         ("milestones", d["_milestone_rows"]),
                         ("tasks",      eng["timeline"]["tasks"])):
        t = find_table(doc, marker)
        if t is None:
            raise ValueError(f"template has no {{{{#{marker}}}}} table for a {etype} build")
        first = next(i for i, row in enumerate(t.rows) if any("{{#" + marker in c.text for c in row.cells))
        fill_rows(t, marker, data)
        if marker == listed:
            indent_subpages(t, first, levels)

    # inclusion bullets: clone the marker paragraph
    for p in doc.paragraphs:
        if "{{#inclusion}}" in p.text:
            anchor = p._p                       # advance the anchor, or clones stack in reverse
            for i, text in enumerate(eng["scope"]["inclusions"]):
                if i == 0:
                    tgt = p
                else:
                    clone = copy.deepcopy(p._p)
                    anchor.addnext(clone); anchor = clone
                    tgt = docx.text.paragraph.Paragraph(clone, p._parent)
                for r in tgt.runs: r.text = ""
                tgt.runs[0].text = "\u2022\u2003" + text
            break

    fill_text(doc, tokens)
    placeholders = flag_placeholders(doc)
    if etype not in reviewed(jur):
        mark_draft(doc)
    doc.save(out_file)

    leftover = set()
    chk = docx.Document(out_file)
    blob = "\n".join(p.text for p in chk.paragraphs) + "\n" + "\n".join(
        c.text for t in chk.tables for r in t.rows for c in r.cells)
    for s_ in chk.sections:                     # check headers/footers as well
        for part in (s_.header, s_.first_page_header, s_.footer, s_.first_page_footer):
            blob += "\n" + "\n".join(p.text for p in part.paragraphs)
    for m in re.findall(r"\{\{[^}]+\}\}", blob): leftover.add(m)

    # House style is the spaced en dash. Word's autocorrect turns " - " into an em
    # dash the moment anyone edits the template by hand, so catch it at the output,
    # which covers engagement data as well as the template.
    em = [ln.strip() for ln in blob.split("\n") if "\u2014" in ln]

    print(f"built -> {out_file}")
    if etype not in reviewed(jur):
        print(f"  DRAFT - the {etype} clauses are not legally reviewed. Marked in the header; not for issue.")
    print(f"  {listed} {len(eng['scope'][listed])} · milestones {len(d['_milestone_rows'])} · tasks {len(eng['timeline']['tasks'])}")
    opts = ", ".join(sorted(options_on(eng))) or "none"
    print(f"  type {eng.get('engagement_type')} · options {opts} · deliverable '{d['deliverable']}' · blocks kept {kept}, cut {cut}")
    print(f"  total {d['fee.total']} ex / {d['fee.total_inc']} inc {jur['tax']['name']}")
    print("  UNREPLACED TOKENS:", sorted(leftover) if leftover else "none")
    if placeholders:
        print(f"  PLACEHOLDERS ({len(placeholders)}, highlighted) - fill these before the contract is issued:")
        for ph in sorted(set(placeholders)):
            print(f"    {ph}")
    if em:
        print(f"  EM DASHES: {len(em)} \u2014 house style is the spaced en dash \u2013")
        for ln in em[:6]:
            i = ln.index("\u2014")
            print(f"    ...{ln[max(0, i-56):i+54]}...")
    return not leftover and not em and (draft or not placeholders)

if __name__ == "__main__":
    draft = "--draft" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--draft"]
    if len(args) != 2:
        sys.exit("usage: build.py <engagement.json> <out.docx> [--draft]")
    ok = build(args[0], args[1], draft=draft)
    sys.exit(0 if ok else 2)
