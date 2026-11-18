# Original plan coverage - v0.10.0

**Not all original requirements are complete.** Implemented means the listed application behavior exists with local tests; it does not certify real-account acceptance, every clause of the original capsule, business quality or production operation. Partial means additional development or evidence remains. External gate requires actual business/account input.

See BUILD-STATUS.md for test evidence and RELEASE-VERIFICATION.md for the public release CI result.


Review totals: **37 Implemented, 15 Partial, 6 External gate**. See [v0.10.0 verification](VERIFICATION-0.10.0.md) and the historical [v0.5.1 review](REVIEW-2026-11-17.md).

## PH-0 - Decisions and spikes

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-0.1 | payment provider viability | External gate | Stripe adapter exists; merchant eligibility/account decision awaits owner. |
| T-0.2 | openrouter account and credit | External gate | Gateway exists; actual credit and priced real completions await account. |
| T-0.3 | model benchmark | External gate | 50 real examples across three candidates have not been scored. |
| T-0.4 | sending domain and DNS | External gate | Actual sending domain and DNS authentication required. |
| T-0.5 | deliverability spike | External gate | Five real seed inbox placements cannot be tested with placeholders. |
| T-0.6 | legal basis and suppression | Partial | Suppression and evidence fields work; jurisdiction-specific policy remains owner review. |
| T-0.7 | brand brain content | External gate | Brand editor supports inputs; actual ICP/pricing/claims remain user supplied. |
| T-0.8 | evaluation dataset | Partial | Fixture format and small regressions exist; 100 outreach/200 labelled replies remain. |
| T-0.9 | cost model worksheet | Partial | Interactive monthly cost/funnel planner, actual ledger and templates exist; real provider prices and review expenses remain owner supplied. |
| T-0.10 | decision log | Implemented | All twelve ADRs record an implemented decision or explicit deferral with an assigned maintainer/workspace-owner role; pending model-catalog and live decisions remain visible. |

## PH-1 - Foundation

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-1.1 | repo CI compose stack | Implemented | Public repository and all four CI jobs passed, including executed Compose HTTP workflow; see RELEASE-VERIFICATION.md. |
| T-1.2 | auth orgs memberships | Implemented | Signup, owner, roles, invitations, workspace switching, recovery and TOTP tested. |
| T-1.3 | migrations 01-06 with RLS | Implemented | Versioned migrations and forced RLS cover all current tenant tables. |
| T-1.4 | ai gateway registry ledger | Implemented | Tenant-scoped verified model IDs, advertised-price snapshots and dates bind to the connection version. Stale verification refreshes automatically; missing/expired verification refuses connected generation. Every attempt stores its historical snapshot; cost/refusal/timeout/reconciliation paths are tested. Catalog verification does not claim model quality (ADR-06). |
| T-1.5 | task runtime and scheduler | Implemented | Durable claims, DAG scheduling, retries and cancellation tested. |
| T-1.6 | tool gateway and read tools | Implemented | All 18 IDs route through schema, permission, policy, budget, approval, idempotency, execution and receipt workflows. Unknown calls, argument/schema failures and guard refusals are durably audited; cross-tenant failure tests pass. |
| T-1.7 | brand brain | Implemented | Text/PDF/website ingestion and cited keyword/embedding retrieval implemented. |
| T-1.8 | approvals model and api | Implemented | Frozen payload/hash, expiry, edit invalidation and single execution tested. |
| T-1.9 | audit logs tracing logging | Implemented | Allowlisted JSON request/task/tool events, stable command workflow traces, rejection logs/audit rows and append-only PostgreSQL grants tested. Supplied API/worker launchers use structured logging without raw query-string access logs. |
| T-1.10 | budgets and enforcement | Implemented | Atomic monthly reservations, caps, cost settlement and cache lineage tested. |
| T-1.11 | settings roles emergency stop | Implemented | Roles, owner administration and emergency stop enforced. |
| T-1.12 | usage and cost screens | Implemented | Query-backed day/agent/type/model/result groups drill into exact paginated request/task ledger rows; costs and holds remain separate. |

