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

# Money as Encyte proposals write it: "$5,500", "AUD 4,850", "AUD $2,650", and in
# Sri Lanka "LKR 510,900".
# A thousands group may carry a stray space after the comma - '$ 8, 946' in the
# Ciro's v1.1 proposal, left by a hand edit in Word - which used to read as $8.
NUMBER = r"\d{1,3}(?:,\s?\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?"
CURRENCY = r"(?:AUD\s*\$?|LKR\s*|\$)"
MONEY = rf"{CURRENCY}\s?({NUMBER})"

# Below this, a build price read from a proposal is almost certainly a misread.
LOW_PRICE = {"AU": 500, "LK": 50000}
TAX = {"AU": "GST", "LK": "SSCL"}

def _amount(s):
    try:
        return float(re.sub(r"[,\s]", "", s))
    except ValueError:
        return None

# After a label, an amount may carry no currency at all: "Standard price 5,500 + GST".
LABELLED_MONEY = rf"(?:{CURRENCY}\s?({NUMBER})|\b(\d{{1,3}}(?:,\s?\d{{3}})+|\d{{3,}})(?=\s*\+\s*(?:GST|SSCL)|\s+discount))"

def _labelled(flat, *labels):
    """Amount following the first of `labels` that has one. Labels are tried in
    order, most specific first, so 'final investment' wins over 'investment'."""
    for label in labels:
        m = re.search(rf"(?:{label})[^\n$\d]{{0,40}}?\n?[^\n$\d]{{0,20}}?{LABELLED_MONEY}", flat, re.I)
        if m:
            return _amount(m.group(1) or m.group(2))
    return None

def _country(flat):
    """'LK' for a Sri Lankan proposal, else None (Australia is the default).

    Sri Lankan proposals price in LKR and add SSCL. Counting currencies rather than
    looking for 'Colombo' matters: MILK quotes hosting in USD, and an Australian
    proposal can mention the Colombo team.
    """
    lkr = len(re.findall(r"\bLKR\b", flat))
    aud = len(re.findall(r"\bAUD\b|\$\s?\d|\bGST\b", flat))
    return "LK" if lkr and (lkr >= aud or re.search(r"\bSSCL\b", flat)) else None


def _sscl_total(flat):
    """(price excluding SSCL, SSCL) from a 'Total investment' that includes it, or None.

    The Colombo Seven Gin proposal gives only milestone amounts, 'SSCL 2.5% 19,875.00'
    and 'Total investment 100% 814,875.00'. The two only count when the levy really is
    2.5% of what is left, so an unrelated total cannot be mistaken for one.
    """
    sscl = re.search(rf"\bSSCL\s*\(?2\.5\s?%\)?\s*\n?\s*(?:LKR\s*)?({NUMBER})", flat)
    total = re.search(rf"total investment\s*\n?\s*(?:\d{{1,3}}\s?%\s*\n?\s*)?(?:LKR\s*)?({NUMBER})", flat, re.I)
    if not (sscl and total):
        return None
    levy, gross = _amount(sscl.group(1)), _amount(total.group(1))
    if levy and gross and gross > levy and abs((gross - levy) * 0.025 - levy) <= 1:
        return gross - levy, levy
    return None


def _split(flat):
    """The payment split as percentages, e.g. [40, 30, 30], or None.

    Milestone amounts follow their percentage: '40% — LKR 204,360.00' in MILK, and a
    table column '40% | 318,000.00' in Colombo Seven Gin. The first run of two to four
    such percentages that adds up to exactly 100 is the split.
    """
    pcts = [int(m) for m in re.findall(rf"(?<!\d)(\d{{2}})\s?%\s*(?:[—–-]\s*)?\n?\s*(?:LKR\s*|\$)?(?:{NUMBER})",
                                        flat)]
    for i in range(len(pcts)):
        for n in (2, 3, 4):
            run = pcts[i:i + n]
            if len(run) == n and sum(run) == 100 and min(run) >= 10:
                return run
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


def _contract_type(text):
    """Suggest website / web_app / mobile_app from how the proposal talks, or None.

    Measured on Encyte proposals: website proposals say 'website' 2-32 times and
    'platform'/'dashboard' at most 5; the Business Marketplace web app proposal says
    'platform', 'portal' or 'dashboard' 38 times against 'website' 3. Only a clear
    lead counts - anything close is left for you to choose.
    """
    count = lambda pat: len(re.findall(pat, text, re.I))
    mobile = count(r"\b(?:ios|android|app store|google play|mobile app)\b")
    webapp = count(r"\b(?:web app|web application|platform|portal|dashboards?|saas)\b")
    website = count(r"\bwebsites?\b")
    both = re.search(r"\b(?:mobile and web|web and mobile) app(?:lication)?s?\b", text, re.I)
    if both:
        return "web_mobile_app", f"it describes a '{both.group(0)}'"
    if mobile >= 3 and mobile > website:
        return "mobile_app", f"it mentions iOS, Android or the app stores {mobile} times"
    if webapp >= 10 and webapp > 2 * website:
        return "web_app", (f"it talks about a platform, portal or dashboards {webapp} times "
                           f"and a website {website}")
    if website >= 2 and website > webapp:
        return "website", None
    return None, None


