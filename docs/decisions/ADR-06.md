# ADR-06 — Model identifiers are registry data

**Status:** deferred; assigned for verified model catalog implementation
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Model identifiers currently come from private connection configuration or development settings. A tenant-scoped registry with provider price snapshots and verification timestamps remains to be implemented; configuration alone is not described as that registry.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Production startup remains gated. This deferral records an engineering gap and does not promote an unbenchmarked model.