## PH-2 - Marketing intelligence

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-2.1 | command center parse confirm | Implemented | Structured command fields, missing-information handling and plan review implemented. |
| T-2.2 | planner (CMO) | Implemented | Planner output validates against the plan schema. |
| T-2.3 | task graph execution | Implemented | Dependency/cycle guards and a completed 20-task graph with no duplicate content or lost jobs are tested. |
| T-2.4 | research agent | Implemented | Uncited or modified research evidence is rejected and not cached. Source records/dates are retained; provider search reuses a tenant/account-version-bound 24-hour receipt cache. Broader live research quality remains an external evaluation concern. |
| T-2.5 | strategy agent | Implemented | Plans use recorded audience/positioning/pricing, bounded channel choices and owner-entered USD allowances. Invented prices, changed facts and budget-range over-allocation are rejected, costed and excluded from cache. |
| T-2.6 | content agent | Implemented | Grounded content and prohibited-claim guards tested. |
| T-2.7 | approval center ui | Implemented | Approval UI, cap enforcement and reviewed bulk workflow implemented. |
| T-2.8 | overview and analytics v1 | Implemented | Query-backed analytics; real/test gross, refund and net amounts separated. |

## PH-3 - Acquisition

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-3.1 | prospect data adapter | Partial | Brave search/observed addresses carry source references, dates, a 24-hour search/90-day observation cache and optional configured-price USD accrual split across results. Actual invoice reconciliation and broader licensed contact adapters remain. |
| T-3.2 | dedupe and enrichment | Implemented | Tenant email deduplication, source evidence and safe public enrichment tested. |
| T-3.3 | qualification scoring | Partial | Versioned recorded feature snapshots and owner-configurable thresholds are used consistently by API, workflows, Autopilot and metrics. Rescoring preserves later pipeline stages. Model feature extraction and representative 85% label-match acceptance remain. |
| T-3.4 | crm entities and pipeline | Implemented | CRM stages and actor activity records implemented. |
| T-3.5 | mailbox connection read | Implemented | Known-contact incremental paged Gmail import, threads and opt-in schedule tested. |
| T-3.6 | send path suppression and caps | Implemented | Suppression and atomic caps enforced at dispatch; provider receipts tested. |
| T-3.7 | outreach drafting claim check | Implemented | Exactly one corrective generation is attempted after rejection; both attempts are costed, and a second invalid result creates no draft. |
| T-3.8 | dispatch with approval | Implemented | Versioned edits void approvals; dispatch and ambiguous receipts tested. |
| T-3.9 | reply sync and classification | Partial | Sync, closed labels, stored conservative-rules version and opt-out ordering tested. Whole-reply checks prevent quoted/ambiguous keyword matches from authorizing automatic sends. Representative classifier/model quality remains. |
| T-3.10 | reply drafting and L4 option | Implemented | Owner-reviewed exact-template standing policy is off by default, capped and expiring; revocation, contactability and weekly effect digest tested. Pricing/refunds/contracts/disputes cannot be authorized by this API. |

## PH-4 - Conversation and revenue

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-4.1 | calendar adapter availability | Implemented | Controlled free/busy contracts and a 45-second read cache are tested. Booking bypasses the read cache and rechecks. |
| T-4.2 | meeting propose confirm book | Partial | Proposal/approval/idempotent booking and local conflicts tested; global external calendar races remain. |
| T-4.3 | payment adapter and webhook | Implemented | Stripe signatures, matching payments, renewals, refunds/disputes and replay tested with fixtures. |
| T-4.4 | customers subscriptions gating | Implemented | Payments/subscriptions are changed through controlled payment receipt paths, not agent tools. |
| T-4.5 | checkout link tool | Implemented | Checkout receipt yields a URL; redirects do not mark paid. |
| T-4.6 | onboarding triggers | Implemented | Customer/onboarding creation follows verified matching payment receipts. |
| T-4.7 | automation center v1 | Implemented | Bounded nonrecursive internal workflows and persisted runs tested. |

