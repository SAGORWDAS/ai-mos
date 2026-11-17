# v0.9.0 verification

18 November 2026. All businesses, contacts, accounts, provider responses and payments used for development verification are synthetic. No real recipient messages, publication, advertising purchases or financial transactions were made.

## Added behavior

- Tenant-scoped model registry rows retain the exact selected ID, operation, advertised USD price snapshot and verification date. Authority binds to the connection version/key; rotating a key cannot reuse old verification. API responses and exports omit the internal fingerprint and credentials.
- Account verification checks selected model metadata using the same bounded provider client. Owners can refresh the catalog before enabling an account. Connected generation requires fresh catalog evidence by default, even before cache reuse. A development override cannot bypass the gate in production.
- Aging evidence refreshes automatically, with shared concurrent refreshes and a one-hour retry interval. A transient catalog outage preserves still-fresh evidence only for the unchanged connection. Missing/expired evidence refuses generation without a provider charge.
- Every generation attempt copies the registry pricing evidence used at that time. A subsequent refresh cannot rewrite old usage snapshots. Catalog checks do not certify model quality or a guaranteed final bill.
- Optional OpenRouter request allowances accept ordinary USD, including zero. Known estimates above the allowance refuse generation before a charge. Text reservations use UTF-8 bytes plus overhead and maximum output; chat routing sends advertised provider-price ceilings. Images reserve the full allowance because generic rates do not fully specify every tier. Unknown provider costs retain holds for reconciliation.
- Stop state, membership, connection version and active task attempt/lease are rechecked under the tenant mutex at reservation. Each generation renews its own active lease. Budget editing reacquires the mutex after budget initialization, and effect dispatch refreshes the budget under that mutex. Monthly configured limits and daily send caps carry forward while counters reset.
- Integrations exposes model/catalog evidence and a plain-dollar request allowance. Placeholder settings remain disabled. Browser QA found and corrected a summary that showed the deployment default instead of the saved placeholder allowance.

## Local evidence

The full Python run passed 182 tests, including 43 native PostgreSQL tests with restricted API/worker identities. After the allowance-display correction and two added regressions, all 11 focused registry tests passed (184 distinct backend tests covered across those runs). One upstream Starlette/httpx deprecation warning remains.

Twelve frontend tests, Ruff, TypeScript, optimized Next build, specification validation and 43-table PGlite forced-RLS checks pass. Cross-tenant model-registry foreign-key assignment is rejected. The Windows upgrade/restart preserved the synthetic QA database. HTTP smoke exercised signup, CRM, durable drafting, exact approval, sandbox delivery and one-brief campaign replay.

Chromium verified placeholder entry and the saved $0.05 summary with catalog refresh still disabled. The changed catalog and provider form, both expanded, were checked at widths 320, 360, 390, 768, 1024 and 1440. No document overflow or unlabelled visible input was found. See responsive-audit-0.9.0.json; earlier full-workspace observations remain in the v0.8 audit. This is not all-device or WCAG certification.

Hosted CI and source archive verification are recorded in the GitHub release notes. Original-plan coverage now records 37 Implemented, 15 Partial and 6 External gate. Representative model/prompt promotion benchmarks, model-assisted feature/intent extraction, independent operational/security review and real-account acceptance remain open. Production startup remains gated; the full PDF plan and 99% automation target are not yet accepted.
