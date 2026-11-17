# ADR-06 — Model identifiers are registry data

**Status:** implemented in v0.9.0; quality promotion remains separate
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 18 November 2026

## Decision

Connections nominate model selections; the gateway resolves them through tenant-scoped registry rows. Provider catalog reads record exact identity, operation route, advertised USD pricing and verification time. Authority binds to the account version and key fingerprint. Account verification is not model verification.

Connected generation requires fresh evidence by default. The development-only override cannot bypass this requirement in production. The gateway automatically refreshes aging evidence, coalesces concurrent refreshes and refuses expired or missing evidence. A transient catalog outage preserves still-fresh evidence only for the unchanged connection.

Each usage attempt copies its registry pricing evidence. Later refreshes or key rotation cannot rewrite that historical snapshot. Chat calls send advertised provider-price ceilings and estimate cost conservatively before reserving money. Images reserve the full request allowance because advertised generic rates do not fully specify every tier. Unknown provider charges retain holds for reconciliation.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

Catalog verification does not certify model quality or a guaranteed final bill. Representative evaluation and model/prompt promotion gates remain separate work. Production startup remains gated. See [model setup](../MODEL-SETUP.md).
