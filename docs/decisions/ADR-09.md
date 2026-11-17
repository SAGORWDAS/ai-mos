# ADR-09 — Payment state only from verified webhooks

**Status:** accepted
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Update paid/customer/subscription state only through verified matching payment receipts. Checkout creation, browser return URLs and agent proposals cannot declare a payment successful.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Signed event replay, renewal, refund and dispute handling is tested with fixtures; real merchant drills remain separate.