STRUCTURE_LABEL = re.compile(r"^(?:(?:store|site|website|page)\s+(?:structure|map)|sitemap|pages(?:\s+included)?)$", re.I)

def _split_item(t):
    """'Collection pages (migrated from Shopify)' or 'Blog — book recommendations'
    -> [name, purpose]; a bare name gets an empty purpose for you to write."""
    t = t.strip(" .;")
    m = re.match(r"^(.*?)\s*\((.+)\)$", t) or re.match(r"^(.*?)\s+[—–-]\s+(.+)$", t)
    if not m:
        return [t, ""]
    purpose = m.group(2).strip()
    return [m.group(1).strip(), purpose[:1].upper() + purpose[1:]]

def _structure_list(path):
    """Pages listed beside a 'Store structure' / 'Site map' / 'Pages' label, as
    (level, text) - level 1 for an indented line, which is how subpages appear.

    MILK's scope slide is a two-column table: labels on the left, what each covers
    on the right. As plain text the next label runs straight on from the last
    page, so this reads positions: a right-hand line belongs to the nearest label
    at or just below it (a label sits level with the middle of its lines).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        from docx import Document
        for table in Document(path).tables:
            for row in table.rows:
                cells = row.cells
                if len(cells) >= 2 and STRUCTURE_LABEL.match(cells[0].text.strip()):
                    items = []
                    for pgh in cells[1].paragraphs:
                        t = pgh.text.strip()
                        if not t:
                            continue
                        indent = pgh.paragraph_format.left_indent
                        level = 1 if (indent and indent > 0) or re.match(r"^[–—\-•]\s", t) else 0
                        items.append((level, re.sub(r"^[–—\-•]\s+", "", t)))
                    if len(items) >= 2:
                        return items
        return []
    if ext != ".pdf":
        return []
    import fitz
    with fitz.open(path) as doc:
        for page in doc:
            lines = []
            for b in page.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(sp["text"] for sp in l["spans"]).strip()
                    if t:
                        lines.append((l["bbox"][0], l["bbox"][1], l["bbox"][2], t))
            for lx0, ly0, lx1, lt in lines:
                if not STRUCTURE_LABEL.match(lt):
                    continue
                labels = sorted(y for x0, y, x1, t in lines if abs(x0 - lx0) < 8)   # the left column
                right = sorted((y, x0, t) for x0, y, x1, t in lines
                               if x0 > lx1 + 40 and x0 < page.rect.width * 0.9)
                mine = [(y, x0, t) for y, x0, t in right
                        if max([ly for ly in labels if ly <= y + 15] or [None]) == ly0]
                if len(mine) < 2:
                    continue
                left = min(x0 for _, x0, _ in mine)
                items = []
                for y, x0, t in mine:
                    if items and t[:1].islower():               # a wrapped line continues the one above
                        items[-1] = (items[-1][0], items[-1][1] + " " + t)
                    else:
                        items.append((1 if x0 > left + 8 else 0, t))
                return items
    return []

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
        m = re.search(r"\bfor\b\s*[:|]?\s*(.*)$", l, re.I)   # 'Prepared for | X' is a Word table row
        if m:                                           # 'for' is on this line
            first = m.group(1).strip()
        elif rest and re.match(r"for\b", rest[0], re.I):  # 'for' starts the next line
            first, rest = re.sub(r"^for\b\s*[:|]?\s*", "", rest[0], flags=re.I).strip(), rest[1:]
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
    # A proposal data file carries the exact values; nothing needs reading from the text.
    if path.lower().endswith(".json"):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import proposal_data
        return proposal_data.read(path)
    text, cover = read_text(path)
    flat = re.sub(r"[ \t]+", " ", text)
    out, notes = {}, []

    country = _country(flat) or "AU"
    tax = TAX[country]
    if country == "LK":
        out["jurisdiction"] = _lo("LK")
        notes.append("this is a Sri Lankan proposal (prices in LKR), so the contract is set to "
                     "Sri Lanka: Encyte (Pvt) Ltd, in LKR with SSCL - check it")
    provider = json.load(open(f"{ROOT}/jurisdictions/{country}.json"))["provider"]
    own_abn = re.sub(r"\s", "", provider.get("abn", ""))
    own_name = provider["legal_name"].lower()

    # --- reference, e.g. 26-NGA-WD-062
    refs = re.findall(r"\b(\d{2}-[A-Z0-9]{2,8}-[A-Z]{2}-\d{2,4})\b", flat)
    if refs:
        out["proposal.ref"] = _hi(refs[0])
        out["atp.ref"] = _lo(refs[0])          # usually the same series, often not identical
        if len(set(refs)) > 1:
            notes.append(f"several references found ({', '.join(sorted(set(refs)))}) - first used")

    # --- what kind of contract. Only an app suggestion gets a note: website is the default.
    kind, why = _contract_type(text)
    if kind:
        out["engagement_type"] = _lo(kind)
        if why:
            label = {"web_app": "a web app", "mobile_app": "a mobile app",
                     "web_mobile_app": "a web and mobile app"}[kind]
            notes.append(f"this looks like {label} proposal - {why} - so the contract type is set to "
                         f"{label[2:] if label.startswith('a ') else label}. Check it")

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
    abns = re.findall(r"\b(\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3})\b", flat) if country == "AU" else []
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
    ents = re.findall(r"\b([A-Z][A-Za-z0-9&.,'\- ]{2,60}?(?:\((?:Pvt|Private)\) (?:Ltd|Limited)|"
                      r"Pty Ltd|Pty\. Ltd\.|Limited|Ltd|Trust|PLC))(?:\b|(?<=\)))", flat)
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
                 "check them against ABN Lookup (abr.business.gov.au) before building"
                 if country == "AU" else
                 "the client's legal name, company registration number and address are rarely in "
                 "a proposal - get them from the client before building")

    # --- money. Proposals state a standard price and what the client pays after
    # a discount; the form wants the standard price and the discount.
    standard = _labelled(flat, r"standard (?:build )?(?:price|investment|fee)(?: for this scope)?")
    final = _labelled(flat, r"net (?:project )?fee", r"subtotal before tax",
                      r"final investment|your investment|(?<!standard )\binvestment\b")
    discount = _labelled(flat, r"discount[^\n$\d]{0,20}?less", r"less a")
    if standard and final and final < standard:
        out["fee.standard"] = _lo(standard)
        out["fee.discount"] = _lo(standard - final)
        if discount and abs(discount - (standard - final)) > 0.5:
            notes.append(f"the stated discount ({discount:,.0f}) does not equal standard less "
                         f"final price ({standard - final:,.0f}) - check which is right")
        notes.append(f"price read as {standard:,.0f} standard less {standard - final:,.0f} "
                     f"discount = {final:,.0f} excluding {tax} - check it against the proposal")
    elif standard or final:
        out["fee.standard"] = _lo(standard or final)
        notes.append(f"price read as {standard or final:,.0f} excluding {tax}, with no discount "
                     f"found - check it against the proposal")
    elif country == "LK" and _sscl_total(flat):
        net, levy = _sscl_total(flat)
        out["fee.standard"] = _lo(net)
        notes.append(f"price read as {net:,.2f} excluding SSCL: the total investment less the "
                     f"SSCL of {levy:,.2f} - check it against the proposal")
    else:
        amounts = [a for a in (_amount(m) for m in re.findall(MONEY, flat)) if a and a >= 500]
        if amounts:
            out["fee.standard"] = _lo(max(amounts))
            notes.append(f"price is the largest {'LKR' if country == 'LK' else 'dollar'} figure in the "
                         f"document - check it is the build price excluding {tax}, not a total "
                         f"including {tax}")
    price = out.get("fee.standard", {}).get("value")
    if price is not None and price - out.get("fee.discount", {}).get("value", 0) < LOW_PRICE[country]:
        notes.append(f"the price read as {price:,.0f} is unusually low for a build - the figure may be "
                     f"split or mistyped in the proposal, so enter it by hand")
    # An allowance inside the investment (plugins, licences) is an expense under
    # clause 5.0, which the ATP charges at cost on top of the fee.
    m = re.search(rf"([^\n]*allowance[^\n]*)\n?[^\n$\d]{{0,20}}?{MONEY}", flat, re.I)
    if m and "fee.standard" in out:
        notes.append(f"the investment includes '{m.group(1).strip()}' of {_amount(m.group(2)):,.0f} - "
                     f"clause 5.0 charges plugins and licences at cost on top of the fee, so decide "
                     f"whether the ATP fee should leave the allowance out")

    # --- payment split. Sri Lankan jobs vary it (MILK 40-30-30, Colombo Seven Gin
    # 40-40-20), so it is read from the proposal and matched to a standard split.
    split = _split(flat) if country == "LK" else None
    if split:
        name = "lk/milestones." + "-".join(map(str, split))
        if os.path.exists(f"{ROOT}/presets/{name}.json"):
            out["milestones"] = _lo(name)
        else:
            notes.append(f"the proposal splits payments {'-'.join(map(str, split))}, which is not a "
                         f"standard split - pick the nearest, then edit the Word file")

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
    # A list under a 'Store structure' / 'Site map' / 'Pages' label is read first:
    # the label says what it is, so no stated count is needed to trust it.
    structured = _structure_list(path)
    names, stated = ([], None) if structured else _page_list(text)
    if structured:
        out["scope.pages"] = _lo([_split_item(t) + ([level] if level else []) for level, t in structured])
        subs = sum(1 for level, _ in structured if level)
        notes.append(f"{len(structured)} pages read from the proposal's page list"
                     + (f", {subs} of them indented like subpages" if subs else "")
                     + " - write a purpose wherever one is missing")
    elif names and stated and len(names) == stated:
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
