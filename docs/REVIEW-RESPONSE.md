# Independent review response — 19 November 2026

Source: the owner's `handoff/REVIEW.md` and its three draft test files. Findings were checked against the working source; drafts were adapted rather than accepted as authoritative instructions.

## Implemented in this change

- **11–12: schema authority and drift.** PostgreSQL startup in development no longer calls `create_all`; it requires migrated tables/columns. A clean-database test runs the real migrator before comparing every model table/column, type family, varchar length, nullability and primary key. Unexpected database columns fail unless explicitly documented (migration ledger and optional pgvector column). SQLite remains a local demonstration path; its additive upgrader records a normalized SHA256 of the executed source, preserves historical records, and checks model-column presence after upgrade. A regression preserves existing data while restoring a removed additive column. This does not claim full dialect/constraint parity.
- **13–15: shared database fixtures.** `db_clients` supports SQLite and separately migrated PostgreSQL with restricted API/worker logins. Foundation/authentication and full route inventory tests opt into both backends when the native URL is supplied; SQLite-file-specific tests retain `clients`. Native regression wrappers reuse the shared fixture. Setup failure and normal teardown both attempt cleanup. The old fixture already cleaned up after successful runs; the review's statement that it never dropped resources was incorrect. The draft also needed an awaited cleanup fix.
- **14: route authentication.** Exact method/path public exemptions replace broad prefix exemptions. Private routes must both contain the identity dependency and return 401 anonymously, including mutating endpoints. The inventory traverses FastAPI's lazy included routers; directly iterating only `APIRoute` entries missed most routes in the supplied draft. A stale exemption fails the test. A dependency regression catches an unprotected route even when body validation might otherwise hide it.
- **7: shipped signing secret.** Validation preflight now refuses the default/placeholder sandbox payment-webhook secret. The private generator, validation Compose environment and template supply an explicit random replacement. Real Stripe signing secrets remain separate encrypted provider credentials.
- **10: payment cleanup.** Removed the unreachable second `payment.succeeded` check.
- **26: migration preview.** `python -m app.migrate plan` lists applied/pending files and checksums without DDL, role provisioning or migration application. It refuses edited/missing applied files. Tests verify an empty database stays empty and altered applied source is rejected.

These are engineering regressions, not proof of business quality, full PDF acceptance or production certification. Existing real-account and representative-evaluation gates remain.

## Recommendations retained or corrected

| Review items | Decision |
|---|---|
| 1–5, 16, 22 | Installer standardization, route/module extraction, shared DB/common helpers and frontend restructuring remain follow-up refactors. Do not combine a broad file move with these security/schema changes. Import-time app creation remains the server entrypoint; tests use explicit isolated settings. |
| 6 | Retain the exclusive tenant transaction mutex. A shared lock alone permits concurrent policy checks and lock-upgrade deadlocks; replacing it indiscriminately could break atomic budget/cap/stop guarantees. Measure contention and design narrower locking with race regressions before changing it. The review's 2,000-task capacity assertion was not measured. |
| 8 | Review provider-specific bulk execution before changing transaction boundaries. Preserve exact approval, idempotency, suppression and partial-receipt semantics; do not introduce automatic resend of uncertain deliveries. |
| 9 | Standing-template match/near-miss instrumentation remains follow-up work. Keep conservative send authority rather than silently widening the accepted language. |
| 17 | Acceptance-criterion markers and a generated evidence index remain work. A marker alone cannot establish that an original task's full acceptance criteria passed. |
| 18–20 | Model-assisted qualification/classification and binding evaluation/promotion remain actual feature work; these tests/refactors do not complete them. |
| 21 | Do **not** automatically settle a hold as a confirmed charge after 24 hours. That would turn missing billing evidence into fabricated actual spend. Retain holds; implement ageing/alerts and provider invoice variance as explicitly labelled evidence in a later change. |
| 23–25 | Browser critical-path automation, operational metrics and launcher check mode remain follow-up work. Existing smoke, responsive checks and deployment preflight remain available. |

The existing coverage counts are not increased by these changes. `PLAN-COVERAGE.md` remains the original-plan inventory.
