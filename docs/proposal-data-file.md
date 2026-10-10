# Proposal data file

Every proposal should be saved with a small data file beside it, holding the exact values
the proposal was written from. Dropping that file on the ATP form fills the contract's
fields exactly, so nothing is guessed from the PDF, and checking the contract takes minutes.

- **Name:** `<proposal reference> - proposal data.json`, for example
  `26-NGA-WD-062 - proposal data.json`, saved in the same folder as the proposal.
- **When:** each time the proposal is issued. A revised proposal gets a fresh file.
- **Who reads it:** the ATP form (upload box, or `python3 build/proposal_data.py <file>`
  to see what it would fill).

Examples: [`examples/example-au-website.json`](examples/example-au-website.json) and
[`examples/example-lk-web-app.json`](examples/example-lk-web-app.json).

## Format (version 1)

A JSON object. Leave out anything the proposal does not state; the form keeps its
standard value for it and, where it matters, says what is missing.

| Field | What it holds | Example |
|---|---|---|
| `format` | always `"encyte-proposal-data"` | |
| `version` | always `1` | |
| `country` | `"AU"` (Encyte Pty Ltd) or `"LK"` (Encyte (Pvt) Ltd) | `"AU"` |
| `contract_type` | `"website"`, `"web_app"`, `"mobile_app"` or `"web_mobile_app"` | `"website"` |
| `proposal.ref` | the proposal's reference | `"26-NGA-WD-062"` |
| `proposal.date` | the day it was issued, written out | `"5 September 2026"` |
| `client.short_name` | the client's trading name, as the proposal uses it | `"NGA Private"` |
| `client.contact_name` | the person the proposal is addressed to | `"Natalie"` |
| `client.legal_name` | the registered entity name, if known | `"NGA Private Pty Ltd"` |
| `client.abn` (AU) or `client.reg_no` (LK) | the client's ABN or company registration number, if known | `"12 345 678 901"` |
| `client.address` | the client's registered address, if known | |
| `project.name` | what the contract calls the job | `"NGA Private website"` |
| `scope.platform` | what it is built on | `"WordPress"` |
| `scope.pages` (website) | the pages, in order, each `{"name", "purpose", "level"}`; `level` 1 is a subpage of the row above, 2 a subpage of that, and can be left out for a page | see the example |
| `scope.features` (apps) | the features, each `{"name", "description"}` | see the example |
| `scope.online_store` (website) | `true` when the website includes a shop | `false` |
| `scope.store_products` | how many products Encyte adds to the store | `50` |
| `scope.devices` (mobile apps) | the phones and operating systems | `"iPhones running iOS 17 or later and Android phones running Android 10 or later"` |
| `scope.exclusions` | only if the proposal excludes something unusual; otherwise leave out for the standard list | |
| `fee.currency` | `"AUD"` or `"LKR"` | `"AUD"` |
| `fee.standard` | the build price before discount, excluding GST or SSCL | `5500` |
| `fee.discount` | the discount, excluding GST or SSCL; `0` for none | `650` |
| `payment_split` | the payments in order: percentages, or each as `{"percent", "when"}` saying when it falls due | `[20, 40, 40]`, or `[{"percent": 20, "when": "kick-off"}, {"percent": 40, "when": "working demo"}, {"percent": 40, "when": "acceptance"}]` |
| `timeline.weeks` | the project length in weeks | `8` |
| `timeline.tasks` | the work plan, each `{"task", "who", "when"}`; `who` is `"Encyte"`, `"Client"` or `"Both"`; `when` is `"Week 3"` or `"Weeks 4–5"` | see the example |
| `support.included_value`, `support.included_unit` | the support included after acceptance | `60`, `"days"` |
| `support.plan_price` (AU) | the monthly care plan price, excluding GST | `99` |
| `hosting.note` (AU) | a line on hosting costs, if the proposal gives one | `"Indicatively about USD $14 a month, currently around AUD $20."` |

## Rules

- **Words as they will appear in the contract.** Page names, purposes and timeline rows go
  into the contract exactly as written, so use the house style: spaced en dashes ( – ),
  never em dashes.
- **The client's legal name, ABN or registration number, and address** are rarely known
  when the proposal is written. Leave them out rather than guess; the form asks for them.
- **Payment splits.** A split whose percentages match one of the country's shortcuts uses
  it: Australia 20-40-40, 30-40-30, 50-50 and 20-30-30-20; Sri Lanka 30-40-30, 40-30-30,
  40-40-20 and 20-30-30-20. Any other split becomes a **custom split**, so give each
  payment's `when`: the first is always the advance on signing and the last always
  acceptance, and those between fall due on *design freeze*, *working demo*,
  *development complete* or *ready for testing*, in that order. A custom split has 2 to 5
  payments, adds up to exactly 100, and its final payment is at least 10%. A proposal
  that says "at launch" is invoiced on acceptance in the contract.
- **Numbers are plain numbers**: `5500`, not `"$5,500"`.

## For the proposal generator

Proposals are built in Claude Code sessions. The Claude skill `encyte-proposal-data`
(`~/.claude/skills/encyte-proposal-data/SKILL.md` on Asitha's Mac) tells every session
that finishes a proposal deck to write this file beside it and check it with
`build/proposal_data.py`. It can also write one for an existing proposal: ask for
"the proposal data file" for that deck. Anywhere the skill is not installed, add this
to the proposal instructions instead:

> When the proposal is final, also save `<proposal reference> - proposal data.json` next to
> it, in the format in `docs/proposal-data-file.md` of the encyte-atp repository. Fill
> every field the proposal states, from the same values the proposal was written from, and
> leave out anything it does not state. Use plain numbers, the payment split as
> percentages, and spaced en dashes in any text.
