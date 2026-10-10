#!/usr/bin/env python3
"""Read a proposal data file: the exact values a proposal was built from.

The proposal generator saves one next to each proposal ("26-NGA-WD-062 - proposal
data.json"). Dropping it on the form fills every field it carries exactly, so nothing
is guessed from the PDF. The format is described in docs/proposal-data-file.md.

    python3 build/proposal_data.py <file.json>      # print what the form would fill

Returns the same shape as extract.extract(): {"fields": {key: {"value", "confidence"}},
"notes": [...]}, with every value it read marked high confidence.
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import splits                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMAT, VERSION = "encyte-proposal-data", 1

TYPES = ("website", "web_app", "mobile_app", "web_mobile_app")
CURRENCY = {"AU": "AUD", "LK": "LKR"}
WHO = {"encyte": "P", "client": "C", "both": "B", "encyte / client": "B"}
WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
         9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen",
         15: "Fifteen", 16: "Sixteen", 17: "Seventeen", 18: "Eighteen", 19: "Nineteen",
         20: "Twenty", 24: "Twenty-four", 26: "Twenty-six"}
DATE = re.compile(r"^\d{1,2} (January|February|March|April|May|June|July|August|September|October|"
                  r"November|December) \d{4}$")
REF = re.compile(r"^\d{2}-[A-Z0-9]{2,8}-[A-Z]{2}-\d{2,4}$")


class DataFileError(ValueError):
    """The file is not a proposal data file the form can use."""


def _hi(v):
    return {"value": v, "confidence": "high"}


def is_data_file(path):
    return path.lower().endswith(".json")


def split_preset(country, percents):
    """The payment split preset with these percentages, e.g. [30, 40, 30] -> 'lk/milestones.30-40-30'."""
    jur = json.load(open(f"{ROOT}/jurisdictions/{country}.json"))
    folder = f"{jur['presets']}/" if jur.get("presets") else ""
    for path in sorted(glob.glob(f"{ROOT}/presets/{folder}milestones.*.json")):
        if [m["percent"] for m in json.load(open(path))] == list(percents):
            return folder + os.path.basename(path)[:-5]
    return None


def read(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DataFileError(f"this is not a readable data file ({e})")
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise DataFileError("this .json is not a proposal data file - it needs \"format\": "
                            f"\"{FORMAT}\" (see docs/proposal-data-file.md)")
    if d.get("version") != VERSION:
        raise DataFileError(f"this data file is version {d.get('version')}; the form reads version {VERSION}")

    out, notes = {}, []
    country = d.get("country")
    if country not in CURRENCY:
        raise DataFileError(f"the data file's country is {country!r} - it must be AU or LK")
    jur = json.load(open(f"{ROOT}/jurisdictions/{country}.json"))
    out["jurisdiction"] = _hi(country)

    ctype = d.get("contract_type")
    if ctype not in jur.get("types", TYPES):
        raise DataFileError(f"the data file's contract type is {ctype!r} - it must be one of "
                            f"{', '.join(jur.get('types', TYPES))}")
    out["engagement_type"] = _hi(ctype)

    client = d.get("client") or {}
    id_key = jur.get("client_id", "abn")
    for k in ("legal_name", "short_name", "contact_name", "address", id_key):
        if client.get(k):
            out[f"client.{k}"] = _hi(str(client[k]).strip())
    missing = [label for k, label in (("legal_name", "legal name"), (id_key, "ABN" if id_key == "abn"
                else "company registration number"), ("address", "address")) if not client.get(k)]
    if missing:
        listed = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " or " + missing[-1]
        notes.append(f"the data file has no client {listed} - get "
                     f"{'it' if len(missing) == 1 else 'them'} from the client before building")

    prop = d.get("proposal") or {}
    if prop.get("ref"):
        out["proposal.ref"] = _hi(prop["ref"])
        out["atp.ref"] = {"value": prop["ref"], "confidence": "low"}   # the ATP's own number may differ
        if not REF.match(prop["ref"]):
            notes.append(f"the proposal reference {prop['ref']!r} does not look like 26-NGA-WD-062 - check it")
    if prop.get("date"):
        out["proposal.date"] = _hi(prop["date"])
        if not DATE.match(prop["date"]):
            notes.append(f"the proposal date {prop['date']!r} should read like 8 September 2026")
    if (d.get("project") or {}).get("name"):
        out["project.name"] = _hi(d["project"]["name"])

    scope = d.get("scope") or {}
    if scope.get("platform"):
        out["scope.platform"] = _hi(scope["platform"])
    rows = scope.get("pages") if ctype == "website" else scope.get("features")
    if rows:
        clean = []
        for r in rows:
            if isinstance(r, dict):
                r = [r.get("name", ""), r.get("purpose", r.get("description", "")), r.get("level", 0)]
            clean.append([str(r[0]), str(r[1]) if len(r) > 1 else "", int(r[2]) if len(r) > 2 and r[2] else 0])
        out["scope.pages"] = _hi(clean)
        if any(not r[1] for r in clean):
            notes.append(f"{sum(not r[1] for r in clean)} of the {'pages' if ctype == 'website' else 'features'} "
                         f"have no {'purpose' if ctype == 'website' else 'description'} - add one, since it is "
                         f"part of the contract's scope")
    if ctype == "website" and "online_store" in scope:
        out["online_store"] = _hi(bool(scope["online_store"]))
        if scope.get("online_store") and scope.get("store_products"):
            out["scope.store_products"] = _hi(str(scope["store_products"]))
    if scope.get("devices"):
        out["scope.devices"] = _hi(scope["devices"])
    if scope.get("exclusions"):
        out["scope.exclusions"] = _hi(scope["exclusions"])

    fee = d.get("fee") or {}
    cur = fee.get("currency")
    if cur and cur != CURRENCY[country]:
        notes.append(f"the fee is in {cur} but a {'Sri Lankan' if country == 'LK' else 'Australian'} "
                     f"contract is in {CURRENCY[country]} - check the country and the price")
    for k in ("standard", "discount"):
        if fee.get(k) is not None:
            out[f"fee.{k}"] = _hi(str(fee[k]))
    split = d.get("payment_split")
    if split:
        # percentages alone, or each payment with when it falls due: {"percent", "when"}
        given = [x for x in split if isinstance(x, dict)]
        percents = [int(x["percent"]) if isinstance(x, dict) else int(x) for x in split]
        phrases = [str(x.get("when", "")) for x in split] if given else None
        rows, guessed = splits.rows_from(percents, phrases)
        name = split_preset(country, percents)
        preset_rows = (splits.rows_from_preset(json.load(open(f"{ROOT}/presets/{name}.json")))
                       if name else None)
        if name and (not given or preset_rows == rows):
            out["milestones"] = _hi(name)
        else:
            out["milestones"] = _hi("custom")
            out["custom_split"] = {"value": rows, "confidence": "low" if guessed else "high"}
            for problem in splits.problems(rows):
                notes.append(f"the payment split: {problem[0].lower() + problem[1:]}")
            if guessed:
                notes.append("the data file does not say when every payment falls due, so the custom "
                             "split places them by position - check each one")

    tl = d.get("timeline") or {}
    weeks = tl.get("weeks")
    if weeks:
        out["timeline.duration"] = _hi(f"{WORDS.get(int(weeks), weeks)} weeks")
    if tl.get("tasks"):
        tasks = []
        for t in tl["tasks"]:
            if isinstance(t, dict):
                t = [t.get("task", ""), t.get("who", "Encyte"), t.get("when", "")]
            who = WHO.get(str(t[1]).strip().lower())
            if not who:
                notes.append(f"timeline row {t[0]!r} says the work is done by {t[1]!r} - use Encyte, "
                             f"Client or Both; it is set to Encyte")
            tasks.append([str(t[0]), who or "P", str(t[2])])
        out["tasks"] = _hi(tasks)

    if (d.get("hosting") or {}).get("note") and country == "AU":
        out["hosting.note"] = _hi(d["hosting"]["note"])

    sup = d.get("support") or {}
    if sup.get("included_value"):
        out["support.value"] = _hi(str(sup["included_value"]))
    if sup.get("included_unit"):
        out["support.unit"] = _hi(sup["included_unit"])
    if sup.get("plan_price") is not None and country == "AU":
        out["support.price"] = _hi(str(sup["plan_price"]))

    notes.insert(0, "read from the proposal's data file, so these values are exact - check only "
                    "what the notes below list")
    return {"fields": out, "notes": notes, "chars": 0}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: proposal_data.py <file.json>")
    try:
        print(json.dumps(read(sys.argv[1]), indent=1, ensure_ascii=False))
    except DataFileError as e:
        sys.exit(f"not used: {e}")
