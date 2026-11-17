# ADR-07 — ESP for bulk, mailbox API for conversation

**Status:** accepted adapters; domain activation deferred
**Owner:** Workspace owner for sending-domain activation
**Reviewed:** 17 November 2026

## Decision

Use Resend for reviewed opt-in bulk campaigns and Gmail for conversations. Preserve suppression, exact-copy approval, recipient caps and provider receipts on both paths.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Real sending domains, DNS authentication, OAuth grants and seed inbox placement require business-owned accounts. A public address is not consent.
