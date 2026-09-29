#!/usr/bin/env python3
"""Pull likely engagement fields out of a proposal (.docx or .pdf).

This is pattern matching, not comprehension. It finds things that have a shape -
an ABN is eleven digits, a reference looks like 26-NGA-WD-062, money starts with
a dollar sign - and it guesses at the rest. It is wrong often enough that every
field it returns must be reviewed before a contract is built from it.

Each field comes back as {"value": ..., "confidence": "high"|"low"} so the form
can show you which ones to look at hardest.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS = ("January February March April May June July August September "
          "October November December").split()


def read_text(path):
    """(full text, cover text) of a .docx or .pdf. Raises with a readable message otherwise.

    The cover is the first page of a PDF, or the first 30 paragraphs of a .docx. It
    matters for dates: the body of a proposal is full of dates that are not its own.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        from docx import Document
        d = Document(path)
        paras = [p.text for p in d.paragraphs]
        parts = list(paras)
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts), "\n".join(paras[:30])
    if ext == ".pdf":
        import fitz
        with fitz.open(path) as doc:
            pages = [p.get_text() for p in doc]
        return "\n".join(pages), (pages[0] if pages else "")
    raise ValueError(f"unsupported file type '{ext}' - upload a .docx or .pdf")


def _hi(v):  return {"value": v, "confidence": "high"}
def _lo(v):  return {"value": v, "confidence": "low"}

# Money as Encyte proposals write it: "$5,500", "AUD 4,850", "AUD $2,650".
# A thousands group may carry a stray space after the comma - '$ 8, 946' in the
# Ciro's v1.1 proposal, left by a hand edit in Word - which used to read as $8.
NUMBER = r"\d{1,3}(?:,\s?\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?"
MONEY = rf"(?:AUD\s*\$?|\$)\s?({NUMBER})"

LOW_PRICE = 500      # below this, a build price read from a proposal is almost certainly a misread


def _amount(s):
    try:
        return float(re.sub(r"[,\s]", "", s))
    except ValueError:
        return None

# After a label, an amount may carry no currency at all: "Standard price 5,500 + GST".
LABELLED_MONEY = rf"(?:(?:AUD\s*\$?|\$)\s?({NUMBER})|\b(\d{{1,3}}(?:,\s?\d{{3}})+|\d{{3,}})(?=\s*\+\s*GST|\s+discount))"

def _labelled(flat, *labels):
    """Amount following the first of `labels` that has one. Labels are tried in
    order, most specific first, so 'final investment' wins over 'investment'."""
    for label in labels:
        m = re.search(rf"(?:{label})[^\n$\d]{{0,40}}?\n?[^\n$\d]{{0,20}}?{LABELLED_MONEY}", flat, re.I)
        if m:
            return _amount(m.group(1) or m.group(2))
    return None

_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
                "twenty": 20}

def _page_name(s):
    """A plausible page name: short, capitalised, no figures, not a heading about pages."""
    s = s.strip(" .;:")
    return (0 < len(s) <= 40 and len(s.split()) <= 5 and s[:1].isupper()
            and not re.search(r"[\d$|]|\bpages?\b", s, re.I))

