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
    """Plain text of a .docx or .pdf. Raises with a readable message otherwise."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        from docx import Document
        d = Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext == ".pdf":
        import fitz
        with fitz.open(path) as doc:
            return "\n".join(p.get_text() for p in doc)
    raise ValueError(f"unsupported file type '{ext}' - upload a .docx or .pdf")


def _hi(v):  return {"value": v, "confidence": "high"}
def _lo(v):  return {"value": v, "confidence": "low"}

# Money as Encyte proposals write it: "$5,500", "AUD 4,850", "AUD $2,650".
MONEY = r"(?:AUD\s*\$?|\$)\s?([\d,]+(?:\.\d{2})?)"

def _amount(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None

# After a label, an amount may carry no currency at all: "Standard price 5,500 + GST".
LABELLED_MONEY = r"(?:(?:AUD\s*\$?|\$)\s?([\d,]+(?:\.\d{2})?)|\b(\d{1,3}(?:,\d{3})+|\d{3,})(?=\s*\+\s*GST|\s+discount))"

def _labelled(flat, *labels):
    """Amount following the first of `labels` that has one. Labels are tried in
    order, most specific first, so 'final investment' wins over 'investment'."""
    for label in labels:
        m = re.search(rf"(?:{label})[^\n$\d]{{0,40}}?\n?[^\n$\d]{{0,20}}?{LABELLED_MONEY}", flat, re.I)
        if m:
            return _amount(m.group(1) or m.group(2))
    return None

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
    text = read_text(path)
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

    # --- dates written as 8 September 2026
    dates = re.findall(r"\b(\d{1,2} (?:%s) \d{4})\b" % "|".join(MONTHS), flat)
    if dates:
        out["proposal.date"] = (_hi if len(set(dates)) == 1 else _lo)(dates[0])
        if len(set(dates)) > 1:
            notes.append(f"{len(set(dates))} dates found - earliest-appearing used for the proposal date")

    # --- ABNs, ignoring your own
    abns = re.findall(r"\b(\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3})\b", flat)
    others = [a for a in abns if re.sub(r"\s", "", a) != own_abn]
    if others:
        out["client.abn"] = (_hi if len(set(others)) == 1 else _lo)(others[0])

    # --- client: "Prepared for" is where proposals name the client, sometimes
    # with the contact and their role first ("Rob, Founder, REKT Productions")
    prepared = _prepared_for(text)
    if prepared:
        parts = [p.strip() for p in prepared.split(",") if p.strip()]
        out["client.short_name"] = _lo(parts[-1])
        if len(parts) > 1 and re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}$", parts[0]):
            out["client.contact_name"] = _lo(parts[0])

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

    # --- pages. Guessing page rows from free text produced junk far more often
    # than pages ("Stated twice", sentence fragments), and it replaced the
    # standard list. Now a list like "8 pages - Home, About, Contact" is only
    # reported, for you to add with a purpose each.
    # A wrapped list continues on a line that starts in lower case ("In / practice");
    # a capital means the next line is something else, such as the price.
    m = re.search(r"\b(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
                  r"\s+pages?\s*[\u2013\u2014:-]\s*([^\n]+(?:(?-i:\n[a-z])[^\n]*)?)", text, re.I)
    if m:
        names = re.split(r",\s*|\s+and\s+", re.sub(r"\s+", " ", m.group(1)).strip(" ."))
        names = [n for n in names if 1 < len(n) < 40 and not re.search(r"[\d$]", n)][:20]
        if names:
            notes.append("pages named in the proposal: " + ", ".join(names)
                         + " - add each to the page list with its purpose")

    return {"fields": out, "notes": notes, "chars": len(text)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: extract.py <proposal.docx|proposal.pdf>")
    print(json.dumps(extract(sys.argv[1]), indent=1))
