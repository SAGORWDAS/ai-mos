# Cost model — T-0.9

The interactive worksheet is available in **Operations / Usage & cost / Campaign cost planner**. It computes variable/fixed cost, projected funnel counts, CPL and CAC from your entered prices/rates. Assumptions remain separate from recorded ledgers and reset on leaving the screen.

Fill with **real prices**, then read the answer at the bottom. Every figure is per 100 discovered prospects unless stated.

## 1. Direct cost lines

| Line | Unit price | Units per 100 | Total |
|---|---|---|---|
| Prospect data | $[ ] per record | [ ] | $[ ] |
| Email verification | $[ ] per record | [ ] | $[ ] |
| Sending infrastructure | $[ ] per mailbox/month | [ ] mailboxes | $[ ] |
| Sending platform | $[ ] per month | 1 | $[ ] |
| Model inference (T1) | $0.0002 per task | [ ] tasks | $[ ] |
| Model inference (T2) | $0.002 per task | [ ] tasks | $[ ] |
| Human review | [ ] min per batch × $[ ] per hour | [ ] batches | $[ ] |
| **Total per 100 prospects** | | | **$[ ]** |

## 2. Funnel assumptions

Use your own numbers; if you have none yet, use these deliberately conservative ones.

| Stage | Rate | Count from 100 |
|---|---|---|
| Discovered → qualified | [50%] | [50] |
| Qualified → delivered | [90%] | [45] |
| Delivered → reply | [5%] | [2.25] |
| Reply → meeting | [30%] | [0.7] |
| Meeting → customer | [30%] | [0.2] |

## 3. Derived numbers

| Metric | Formula | Value |
|---|---|---|
| Cost per qualified lead | total ÷ qualified | $[ ] |
| Cost per reply | total ÷ replies | $[ ] |
| **Cost per customer (CAC)** | **total ÷ customers** | **$[ ]** |
| Inference as % of total | inference ÷ total | [ ]% |

## 4. Infrastructure (fixed, monthly)

| Item | Monthly |
|---|---|
| VPS / app host | $[ ] |
| Managed Postgres | $[ ] |
| Redis | $[ ] |
| Object storage | $[ ] |
| Error tracking | $[ ] |
| **Fixed total** | **$[ ]** |

> Run locally until the first paying customer. Nothing in PH-1 to PH-3 needs a server, and a $0 fixed cost changes the break-even arithmetic completely.

## 5. The two numbers that decide whether to proceed

1. **CAC.** If it exceeds a third of first-year revenue per customer, the motion is too expensive — widen the ICP or raise the price before spending more.
2. **Reply rate.** Below 2% on a segment that should work means the list, the offer or the sending reputation is wrong. More volume will not fix it.
