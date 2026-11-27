# AI-MOS — independent code review

**Reviewed:** `C:\Users\dsago\Documents\Codex\2026-11-16\re\outputs\ai-mos` (v0.10.0 public beta)
**Also read:** `docs/BUILD-STATUS.md`, `docs/PLAN-COVERAGE.md`, the CI workflow, the test inventory
**Method:** static reading of `main.py`, `tenancy.py`, `config.py`, `deployment.py`, `schema.py`, `migrate.py`, `growth/gateway.py`, `growth/effects.py`, `growth/qualification.py`, `growth/reply_policy.py`, `growth/evaluation.py`, `growth/models.py` surface, `tests/conftest.py`, `tests/test_boundaries.py`, `tests/test_postgres.py`, `migrations/`, `infra/docker-compose.yml`, `frontend/app/`
**Not reviewed:** the remaining ~40 modules line by line; the suites were not executed

---

## Verdict

Well above the usual solo-beta standard. The guards sit in the right places — payload hashes, single-use approvals, budget reservations, forced RLS, fail-closed preflight — and the documentation does not overclaim.

The weaknesses are **structural rather than sloppy**. They cost velocity at 20k lines, not correctness today. The riskiest thing in the repository is not a security defect; it is that three schema histories can disagree while every local test still passes.

---

## What is genuinely strong

- `deployment.py` preflight: HTTPS, secure cookies, single origin, valid Fernet key, strong DB password, PostgreSQL only, verified models required, 32-character pilot code, review reference, separate worker — plus live inspection of runtime role privileges, forced RLS on every tenant table, append-only audit grants and queue ownership. That is a real gate, not a checklist.
- `migrate.py`: advisory lock, checksum that refuses an edited applied migration, one transaction per file, optional role provisioning. Better than a default Alembic setup.
- `effects.py`: the gate ordering is correct (budget → stop → idempotency → approval validity → single-use claim → payload hash → suppression → contactability → daily cap), and the rollback semantics are deliberate.
- `gateway.py`: atomic budget reservation before dispatch, provider cost parsed from the response, reservations held when cost is unknown, cache lineage recorded, policy rechecked under the transaction.
- `docker-compose.yml`: every port bound to `127.0.0.1`, `migrate` gated by `service_completed_successfully`, distinct `ai_mos_app` / `ai_mos_worker` logins, access log off in favour of structured logging.
- The documentation. `PLAN-COVERAGE.md` marking six items "external gate" and refusing to call fixture tests production evidence is rarer than the code quality.

---

## The three things I would do first

1. **Schema-drift test in CI** — migrations vs `Base.metadata`. The highest-probability bug in the next month is a column that exists locally and not in validation.
2. **Route-enumeration auth test** — replaces the hand-kept path list with a rule that covers every future route.
3. **Parametrised database fixture** — makes tenant isolation the default test path instead of the special one.

All three are drafted in `handoff/tests/`.

---

## Architecture and structure

**1. `growth/` is 45 flat modules, wired by hand.** `main.py` calls roughly thirty installers, each with a different signature — `install_esp(app, settings, db)`, `install_usage(app, db, identity)`, `install(app, runtime, settings, db, identity, require, tool_services)`. The wiring order is load-bearing knowledge held in one function.
*Fix:* one `installer(app, ctx)` contract and a single registry list; adding a capability becomes one line.

**2. `main.py` is a hybrid.** It defines ~20 routes inline (auth, orgs, brands, audit, metrics, workspace) while everything else lives in modules. It is now the file every change touches.
*Fix:* move them to `app/routes/`; leave `main.py` as composition only.

**3. Dialect branching is scattered.** `session.bind.dialect.name` appears across `effects.py`, `gateway.py`, `tenancy.py` to choose upsert flavour and scope handling.
*Fix:* centralise as `db.upsert()`, `db.scope()`, `db.lock_org()`. Right now every new query is written twice.

