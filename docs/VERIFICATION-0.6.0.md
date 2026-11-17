# v0.6.0 verification

Date: 17 November 2026. Synthetic development verification; no real recipients, public posts, ad purchases or financial transactions.

## Covered behavior

- One-brief setup creates a business, sample contact where requested, campaign and durable plan in one transaction. Duplicate requests reuse the same task; changed payloads conflict. Missing enabled research rolls back all new setup rows.
- Discovered same-domain contacts are scored and drafted automatically. Sending remains blocked without reviewed contactability. Drafts join the final review dependencies before it can run.
- All 18 tool IDs route to guarded workflow/read/compute handlers; manifest ceilings still refuse disallowed agents/actions. Tools cannot mint payment facts or bypass execution approvals.
- Exactly one corrective generation attempt is allowed for rejected outreach. A second invalid result persists no draft. Both attempts remain in the cost ledger.
- A 20-task graph completes without lost tasks or duplicate content. This is not a 10x production burst/load certification.
- Owner opt-in prepares clear inbox replies once; ambiguous replies stay with a human. Follow-up drafts enter the review queue. Disconnect clears the automatic-draft policy.
- First/last/linear campaign attribution conserves integer payment units and separates currencies/test/live records. Future and out-of-window interactions are excluded. Tenant-scoped replay and cost linkage are tested.
- WordPress.com and LinkedIn member publishing use fixed provider origins, exact-copy review, version-bound connections and durable effect receipts. Missing/ambiguous receipts do not trigger another post. Queued effects recheck brand facts. These are controlled HTTP contracts, not real-account acceptance.
- Calendar read availability is cached at most 45 seconds; booking bypasses that read cache and rechecks.
- Fictional sample AI calls remain simulated despite an enabled model connection. Live checkout/sending/booking paths refuse sample businesses.

## Local checks

Full test counts and hosted CI are recorded in BUILD-STATUS.md and the tagged release. Ruff, frontend request/setup tests, TypeScript, optimized Next build, specification validation and 41-table PGlite/RLS checks pass. HTTP smoke exercises the actual running API/worker, private frontend headers, original send workflow and the new one-brief preparation/replay flow.

The 44 additional reply examples are explicitly synthetic. The evaluation CLI reports accuracy, per-label precision/recall, abstention and data provenance; it can consume independently labelled datasets and externally produced prediction JSONL. Synthetic success is not a representative live-model benchmark.

## Small-workspace API timings

Measured against the rebuilt local application with a fresh synthetic workspace, 20 sequential requests per route:

| Route | p50 | p95 |
|---|---:|---:|
| `/v1/workspace` | 12.1 ms | 16.8 ms |
| `/v1/analytics` | 13.4 ms | 19.8 ms |
| `/v1/attribution/report` | 7.1 ms | 10.1 ms |

These numbers exclude browser rendering, external provider latency and production concurrency. Reproduce with `AI_MOS_SMOKE_TIMINGS=true` and `scripts/smoke-http.py` against an explicitly selected development instance. The script creates synthetic fixture data.

## Visual verification limit

The earlier v0.5.1 Chromium matrix is historical evidence, not a rerun against every v0.6.0 screen. Native browser verification for this increment was blocked by an automatic URL-confidence safety check. New setup flow behavior is covered by frontend component tests and HTTP regressions; final visual/accessibility/device checks remain outstanding. Do not describe this release as flawless, all-device certified or production approved.

## Provider contracts consulted

[WordPress.com sites identity](https://developer.wordpress.com/docs/api/1.1/get/me/sites/), [WordPress API getting started](https://developer.wordpress.com/docs/api/getting-started/), and [LinkedIn Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-09). The LinkedIn contract pins API version 202609; review provider version support before live activation.
