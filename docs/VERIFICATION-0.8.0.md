# v0.8.0 verification

17-18 November 2026. All businesses, contacts, provider responses and payments used for development verification are synthetic. No real recipient messages, posts, advertising purchases or financial transactions were made.

## Added behavior

- All twelve decision records now contain an actual implementation decision or an explicit deferral and assigned owner role. The verified model/price registry is explicitly deferred in ADR-06; private model configuration is not presented as that registry.
- Tool argument/permission/policy failures are durably audited after rollback. Authenticated tool schema failures also create audit records. Allowlisted JSON request/task/tool events omit request bodies, credentials, raw query strings and raw failure text. Command tasks share a stable workflow trace. The supplied API and worker launchers load the JSON logging configuration; raw Uvicorn access logs are disabled.
- Qualification records the rubric version, feature snapshot and threshold. Owners configure the threshold inside Leads & CRM. API scoring, internal rules, Autopilot and metrics share the same assessment. Rescoring does not move contacted/converted customers back into prospect stages. Qualified status never establishes contactability. This rubric uses recorded features without a paid model call; representative model feature-extraction/label acceptance remains separate.
- Search results preserve source references and retrieval dates, with a tenant/account-version/query-bound 24-hour cache. Optional configured contract prices accrue recorded USD expenses once per successful provider request and allocate exact integer units across returned results. Cache hits add zero new provider cost. Missing prices remain unknown; this is configured-price accrual, not a provider invoice or automatic reconciliation.
- Observed contact pages reuse a 90-day cache based on the original observation time. Cache hits do not refresh that age. Owners can force a fresh read. Sources remain scoped to the business, and suppressed contacts are excluded from returned lead IDs.
- Research output must select unchanged cited evidence from the retrieved source records. Strategy output may select bounded channels but cannot invent an audience, price, positioning, capability or spending allowance. Channel maxima cannot exceed the owner's allowance. Rejected output remains costed, is marked invalid in usage and is not reused from cache. Validated research/strategy can be reused.
- Campaign setup accepts an optional USD planning allowance. It does not authorize an external purchase and is separate from model budgets. The connection form accepts an optional search price in normal USD and converts it to ledger units internally.
- Automatic replies require a clear whole reply in addition to classification and standing authority. Quoted text, mixed intent and phrases such as "not at all interested" cannot gain sending authority from a keyword match. Classification stores its conservative-rules version. Broader model/classifier quality is not claimed from these cases.

## Local evidence

168 Python tests passed, including 38 native PostgreSQL tests with restricted API/worker identities. Eleven frontend tests, Ruff, TypeScript, optimized Next build, specification checks and 42-table forced-RLS checks pass. One upstream Starlette/httpx deprecation warning remains.

The running Windows application preserved the existing QA database through upgrade/restart. HTTP smoke exercised signup, CRM, durable drafting, approval, sandbox delivery and one-brief campaign replay. Live application log inspection found valid structured task/request events using route templates without query strings.

Chromium checked 29 workspace views at six widths (174 observations) plus three expanded forms/evidence views at those widths (18 observations). No page overflow or unlabelled visible form control was found. Data is in responsive-audit-0.8.0.json. Interaction checks verified threshold persistence, preserved converted status, a completed fictional campaign with the exact $1.25 allowance and its stored pricing evidence. This is not all-device, WCAG, production-load or business-performance certification.

Hosted CI and source archive verification are recorded in this release's GitHub notes. Original-plan coverage remains explicit in PLAN-COVERAGE.md. Model registry/promotion work, representative datasets and role benchmarks, independent operational/security review and real account acceptance remain open.
