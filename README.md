# Encyte ATP template system

Build a client ATP from **one locked legal spine** plus a small data file.

```
python3 build/build.py engagements/<client>.json ~/Downloads/ATP-<Client>.docx
```

## Creating a new agreement

**Start here. You do not need to edit JSON, and you must not open the template.**

```
python3 build/serve.py
```

That opens a form in your browser at `http://127.0.0.1:8420`. Fill it in, click
**Build the ATP**, and the `.docx` downloads. The server listens on localhost
only - nothing is reachable from outside the machine and no client data leaves it.
Ctrl-C in the terminal stops it.

**Starting from a proposal.** Drop a `.docx` or `.pdf` onto the top of the form and
it fills in what it can find. It matches patterns, not meaning:

- A reference looks like `26-NGA-WD-062`. The proposal date is taken from the cover, or from
  a date labelled *dated*. Other dates in the body are ignored: the Ciro's proposal quotes
  a 19 June 2026 post from the client's current site. If the cover gives only *August 2026*,
  the notes ask for the day.
- The client follows *Prepared for* or *Prepared by Encyte for*, including when *for* starts
  the next line. When that line has a role in it (*Rob, Founder, REKT Productions*), the
  client comes last and the first name becomes the contact. Without a role (*Ciro's Cakes &
  Biscuits, Noble Park*), the client comes first.
- The price is the standard price and the discount, read from *Standard price … Your
  investment / Final investment …* in `$` or `AUD`. The largest figure is used only when
  there are no labels. If the price includes an allowance (plugins, licences), the notes say
  so, because clause 5.0 charges those at cost on top of the fee.
- Pages fill the page rows only when the names found match the page count the proposal
  states: *8 pages – Home, …*, *Page scope · 9 pages* with names below, or *Up to 8 core
  pages* with *A likely core set is …*. A shorter list goes in the notes instead of replacing
  the standard list. Purposes are left empty, because they are part of the contract's scope.

Checked against the NGA, REKT, both Smiles 4 Miles versions, Colombo Seven Gin and Ciro's
proposals. Anything it guessed is **shaded**, and the notes above the form say what to check.
The client's legal name, ABN and address are rarely in a proposal, so get them from the client.

**Before it builds, the form checks** that every field the contract prints is filled in,
that the price is not $0, that the ABN passes its check digit, that dates read like
*8 September 2026* and references like *26-NGA-WD-062*, and that no page is missing its
purpose. Problems are listed in the form's own words, with the fields marked in red.

**Pages are editable rows**, not a preset, because every project differs. They appear
in the contract exactly as typed.

**So is the timeline.** Section 3.1 starts as the standard eight-week plan. Rows can be
edited, added or removed to match the proposal: a task, who is responsible (Encyte, the
client, or both) and the week. The form shows which week the plan runs to. The build
refuses a plan longer than the Duration, and a row with no week number, which would
otherwise slip past that check. It also refuses a payment split that names a week the plan
doesn't reach. 20-40-40 says *on acceptance (Week 8)*, so a seven-week job needs 30-40-30
or 50-50. The terminal wizard still uses the work plan presets.

A build that fails validation leaves nothing behind. A build that succeeds writes
`engagements/<client>.json`, which is the record of that deal - commit it.

There is also a terminal version if you prefer it:

```
python3 build/new.py
```

It asks for the client details, references, scope, fee, timeline and support, then
writes `engagements/<client>.json` and offers to build the ATP straight away. Press
Enter to accept anything shown in brackets. Ctrl-C at any point writes nothing.

What it protects you from:

- **ABN, reference and date formats** are checked as you type and re-asked until valid.
- **The duration defaults to the work plan's own length.** A six-week duration against
  the eight-week plan produces a contract whose timeline contradicts its own schedule,
  so the build refuses it - the prompt now defaults so the two agree by construction.
- **Presets are listed from disk**, so a new inclusions or milestone preset appears in
  the menu automatically. Nobody has to remember what exists.
