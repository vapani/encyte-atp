#!/usr/bin/env python3
"""Build every contract the generator can make, and check each one.

    python3 qa/check_contracts.py

Every country x contract type x payment split, and websites with and without the
online store, built from the sample engagements. Each contract is checked for:
leftover tokens, placeholders and em dashes; doubled words and stray spaces;
section numbers in order; every "section X.Y" pointing at a section that exists;
milestones that add up to the fee, each the right percentage, with the tax right;
and the DRAFT marking only where the type is not approved.

A split that names a week the timeline never reaches (20-40-40 pays in week 8) is
refused for the longer app timelines. That refusal is expected, not a failure.
Writes nothing into the project. Exits 1 if anything fails.
"""
import copy, glob, json, os, re, subprocess, sys, tempfile
from decimal import Decimal
import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{ROOT}/build")
import build as builder                                    # noqa: E402

SAMPLES = {
    ("AU", "website"): "sample-example-co", ("AU", "web_app"): "sample-web-app",
    ("AU", "mobile_app"): "sample-mobile-app", ("AU", "web_mobile_app"): "sample-web-mobile-app",
    ("LK", "website"): "sample-lk-website", ("LK", "web_app"): "sample-lk-web-app",
    ("LK", "mobile_app"): "sample-lk-mobile-app", ("LK", "web_mobile_app"): "sample-lk-web-mobile-app",
}
PLAN = {"website": ("website-8week", "Eight weeks"), "web_app": ("web-app-12week", "Twelve weeks"),
        "mobile_app": ("mobile-app-14week", "Fourteen weeks"),
        "web_mobile_app": ("web-mobile-app-16week", "Sixteen weeks")}

LABEL = re.compile(r"^(\d+)\.(\d+)\s")                    # "3.6 User acceptance..." or "4.2 The first..."
REF = re.compile(r"\bsections?\s+((?:\d+(?:\.\d+)?[a-z]?)(?:(?:,\s*|\s+and\s+|\s+to\s+)\d+(?:\.\d+)?[a-z]?)*)")
WORDING = (  # (pattern, what it means), checked in paragraph text only
    (r"\b(\w+) \1\b", "doubled word"), (r"  +\S", "double space"),
    (r"\s[,.;:]", "space before punctuation"), (r"\ba (?=[aeioAEIO]\w)", "'a' before a vowel"),
)
LEFTOVERS = ((r"\{\{[^}]*\}\}", "token or block marker"), ("—", "em dash"),
             (r"to confirm\]", "placeholder"))


def doc_lines(path):
    """The body in order, paragraphs as text and table rows as cell lists, plus the header."""
    d = docx.Document(path)
    out = []
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            t = Paragraph(el, d).text
            if t.strip():
                out.append(("p", t.strip()))
        elif tag == "tbl":
            for r in Table(el, d).rows:
                cells = []
                for c in r.cells:
                    if not cells or cells[-1] != c.text.strip():
                        cells.append(c.text.strip())
                out.append(("row", cells))
    header = " ".join(p.text for s in d.sections for p in s.header.paragraphs)
    return out, header


