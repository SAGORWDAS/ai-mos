# ADR-03 — Row-level security from migration 01

**Status:** accepted
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

PostgreSQL uses forced tenant RLS and restricted API/worker identities. SQLite is available for local development with application scoping, not as a production isolation boundary.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Every new tenant table must join the migration and two-tenant RLS tests. Native and PGlite evidence is recorded in release verification.