**4. Circular dependencies papered over with function-level imports.** `qualification.save` imports `runtime.record` inside the function; `reply_policy.maybe_send` imports `effects` inside the function; `effects.send_one` imports `attribution` inside the function.
*Fix:* move `record`, `find`, `public` into `growth/common.py`; the cycle disappears at module level.

**5. `app = create_app()` runs at import.** Importing `app.main` builds an engine, runs `enforce_configuration` and points at `./ai-mos.db`.
*Fix:* acceptable for the server entry point, but tools and tests should always use `create_app(Settings(...))` explicitly — which your tests already do.

---

## Correctness and security

**6. A no-op UPDATE is used as a lock — and it sits on the tenant's hottest row.** `require()`, `execute()`, `settle_payment()` and `gateway.generate()` all run `update(Organization).values(emergency_stop=Organization.emergency_stop)` to serialise against the stop flag. Every write in a tenant contends on one row. It passed your 10× burst at 22 tasks; it will not pass at 2,000.
*Fix:* `SELECT … FOR SHARE` on the org row, or a cached stop flag invalidated explicitly on `/v1/org/emergency-stop`.

**7. `payment_webhook_secret` has a working default and is not in `configuration_checks()`.** Mitigated by `provider_verified` and the sandbox-reference check, so it cannot settle a real checkout today — but it is the only secret with a shipped default that the preflight ignores.
*Fix:* three lines in `configuration_checks`, and the class of "forgot to set it" risk is gone.

**8. Bulk send is one large transaction.** A single bad recipient rolls back the whole campaign — deliberate, and the right default — but a 500-recipient campaign holds one write transaction while calling the provider.
*Fix:* chunk at ~50 per transaction with a resumable cursor and per-message status, keeping the campaign-level approval.

**9. `clear_automatic_intent()` will rarely match.** The full-reply regex is safe by design, which also makes L4 effectively dead in practice.
*Fix:* instrument matches and near-misses weekly. If it fires zero times in a month, either widen it deliberately or document it as unavailable at current volumes.

**10. Minor:** `settle_payment` checks `type != "payment.succeeded"` twice; the second check is unreachable.

---

## Schema and migrations — the highest-risk area

**11. Three schema authorities and a fourth path.**

| Source | Used by | Checksummed |
|---|---|---|
| `migrations/0001…0021.sql` | validation / production via `app/migrate.py` | yes |
| `app/schema.py::upgrade_local` | local SQLite | no — literal string `'sqlite-v4.1'` |
| `Base.metadata` + `create_all` | any non-validation `app_env`, **including Postgres** | n/a |

Two concrete failure modes:

- Add a column to the model and a migration, forget `upgrade_local` → every contributor's SQLite database raises `no such column` on pull. This is the bug a new developer hits first.
- Run development against Postgres → `create_all` builds the schema from models, so a model change missing from `migrations/` works locally and fails at validation. Drift stays invisible until deploy.

*Fix:* one authority plus a CI test that starts a clean Postgres, runs the real migrator and diffs `information_schema` against `Base.metadata`. You already compute most of this in `deployment_checks()`, but as a startup check it only protects the validation environment; as a test it protects every commit. Then generate `upgrade_local` from the same diff, or declare SQLite demo-only and stop claiming parity.

**12. The SQLite migration record is not a checksum.** `schema_migrations` stores the literal string `'additive-and-subscription-constraint-upgrade'`, so it records that something ran, not what.

---

## Testing and evidence

**13. Most of the suite never touches RLS.** The default `clients` fixture is SQLite. Forced-RLS policies, queue grants, `resolve_checkout_org` and advisory locks run only in `test_postgres.py`, the PGlite isolation test and the CI validation job.
*Fix:* the parametrised `db_clients` in `handoff/tests/conftest.py`.

**14. `test_boundaries.py::test_authentication_required_every_private_surface` is a hand-kept list of seven paths.** Every route added since sits outside it.
*Fix:* enumerate `app.routes` against a public allowlist — fifteen lines, and it becomes a rule.