- **Your own details are never asked for.** Encyte's legal name, ABN, address, phone,
  email, GST, governing law and the statute names all come from `jurisdictions/AU.json`.
  Change your address once and every future ATP is correct.

Press Enter at *What is NOT included* and *Hosting note* to use the standard wording.

**The template is under legal review and its wording is fixed.** If a clause needs to
change, that is a change to `template/atp-website.docx` reviewed once for everybody -
never a per-client edit to a generated `.docx`. Editing the output silently voids the
review for that client and leaves no trace.

To rebuild after editing an engagement file by hand:

```
python3 build/build.py engagements/<client>.json ~/Downloads/ATP-<Client>.docx
```

## Reviewing template changes

The repository is the history. `template/atp-website.docx` is the reviewed legal
spine, so every change to it should be a commit someone can read.

Run once per clone:

```
./build/setup-git.sh
```

That routes `.docx` through `build/docxtext.py`, so `git diff` and `git log -p`
show the clause wording that changed instead of *"binary files differ"*:

```
-4.1 Invoices are payable within {{terms.payment_days}} days of the invoice date.
+4.1 Invoices are due within {{terms.payment_days}} days of the invoice date.
```

Two things worth knowing about this repo:

- **The template carries no embedded fonts.** Twelve unsubsetted font files left
  over from authoring were removed - the document had moved to Aptos and none was
  in use. Template 4.56 MB to 42 KB, and every generated contract with it. If a
  clause ever needs a font the reader may not have, send the PDF rather than
  re-embedding.
- **`.gitignore` anchors `/ATP-*.docx` to the root on purpose.** macOS sets
  `core.ignorecase`, so an unanchored `ATP-*.docx` also matches
  `template/atp-website.docx` and silently leaves the contract out of the repo.

## Architecture

| Layer | Where | Changes per deal? |
|---|---|---|
| **Legal spine** — sections 4–14 | `template/atp-website.docx` | **No. Locked.** |
| **Scope module** — section 2 | same file, token-driven | Shape is fixed, content varies |
| **Jurisdiction pack** | `jurisdictions/AU.json` | Only when the entity/country changes |
| **Engagement data** | `engagements/*.json` | Every deal |

The template is the NGA contract with its values replaced by `{{tokens}}`, so all
styling, numbering and formatting are inherited rather than rebuilt.

## What is deliberately NOT a variable

The clauses that took work to get right, and must not drift deal to deal:

- Australian Consumer Law carve-out (10.0)
- Moral rights consent, Part IX Copyright Act 1968 (9.0)
- Background IP carve-out and perpetual licence (9.0)
- Mutual confidentiality (8.0)
- Liability cap, aggregate and however arising, with **no** confidentiality carve-out (10.0)
- Narrow indemnity with negligence carve-back, uncapped only for third-party IP and
  privacy claims, with notice, no-admission and control-of-defence (10.0)
- Approvals clause — *we will not publish or build on anything you have not approved* (6.5)
- Support hours and file retention (fixed; support hours live in the jurisdiction pack)
- Extra design rounds — quoted and approved in writing, never a stated rate

## Derived, never typed

Computed from `fee.standard`, `fee.discount` and `milestones[].percent`:

`fee.total` · `fee.tax` · `fee.total_inc` · every milestone amount ex and inc tax · the totals row.
The last milestone absorbs rounding so the column always sums to the total exactly.

**The payment split is stated in exactly one place.** This is the failure that broke the
Acentura ATP — 30/40/30 in clause 2.3 and 40/20/20 in clause 4.0, because it was typed twice.

## Validation — build fails, it does not warn

- milestone percentages sum to 100
- a percentage written into a milestone description must match its `percent`
- milestone amounts sum to the total
- discount cannot exceed the standard price
- required fields present and non-empty
- `scope.pages` non-empty
- **no unreplaced `{{tokens}}` in the output**, including in headers and footers
- **no em dashes** anywhere in the output. House style is the spaced en dash, and Word's
  autocorrect turns ` - ` into an em dash the moment anyone edits the template by hand
