#!/usr/bin/env python3
"""Payment splits: the events a payment can fall due on, and how the contract words each one.

A split is a list of (percent, trigger) rows. The first payment is always the advance,
due on signing, and the last is always on acceptance: the termination clauses depend on
the advance, and the testing, support and delay clauses on acceptance. Payments in
between fall due on one of a short list of events the contract defines, in project
order. The preset splits in presets/ are shortcuts; a custom split is built here.
"""
import re

ADVANCE, ACCEPTANCE = "advance", "acceptance"
MIDDLE = ("design_freeze", "demo", "dev_complete", "ready")      # in project order
TRIGGERS = (ADVANCE,) + MIDDLE + (ACCEPTANCE,)
MIN_PAYMENTS, MAX_PAYMENTS, MIN_FINAL = 2, 5, 10

LABELS = {ADVANCE: "Advance, on signing", "design_freeze": "Design freeze", "demo": "Working demo",
          "dev_complete": "Development complete", ACCEPTANCE: "Acceptance"}

# How each payment reads in the contract's payment table, per country. {p} is the
# percentage; {{deliverable}} is filled by the build like any other token.
WORDING = {
    "AU": {ADVANCE: "{p}% at kick-off, due on signing this agreement.",
           "design_freeze": "{p}% on design freeze.",
           "demo": "{p}% on the first working demo.",
           "dev_complete": "{p}% on completion of development.",
           "ready_website": "{p}% when the {{{{deliverable}}}} is ready for review.",
           "ready_app": "{p}% when the complete build is ready for user acceptance testing (UAT).",
           ACCEPTANCE: "{p}% on acceptance."},
    "LK": {ADVANCE: "{p}% of the total project fee, an advance under section 4.0, invoiced on signing "
                    "this Agreement.",
           "design_freeze": "{p}% of the total project fee upon design freeze.",
           "demo": "{p}% of the total project fee upon the first working demo.",
           "dev_complete": "{p}% of the total project fee upon completion of the development.",
           "ready_website": "{p}% of the total project fee when the {{{{deliverable}}}} is ready for "
                            "review under section 3.4.",
           "ready_app": "{p}% of the total project fee when the complete build is ready for user "
                        "acceptance testing (UAT).",
           ACCEPTANCE: "{p}% of the total project fee upon acceptance of the {{{{deliverable}}}} under "
                       "section 3.4."},
}


def label(trigger, etype):
    if trigger == "ready":
        return "Ready for review" if etype == "website" else "Ready for UAT"
    return LABELS[trigger]


def choices(etype):
    """[(trigger, label)] for the form: every trigger, labelled for this contract type."""
    return [(t, label(t, etype)) for t in TRIGGERS]


def problems(rows, etype=None):
    """Everything wrong with a custom split, in the form's words. Empty when it is usable."""
    errs = []
    if not isinstance(rows, list) or not rows:
        return ["Add the payments for the custom split"]
    n = len(rows)
    if not MIN_PAYMENTS <= n <= MAX_PAYMENTS:
        errs.append(f"A custom split has {MIN_PAYMENTS} to {MAX_PAYMENTS} payments, not {n}")
    pcts = []
    for i, r in enumerate(rows, 1):
        try:
            p = float(r[0])
        except (TypeError, ValueError, IndexError):
            errs.append(f"Payment {i} has no percentage"); continue
        if p != int(p) or p < 1:
            errs.append(f"Payment {i} must be a whole percentage of at least 1%")
        pcts.append(int(p))
    total = sum(pcts)
    if len(pcts) == n and total != 100:
        errs.append(f"The payments add up to {total}%, not 100%")
    trig = [r[1] if isinstance(r, (list, tuple)) and len(r) > 1 else None for r in rows]
    if trig and trig[0] != ADVANCE:
        errs.append("The first payment must be the advance, on signing")
    if trig and trig[-1] != ACCEPTANCE:
        errs.append("The last payment must be on acceptance")
    middle = trig[1:-1]
    if any(t not in MIDDLE for t in middle):
        errs.append("A payment in between must fall due on design freeze, a working demo, "
                    "development complete or ready for testing")
    elif middle != sorted(middle, key=MIDDLE.index) or len(set(middle)) != len(middle):
        errs.append("The payments in between must follow the project's order (design freeze, "
                    "working demo, development complete, ready for testing), each used once")
    if pcts and len(pcts) == n and pcts[-1] < MIN_FINAL:
        errs.append(f"The final payment is {pcts[-1]}% - make it at least {MIN_FINAL}%, so acceptance "
                    f"carries real weight")
    return errs


def milestones(country, etype, rows):
    """The contract's milestone list for a custom split: [{"percent", "description"}]."""
    words = WORDING[country]
    out = []
    for p, t in rows:
        key = ("ready_website" if etype == "website" else "ready_app") if t == "ready" else t
        out.append({"percent": int(float(p)), "description": words[key].format(p=int(float(p)))})
    return out


# ---- reading a split from a proposal's words or a preset's descriptions ----

_WORDS = [  # checked in order: the first match wins
    (ACCEPTANCE, r"accept|launch|go[- ]?live|sign[- ]?off|handover|hand-over|final"),
    (ADVANCE, r"kick[- ]?off|signing|sign\b|start|commence|deposit|advance|confirm|order"),
    ("design_freeze", r"design"),
    ("demo", r"demo"),
    ("ready", r"\buat\b|user acceptance|testing|ready for (?:review|test)|review"),
    ("dev_complete", r"develop|build|content|complet|integration|delivery"),
]


def trigger_for(words):
    """The trigger a proposal's phrase names ('at kick-off', 'at demo'), or None."""
    w = (words or "").lower()
    for trig, pat in _WORDS:
        if re.search(pat, w):
            return trig
    return None


def default_triggers(n):
    """Triggers by position when a proposal gives percentages but no events."""
    middle = {0: [], 1: ["dev_complete"], 2: ["design_freeze", "ready"],
              3: ["design_freeze", "dev_complete", "ready"]}.get(max(0, n - 2), [])
    return [ADVANCE] + middle + [ACCEPTANCE] if n >= 2 else [ACCEPTANCE]


def rows_from(percents, phrases=None):
    """(rows, guessed): a split's rows from percentages and, where given, each payment's phrase.

    The first is always the advance and the last acceptance; a phrase that names an event
    places a payment in between, and anything unnamed falls back to its position."""
    n = len(percents)
    fallback = default_triggers(n)
    trig, guessed = [], False
    for i, p in enumerate(percents):
        if i == 0:
            trig.append(ADVANCE); continue
        if i == n - 1:
            trig.append(ACCEPTANCE); continue
        t = trigger_for(phrases[i]) if phrases and i < len(phrases) else None
        if t not in MIDDLE:
            t, guessed = fallback[i], True
        trig.append(t)
    return [[int(p), t] for p, t in zip(percents, trig)], guessed


def rows_from_preset(preset):
    """A preset split as custom rows, so a shortcut can be edited or used where it does not fit."""
    rows, _ = rows_from([m["percent"] for m in preset], [m["description"] for m in preset])
    return rows
