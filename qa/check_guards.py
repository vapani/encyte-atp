#!/usr/bin/env python3
"""Feed the build bad engagements and check that each is refused, with a useful message.

    python3 qa/check_guards.py

Each case starts from a good sample engagement and breaks one thing. Exit 1 means
validation failed and nothing was issued; exit 2 means the contract was built but
flagged (an em dash, a leftover token, an unfilled placeholder). Writes nothing into
the project. Exits 1 if any guard misbehaves.
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AU, AU_APP, AU_MOBILE = "sample-example-co", "sample-web-app", "sample-mobile-app"
LK, LK_APP = "sample-lk-website", "sample-lk-web-app"


def resolved(v):
    if isinstance(v, str) and v.startswith("preset:"):
        return json.load(open(f"{ROOT}/presets/{v.split(':', 1)[1]}.json"))
    return v


def milestones(e):
    e["milestones"] = resolved(e["milestones"])
    return e["milestones"]


def pages(rows):
    return lambda e: e["scope"].update(pages=rows)


# (name, sample, how to break it, words the message must contain, --draft, expected exit code)
CASES = [
    ("percentages not 100", AU, lambda e: milestones(e)[0].update(percent=40), "sum to", False, 1),
    ("description says another %", AU,
     lambda e: (milestones(e)[0].update(percent=60), milestones(e)[1].update(percent=40)), "description says", False, 1),
    ("final payment not on acceptance", AU,
     lambda e: milestones(e)[-1].update(description="50% at launch."), "on acceptance", False, 1),
    ("discount above the price", AU, lambda e: e["fee"].update(discount=99999), "discount exceeds", False, 1),
    ("zero price", AU, lambda e: e["fee"].update(standard=0, discount=0), "enter the standard price", False, 1),
    ("plan longer than duration", AU, lambda e: e["timeline"].update(duration="Three weeks"), "work plan runs to week", False, 1),
    ("duration not a number of weeks", AU, lambda e: e["timeline"].update(duration="soon"), "cannot read a number of weeks", False, 1),
    ("split names a later week", AU_APP, lambda e: e.update(milestones="preset:milestones.20-40-40"), "says week 8", False, 1),
    ("unknown contract type", AU, lambda e: e.update(engagement_type="brochure"), "has no template", False, 1),
    ("preset of another type", AU, lambda e: e["scope"].update(inclusions="preset:inclusions.web-app"), "is not a website preset", False, 1),
    ("no client name", AU, lambda e: e["client"].update(legal_name=""), "client.legal_name", False, 1),
    ("no ABN", AU, lambda e: e["client"].pop("abn"), "client.abn", False, 1),
    ("no proposal date", AU, lambda e: e["proposal"].update(date=""), "proposal.date", False, 1),
    ("mobile app without devices", AU_MOBILE, lambda e: e["scope"].pop("devices"), "scope.devices", False, 1),
    ("online store on a web app", AU_APP, lambda e: e["scope"].update(online_store=True), "online_store applies only", False, 1),
    ("no pages", AU, pages([]), "scope.pages is empty", False, 1),
    ("first row a subpage", AU, pages([["Home", "", 1], ["About", ""]]), "subpage with no page above", False, 1),
    ("subpage skips a level", AU, pages([["Home", ""], ["Team", "", 2]]), "subpage with no subpage above", False, 1),
    ("subpage level 3", AU, pages([["Home", ""], ["A", "", 1], ["B", "", 2], ["C", "", 3]]), "use 0, 1 or 2", False, 1),
    ("no timeline rows", AU, lambda e: e["timeline"].update(tasks=[]), "timeline.tasks is empty", False, 1),
    ("Sri Lankan without registration number", LK, lambda e: e["client"].pop("reg_no"), "client.reg_no", True, 1),
    ("em dash in the data", AU, lambda e: e["project"].update(name="Example — site"), "EM DASHES", False, 2),
    ("token in the data", AU, lambda e: e["project"].update(name="{{oops}}"), "{{oops}}", False, 2),
    ("placeholder in the data", AU, lambda e: e["scope"].update(exclusions="[scope – to confirm]"), "PLACEHOLDERS", False, 2),
    ("placeholder allowed in a draft", AU, lambda e: e["scope"].update(exclusions="[scope – to confirm]"), "PLACEHOLDERS", True, 0),
]


def unapproved_sample():
    """A sample whose type its country has not approved yet, or None once every type is approved."""
    sys.path.insert(0, f"{ROOT}/build")
    import build as builder
    for name in sorted(os.listdir(f"{ROOT}/engagements")):
        if not name.startswith("sample"):
            continue
        e = json.load(open(f"{ROOT}/engagements/{name}"))
        jur = json.load(open(f"{ROOT}/jurisdictions/{e['jurisdiction']}.json"))
        if e["engagement_type"] not in builder.reviewed(jur):
            return name[:-5]
    return None


def main():
    failed = 0
    sample = unapproved_sample()
    if sample:      # an unapproved type must not be issued without --draft
        CASES.append(("unapproved type issued", sample, lambda e: None, "not been approved for issue", False, 1))
    else:
        print("  (every type is approved, so there is no unapproved type to try issuing)")
    with tempfile.TemporaryDirectory() as out:
        for i, (name, base, breakit, expect, draft, code) in enumerate(CASES):
            eng = json.load(open(f"{ROOT}/engagements/{base}.json"))
            breakit(eng)
            path = f"{out}/case{i}.json"
            json.dump(eng, open(path, "w"), ensure_ascii=False)
            r = subprocess.run([sys.executable, f"{ROOT}/build/build.py", path, f"{out}/case{i}.docx"]
                               + (["--draft"] if draft else []), capture_output=True, text=True)
            said = r.stdout + r.stderr
            if r.returncode != code or expect.lower() not in said.lower():
                failed += 1
                last = said.strip().splitlines()[-1] if said.strip() else "(no output)"
                print(f"  FAIL     {name}: exit {r.returncode} (expected {code}); {last[:120]}")
    print(f"guards: {len(CASES) - failed} of {len(CASES)} behave as expected")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
