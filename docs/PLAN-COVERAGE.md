# Original plan coverage - v0.4.0

**Not all original requirements are complete.** Implemented means the listed application behavior exists with local tests; it does not certify real-account acceptance, every clause of the original capsule, business quality or production operation. Partial means additional development or evidence remains. External gate requires actual business/account input.

See BUILD-STATUS.md for test evidence and RELEASE-VERIFICATION.md for the public release CI result.


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
| T-0.9 | cost model worksheet | Partial | Cost templates and ledger exist; real provider prices and review expenses remain. |
| T-0.10 | decision log | Partial | Decision templates preserved; original ADR closure is not asserted. |

## PH-1 - Foundation

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-1.1 | repo CI compose stack | Implemented | Public repository and all four CI jobs passed, including executed Compose HTTP workflow; see RELEASE-VERIFICATION.md. |
| T-1.2 | auth orgs memberships | Implemented | Signup, owner, roles, invitations, workspace switching, recovery and TOTP tested. |
| T-1.3 | migrations 01-06 with RLS | Implemented | Versioned migrations and forced RLS cover all current tenant tables. |
| T-1.4 | ai gateway registry ledger | Implemented | Gateway, schema validation, cost ledger, timeout holds and reconciliation tested. |
| T-1.5 | task runtime and scheduler | Implemented | Durable claims, DAG scheduling, retries and cancellation tested. |
| T-1.6 | tool gateway and read tools | Partial | Registry ceilings and controlled tools enforced; not every original service/tool is independent. |
| T-1.7 | brand brain | Implemented | Text/PDF/website ingestion and cited keyword/embedding retrieval implemented. |
| T-1.8 | approvals model and api | Implemented | Frozen payload/hash, expiry, edit invalidation and single execution tested. |
| T-1.9 | audit logs tracing logging | Partial | Audit/trace and hidden SQL parameters implemented; deployment-wide observability review remains. |
| T-1.10 | budgets and enforcement | Implemented | Atomic monthly reservations, caps, cost settlement and cache lineage tested. |
| T-1.11 | settings roles emergency stop | Implemented | Roles, owner administration and emergency stop enforced. |
| T-1.12 | usage and cost screens | Partial | Attempt ledger and agent totals available; original full day/type drill-down UI remains. |

## PH-2 - Marketing intelligence

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-2.1 | command center parse confirm | Implemented | Structured command fields, missing-information handling and plan review implemented. |
| T-2.2 | planner (CMO) | Implemented | Planner output validates against the plan schema. |
| T-2.3 | task graph execution | Partial | Dependency execution and cycle guards tested; exact original 20-task acceptance drill remains. |
| T-2.4 | research agent | Partial | Claim citations enforced and public research available; broad research quality benchmark remains. |
| T-2.5 | strategy agent | Partial | Pricing is human supplied and claims constrained; full strategy budget-range acceptance remains. |
| T-2.6 | content agent | Implemented | Grounded content and prohibited-claim guards tested. |
| T-2.7 | approval center ui | Implemented | Approval UI, cap enforcement and reviewed bulk workflow implemented. |
| T-2.8 | overview and analytics v1 | Implemented | Query-backed analytics; real/test gross, refund and net amounts separated. |

## PH-3 - Acquisition

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-3.1 | prospect data adapter | Partial | Brave search/observed addresses with provenance; actual per-record provider cost is manual. |
| T-3.2 | dedupe and enrichment | Implemented | Tenant email deduplication, source evidence and safe public enrichment tested. |
| T-3.3 | qualification scoring | Partial | Deterministic score exists; representative 85% label-match benchmark remains. |
| T-3.4 | crm entities and pipeline | Implemented | CRM stages and actor activity records implemented. |
| T-3.5 | mailbox connection read | Implemented | Known-contact incremental paged Gmail import, threads and opt-in schedule tested. |
| T-3.6 | send path suppression and caps | Implemented | Suppression and atomic caps enforced at dispatch; provider receipts tested. |
| T-3.7 | outreach drafting claim check | Partial | Grounding rejects invalid copy; original single corrective-generation retry is not asserted. |
| T-3.8 | dispatch with approval | Implemented | Versioned edits void approvals; dispatch and ambiguous receipts tested. |
| T-3.9 | reply sync and classification | Partial | Sync/classification/opt-out order tested; representative classification quality benchmark remains. |
| T-3.10 | reply drafting and L4 option | Partial | Reviewed reply drafts and human escalation work; autonomous L4 sending stays disabled. |

## PH-4 - Conversation and revenue

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-4.1 | calendar adapter availability | Partial | Live free/busy adapter works against fixtures; original sub-60-second availability cache remains. |
| T-4.2 | meeting propose confirm book | Partial | Proposal/approval/idempotent booking and local conflicts tested; global external calendar races remain. |
| T-4.3 | payment adapter and webhook | Implemented | Stripe signatures, matching payments, renewals, refunds/disputes and replay tested with fixtures. |
| T-4.4 | customers subscriptions gating | Implemented | Payments/subscriptions are changed through controlled payment receipt paths, not agent tools. |
| T-4.5 | checkout link tool | Implemented | Checkout receipt yields a URL; redirects do not mark paid. |
| T-4.6 | onboarding triggers | Implemented | Customer/onboarding creation follows verified matching payment receipts. |
| T-4.7 | automation center v1 | Implemented | Bounded nonrecursive internal workflows and persisted runs tested. |

## PH-5 - Measurement and learning

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-5.1 | attribution | Partial | Customer-to-lead linkage exists; complete campaign/multitouch attribution remains. |
| T-5.2 | cost per outcome | Partial | Expenses and recorded CAC/CPL supported; actual complete costs must be supplied. |
| T-5.3 | evaluation in CI | Partial | Small supplied reply regressions run in CI; full model/prompt promotion benchmarks remain. |
| T-5.4 | learning records | Implemented | Learning records require workspace evidence and effect size. |
| T-5.5 | support and retention | Partial | Support and lifecycle views/escalations implemented; broader live retention quality remains. |
| T-5.6 | seo social creative | Partial | SEO/social/creative drafts and SVG cards work; external social and raster-image adapters remain. |

## PH-6 - Scale and hardening

| Task | Original deliverable | Status | Evidence or remaining work |
|---|---|---|---|
| T-6.1 | second tenant audit | Partial | Two-tenant API/native SQL/RLS tests pass; independent exhaustive tenant audit remains. |
| T-6.2 | load and queue tuning | Partial | Concurrency/race regressions pass; original 10x burst/load certification remains. |
| T-6.3 | backup and restore drill | Implemented | SQLite and PostgreSQL restore drills verify counts/audit/RLS without active DB replacement. |
| T-6.4 | security review | Partial | Recovery/MFA/encryption/throttles/scope/dependency checks implemented; production security review remains. |
| T-6.5 | P1 P2 agent rollout | Partial | All twenty manifests ship; representative per-role golden sets and staged rollout remain. |

## Acceptance areas

| Area | Implemented evidence and limit |
|---|---|
| AC-01/02 | 40 tenant tables; native PostgreSQL restricted-role and PGlite RLS/foreign-key tests. Independent exhaustive audit remains. |
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