def check(path, eng, jur, expect_draft):
    """Problems found in one built contract, as readable lines."""
    problems = []
    lines, header = doc_lines(path)
    text = "\n".join(t if k == "p" else " | ".join(t) for k, t in lines)
    prose = "\n".join(t for k, t in lines if k == "p")

    def near(src, m):
        return src[max(0, m.start() - 40):m.end() + 40].replace("\n", " / ")

    for pat, what in LEFTOVERS:
        for m in re.finditer(pat, text):
            problems.append(f"{what}: …{near(text, m)}…")
    for pat, what in WORDING:
        for m in re.finditer(pat, prose):
            if what == "doubled word" and (m.group(1).lower() in ("that", "had", "is") or m.group(1).isdigit()):
                continue
            problems.append(f"{what}: …{near(prose, m)}…")

    if ("DRAFT FOR LEGAL REVIEW" in header) != expect_draft:
        problems.append(f"the DRAFT marking is {'missing' if expect_draft else 'present'} in the header")

    tops, subs = [], {}
    for k, t in lines:
        m = LABEL.match(t) if k == "p" else None
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            (tops.append(a) if b == 0 else subs.setdefault(a, []).append(b))
    if tops != list(range(1, len(tops) + 1)):
        problems.append(f"top-level sections out of order: {tops}")
    for a, bs in subs.items():
        if a not in tops:
            problems.append(f"subsections {a}.x with no {a}.0 heading")
        if bs != list(range(1, len(bs) + 1)):
            problems.append(f"subsections of {a} skip or repeat: {bs}")
    known = {f"{a}.0" for a in tops} | {str(a) for a in tops} | {f"{a}.{b}" for a, bs in subs.items() for b in bs}
    for m in REF.finditer(text):
        for ref in re.split(r",\s*|\s+and\s+|\s+to\s+", m.group(1)):
            if ref not in known:
                problems.append(f"refers to section {ref}, which does not exist: …{near(text, m)}…")

    rate = Decimal(str(jur["tax"]["rate"]))
    sym = jur.get("currency_symbol", "$").strip()
    val = lambda s: Decimal(re.sub(r"[^\d.]", "", s))
    rows = [t for k, t in lines if k == "row" and len(t) == 4 and re.fullmatch(r"\d+", t[0])]
    total = next((t for k, t in lines if k == "row" and t and t[0] == "Total"), None)
    if not (rows and total):
        return problems + ["no milestone table found"]
    ex, inc = sum(val(r[2]) for r in rows), sum(val(r[3]) for r in rows)
    tot_ex, tot_inc = val(total[-2]), val(total[-1])
    fee = Decimal(str(eng["fee"]["standard"])) - Decimal(str(eng["fee"]["discount"]))
    if not (ex == tot_ex == fee):
        problems.append(f"milestones {ex}, total {tot_ex} and fee {fee} disagree")
    if abs(inc - tot_inc) > Decimal("0.02") * len(rows):
        problems.append(f"milestones including tax {inc} vs total {tot_inc}")
    if tot_inc != (tot_ex * (1 + rate)).quantize(Decimal("0.01")):
        problems.append(f"total including tax {tot_inc} is not {tot_ex} plus tax")
    for r in rows:
        if not (r[2].startswith(sym) and r[3].startswith(sym)):
            problems.append(f"milestone {r[0]} is not in {sym}: {r[2]}")
        p = re.match(r"(\d+)%", r[1])
        if p and (val(r[2]) - tot_ex * int(p.group(1)) / 100).copy_abs() > Decimal("0.02"):
            problems.append(f"milestone {r[0]} is not {p.group(1)}% of the fee: {r[2]}")
    return problems


def run(out):
    results = []
    for (country, etype), base in SAMPLES.items():
        eng0 = json.load(open(f"{ROOT}/engagements/{base}.json"))
        jur = json.load(open(f"{ROOT}/jurisdictions/{country}.json"))
        draft = etype not in builder.reviewed(jur)
        pre = f"{jur['presets']}/" if jur.get("presets") else ""
        splits = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{ROOT}/presets/{pre}milestones.*.json"))
        for split in splits:
            for store in ((False, True) if etype == "website" else (False,)):
                eng = copy.deepcopy(eng0)
                eng["milestones"] = f"preset:{pre}{split}"
                plan, dur = PLAN[etype]
                eng["timeline"] = {"duration": dur, "tasks": f"preset:{pre}workplan.{plan}"}
                if store:
                    eng["scope"]["online_store"] = True
                name = f"{country}-{etype}-{split.replace('milestones.', '')}{'-store' if store else ''}"
                path = f"{out}/{name}.json"
                json.dump(eng, open(path, "w"), ensure_ascii=False)
                cmd = [sys.executable, f"{ROOT}/build/build.py", path, f"{out}/{name}.docx"] + (["--draft"] if draft else [])
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode == 1:
                    errs = [l.strip(" -") for l in r.stdout.splitlines() if l.strip().startswith("-")]
                    expected = errs and all("says week" in e for e in errs)
                    results.append((name, "refused" if expected else "FAIL", errs))
                    continue
                probs = [] if r.returncode == 0 else [f"build exited {r.returncode}"]
                probs += check(f"{out}/{name}.docx", eng, jur, draft)
                results.append((name, "FAIL" if probs else "ok", probs))
    return results


def main():
    with tempfile.TemporaryDirectory() as out:
        res = run(out)
    for name, status, detail in res:
        if status == "refused":
            print(f"  refused  {name} (as expected: {detail[0].split(' - ')[0]})")
        elif status != "ok":
            print(f"  {status:8} {name}")
            for d in detail[:8]:
                print(f"           - {d}")
    ok, refused, failed = (sum(s == k for _, s, _ in res) for k in ("ok", "refused", "FAIL"))
    print(f"contracts: {len(res)} combinations, {ok} built cleanly, {refused} refused as expected, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
