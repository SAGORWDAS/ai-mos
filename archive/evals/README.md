# Evaluation sets — T-0.8

Two files, both JSON-lines, both from **your own history**. Public benchmarks are useless here: what matters is whether a model reproduces the judgement you would make on your own market.

| File | Size | Purpose |
|---|---|---|
| `data/outreach.jsonl` | 100 good and bad emails you actually sent | Score drafts on groundedness, specificity, spam risk |
| `data/replies.jsonl` | 200 replies you labelled by hand | Measure classification accuracy before it handles a real inbox |

Keep 20% as a holdout you never tune against. Split by company, not by message — otherwise the same thread leaks into both sides.

## `outreach.jsonl`

```json
{"id":"o-001","subject":"…","body":"…","sent_at":"2026-09-14","outcome":"replied|no_reply|bounced","human_scores":{"groundedness":1.0,"specificity":0.7,"spam_risk":0.1},"notes":"…"}
```

`groundedness` — 1.0 if every factual statement is true of the product, 0 otherwise. It is binary on purpose: a hallucinated claim is not "80% good".
`specificity` — 0 to 1, how much of the email could only have been sent to this person.
`spam_risk` — 0 to 1, your instinct on triggers: links, subject punctuation, hype words.

## `replies.jsonl`

```json
{"id":"r-001","text":"…","label":"interested","confidence_expected":0.9,"notes":"asked about onboarding time"}
```

Exactly one `label` from the closed set. If a reply genuinely has two intents, label it `needs_human` — that is what the system would do.

## The fifteen labels

| Label | When to use it | Test phrase |
|---|---|---|
| `interested` | Wants detail, asks a real question | "How does the HubSpot sync work?" |
| `meeting_request` | Proposes or accepts a call | "Happy to chat Tuesday" |
| `pricing_question` | Any question about cost or plans | "What does it cost for 5 seats?" |
| `objection` | A specific reason to hesitate | "We already use Apollo" |
| `not_now` | Right person, wrong time | "Circle back next quarter" |
| `not_interested` | Declines, no reason | "Not for us, thanks" |
| `wrong_person` | Not their remit, no alternative named | "I don't handle this" |
| `referral` | Names someone else or a route in | "Speak to Sarah in ops" |
| `unsubscribe` | Opt-out in any phrasing | "Take me off this list" |
| `complaint` | Anger, spam report, legal threat | "This is unsolicited spam" |
| `auto_reply` | OOO, ticket ack, vacation | "I'm away until Monday" |
| `bounce_notice` | Delivery status notification | "550 mailbox unavailable" |
| `vendor_pitch` | Someone selling to you | "We help companies like yours…" |
| `unrelated` | Wrong context, accidental, spam | "Your invoice is attached" |
| `needs_human` | Ambiguous or multi-intent | "Interesting — but who are you?" |

## Labelling rules

1. Label the **primary** intent — what the sender wants from you.
2. Tone never changes the label. An angry opt-out is `unsubscribe`, not `complaint`... unless they threaten or report you, which is `complaint`.
3. If you hesitate for more than five seconds, it is `needs_human`. The hesitation is the data.
4. Do not re-label to make a model look better. The set exists to find failures, not to hide them.
5. Never label with a model you have not evaluated.

## How the sets are used

- Before promoting a model or changing a prompt (`T-5.3` blocks CI on regression).
- When setting a threshold: pick the confidence at which your accuracy is acceptable, not the one that looks high.
- After a bad week in production: add the failures to the set. That is the only maintenance it needs.
