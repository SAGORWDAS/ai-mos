# ADR-05 — OpenRouter as the single model gateway

**Status:** accepted
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Route configured chat, embedding and image calls through the shared OpenRouter gateway. The gateway reserves model budget, records every attempt, validates results, reuses validated output and holds unresolved charges.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Provider grants, model quality and catalog/pricing verification are separate concerns. A successful key check does not establish them.