def _page_list(text):
    """(page names, count the proposal states), from the three layouts Encyte uses:

        8 pages - Home, Expertise, How we work, ...           (NGA)
        Page scope - 9 pages / Home - Our Story - Contact / ...  (Smiles 4 Miles)
        Up to 8 core pages ... A likely core set is Home, ...  (REKT)
    """
    count_re = r"\b(?:up to\s+)?(\d{1,2}|%s)\s+(?:core\s+|main\s+)?pages\b" % "|".join(_COUNT_WORDS)
    # Every count in the document, scope counts first. Audit text quotes the
    # current site's pages too ("five of the seven pages ... have no ...").
    counts = []
    for line in text.split("\n"):
        for c in re.finditer(count_re, line, re.I):
            w = c.group(1).lower()
            n = int(w) if w.isdigit() else _COUNT_WORDS[w]
            scope = bool(re.search(r"up to|core|main|page scope", line, re.I)) or not line[:c.start()].strip(" ·-")
            counts.append((not scope, n))
    counts = [n for _, n in sorted(counts, key=lambda t: t[0])]
    stated = counts[0] if counts else None

    candidates = []
    lines = [l.strip() for l in text.split("\n")]
    for i, line in enumerate(lines):
        c = re.search(count_re, line, re.I)
        if not c:
            continue
        tail = line[c.end():]
        same = re.match(r"\s*[\u2013\u2014:\-]\s*(.+)$", tail)
        if same:                                   # the list follows on the same line
            body = same.group(1)
            if i + 1 < len(lines) and lines[i + 1][:1].islower():   # wrapped: "In / practice"
                body += " " + lines[i + 1]
            items = re.split(r",\s*|\s+and\s+|\s*\u00b7\s*", body.strip(" ."))
        else:                                      # the list runs down the following lines
            items = []
            for nxt in lines[i + 1:i + 8]:
                parts = [p for p in re.split(r"\s*\u00b7\s*|,\s*", nxt) if p]
                if not parts or not all(_page_name(p) for p in parts):
                    break
                items += parts
        items = [re.sub(r"^and\s+", "", p).strip(" .") for p in items]
        if items and all(_page_name(p) for p in items):
            candidates.append(items)

    flat = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"(?:core set is|pages are|pages include|sitemap (?:is|includes))\s+(.+?)\.", flat, re.I):
        items = [re.sub(r"^and\s+", "", p).strip() for p in re.split(r",\s*|\s+and\s+", m.group(1))]
        items = [p for p in items if p]
        if items and all(_page_name(p) for p in items):
            candidates.append(items)

    for n in counts:                               # a list that matches a stated count wins,
        for items in candidates:                   # scope counts tried first
            if len(items) == n:
                return items, n
    best = max(candidates, key=len) if candidates else []
    return best, stated


def _prepared_for(text):
    """The client named on the cover by 'Prepared for', joined into one line.

    Covers lay this out three ways, all seen in Encyte proposals:
        Prepared for / Rob, Founder, REKT / Productions      (REKT)
        Prepared by Encyte for / Smiles 4 Miles              (Smiles 4 Miles, Sep)
        Prepared by Encyte / for Smiles 4 Miles              (Smiles 4 Miles, Aug)
    or all on one line. The contact sometimes comes first ('Rob, Founder, ...').
    Stops at a date, a reference, a URL, the next 'Prepared by', or a line
    that reads like a sentence.
    """
    def stop(line):
        return (not line or re.match(r"prepared\b", line, re.I)
                or re.search(r"\b(?:%s)\b|\d{2}-[A-Z0-9]+-|www|W W W|\d{4}" % "|".join(MONTHS), line)
                or len(line.split()) > 5 or line.endswith("."))

    lines = [l.strip() for l in text.split("\n")]
    for i, l in enumerate(lines):
        if not re.match(r"prepared\b", l, re.I):
            continue
        rest = lines[i + 1:i + 4]
        m = re.search(r"\bfor\b\s*:?\s*(.*)$", l, re.I)
        if m:                                           # 'for' is on this line
            first = m.group(1).strip()
        elif rest and re.match(r"for\b", rest[0], re.I):  # 'for' starts the next line
            first, rest = re.sub(r"^for\b\s*:?\s*", "", rest[0], flags=re.I).strip(), rest[1:]
        else:
            continue
        block = [first] if first else []
        for nxt in rest:
            if stop(nxt):
                break
            block.append(nxt)
        if block:
            return " ".join(block)
    return None


