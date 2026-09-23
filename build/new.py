#!/usr/bin/env python3
"""Create a new engagement file by answering prompts, then optionally build the ATP.

    python3 build/new.py

Writes engagements/<name>.json. Nobody needs to edit JSON, and nobody needs to
open the contract template - the wording is under legal review and stays fixed.
"""
import json, os, re, subprocess, sys, datetime, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"


def head(t):
    print(f"\n{BOLD}{t}{RESET}\n" + DIM + "-" * max(len(t), 34) + RESET)


def ask(label, default=None, check=None, hint=None, required=True):
    """Prompt until the answer passes `check`. Enter accepts `default`."""
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        if hint:
            print(f"{DIM}  {hint}{RESET}")
        raw = input(f"  {label}{suffix}: ").strip()
        if not raw and default not in (None, ""):
            raw = str(default)
        if not raw:
            if not required:
                return ""
            print(f"{RED}  ! required{RESET}")
            continue
        if check:
            err = check(raw)
            if err:
                print(f"{RED}  ! {err}{RESET}")
                continue
        return raw


def pick(label, options, default_idx=0):
    """Choose one of a list. Returns the chosen string."""
    print(f"\n  {label}")
    for i, o in enumerate(options, 1):
        mark = "*" if i - 1 == default_idx else " "
        print(f"   {mark} {i}) {o}")
    while True:
        raw = input(f"  choose 1-{len(options)} [{default_idx + 1}]: ").strip()
        if not raw:
            return options[default_idx]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"{RED}  ! pick a number between 1 and {len(options)}{RESET}")


