# Release verification - v0.4.0

Verified on 17 November 2026. Public repository: [SAGORWDAS/ai-mos](https://github.com/SAGORWDAS/ai-mos).

The application source at commit `eb3b0752a0c0d713554f6403df0032b7f1027a8b` passed [all four hosted CI jobs](https://github.com/SAGORWDAS/ai-mos/actions/runs/43996086407):

| Check | Observed result |
|---|---|
| Backend on Ubuntu 24.04 / PostgreSQL 16 + pgvector | Ruff passed; 84 tests passed, one upstream deprecation warning |
| Specification | Validator regression, forced RLS/vector isolation and scaffold validation passed |
| Frontend | Clean install, TypeScript and optimized Next.js build passed |
| Docker Compose | Images built, migrator/API/worker/database/web started; HTTP account-to-approved-sandbox-send smoke passed; disposable stack removed |

Local Windows verification also passed 84 tests with a separate native PostgreSQL 16 instance, including 13 restricted API/worker integration tests and an isolated PostgreSQL backup/restore drill. The portable instance's no-pgvector path and hosted pgvector path were both exercised. Test databases and temporary login roles were removed by their fixtures.

Additional evidence:

- Windows launch, stop, upgrade and restart preserved existing synthetic QA data; a private pre-upgrade SQLite backup was created.
- Browser: contact observation edit, exact publication approval, local service page, actual HTML enquiry submission and private inbox capture.
- Mobile: 390 CSS-pixel viewport, 375-pixel document width excluding scrollbar; no horizontal document overflow. Temporary viewport override was reset.
- Frontend production dependency audit and Python locked dependency audit found no known vulnerabilities at verification time. This does not replace a security assessment.
- Tracked source scan found no GitHub/OpenRouter/live Stripe credential or private-key patterns. `.run`, `.env`, databases, keys, logs, virtual environments and installed dependencies are excluded. Pattern scans cannot prove absence of every possible secret.

Public source and the release archive contain synthetic examples and reference plans, not local user accounts or credentials. The source release is a beta, not a public production deployment. See [BUILD-STATUS.md](BUILD-STATUS.md) and [PLAN-COVERAGE.md](PLAN-COVERAGE.md) for remaining implementation, external-account and business-quality gates.