- `engagement_type` has a template, and is in `REVIEWED` unless the build is `--draft`
- scope and work-plan presets belong to the engagement's type
- the final milestone is invoiced **on acceptance**. 3.6, 3.5 and 11.0 all key to acceptance,
  so a final milestone "at launch" contradicts them
- the work plan cannot run past the stated duration (a "six weeks" timeline against the
  eight-week plan builds a contract that contradicts its own schedule), and a duration with
  no readable week count fails rather than skipping this check
- conditional blocks name only known types

## Web app and mobile app ATPs — drafted, not yet reviewed

`engagement_type` accepts `website`, `web_app` and `mobile_app`. All three build from the
**same template**. An earlier plan was one template file per type. It was dropped because
three copies of sections 4 to 14 would drift apart, which is the Acentura failure again.
The type-specific wording sits in conditional blocks:

```
{{?web_app|mobile_app}}  ...kept for either app type...  {{/web_app|mobile_app}}
```

A block names one or more types. A name that is not a known type fails the build, so a
typo cannot silently drop a clause from every contract. Sections 4 to 14 have no blocks.

| Clause | Website | Web app | Mobile app |
|---|---|---|---|
| 2.2 | Pages included | Features included | Features included |
| 2.3 held items | three | three | four (adds developer accounts) |
| 2.3 support | browsers | browsers | `scope.devices` |
| 2.3 results | search and traffic | security, performance; no promise of error-free software | same as web app |
| 3.5 | – | defect severity: start within 1 / 3 business days | same |
| 3.6 | – | written acceptance criteria per feature, agreed before development | same |
| 3.7 Handover | platform admin, site transfer | admin area, repository transfer, documentation | same |
| 3.8 Environments and source code | – | ours until handover; production in client's accounts; permissive licences only | same |
| 3.9 Third-party services and platform changes | – | provider changes are a change; new OS/browser versions are not a defect | same |
| 3.10 App store release | – | – | client's developer accounts; rejection split by fault; acceptance does not wait for store review |

New clauses are numbered after 3.7, so no existing clause number or cross-reference moves.

**The app clauses have not been legally reviewed.** `REVIEWED` in `build/build.py` lists the
types that may be issued, and it holds only `website`. An app build refuses unless you pass
`--draft`. The draft then carries *DRAFT FOR LEGAL REVIEW – NOT FOR ISSUE* in red in the header
on every page:

```
python3 build/build.py engagements/sample-mobile-app.json ~/Downloads/ATP-DRAFT-Mobile.docx --draft
```

The browser form and `new.py` offer websites only, and list only website presets. Adding a type
to `REVIEWED` is the record that a lawyer has read its clauses, so do it in a commit of its own.

**Engagement data for apps.** `scope.features` replaces `scope.pages`, with the same
`[name, description]` rows. `scope.platform` has no default, because the stack is a decision
for every project. `mobile_app` also requires `scope.devices`, which is written into 2.3 as
typed, for example *"iPhones running iOS 17 or later and Android phones running Android 10
or later"*. See `engagements/sample-web-app.json` and `sample-mobile-app.json`.

**Presets are named for their type.** Examples are `inclusions.web-app`,
`workplan.mobile-app-14week` and `features.mobile-app-starter`. The build rejects a scope or
work-plan preset that belongs to another type. Milestone splits are shared.
`milestones.20-30-30-20` was added for longer builds.

### Before an app ATP is issued

- **Legal review** of the app blocks listed above. The text to send is the output of
  `python3 build/docxtext.py` on a `--draft` build.
- **Privacy.** An app build almost always holds personal information, so the deferred privacy
  decision (below) stops being optional. 3.8 deliberately says nothing yet about where
  production data may be accessed from.
- **Insurance.** Check that the declared business activities cover app development, not
  only websites.

### Still to build

1. An annexure mechanism for an SLA schedule and a Data Processing Addendum.
2. `engagement.model`: fixed price, phased, or time and materials with a cap.
3. App types in the browser form and `new.py`, once the clauses are reviewed.

## Adding a jurisdiction