def yes(label, default=True):
    d = "Y/n" if default else "y/N"
    raw = input(f"  {label} [{d}]: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


# ---------------- validators ----------------
def v_abn(s):
    digits = re.sub(r"\s", "", s)
    if not digits.isdigit() or len(digits) != 11:
        return "an ABN is 11 digits, e.g. 62 633 260 474"


def v_money(s):
    try:
        float(re.sub(r"[$,]", "", s))
    except ValueError:
        return "a number, e.g. 9500 or $9,500"


def v_date(s):
    if not re.match(r"^\d{1,2} [A-Z][a-z]+ \d{4}$", s):
        return "format: 8 September 2026"


def v_ref(s):
    if not re.match(r"^\d{2}-[A-Z0-9]+-[A-Z]{2}-\d{3}$", s):
        return "format: 26-NGA-WD-062"


def money(s):
    return float(re.sub(r"[$,]", "", s))


def presets(prefix):
    names = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{ROOT}/presets/{prefix}.*.json"))
    if not names:
        sys.exit(f"no presets found for '{prefix}.*' in {ROOT}/presets")
    return names


def main():
    print(f"\n{BOLD}New engagement{RESET}")
    print(f"{DIM}Answers become engagements/<name>.json. Enter accepts the value in brackets.{RESET}")

    jurs = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{ROOT}/jurisdictions/*.json"))
    jur = jurs[0] if len(jurs) == 1 else pick("Jurisdiction", jurs)
    provider = json.load(open(f"{ROOT}/jurisdictions/{jur}.json"))["provider"]
    print(f"{DIM}  Provider: {provider['legal_name']} (from jurisdictions/{jur}.json){RESET}")

    head("Client")
    legal_name = ask("Client legal entity name", hint="exactly as registered, including any trustee wording")
    short_name = ask("Trading / short name", default=legal_name.split(" Pty")[0])
    abn = ask("Client ABN", check=v_abn)
    address = ask("Client address", hint="Street, Suburb STATE 0000")
    contact = ask("Contact person")
    domain = ask("Domain", hint="the client's website domain, e.g. acme.com.au")

    head("References")
    today = datetime.date.today().strftime("%-d %B %Y")
    atp_ref = ask("ATP reference", check=v_ref, hint="YY-CLIENT-WD-NNN, e.g. 26-NGA-WD-062")
    atp_date = ask("ATP date", default=today, check=v_date)
    prop_ref = ask("Proposal reference", default=atp_ref, check=v_ref)
    prop_date = ask("Proposal date", check=v_date)
    project = ask("Project name", default=f"{short_name} website")

    head("Scope")
    inclusions = pick("What's included", presets("inclusions"))
    pages = pick("Page list", presets("pages"))
    platform = ask("Platform", default="WordPress")
    exclusions = ask("What is NOT included", required=False,
                     hint="Enter to keep the standard list (copywriting, legal review, "
                          "SEO campaigns, client portal)")
    hosting = ask("Hosting note", required=False,
                  hint="optional, e.g. 'Indicatively about USD $14 a month.' - Enter to skip")

    head("Fee")
    standard = money(ask("Standard price, excluding tax", check=v_money))
    discount = money(ask("Discount, excluding tax", default="0", check=v_money))
    if discount > standard:
        sys.exit(f"{RED}discount exceeds the standard price{RESET}")
    if discount:
        print(f"{DIM}  -> client pays {standard - discount:,.2f} excluding tax{RESET}")
    milestones = pick("Payment split", presets("milestones"))

    head("Timeline and support")
    workplan = pick("Work plan", presets("workplan"))
    # default the duration to the work plan's own length, so the two cannot disagree
    m = re.search(r"(\d+)\s*week", workplan)
    words = {6: "Six", 8: "Eight", 10: "Ten", 12: "Twelve"}
    dur_default = f"{words.get(int(m.group(1)), m.group(1))} weeks" if m else "Eight weeks"
    duration = ask("Duration", default=dur_default,
                   hint=f"the work plan runs {m.group(1)} weeks - a shorter duration will fail the build"
                        if m else "as it should read, e.g. 'Eight weeks'")
    sup_val = ask("Included support", default="60")
    sup_unit = ask("Support unit", default="days")
    plan_price = money(ask("Care plan price per month, excluding tax", default="99", check=v_money))

    eng = {
        "jurisdiction": jur,
        "engagement_type": "website",
        "atp": {"date": atp_date, "ref": atp_ref},
        "proposal": {"ref": prop_ref, "date": prop_date},
        "client": {"legal_name": legal_name, "abn": abn, "address": address,
                   "short_name": short_name, "contact_name": contact, "domain": domain},
        "scope": {"inclusions": f"preset:{inclusions}", "pages": f"preset:{pages}",
                  "platform": platform},
        # scope.exclusions omitted below unless given, so DEFAULTS supplies the standard list
        "hosting": {"note": hosting},
        "fee": {"standard": standard, "discount": discount},
        "milestones": f"preset:{milestones}",
        "timeline": {"duration": duration, "tasks": f"preset:{workplan}"},
        "support": {"included": {"value": int(sup_val), "unit": sup_unit},
                    "plan": {"price": plan_price}},
        "project": {"name": project},
    }
    if exclusions:
        eng["scope"]["exclusions"] = exclusions

    head("Check")
    for line in (f"{short_name}  ({legal_name})",
                 f"{atp_ref}   {atp_date}",
                 f"{standard - discount:,.2f} excluding tax" + (f"  (from {standard:,.2f} less {discount:,.2f})" if discount else ""),
                 f"{duration}, {milestones.split('.')[-1]} split",
                 f"{sup_val} {sup_unit} support, then ${plan_price:,.0f}/month"):
        print(f"  {line}")

    slug = re.sub(r"[^a-z0-9]+", "-", short_name.lower()).strip("-")
    path = f"{ROOT}/engagements/{slug}.json"
    if os.path.exists(path):
        print(f"\n{RED}  engagements/{slug}.json already exists{RESET}")
        if not yes("Overwrite it?", default=False):
            slug = ask("New file name", default=f"{slug}-2")
            path = f"{ROOT}/engagements/{slug}.json"

    print()
    if not yes("Write this engagement file?"):
        print("  nothing written")
        return

    json.dump(eng, open(path, "w"), indent=1)
    open(path, "a").write("\n")
    print(f"{GREEN}  wrote engagements/{slug}.json{RESET}")

    out = os.path.expanduser(f"~/Downloads/ATP-{short_name.replace(' ', '-')}.docx")
    if yes(f"Build the ATP now to {out}?"):
        r = subprocess.run([sys.executable, f"{ROOT}/build/build.py", path, out])
        if r.returncode:
            print(f"{RED}  build failed - fix the engagement file and run:{RESET}")
            print(f"    python3 build/build.py engagements/{slug}.json '{out}'")
    else:
        print(f"  build it later with:\n    python3 build/build.py engagements/{slug}.json '{out}'")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n  cancelled, nothing written")
