# ADR-11 — Single VPS with Docker Compose through PH-4

**Status:** accepted development deployment; public operations deferred
**Owner:** Workspace owner for hosting and operations
**Reviewed:** 17 November 2026

## Decision

Use the supplied local launcher or Compose stack until measured capacity requires a different deployment. Preserve private persistent keys and backups; production is not enabled by a placeholder account.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

HTTPS, identity/recovery delivery, monitoring, operational review and live drills remain deployment work. Localhost publication is not internet hosting.
