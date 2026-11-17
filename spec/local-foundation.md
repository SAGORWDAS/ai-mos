# Implemented application profile

The executable application is version 0.4.0 public beta. The original YAML specification, task capsules and PDFs are preserved as reference scope. Current behavior and limitations are documented in `docs/BUILD-STATUS.md`; all 58 tasks are accounted for in `docs/PLAN-COVERAGE.md`.

The runtime consolidates twenty agent manifests into one engine. It uses FastAPI, SQLAlchemy, Next.js, a database-backed queue and tenant-scoped provider connections. Local Windows operation uses SQLite; Docker development uses PostgreSQL with separate API and worker roles, forced RLS and append-only payment/audit/provider receipts. Redis is not required by this engine.

Sandbox is deterministic and free of external provider actions. Real adapters need explicitly verified/enabled connections and reviewed execution. Owned publication is a separate local execution option that creates an unauthenticated page and private enquiry form. See the agency guide, setup guide and integration checklist.
