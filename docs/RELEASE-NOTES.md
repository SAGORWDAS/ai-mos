# AI-MOS v0.5.0 - automated campaign setup beta

Business details are now explicitly runtime inputs: install the platform without them, save a name-only business profile, and complete facts when starting a campaign.

New Autopilot runs planning, research, strategy, content, reporting, selected-contact drafting and approval preparation after one owner start. Optional connected prospect research reads up to three suggested business pages and imports observed same-domain addresses without inventing marketing permission. Durable jobs, idempotency, tenant isolation, pause, caps and role checks remain enforced.

New connection guidance shows each optional provider, required inputs, status and exact callback address. Credentials stay in private integration configuration. Connecting accounts does not alone certify production readiness.

Validation: 90 tests passed across local regression suites, including 14 native PostgreSQL tests; TypeScript and optimized frontend build passed. Hosted CI results are available on the tagged source commit. Browser QA verified a one-start synthetic campaign completed without per-task approval.

This beta automates preparation and configured workflows. Sending, publication, bookings and financial commitments retain explicit owner controls. Broader production engineering and live provider/business-quality gates remain; see docs/PLAN-COVERAGE.md and docs/AUTOMATION.md. No client or revenue outcome is guaranteed.