**15. `pg_clients` leaks resources.** Each run creates an `ai_mos_test_*` database and two roles that are never dropped. Check with:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'ai_mos_test_%';
SELECT rolname FROM pg_roles WHERE rolname LIKE 'api_%' OR rolname LIKE 'worker_%';
```

**16. Cross-test imports.** `from test_foundation import signup` means a failure there cascades as import errors across six files and hides the real cause. Move helpers to `conftest.py`.

**17. Test names do not bind to acceptance criteria.** 204 tests named `test_growth.py`, `test_boundaries.py` cannot be checked against the 37/15/6 coverage claim.
*Fix:* `@pytest.mark.ac("AC-02")` with strict markers, plus a generated `docs/AC-TESTS.md`. This is the change that turns "37 implemented" from a claim into a checked fact.

---

## The three gaps you named

**18. Model-assisted qualification (T-3.3).** `qualification.py` is `MODEL_VERSION = "recorded-features-v2"` — recorded features only.
*Fix:* a `qualify_features` task whose schema permits only booleans/enums with an `evidence_ref` per feature, feeding the existing deterministic `score()`. The model never returns a number. The gate is then measurable: model-extracted features vs 300 human-labelled leads.

**19. Model-assisted classification (T-3.9).** `classify()` is rules-only.
*Fix:* run rules first, send only the `needs_human` residual to the model with a confidence floor. Cost stays near zero, the rule path remains the free baseline, and "model adds N% coverage" becomes a number instead of an opinion.

**20. Evaluation and promotion (T-5.3).** `evaluation.py` is genuinely good — precision, recall, abstention rate, honest provenance note. What's missing is that the gate is not binding.
*Fix:* store `evals/baselines/<role>.json`, add `--baseline` with an epsilon, and attach the eval run id to the registry promotion record. Without a baseline, exit-code-1 in CI is advisory.

**21. Cost reconciliation (T-5.2).** Reservations with unknown cost are held (`settled=False`) — correct — but nothing ages them.
*Fix:* `reconcile_unsettled()` settles at the reserved amount after 24 hours with `status="assumed"`, surfaces the total in the usage screen, and alerts above a threshold. For true reconciliation, import the provider's monthly invoice and report variance against your snapshots — that is the difference between computing cost and reconciling it.

---

## Frontend

**22. The frontend is a monolith inside the router.** 25 files sit directly in `frontend/app/` with no `components/` or `lib/`; `api.ts`, `money.ts` and `globals.css` sit beside `page.tsx`. `growth-workspace.tsx` is a `"use client"` component owning a 23-section navigation plus a resources map for every section.

App Router only treats `page` / `layout` / `route` specially, so this is a **pure move** — no routing change required.
*Fix:* move non-route modules out, split the workspace by section behind a shared shell. Do it while there are 12 tests to re-point, not after PH-4 adds screens.

**23. Twelve frontend tests across roughly 29 views.** The responsive audit (174 observations) is good manual evidence, but the critical path has no automated cover.
*Fix:* four Playwright flows — signup → brief → draft → approve → sandbox send.

---

## Operations

**24. No metrics endpoint.** You emit structured logs but expose no p95, queue depth, task failure rate or unsettled-reservation total. All computable from existing tables; no new dependency.

**25. `Start-AI-MOS.cmd` has no `--check` mode.** Running `python -m app.deployment --check-db` before launch would turn a failed start into a clear report.

**26. `migrate.py` has no `--plan`.** A dry-run listing pending migrations would make deploy review trivial.

---

## What I would resist

Adding the next module. The coverage table is the most trustworthy artifact in the repository; the risk is breadth growing faster than the AC↔test binding. Fix the schema drift and the locking pattern first — everything after them is cheaper.

---

## Limits of this review

- Static reading only. No Python interpreter was available in the reviewing environment and the repository was outside it, so `pytest` and `ruff` were never executed against the code or the drafts.
- Roughly 40 `growth/` modules were not read line by line; findings there may exist that this review does not mention.
- The 204-test figure is consistent with the test inventory observed, but was not re-verified by running the suite.
- Nothing in the reviewed repository was modified.
