# Hand-off — three tests for AI-MOS

Drafts from the code review. **Nothing has been applied to your repo.** Copy what you want into `backend/tests/`.

| File | Goes to | Replaces existing |
|---|---|---|
| `tests/conftest.py` | `backend/tests/conftest.py` | yes — superset of the current 28-line file |
| `tests/test_schema_drift.py` | `backend/tests/test_schema_drift.py` | new |
| `tests/test_route_auth.py` | `backend/tests/test_route_auth.py` | new |

## What each one proves

**`test_schema_drift.py`** — creates a throwaway PostgreSQL database, runs your real `app.migrate.upgrade`, and compares `information_schema` against `Base.metadata`. It fails on a missing table, missing column, type-family mismatch, nullability mismatch, or primary-key mismatch. Extra database columns are printed and only fail with `AI_MOS_SCHEMA_STRICT=1`, because some of your migrations create helper objects on purpose.

This is the one that closes the gap you can't see locally: `create_all` and `upgrade_local` both hide a model column that never made it into `migrations/000N_*.sql`.

**`test_route_auth.py`** — walks `app.routes` instead of a hand-written list. Property 1: no non-public route returns a 2xx/3xx without a session. Property 2: every GET route returns exactly `401`. Mutating routes accept `401/403/404/422` because body validation can fire before the identity dependency.

This is your `test_boundaries.py` list generalised — a route added tomorrow is covered automatically, and a route that forgets `Depends(identity)` fails immediately.

**`conftest.py`** — keeps `clients` byte-for-byte equivalent, so none of your 204 tests change. Adds:

- `settings_for(url, worker_url)` — the `Settings(...)` block you were repeating in `pg_clients` and `clients`.
- `paired(app)` — the `TestClient` + shared `portal` trick, factored out.
- `make_postgres_database()` — your `pg_clients` setup lifted verbatim, **plus** the cleanup that was missing (dropped database and roles). Leftover `ai_mos_test_*` databases and `api_*` roles accumulate today.
- `db_clients` — the same pair as `clients`, parametrised over `sqlite` and, when `AI_MOS_TEST_ADMIN_URL` is set, `postgres`.

## Applying it

```bash
cd backend
cp <handoff>/tests/conftest.py tests/conftest.py
cp <handoff>/tests/test_schema_drift.py tests/
cp <handoff>/tests/test_route_auth.py tests/
ruff check tests/ && pytest -q                    # without Postgres: schema test skips
AI_MOS_TEST_ADMIN_URL=postgresql://... pytest -q  # with Postgres: drift test runs
```

Test IDs become `[sqlite]` / `[postgres]` for anything using `db_clients`.

## Expect failures on the first run

That is the point — but know which kind:

- **Schema drift** will probably surface at least one column. Treat each as a real bug: either add an `ALTER TABLE` migration or remove the column from the model.
- **Route auth** may surface a route that never got `Depends(identity)`. If it does, that is a genuine finding, not a broken test. Check it before "fixing" the test.
- If `test_route_inventory_is_discovered` fails, the app failed to import — check that first, everything else is downstream of it.

## Migrating a test to `db_clients`

Only do this for tests that do not read the SQLite file directly. `test_boundaries.py` opens `sqlite3.connect(tmp_path / "test.db")`, so it must stay on `clients`; split those assertions into a `test_sqlite_specific.py` first, then move the rest.

```python
def test_something(db_clients):      # was: clients
    a, _ = db_clients
```

Start with `test_foundation.py` and `test_growth.py` — the highest-value files and the least SQLite-coupled.

## Caveats, stated plainly

- **None of this has been executed.** There is no Python interpreter in the workspace where I drafted it, and your repository is outside it, so I could not run `pytest` or `ruff`. Syntax is hand-checked; behaviour is not.
- `make_postgres_database()` assumes `ai_mos_app` and `ai_mos_worker` exist after `upgrade()`, which is what your `pg_clients` assumes too.
- The schema-drift comparison uses a **type-family** table, not exact types, so it catches varchar-vs-integer and missing columns but will not object to `varchar(200)` vs `varchar(400)`. Deliberate: exact-width comparison produces noise that gets ignored.
- `db_clients` doubles runtime for every test migrated to it. Leave the default suite on SQLite for the fast loop and run the parametrised set in CI.