def extract(path):
    text, cover = read_text(path)
    flat = re.sub(r"[ \t]+", " ", text)
    out, notes = {}, []

    provider = json.load(open(f"{ROOT}/jurisdictions/AU.json"))["provider"]
    own_abn = re.sub(r"\s", "", provider["abn"])
    own_name = provider["legal_name"].lower()

    # --- reference, e.g. 26-NGA-WD-062
    refs = re.findall(r"\b(\d{2}-[A-Z0-9]{2,8}-[A-Z]{2}-\d{2,4})\b", flat)
    if refs:
        out["proposal.ref"] = _hi(refs[0])
        out["atp.ref"] = _lo(refs[0])          # usually the same series, often not identical
        if len(set(refs)) > 1:
            notes.append(f"several references found ({', '.join(sorted(set(refs)))}) - first used")

    # --- the proposal date, written as 8 September 2026. Only the cover, or a date
    # labelled 'dated', counts: the body quotes other dates - the Ciro's proposal
    # cites a 19 June 2026 blog post on the client's current site.
    month = "|".join(MONTHS)
    full = r"\d{1,2} (?:%s) \d{4}" % month
    on_cover = re.findall(rf"\b({full})\b", re.sub(r"[ \t]+", " ", cover))
    labelled = re.search(rf"\bdated\s+({full})\b", flat)
    if on_cover:
        out["proposal.date"] = (_hi if len(set(on_cover)) == 1 else _lo)(on_cover[0])
    elif labelled:
        out["proposal.date"] = _lo(labelled.group(1))
    else:
        m = re.search(rf"\b((?:{month}) \d{{4}})\b", cover)
        notes.append(f"the cover is dated only '{m.group(1)}' - enter the day the proposal was issued"
                     if m else "no proposal date found - enter the date on the proposal")

    # --- ABNs, ignoring your own
    abns = re.findall(r"\b(\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3})\b", flat)
    others = [a for a in abns if re.sub(r"\s", "", a) != own_abn]
    if others:
        out["client.abn"] = (_hi if len(set(others)) == 1 else _lo)(others[0])

    # --- client: "Prepared for" is where proposals name the client, sometimes
    # with the contact and their role first ("Rob, Founder, REKT Productions")
    prepared = _prepared_for(text)
    if prepared:
        # 'Rob, Founder, REKT Productions' puts the client after a role;
        # 'Ciro's Cakes & Biscuits, Noble Park' puts it first, then the suburb.
        parts = [p.strip() for p in prepared.split(",") if p.strip()]
        ROLE = (r"\b(?:founder|co-founder|director|owner|ceo|coo|cfo|cmo|chief|manager|head|"
                r"principal|partner|president|chair|lead|coordinator|officer|executive)\b")
        role_at = next((i for i, p in enumerate(parts) if i and re.search(ROLE, p, re.I)), None)
        if role_at is not None and role_at + 1 < len(parts):
            out["client.short_name"] = _lo(", ".join(parts[role_at + 1:]))
            if re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}$", parts[0]):
                out["client.contact_name"] = _lo(parts[0])
        else:
            out["client.short_name"] = _lo(parts[0])

    # --- client legal name: a company/trust that is not you. Always a guess: a
    # wrong legal name in a signed contract is worse than an empty field.
    LABEL = r"^(?:client|prepared (?:by \S+ )?for|for|to|attention|company|entity)\s*:?\s+"
    ents = re.findall(r"\b([A-Z][A-Za-z0-9&.,'\- ]{2,60}?(?:Pty Ltd|Pty\. Ltd\.|Limited|Ltd|Trust))\b", flat)
    cands = []
    for e in ents:
        e = re.sub(LABEL, "", e.strip(" ,."), flags=re.I)
        if own_name.split()[0] in e.lower():
            continue
        if e.lower() not in [c.lower() for c in cands]:
            cands.append(e)
    if cands:
        out["client.legal_name"] = _lo(cands[0])
        if "client.short_name" not in out:
            out["client.short_name"] = _lo(re.split(r"\s+(?:Pty|Limited|Ltd)\b", cands[0])[0].strip())
        if len(cands) > 1:
            notes.append(f"possible client names: {', '.join(cands[:4])}")
    notes.append("the client's legal name, ABN and address are rarely in a proposal - "
                 "check them against ABN Lookup (abr.business.gov.au) before building")

    # --- money. Proposals state a standard price and what the client pays after
    # a discount; the form wants the standard price and the discount.
    standard = _labelled(flat, r"standard (?:build )?(?:price|investment)(?: for this scope)?")
    final = _labelled(flat, r"final investment|your investment|(?<!standard )\binvestment\b")
    discount = _labelled(flat, r"discount[^\n$\d]{0,20}?less", r"less a")
    if standard and final and final < standard:
        out["fee.standard"] = _lo(standard)
        out["fee.discount"] = _lo(standard - final)
        if discount and abs(discount - (standard - final)) > 0.5:
            notes.append(f"the stated discount ({discount:,.0f}) does not equal standard less "
                         f"final price ({standard - final:,.0f}) - check which is right")
        notes.append(f"price read as {standard:,.0f} standard less {standard - final:,.0f} "
                     f"discount = {final:,.0f} excluding GST - check it against the proposal")
    elif standard or final:
        out["fee.standard"] = _lo(standard or final)
        notes.append(f"price read as {standard or final:,.0f} excluding GST, with no discount "
                     f"found - check it against the proposal")
    else:
        amounts = [a for a in (_amount(m) for m in re.findall(MONEY, flat)) if a and a >= 500]
        if amounts:
            out["fee.standard"] = _lo(max(amounts))
            notes.append("price is the largest dollar figure in the document - check it is the "
                         "build price excluding GST, not a total including GST")
    price = out.get("fee.standard", {}).get("value")
    if price is not None and price - out.get("fee.discount", {}).get("value", 0) < LOW_PRICE:
        notes.append(f"the price read as {price:,.0f} is unusually low for a build - the figure may be "
                     f"split or mistyped in the proposal, so enter it by hand")
    # An allowance inside the investment (plugins, licences) is an expense under
    # clause 5.0, which the ATP charges at cost on top of the fee.
    m = re.search(rf"([^\n]*allowance[^\n]*)\n?[^\n$\d]{{0,20}}?{MONEY}", flat, re.I)
    if m and "fee.standard" in out:
        notes.append(f"the investment includes '{m.group(1).strip()}' of {_amount(m.group(2)):,.0f} - "
                     f"clause 5.0 charges plugins and licences at cost on top of the fee, so decide "
                     f"whether the ATP fee should leave the allowance out")

    # --- duration
    m = re.search(r"\b(?:(\d{1,2})|(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))"
                  r"[\s-]+weeks?\b", flat, re.I)
    if m:
        word = m.group(2)
        out["timeline.duration"] = _hi(f"{word.capitalize()} weeks" if word else f"{m.group(1)} weeks")

    # --- platform
    for plat in ("WordPress", "Webflow", "Shopify", "Squarespace"):
        if re.search(rf"\b{plat}\b", flat, re.I):
            out["scope.platform"] = _hi(plat)
            break

    # --- contact: a person's name after "Attention:" or "Dear", unless "Prepared
    # for" already named one. A bare "to" matched phrases like "to Premium Production".
    if "client.contact_name" not in out:
        m = re.search(r"(?:\battention\s*:?|\bdear)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", flat)
        if m:
            out["client.contact_name"] = _lo(m.group(1))

    # --- pages. Only a list that matches the count the proposal states fills the
    # page rows; anything less is reported in the notes. Guessing rows from free
    # text ("Stated twice", sentence fragments) used to replace the standard list.
    names, stated = _page_list(text)
    if names and stated and len(names) == stated:
        out["scope.pages"] = _lo([[n, ""] for n in names])
        notes.append(f"{stated} pages read from the proposal - write a purpose for each, "
                     f"since the purpose column is part of the contract's scope")
    elif names:
        found = f"found {len(names)} of {stated}" if stated else f"found {len(names)}"
        notes.append(f"pages named in the proposal ({found}): " + ", ".join(names)
                     + " - add them to the page list with a purpose each")

    return {"fields": out, "notes": notes, "chars": len(text)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: extract.py <proposal.docx|proposal.pdf>")
    print(json.dumps(extract(sys.argv[1]), indent=1))
