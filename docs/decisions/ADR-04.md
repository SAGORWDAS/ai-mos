# ADR-04 — Task graph in Postgres, not a framework

**Status:** accepted
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Persist plans, tasks, dependencies, leases and effect receipts in the database. Queue claims and idempotency control retries; no external orchestration framework is required by the current bounded workflows.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Multi-host capacity and outage behavior still require staging drills. Unknown provider outcomes remain reconciliation work.
