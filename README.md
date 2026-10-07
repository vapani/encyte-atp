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
  A *Store structure* list, as in the MILK proposal, is read with its subpages, and an item
  written *Name (what it covers)* or *Name – what it covers* fills the purpose too.
- A proposal priced in LKR sets the country to Sri Lanka. The price is read from *net project
  fee … standard fee … less a discount* (MILK), from a total investment less its SSCL
  (Colombo Seven Gin), or from *subtotal before tax* (NVQ). The payment split is read from
  the milestone amounts, e.g. *40% – LKR 204,360.00*, and matched to a Sri Lankan split.

Checked against the NGA, REKT, both Smiles 4 Miles versions, both Ciro's versions, the
marketplace and Angelucci proposals, and in Sri Lanka MILK, Colombo Seven Gin and NVQ. Anything it guessed is **shaded**, and the notes above the form say what to check.
The client's legal name, ABN and address are rarely in a proposal, so get them from the client.

**Before it builds, the form checks** that every field the contract prints is filled in,
that the price is not $0, that the ABN passes its check digit, that dates read like
*8 September 2026* and references like *26-NGA-WD-062*, and that no page is missing its
purpose (a subpage's purpose is optional, and so is every purpose in a Sri Lankan contract).
Problems are listed in the form's own words, with the fields marked in red. The form asks
before building a price under $500, or LKR 50,000 in Sri Lanka.

**Choose the contract type first** - Website, Web app, Mobile app, or Web and mobile app (one
contract for a job with both, such as NVQ's "Mobile and Web Application"). It switches
everything that depends on it:

- *What's included*, the list in 2.2 (pages for a website, features for an app);
- the platform, with no default for apps;
- a *Devices and operating systems* field for a mobile app, or a web and mobile app;
- the standard timeline (8, 12, 14 or 16 weeks), duration and payment split.

**A website can include an online store.** Ticking *Includes an online store* adds the payment
provider account to the items the client holds and pays for, an online store line to *What's
included*, and clause 3.8 Online store: payments through the client's own Stripe, Square or
PayPal account, card details held by the provider and never stored by the site, products,
prices and terms of sale supplied by the client, and orders and refunds run by the client. We
enter up to *Products we add* products (50 unless changed, `scope.store_products`), and more
are added by the client or quoted. By Asitha's decision (30 September 2026) it is issued now and
reviewed with the rest later.

Anything you've already edited stays when you switch. A proposal upload suggests the type:
it picks *Web app* when the proposal talks about a platform, portal or dashboards far more
than a website, *Mobile app* when it keeps mentioning iOS, Android or the app stores, and
*Web and mobile app* when it describes a "mobile and web application".
**App contracts of all three kinds come out as drafts** (see below): marked *DRAFT FOR LEGAL
REVIEW – NOT FOR ISSUE* on every page, named `ATP-DRAFT-…`.

**Pages are editable rows**, not a preset, because every project differs. They appear
in the contract exactly as typed. The **›** button makes a row a subpage of the page above
it, and **‹** moves it back out. A subpage can have subpages of its own, two levels at most.
In the contract a subpage is indented under its page and starts with an en dash. In the
engagement file a row is `[name, purpose]`, and a subpage adds its level:
`["Telecom", "", 1]`.

**So is the timeline.** Section 3.1 starts as the standard eight-week plan. Rows can be
edited, added or removed to match the proposal: a task, who is responsible (Encyte, the
client, or both) and the week. The form shows which week the plan runs to. The build
refuses a plan longer than the Duration, and a row with no week number, which would
otherwise slip past that check. It also refuses a payment split that names a week the plan
doesn't reach. 20-40-40 says *on acceptance (Week 8)*, so a seven-week job needs 30-40-30
or 50-50.

A build that fails validation leaves nothing behind. A build that succeeds downloads the
contract to your computer, and for now that downloaded copy is the record: nothing else is
saved (7 October 2026). Saving a copy to SharePoint is planned.


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
| **Jurisdiction pack** | `jurisdictions/AU.json`, `LK.json` | Only when the entity/country changes |
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

Words that differ by type are derived too, so the template says them once: `{{ready_for}}`
("review" for a website, "UAT" for an app, matching the payment that falls due then),
`{{pages_word}}` ("pages" or "screens") and `{{deliverable.short}}` ("app" for a web and
mobile app, so 3.4 says "a reference app").

**The payment split is stated in exactly one place.** This is the failure that broke the
Acentura ATP — 30/40/30 in clause 2.3 and 40/20/20 in clause 4.0, because it was typed twice.

## Validation — build fails, it does not warn

- milestone percentages sum to 100
- a percentage written into a milestone description must match its `percent`
- milestone amounts sum to the total
- discount cannot exceed the standard price
- required fields present and non-empty
- `scope.pages` non-empty
- a subpage has a page above it, one level deeper at most, and no deeper than level 2
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

`engagement_type` accepts `website`, `web_app`, `mobile_app` and `web_mobile_app`. All four build from the
**same template**. An earlier plan was one template file per type. It was dropped because
three copies of sections 4 to 14 would drift apart, which is the Acentura failure again.
The type-specific wording sits in conditional blocks:

```
{{?web_app|mobile_app|web_mobile_app}}  ...kept for any app type...  {{/web_app|mobile_app|web_mobile_app}}
{{?online_store}}  ...kept when the website has an online store...  {{/online_store}}
```

A block names one or more types, or an option (`OPTIONS` in `build/build.py`). A name that is
neither fails the build, so a typo cannot silently drop a clause from every contract. Sections
4 to 14 have no blocks. The number of items the client holds and pays for in 2.3 is
calculated (`{{held.count}}`: three, plus the app store accounts, plus the payment provider
account), and 3.10 names the part that goes to the stores (`{{store_app}}`: "the app", or "the
mobile app" in a web and mobile app).

| Clause | Website | Web app | Mobile app | Web and mobile app |
|---|---|---|---|---|
| 2.2 | Pages included | Features included | Features included | Features included |
| 2.3 environments | browsers | browsers | `scope.devices`, tested on a representative set of devices | browsers for the web app, `scope.devices` for the mobile app |
| 2.3 held items | three (four with a store) | three | four (adds developer accounts) | four |
| 2.4 results | search and traffic | security, performance; no promise of error-free software | same as web app | same |
| 3.4 rounds | two design rounds, two feedback rounds | two design rounds, and feedback on every testing release within scope | same | same |
| 3.5 | – | defect severity: start within 1 / 3 business days | same | same |
| 3.6 | Acceptance, from "ready for review" | User acceptance testing (UAT), from "ready for UAT": criteria per feature agreed before development, the client's testers and data, in the browsers and a testing environment; only critical and major defects hold up sign-off, and minor ones are fixed before the support period ends | same, on the client's devices through TestFlight and Google Play testing | both, each its own way |
| 3.5 support | defect fixes only: no content changes, integrations, theme or plugin updates, platform changes or accessibility audits | – | – | – |
| 3.6 web and mobile | – | – | – | three-part UAT (web, mobile, end to end) and one acceptance for the whole |
| 3.7 Handover | platform admin; a checklist once paid: site transfer, credentials, content export, licence list | admin area; a checklist once paid: repository, database export, documentation, credentials, licence notices, our own tools | same, plus signing keys and store credentials | same as mobile |
| 3.8 | – | security (encryption, hashed passwords, role access, 30 days of daily backups) and who monitors after support | same | same, plus the shared back end |
| 3.10 | – | – | delivery on submission; the list of what the client supplies for the stores | same |
| 3.8 | Online store, when ticked | Environments and source code: ours until handover; production and daily backups in client's accounts, the backups the client's once support ends; permissive licences only | same | same |
| 3.9 Third-party services and platform changes | – | provider changes are a change; new OS/browser versions are not a defect | same | same |
| 3.10 App store release | – | – | client's developer accounts; rejection split by fault; acceptance does not wait for store review | same, for the mobile app |

New clauses are numbered after 3.7, so no existing clause number or cross-reference moves.

**App contracts are issued as drafted.** Asitha confirmed the six app defaults on 7 October
2026, so `REVIEWED` in `build/build.py` lists every type and the form issues app contracts
normally. Like the website wording, they are legally reviewed later, and any change goes into
the template. A type left out of `REVIEWED` builds only with `--draft`, and carries *DRAFT FOR
LEGAL REVIEW – NOT FOR ISSUE* in red in the header on every page:

```
python3 build/build.py engagements/sample-mobile-app.json ~/Downloads/ATP-DRAFT-Mobile.docx --draft
```

Adding a type to `REVIEWED` is the record that it was approved for issue, so do it in a
commit of its own. The form then issues that type with no other change.

**Engagement data for apps.** `scope.features` replaces `scope.pages`, with the same
`[name, description]` rows. `scope.platform` has no default, because the stack is a decision
for every project. `mobile_app` and `web_mobile_app` also require `scope.devices`, which is
written into 2.3 as typed, for example *"iPhones running iOS 17 or later and Android phones
running Android 10 or later"*. See `engagements/sample-web-app.json`, `sample-mobile-app.json`
and `sample-web-mobile-app.json`. A website's online store is `"online_store": true` in
`scope`; the build refuses it on any other type.

**Presets are named for their type.** Examples are `inclusions.web-app`,
`workplan.mobile-app-14week` and `features.mobile-app-starter`. The build rejects a scope or
work-plan preset that belongs to another type. Milestone splits are shared.
`milestones.20-30-30-20` was added for longer builds.

### Still open for app contracts

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
3. Reading an app proposal's features. The Business Marketplace proposal has a clean
   *Area | Purpose* table that could fill the feature rows, descriptions included.

## Adding a jurisdiction

Copy `jurisdictions/AU.json`. The pack moves as a set: provider entity, governing law,
dispute body, interest benchmark, currency and tax, support hours, and the statutes
referenced in 6.1, 8.0, 9.0 and 10.0.

A country whose contract reads differently gets its own template, named in the pack.
These pack settings are all optional, and Australia uses none of them:

| Setting | What it does |
|---|---|
| `template` | the template file in `template/`, instead of `atp-website.docx` |
| `types` | the contract types that template covers; the form offers only these |
| `presets` | the folder in `presets/` holding that country's presets, e.g. `lk` |
| `reviewed` | the types that country can issue; any other type builds only with `--draft` |
| `client_id` | the client field the build requires, `reg_no` instead of `abn` |
| `currency_symbol` | put in front of every amount, e.g. `LKR ` |
| `store_inclusion` | the online store line added to 2.1 |
| `defaults` | engagement values the country fills in when the engagement leaves them out |
| `type_defaults` | the same, per contract type, such as each app type's exclusions |

## Sri Lankan contracts

`jurisdictions/LK.json` builds from `template/atp-website-lk.docx`: the revised Acentura
agreement, in formal language (the Client, the Provider), with sections 1.0 to 18.0
and a signing block with two optional witnesses. Amounts are in LKR. Fees exclude SSCL, VAT
and any other tax properly chargeable by law; the Provider is registered for SSCL only, so
2.5% is added and shown separately. Nothing is withheld from a resident company's service
fees, so 4.0 asks for payment in full, with a certificate only if a future law requires a
withholding.

**Core terms (October 2026 redraft).** After an external review, the parts every type shares
were redrafted once and apply to all four:

- 1.0 and 17.0: the ATP is self-contained and replaces the proposal.
- 2.3 *Supported environments and Client accounts* is split from 2.4 *Exclusions*, so fees
  are 2.5. 2.3 carries an accessibility qualification on every type.
- 4.0: the first payment is a defined **advance**, labelled in the payment table. Every
  invoice is payable within 14 days of its date, as in Australia (the Acentura original said
  on receipt), and the final payment is invoiced on acceptance.
- 13.0 *Ending This Agreement*: one table of the six ways it can end early (client
  convenience, client breach, client silence, provider breach, provider convenience, force
  majeure), with the notice, what the Client pays and what happens to the advance. The
  advance is kept on the Client's side of the table, as the greater of it and the work
  done, never on top of it; it counts toward the work, or is refunded, on the Provider's
  side. 13.2 to 13.5 cover refunds, handover, dissatisfaction and what continues.
- 14.0: the lien covers unpaid work only, never the Client's materials, data or accounts.
- 15.0: silence for 30 days leads to a written notice and 10 business days before the
  project can be suspended or ended. Payment milestones do not move for client delays.
- 16.0: approval by silence is limited to designs and content sent by email, with a
  reminder that says so, and never covers legal wording, facts, payments or release.
- 10.1: a personal-data clause (the Client controls, the Provider processes), with the
  PDPA "as amended" and breach notice within 48 hours.
- 3.5: a handover checklist, with items by type.
- 17.0: electronic signing and counterparts.

Type-specific: the website has an acceptance checklist in 3.4 and says included support is
defect correction only, not platform updates (4.1). The apps add security, backups and
who monitors after support (3.6), and capacity targets in the acceptance criteria. The
mobile types list what the Client supplies for the stores and make submission, not store
approval, the point of delivery (3.8). The web and mobile app adds an end-to-end test,
acceptance of the whole, and the shared back end.

- **All four types.** A website, with the online store option (3.6, with PayHere, WebXPay
  or a bank as the gateway, and up to `scope.store_products` products entered, 50 by
  default). The app types carry the Australian app terms in the Sri Lankan voice: 2.2
  Features, what the Client holds and the browsers or devices in 2.3, 3.4 User acceptance
  testing (10 business days, then 5 per re-test), 3.5 handover of the code once paid, 3.6
  Environments and source code with backups, 3.7 Third-party services and platform changes,
  3.8 App store release for the mobile types, and feedback on each testing release in 4.2.
  App contracts default to the four-part split `lk/milestones.20-30-30-20`.
- **Drafts until approved.** The website was approved on 7 October 2026, then paused the
  same day for the core-terms redraft, so `reviewed` is empty and every Sri Lankan build is
  a draft. Adding a type to `reviewed` approves it. 18.4 names the CCC-ICLP International
  ADR Center to appoint a mediator if the parties cannot agree.
- **Placeholders.** A fact still to come is written `[... – to confirm]`. The build
  highlights each one and lists it, and refuses to issue a contract that still has one.
  The Sri Lankan template has none left.
- **Presets** live in `presets/lk/` and are named `preset:lk/...`: the inclusions, the
  eight-week plan (5 business days of testing in week 7) and the 30-40-30, 40-30-30,
  40-40-20 and 20-30-30-20 splits. The first payment is always the advance, and the final
  payment is always on acceptance under 3.4.
- **The samples** are `engagements/sample-lk-website.json`, with subpages in 2.2,
  `sample-lk-web-app.json`, `sample-lk-mobile-app.json` and `sample-lk-web-mobile-app.json`,
  each with its own ATP and proposal numbers.
- **Engagement fields** differ from Australia's: `client.reg_no` replaces
  `client.abn`, and `support.plan` is not used, because 4.1 quotes ongoing support
  separately.
- **In the form**, pick Sri Lanka under *Country*. It asks for a company registration
  number instead of an ABN, and prices excluding SSCL. There is no care plan price or
  hosting note, and page purposes are optional, because Sri Lankan proposals list pages by
  name. It offers the types listed under `types` in the pack, now all four.


## Known gaps — deliberately not in the template

Reviewed and consciously left out. None is urgent at $5–7k; all become material on a
larger engagement, and insurance and privacy would both be table stakes for an app build.

| Gap | Status |
|---|---|
| **Insurance / professional indemnity** | **Parked — Encyte does not hold cover yet.** Do not add a warranty until policies exist; warranting cover you do not hold is worse than silence. See below — this is now the binding constraint on three separate terms. |
| **Privacy / overseas contractors** | **Partly closed 7 Oct 2026.** 8.0 now limits use to the work, sets security basics, binds everyone who handles the data (contractors included) to written terms under the APPs, gives a 48-hour breach notice, and returns or deletes data within 30 days. Still open: naming the countries, and whether offshore personnel get production access. Encyte must actually hold those written terms with its team. |
| **Cap on reimbursable expenses** | Clause 5.0 requires written approval per purchase, but sets no ceiling. |
| **Unfair contract terms review** | **Recommended 7 Oct 2026, not yet done.** An external review asked for the standard terms to be checked as a package, because they are used with small businesses. 4.2 was changed first: if the client cancels or breaches, Encyte keeps the greater of 10% of the fee and the work done, and refunds the rest, and never keeps it if Encyte breaches. Left for the lawyer: the client's uncapped cover for IP and privacy claims against Encyte's capped liability (10.0). |

*Acceptance criteria* and *force majeure exit* were listed here until 23 Sep 2026. Both are
now in the template (3.6 and 11.0) and are no longer gaps.

### Privacy — what to settle before the next engagement

Two of four are now answered in 8.0 (7 Oct 2026): everyone who handles the data is bound by
**written terms** (a flow-down, whether employee or subcontractor), and the **breach
notification timeframe** is 48 hours, inside the client's 30-day assessment clock. Still open:
**which countries** the team works from, and whether offshore personnel get **production
access** — WordPress admin usually exposes contact-form submissions, which are personal
information.

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
