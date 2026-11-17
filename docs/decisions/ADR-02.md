# ADR-02 — Seven services, twenty-three modules

**Status:** accepted for this development release
**Owner:** Project maintainer (SAGORWDAS)
**Reviewed:** 17 November 2026

## Decision

Use a modular backend, durable worker and web application with the original module/agent boundaries represented in code and configuration. Separate deployable services are deferred until measurements justify their cost.

## Reason

Record the implemented boundary and its owner explicitly so a later business can connect accounts without treating placeholder evidence as live acceptance.

## Consequences and follow-up

This deliberately differs from deploying seven application services immediately; extraction must preserve the same tenant and approval boundaries.
