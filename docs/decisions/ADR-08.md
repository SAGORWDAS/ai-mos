# ADR-08 — Approvals bound to a payload hash

**Status:** accepted
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Freeze a versioned payload hash for every external effect. Approvals are expiring and single use; changes to relevant facts, copy or connections invalidate execution.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Standing authority is restricted to the exact reviewed reply policy and is rechecked before queued delivery. It is not a global approval bypass.
