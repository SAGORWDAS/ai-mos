# ADR-01 — Payment provider

**Status:** accepted adapter; merchant activation deferred
**Owner:** Workspace owner for merchant activation
**Reviewed:** 17 November 2026

## Decision

Use the Stripe adapter and signed receipt workflow. Sandbox remains usable without a merchant account. Eligibility, fees and real activation are decided separately for each business.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Merchant approval and live payment/refund drills need a real account.