Copy `jurisdictions/AU.json`. The pack moves as a set: provider entity, governing law,
dispute body, interest benchmark, currency and tax, support hours, and the statutes
referenced in 6.1, 8.0, 9.0 and 10.0. A Sri Lankan pack also needs PDPA No. 9 of 2022
and IP Act No. 36 of 2003 in place of the Australian statutes.


## Known gaps — deliberately not in the template

Reviewed and consciously left out. None is urgent at $5–7k; all become material on a
larger engagement, and insurance and privacy would both be table stakes for an app build.

| Gap | Status |
|---|---|
| **Insurance / professional indemnity** | **Parked — Encyte does not hold cover yet.** Do not add a warranty until policies exist; warranting cover you do not hold is worse than silence. See below — this is now the binding constraint on three separate terms. |
| **Privacy / overseas contractors** | **Deferred 23 Sep 2026, consciously.** Clause 8.0 states offshore handling but names no countries, binds no subcontractors and sets no breach timeframe. Risk dropped sharply when the §8 liability carve-out was removed, so a privacy failure is now capped at fees rather than unlimited. Open questions are recorded below. |
| **Cap on reimbursable expenses** | Clause 5.0 requires written approval per purchase, but sets no ceiling. |

*Acceptance criteria* and *force majeure exit* were listed here until 23 Sep 2026. Both are
now in the template (3.6 and 11.0) and are no longer gaps.

### Privacy — what to settle before the next engagement

Four things, none answered yet. **Which countries** the team works from; whether they are
**employees or subcontractors** (decides whether a flow-down obligation is needed); whether
offshore personnel get **production access** — WordPress admin usually exposes contact-form
submissions, which are personal information; and a **breach notification timeframe** the
client can rely on, since their own assessment clock runs 30 days.

Two ways to close it. **Disclose and control** — name countries, bind subcontractors,
define the breach process. Or **narrow the exposure** — commit that personal information
stays in Australia and offshore personnel work on code and design only. The second is far
stronger with a client holding tax file numbers, and is often simply true, but it is only
available if production access really is restricted. Check before writing it.

Note also that the **TFN Rule has no small business exemption**. The Privacy Act's $3m
threshold likely keeps Encyte outside the APPs today, but any engagement where the team can
reach an environment holding tax file numbers sits under a stricter regime regardless of
turnover — and the small business exemption has been repeatedly flagged for removal.

### When insurance is taken out

Add as the **last paragraph of section 10.0 Liability** — not a new section, which would
renumber 10–14 and every cross-reference. Placing it beside the cap is deliberate.

It must end with wording to the effect of *"Holding this insurance does not increase our
liability beyond the limits in section 10."* **Without that sentence an insurance clause can
undermine the liability cap** — naming $2m of cover against a cap of fees paid invites the
argument that the cap is unreasonable.

Limits belong in the **jurisdiction pack** (`insurance.pi`, `insurance.public_liability`,
`insurance.cyber`), not the engagement file — they are a property of the insuring entity.
Per-deal fields do not grow — they stand at 23 in `_starter.json`. `terms.payment_days` and
`hosting.note` fall back to `DEFAULTS` if omitted, and `scope.exclusions` to the engagement
type's entry in `TYPE_DEFAULTS`. `scope.platform` defaults to WordPress for websites only.

Three things to confirm with the broker first: whether PI is claims-made and what the
**retroactive date** is; whether limits are **any one claim** or **aggregate**; and whether the
**declared business activities** cover app development and data handling, or only websites.
The last one matters before the first app engagement, not after.

**Insurance is now the constraint, not a nice-to-have.** It set the ceiling on three separate
decisions during the September 2026 review: the confidentiality liability carve-out (removed
outright, because an uncapped promise with no policy behind it is paid from Encyte's own
pocket), the indemnity structure, and what can be offered to a client holding sensitive
financial data. A carve-out capped at an insured amount is attractive and saleable; the same
carve-out uninsured is not. Expect this to recur on every engagement above this size until
cover exists.
