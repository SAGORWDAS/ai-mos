# v0.10.0 verification

18 November 2026. This release prepares a controlled live-validation path for the implemented workflow. It does not complete all original PDF features, certify production operation or establish 99% automation. All development contacts, businesses and provider responses remain synthetic. No real recipients, external posts, ad purchases or financial transactions were used.

## Implemented preparation

- `APP_ENV=validation` is distinct from development and production. It requires HTTPS configuration, secure cookies, one allowed website origin, a persistent valid encryption key, a strong database password, strict model catalog enforcement, a private pilot signup code and an operator review reference. Production startup remains separately refused.
- API and worker startup inspect the actual PostgreSQL login privileges, role membership, installed tables/columns, forced tenant RLS, table ownership, append-only audit grants and queue permissions. Validation runtime logins do not create or repair schema. Startup failure disposes the database engines.
- Hosted signup requires the private pilot code; normal login still uses account credentials and optional TOTP. Auth input-error responses omit submitted secrets. This controlled-code pilot is not managed identity or proof of email ownership.
- The separate validation Compose stack builds an optimized web server, separates migration/API/worker credentials, exposes only the TLS proxy and preserves database/TLS volumes. API/worker containers do not receive migrator credentials. A private generator refuses overwrite and avoids printing secrets. Public TLS requires the actual DNS hostname and hosting.
- The owner-only validation center checks setup without provider calls, supports discovery plus email or imported-contact outreach, displays connected receipt counts separately from sandbox work and downloads a review report. Marked sample profiles, suppressed contacts and reserved demo email domains do not qualify as live seed setup. Candidate profile/contact scans are bounded at 500.
- Owner-reported external drill outcomes form tenant-scoped append-only history. They never enable providers or approve production. Setup/business/software changes or 30 days stale earlier reports. Failures can still be recorded while the workspace is stopped. Manual assertions are not automated proof of quality, deliverability or provider behavior.
- Windows upgrade backups now fingerprint every migration as well as local schema code. Chat cache identity includes the system prompt, preventing reuse after its content changes.

## Local evidence

The full backend run passed 200 tests, including 47 native PostgreSQL tests. After the demo-profile/seed correction, all 15 focused validation tests and four native validation tests passed (203 distinct backend tests covered across the runs). One upstream Starlette/httpx deprecation warning remains.

Native tests successfully started the controlled validation app under a restricted API role with secure cookies/private signup and refused startup after forced RLS was removed. PGlite checks all 44 tenant tables, including append-only validation evidence and cross-tenant foreign-key boundaries. Twelve frontend tests, Ruff, TypeScript, optimized Next build and specification checks pass.

Windows upgrade/restart preserved synthetic QA data and created a private pre-upgrade backup with the updated migration fingerprint. HTTP smoke exercised signup, CRM, durable drafting, exact approval, sandbox delivery and one-brief campaign replay. Browser verification covered workflow selection, owner evidence save/history and downloaded JSON with production approval false. Changed signup and expanded validation views were reviewed at six widths; observations are retained in responsive-audit-0.10.0.json. These checks do not certify every device or WCAG conformance.

## Hosted and external boundaries

Hosted CI results and source-archive checksums are recorded in the public release notes. The additional validation job builds and starts the separate stack, checks the actual API/worker preflight, optimized web/private signup and a completed sandbox graph, and validates Caddy configuration. Its Docker-internal HTTP tests do not prove public DNS, real certificates or provider grants. Actual model quality, seed-inbox placement, signed provider drills and recovery evidence must come from the owner's controlled pilot.

Coverage remains 37 Implemented, 15 Partial and 6 External gate in PLAN-COVERAGE.md. Representative model/prompt promotion, model-assisted feature/intent extraction, independent operational/security review and the other listed implementation gaps remain open. See LIVE-VALIDATION.md for the prepared pilot path and MODEL-SETUP.md for cost controls.