## PH-5 - Measurement and learning

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-5.1 | attribution | Partial | First/last/linear gross-payment campaign attribution, automatic outreach touchpoints and manual evidence records work. Signed owned-page enquiry source capture, model-cost/refund allocation and funnel credits are implemented. Historical/ambiguous receipts and customers with no observed source remain explicitly unassigned; cross-device and third-party conversions need evidence. |
| T-5.2 | cost per outcome | Partial | Model cost, expense/ad-spend evidence and outcome credits produce recorded CAC/CPL; complete external/non-USD costs still need evidence and no FX is guessed. |
| T-5.3 | evaluation in CI | Partial | Three supplied reply cases plus 44 synthetic cases and an evaluation/prediction CLI run locally/in CI. Representative model/prompt promotion benchmarks remain. |
| T-5.4 | learning records | Implemented | Learning records require workspace evidence and effect size. |
| T-5.5 | support and retention | Partial | Support and lifecycle views/escalations implemented; broader live retention quality remains. |
| T-5.6 | seo social creative | Partial | SEO/social/creative drafts, SVG cards, reviewed WordPress.com/Jetpack and LinkedIn member publishing work against HTTP fixtures. Private raster generation via an enabled image model and reviewed Meta link-ad execution are implemented with HTTP fixtures. Company-page/other-network publication and live acceptance remain. |

## PH-6 - Scale and hardening

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-6.1 | second tenant audit | Partial | Two-tenant API/native SQL/RLS tests pass; independent exhaustive tenant audit remains. |
| T-6.2 | load and queue tuning | Implemented | Controlled 10x burst (baseline two, twenty tasks) under four workers, replayed requests and twenty HTTP-mocked provider deliveries has zero duplicate provider IDs or lost jobs on SQLite/PostgreSQL. Production capacity/SLO certification remains separate. |
| T-6.3 | backup and restore drill | Implemented | SQLite and PostgreSQL restore drills verify counts/audit/RLS without active DB replacement. |
| T-6.4 | security review | Partial | Recovery/MFA/encryption/throttles/scope checks, controlled-pilot signup and real runtime-role/schema/RLS/queue preflight are implemented. Validation deployment and evidence capture exist; independent production security review remains. |
| T-6.5 | P1 P2 agent rollout | Partial | All twenty manifests ship; representative per-role golden sets and staged rollout remain. |

## Acceptance areas

| Area | Implemented evidence and limit |
|---|---|
| AC-01/02 | 44 tenant tables; native PostgreSQL restricted-role and PGlite RLS/foreign-key tests. Independent exhaustive audit remains. |
| AC-03 | Suppression blocks sandbox/live dispatch; signed bounce/complaint handling tested. |
| AC-04 | Unique tenant idempotency, task identity and effect receipt/replay tests; large-load certification remains. |
| AC-05 | Frozen payload, version invalidation, expiry and single-use approval tests. |
| AC-06 | CRM import/enrichment deduplication and source preservation tests. |
| AC-07 | Atomic budget reservations and daily caps under concurrency; unknown charges held. |
| AC-08 | Model attempts including failure/refusal/cache/timeout have attributable ledger evidence. |
| AC-09 | Local conflict/idempotent Calendar insert checks; provider-wide slot locking is not guaranteed. |
| AC-10 | Signed matching Stripe/Resend callbacks and replay tests; live account drills pending. |
| AC-11 | Registry permission ceiling and role checks; no arbitrary agent payment write tool. |
| AC-12 | Emergency stop blocks new work; cannot recall an already in-flight external request. |
| AC-13 | Isolated SQLite/PostgreSQL backup/restore verifies integrity, counts, audit and restricted access. |
| AC-14 | Grounding/prohibited-claim guards reject uncited copy; free-form creative quality remains constrained. |
