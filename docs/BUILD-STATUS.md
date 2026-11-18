# Build status - 18 November 2026

Version 0.10.0 public beta. The local agency workflow is implemented and tested. **The entire original plan is not fully accepted.** [PLAN-COVERAGE.md](PLAN-COVERAGE.md) accounts for all 58 tasks and 14 acceptance areas without treating a manifest or mock test as production evidence.

## New in 0.10.0

Controlled live-validation deployment: private pilot signup, secure startup preflight for configuration and actual restricted PostgreSQL roles/schema/forced RLS/grants, an optimized HTTPS Compose stack, private configuration generation, and an owner validation center with receipt observations and append-only manual drill history. The preparation checks do not call providers or approve production. See [live-validation guide](LIVE-VALIDATION.md) and [verification](VERIFICATION-0.10.0.md). Coverage remains 37 Implemented, 15 Partial and 6 External gate; the remaining original features and real quality acceptance are not erased by adding a pilot path.

## New in 0.9.0

Tenant model catalog verification, historical per-attempt price snapshots, automatic stale-catalog refresh, owner-configured USD request allowances, advertised chat provider-price ceilings, atomic stop/connection/lease rechecks and persistent monthly budget policy. See [verification](VERIFICATION-0.9.0.md) and [model setup](MODEL-SETUP.md). Coverage now counts 37 Implemented, 15 Partial and 6 External gate.

## New in 0.8.0

Structured operational logs and complete tool-refusal auditing; versioned, configurable qualification; source/cache dates and configured-price search accrual; 24-hour research and 90-day observation reuse; strict research/strategy grounding and channel-budget bounds; safer whole-reply standing authority. See [verification](VERIFICATION-0.8.0.md) and [logging operations](ops/observability.md). Review now counts 36 Implemented, 16 Partial and 6 External gate. The model-price registry gap is explicitly reopened instead of treating configurable IDs as verified catalog rows.

## New in 0.7.0

Signed campaign enquiry links; model-cost/refund/funnel attribution; private image generation; owner-reviewed Meta link ads, partial-resource receipts, pause and spend reconciliation; expiring exact-template automatic replies and a weekly digest; query-backed usage drilldown; an interactive campaign cost planner. See [current verification](VERIFICATION-0.7.0.md). Coverage at that release was 32 Implemented, 20 Partial and 6 External gate across the original 58 tasks.

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

- Local regression suites: **168 Python tests passed**, including **38 native PostgreSQL tests** with separate restricted API/worker logins. One upstream Starlette/httpx deprecation warning remains.
- PostgreSQL 16 backup/restore into a different empty database verified counts, audit content, restricted queue function ownership and RLS. SQLite backup/restore and pre-upgrade data preservation are also checked.
- PGlite/pgvector regression exercises all **42 tenant tables**, two organizations, missing context, cross-tenant references, immutable payments/audit/provider receipts and vector isolation. Native PostgreSQL tests also exercise fallback retrieval when pgvector is unavailable.
- Specification checks pass: 23 modules, 20 agents, 18 tools, seven phases, 58 matching capsules, four JSON schemas, dependency and cycle failure paths.
- Ruff, TypeScript and optimized Next.js build pass. Frontend production-dependency audit reports zero vulnerabilities at verification time.
- Windows launcher restart, existing QA database upgrade and automatic private pre-upgrade backup succeeded. HTTP smoke verified signup, brand, CRM, background drafting, approval and sandbox send.
- Browser verification saved sourced contact edits, published an approved local service page, submitted an actual HTML form and observed the enquiry in the private inbox. The form test exposed and fixed a referrer/origin mismatch. Earlier sandbox walkthrough covered planning through customer onboarding. Screenshots contain synthetic fixtures only.
- All four v0.5.1 hosted CI jobs passed. The v0.6.0 result is recorded with its tagged release; exact earlier evidence is in RELEASE-VERIFICATION.md.
- Eleven frontend API/setup/forecast/price-input tests pass. Current Chromium review checked 29 workspace views at widths 320, 390, 768, 1024, 1280 and 1440: 174 standard and 18 expanded-view observations, no page overflow or unlabelled visible form controls. See responsive-audit-0.8.0.json. Manual browser checks verified private image preview, sandbox ad review/execution, policy enable/disable, forecast arithmetic, agent filtering, usage records, signed public enquiry capture and report refresh. This is not all-device or WCAG certification.
- Backend and frontend dependency audits reported no known vulnerabilities at verification time. One upstream Starlette/httpx warning remains.

## Remaining implementation and evidence

Representative model/prompt promotion gates, model-assisted feature/intent extraction, company-page/other-network publication, attachments/OCR, managed identity/email verification and automatic password-reset email, provider-level global calendar slot locking, automated search-price reconciliation, cross-device/third-party attribution and large-scale monitoring/load/failure certification remain outside this beta. Meta ordinary-commercial ads, private raster images, owned-enquiry tracking, cost/refund/funnel attribution and the controlled tenfold worker/provider burst now have implemented fixture-tested paths. The original qualification/model accuracy benchmarks and per-role golden sets are not complete. Three supplied labelled reply examples, 44 additional synthetic cases and focused boundary regressions are evaluated; these are not a representative live-model benchmark.

Some specialized agent roles share constrained templates and internal tools rather than independent production services. Copy is deliberately restricted to approved facts and reviewed prospect observations. A broad creative agency writing system still needs representative quality evaluation and richer evidence-aware generation.

Business/provider gates remain: actual offer/pricing/claims/policies, selected audience, real credentials/grants, eligible merchant account, domain authentication, live deliverability, priced model benchmarks and live replay/failure drills. No software can guarantee client acquisition or business performance.

`APP_ENV=production` refuses startup pending deployment review. SQLite uses application scoping; PostgreSQL runtime identities enforce RLS. HTTPS, secure cookies, trusted proxy addresses, hosting, monitoring, persistent secrets and operational recovery must be configured before public client use. A paused workspace cannot recall an already in-flight provider request or stop an already active ad campaign; use the dedicated provider pause control. Model budget reservations are separate from approved ad lifetime caps. Localhost publication is not public internet hosting.

The original Downloads folder remains untouched. Private accounts, databases, encryption keys, logs and dependencies are excluded from public source packages. No license grant is inferred merely from making the source public.
