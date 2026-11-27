# PH-0 — start here

Ten tasks, no product code. This phase exists because four things can invalidate the whole build, and all four are outside the repository.

## The four gates — do not start PH-1 until all four are true

| Gate | Task | Pass condition |
|---|---|---|
| Someone can pay you | T-0.1 | A merchant account exists, or a documented alternative with webhooks and subscriptions does |
| Mail reaches an inbox | T-0.4, T-0.5 | SPF, DKIM, DMARC verify; 5 of 5 seed messages land in the inbox |
| One model call works and is priced | T-0.2, T-0.3 | A completion per tier, with its real price recorded |
| The business facts exist | T-0.7 | Positioning, ICP, pricing and claims written by a human |

## Order

Start **T-0.1** (payment provider) and **T-0.4** (domain) first. Both involve an external party reviewing you; everything else you can do while you wait. Do **T-0.7** last — it is the only one that requires you to have decided what you are actually selling.

| # | Task | Artifact | Done when |
|---|---|---|---|
| 1 | T-0.1 payment provider | `docs/decisions/ADR-01.md` | account exists or alternative chosen |
| 2 | T-0.2 OpenRouter | `docs/decisions/ADR-05.md`, `.env` | one priced completion per tier |
| 3 | T-0.3 model benchmark | `evals/benchmark.py`, `docs/decisions/model-defaults.md` | 50 real examples scored on 3 candidates |
| 4 | T-0.4 sending domain | `docs/ops/email-setup.md` | SPF/DKIM/DMARC verify |
| 5 | T-0.5 deliverability spike | `docs/ops/deliverability-report.md` | 5/5 inbox placement |
| 6 | T-0.6 lawful basis | `docs/legal/outreach-policy.md` | policy names the fields the schema carries |
| 7 | T-0.7 brand facts | `seed/brand.json` | a human signed every claim |
| 8 | T-0.8 eval dataset | `evals/data/outreach.jsonl`, `evals/data/replies.jsonl` | 100 + 200 labelled |
| 9 | T-0.9 cost model | `docs/finance/cost-model.md` | filled with real prices |
| 10 | T-0.10 decision log | `docs/decisions/ADR-01..12.md` | each closed or owned |

## Templates already in the repo

Do not invent a format — fill these:

| File | What to do with it |
|---|---|
| `seed/brand.json` | Fill every field. This is the Brand Brain; every agent reads it. **Nothing here may come from a model.** |
| `docs/legal/outreach-policy.md` | Fill the brackets. The fields it names become columns in `contacts`. |
| `docs/finance/cost-model.md` | Fill the blanks with real prices, then read your CPL. |
| `evals/README.md` | Labelling rules for the 15 intents, plus the JSONL shape. |
| `docs/decisions/ADR-01.md` … `ADR-12.md` | Each is a stub with the decision, the rejected alternative and a blank outcome. |

## `seed/brand.json` — what each field is for

| Field | Why it matters |
|---|---|
| `positioning` | The one paragraph every content agent reuses. If it is vague, output is vague. |
| `icp.segments` | Drives discovery queries. Too broad and the list is noise. |
| `icp.signals` | What makes an account worth contacting (technology, headcount, hiring). |
| `voice.tone`, `voice.formality` | Controls drafting, not just style — tone drift is the first thing prospects notice. |
| `voice.banned_phrases` | Enforced in code by the drafting guard. |
| `pricing.plans` | The only permitted source for any price a model may state. Empty here means every pricing question escalates. |
| `approved_claims` | Facts an agent may assert. |
| `prohibited_claims` | Assertions that fail validation. Put "guaranteed", "instant", "fully compliant" here. |
| `objections` | The approved answer to each common objection. Without these, every objection escalates to you. |
| `testimonials` | Only with written permission. Never generated. |

## What not to do in this phase

- Do not write product code because you are waiting on somebody. The four gates are not blockers to be routed around.
- Do not let a model produce any value in `seed/brand.json`.
- Do not buy a prospect list before T-0.6 exists — you would be buying records you cannot lawfully use.
- Do not start PH-1 with ADR-01 or ADR-03 open. Everything downstream assumes them.
