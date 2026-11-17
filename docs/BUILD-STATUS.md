# Build status - 17 November 2026

Version 0.6.0 public beta. The local agency workflow is implemented and tested. **The entire original plan is not fully accepted.** [PLAN-COVERAGE.md](PLAN-COVERAGE.md) accounts for all 58 tasks and 14 acceptance areas without treating a manifest or mock test as production evidence.

## New in 0.6.0

[One-brief setup](DAY-ONE.md), automatic discovered-contact scoring/drafts, owner-enabled reply drafting, follow-up approvals, guarded tool workflow dispatch, one corrective drafting attempt, 45-second Calendar reads, first/last/linear gross campaign attribution, and reviewed WordPress.com/LinkedIn member publishing. New [verification evidence](VERIFICATION-0.6.0.md) separates synthetic tests, local latency and the outstanding visual review.

## New in 0.5.1

The [system review](REVIEW-2026-11-17.md) adds public SEO metadata/sitemaps and staging defaults, publication withdrawal on changed facts, streaming upload bounds, total fetch deadlines, atomic workspace snapshots/session binding, cross-tab refresh and responsive/accessibility corrections. See [SEO.md](SEO.md) for later domain configuration. Four frontend request-helper tests and recorded Chromium responsive checks were added.

## New in 0.5.0

Business details are entered by workspace owners inside the app when needed, not required to build/install it. Autopilot runs a bounded internal campaign graph from one request, optionally researching/importing observed contacts, drafting selected contacts and preparing exact approvals. Provider setup guidance displays connection requirements and callback addresses. Production remains separately gated. See AUTOMATION.md.

## Implemented

Accounts/workspaces/roles/invitations, offline recovery/TOTP/member administration; brand profiles/pricing/claims; text/PDF/public-website ingestion; lexical and optional embedding retrieval; twenty manifests and shared durable engine; plans/DAG/jobs/cancellation; CRM/CSV/Brave research/observed-address enrichment; sourced personalisation; grounded drafts/version guards; exact approvals/suppression/caps; Gmail and Resend adapters; Google OAuth and opt-in scheduled inbox; native approved publication/enquiry capture/SVG cards; Calendar; Stripe Checkout and lifecycle receipts; onboarding/support/internal automation/follow-ups; learning/analytics/expenses/export; encrypted connections; atomic budgets/unknown-cost reconciliation/validated caching; RLS/migrations/audit/emergency stop; backup and restore tools.

Real provider adapters are tested using controlled HTTP responses and signed synthetic events. This is distinct from running them successfully against your own accounts. No real recipient messages, paid advertising or financial transactions were performed during development.

## Verification evidence

- Local regression suites: **128 Python tests passed**, including **20 native PostgreSQL tests** with separate restricted API/worker logins. One upstream Starlette/httpx deprecation warning remains.
- PostgreSQL 16 backup/restore into a different empty database verified counts, audit content, restricted queue function ownership and RLS. SQLite backup/restore and pre-upgrade data preservation are also checked.
- PGlite/pgvector regression exercises all **41 tenant tables**, two organizations, missing context, cross-tenant references, immutable payments/audit/provider receipts and vector isolation. Native PostgreSQL tests also exercise fallback retrieval when pgvector is unavailable.
- Specification checks pass: 23 modules, 20 agents, 18 tools, seven phases, 58 matching capsules, four JSON schemas, dependency and cycle failure paths.
- Ruff, TypeScript and optimized Next.js build pass. Frontend production-dependency audit reports zero vulnerabilities at verification time.
- Windows launcher restart, existing QA database upgrade and automatic private pre-upgrade backup succeeded. HTTP smoke verified signup, brand, CRM, background drafting, approval and sandbox send.
- Browser verification saved sourced contact edits, published an approved local service page, submitted an actual HTML form and observed the enquiry in the private inbox. The form test exposed and fixed a referrer/origin mismatch. Earlier sandbox walkthrough covered planning through customer onboarding. Screenshots contain synthetic fixtures only.
- All four v0.5.1 hosted CI jobs passed. The v0.6.0 result is recorded with its tagged release; exact earlier evidence is in RELEASE-VERIFICATION.md.
- Seven frontend API/setup component tests pass. Historical v0.5.1 Chromium evidence checked 27 workspace views at six widths plus authentication/public/expanded forms; machine-readable observations are in responsive-audit.json. This is not all-device or WCAG certification; browser verification of the new v0.6.0 screens remains outstanding after an automatic URL-confidence block.
- Backend and frontend dependency audits reported no known vulnerabilities at verification time. One upstream Starlette/httpx warning remains.

## Remaining implementation and evidence

Company-page/other-network publication, paid-ad execution, AI raster-image generation, attachments/OCR, managed identity/email verification and automatic password-reset email, provider-level global calendar slot locking, automated search-price reconciliation, full campaign attribution and large-scale monitoring/load/failure certification remain outside this beta. The original qualification/model accuracy benchmarks and per-role golden sets are not complete. Three supplied labelled reply examples, 44 additional synthetic cases and focused boundary regressions are evaluated; these are not a representative live-model benchmark.

Some specialized agent roles share constrained templates and internal tools rather than independent production services. Copy is deliberately restricted to approved facts and reviewed prospect observations. A broad creative agency writing system still needs representative quality evaluation and richer evidence-aware generation.

Business/provider gates remain: actual offer/pricing/claims/policies, selected audience, real credentials/grants, eligible merchant account, domain authentication, live deliverability, priced model benchmarks and live replay/failure drills. No software can guarantee client acquisition or business performance.

`APP_ENV=production` refuses startup pending deployment review. SQLite uses application scoping; PostgreSQL runtime identities enforce RLS. HTTPS, secure cookies, trusted proxy addresses, hosting, monitoring, persistent secrets and operational recovery must be configured before public client use. A paused workspace cannot recall an already in-flight provider request. Localhost publication is not public internet hosting.

The original Downloads folder remains untouched. Private accounts, databases, encryption keys, logs and dependencies are excluded from public source packages. No license grant is inferred merely from making the source public.
