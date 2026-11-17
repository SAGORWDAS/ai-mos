# Build status - 17 November 2026

Version 0.5.0 public beta. The local agency workflow is implemented and tested. **The entire original plan is not fully accepted.** [PLAN-COVERAGE.md](PLAN-COVERAGE.md) accounts for all 58 tasks and 14 acceptance areas without treating a manifest or mock test as production evidence.

## New in 0.5.0

Business details are entered by workspace owners inside the app when needed, not required to build/install it. Autopilot runs a bounded internal campaign graph from one request, optionally researching/importing observed contacts, drafting selected contacts and preparing exact approvals. Provider setup guidance displays connection requirements and callback addresses. Production remains separately gated. See AUTOMATION.md.

## Implemented

Accounts/workspaces/roles/invitations, offline recovery/TOTP/member administration; brand profiles/pricing/claims; text/PDF/public-website ingestion; lexical and optional embedding retrieval; twenty manifests and shared durable engine; plans/DAG/jobs/cancellation; CRM/CSV/Brave research/observed-address enrichment; sourced personalisation; grounded drafts/version guards; exact approvals/suppression/caps; Gmail and Resend adapters; Google OAuth and opt-in scheduled inbox; native approved publication/enquiry capture/SVG cards; Calendar; Stripe Checkout and lifecycle receipts; onboarding/support/internal automation/follow-ups; learning/analytics/expenses/export; encrypted connections; atomic budgets/unknown-cost reconciliation/validated caching; RLS/migrations/audit/emergency stop; backup and restore tools.

Real provider adapters are tested using controlled HTTP responses and signed synthetic events. This is distinct from running them successfully against your own accounts. No real recipient messages, paid advertising or financial transactions were performed during development.

## Verification evidence

- Local regression suites: **90 Python tests passed**, including **14 native PostgreSQL tests** with separate restricted API/worker logins. One upstream Starlette/httpx deprecation warning remains.
- PostgreSQL 16 backup/restore into a different empty database verified counts, audit content, restricted queue function ownership and RLS. SQLite backup/restore and pre-upgrade data preservation are also checked.
- PGlite/pgvector regression exercises all **40 tenant tables**, two organizations, missing context, cross-tenant references, immutable payments/audit/provider receipts and vector isolation. Native PostgreSQL tests also exercise fallback retrieval when pgvector is unavailable.
- Specification checks pass: 23 modules, 20 agents, 18 tools, seven phases, 58 matching capsules, four JSON schemas, dependency and cycle failure paths.
- Ruff, TypeScript and optimized Next.js build pass. Frontend production-dependency audit reports zero vulnerabilities at verification time.
- Windows launcher restart, existing QA database upgrade and automatic private pre-upgrade backup succeeded. HTTP smoke verified signup, brand, CRM, background drafting, approval and sandbox send.
- Browser verification saved sourced contact edits, published an approved local service page, submitted an actual HTML form and observed the enquiry in the private inbox. The form test exposed and fixed a referrer/origin mismatch. Earlier sandbox walkthrough covered planning through customer onboarding. Screenshots contain synthetic fixtures only.
- All four v0.4.0 hosted CI jobs passed. The v0.5.0 CI result is recorded with its release after push; exact earlier evidence is in RELEASE-VERIFICATION.md.

## Remaining implementation and evidence

External social-network/WordPress publication, paid-ad execution, AI raster-image generation, attachments/OCR, managed identity/email verification and automatic password-reset email, provider-level global calendar slot locking, automated search-price reconciliation, full campaign attribution and large-scale monitoring/load/failure certification remain outside this beta. The original qualification/model accuracy benchmarks and per-role golden sets are not complete. Only three supplied labelled reply examples plus focused boundary regressions are evaluated; that is not a representative benchmark.

Some specialized agent roles share constrained templates and internal tools rather than independent production services. Copy is deliberately restricted to approved facts and reviewed prospect observations. A broad creative agency writing system still needs representative quality evaluation and richer evidence-aware generation.

Business/provider gates remain: actual offer/pricing/claims/policies, selected audience, real credentials/grants, eligible merchant account, domain authentication, live deliverability, priced model benchmarks and live replay/failure drills. No software can guarantee client acquisition or business performance.

`APP_ENV=production` refuses startup pending deployment review. SQLite uses application scoping; PostgreSQL runtime identities enforce RLS. HTTPS, secure cookies, trusted proxy addresses, hosting, monitoring, persistent secrets and operational recovery must be configured before public client use. A paused workspace cannot recall an already in-flight provider request. Localhost publication is not public internet hosting.

The original Downloads folder remains untouched. Private accounts, databases, encryption keys, logs and dependencies are excluded from public source packages. No license grant is inferred merely from making the source public.
