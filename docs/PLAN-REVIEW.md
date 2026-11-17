# Plan review and recommended build sequence

Reviewed 16 November 2026. This review covers both PDFs, their repository sources, the canonical YAML, the 58 task capsules, and the existing application scaffold.

## What you are building

AI-MOS is a controlled execution system for marketing, sales and growth. A human supplies the business facts and an objective. The system researches, proposes a structured plan, produces grounded work, requests approval, executes permitted actions and measures the result and its cost.

Your first intended use is promoting a web development agency or SaaS product. Keep one shared engine, with separate brand profiles and workspaces. The agency name, exact offer, ideal customer, pricing and proof remain yours to decide. Your public agency website is a separate customer-facing deliverable; the current build is the internal operating workspace.

The UI direction is black and white with editorial hierarchy, serif headlines, readable body text, clear sections and restrained navigation. It is inspired by your BBC reference rather than a copy of its branding. The BBC page could not be fetched during review; no claim is made that the design is a pixel match.

## Assessment

The strongest parts of the plan are the focus on verified outcomes, human approvals, suppression, tenant isolation, idempotency and fully loaded cost. Preserve these. Twenty agents and twenty-three menu entries should remain configuration and future views, not twenty separate software projects.

The largest product risk is an unclear offer and customer segment. For the first campaign, choose one service and one customer segment. Possible starting hypotheses are a clearly scoped website build for a narrow type of business, or a specific recurring maintenance service. These are options for you to evaluate, not facts added to Brand Brain.

Build a small, usable workflow before expanding the navigation. The first meaningful proof should be a real brief leading to grounded drafts, explicit approval, a small permitted outreach batch, real replies, an honoured opt-out and attributable costs. Payment integration can follow before any claim of verified revenue.

## Findings that need correction

1. **Preflight gating conflicts with your current instruction.** PH-0 says no application code before provider gates close. You explicitly asked to develop now and supply APIs later. Local development proceeds, while gates remain open for live operations. No external gate has been falsely marked passed.
2. **The handoff status is stale.** It says no application code exists, while backend/frontend/Compose/CI scaffold files already existed. SETUP acknowledges that scaffold but describes different status. The new build status is the current entry point.
3. **Auth is underspecified.** Users have an auth_subject but no local credential or session schema; invitations are named without a complete table contract. Managed identity, invitations, sessions, revocation and recovery need a production decision. The local development contract records the temporary implementation.
4. **Task ordering has a dependency mismatch.** T-1.2 needs persistent org/user/membership tables, but T-1.3 adds those tables after T-1.2. Introduce the auth migration before auth implementation, then extend it. Audit storage is listed at migration 0014 but is required in foundation. Move the audit prerequisite earlier.
5. **RLS requires an actual database role boundary.** The inherited Compose user is the database bootstrap superuser. FORCE RLS does not constrain superusers. Production needs separate migrator/application roles without BYPASSRLS, session-scoped tenant context, composite tenant foreign keys, and direct SQL isolation tests. Application filters alone do not close AC-01/AC-02.
6. **Model identifiers and prices are explicitly unverified.** Do not promote them to defaults or use their cost claims as a forecast. Benchmark real candidates and store model version, price snapshot, tokens, provider cost and outcome for every attempt, including failures. No model is selected in this increment.
7. **Provider-side exactly-once execution needs a recovery design.** A unique database key prevents duplicate claims, but cannot alone resolve a crash after the provider acts and before the app persists the result. Use provider idempotency where supported, durable intent/outbox records, receipt reconciliation and visible uncertain states. Do not blindly retry a send with unknown outcome.
8. **Budgets need atomic reservations.** Checking a balance then dispatching allows concurrent overspend. Reserve before work, settle the actual cost afterward and release or reconcile failed reservations.
9. **Claim citation is necessary but insufficient.** A valid citation ID does not prove that a generated sentence is supported. Check tenant ownership, source content, version and contradiction, plus prohibited claims and human review. The current completeness check deliberately does not claim to solve semantic grounding.
10. **Economics are illustrative.** The low inference targets are assumptions pending measured calls. Track data, sending, review time, infrastructure and verified conversion; do not present token spend as CAC. No market price or financial forecast was adopted from the documents.
11. **Local operation has limits.** Local drafting is practical. Push notifications, OAuth redirects and payment webhooks require a reachable callback arrangement for end-to-end provider tests. Do not assume a localhost-only app can receive every provider event without additional setup.
12. **Operational foundations should move earlier.** Basic backup/restore, dependency pinning, secret handling and two-workspace tests should precede real customer data. Later hardening phases can expand them, rather than introduce them for the first time.
13. **The original validator produced false positives and did not fail CI.** It checked dependencies only within a phase even though the plan uses cross-phase dependencies, and printed errors without a nonzero exit code. This is corrected, with cycle/reference/capsule checks and a regression test. The current canonical task graph validates successfully; that does not resolve the auth/migration sequencing issue above.

## Build sequence

| Increment | Result | Evidence required |
|---|---|---|
| Local foundation | Account, workspace, brand facts, roles, audit, pause/resume | Automated boundary tests and browser walkthrough |
| Production foundation | PostgreSQL migrations/RLS, managed identity, restore, schema versioning | Direct SQL isolation with a non-superuser app role; restore drill |
| Shared engine | AI gateway, model registry, ledger, atomic budgets, task DAG and tools | Timeout ledger, concurrency, retries and budget tests |
| Intelligence | Goal clarification, structured plans, retrieval and grounded drafts | Schema/golden-set checks and human review |
| Approval and acquisition | Frozen approvals, sourced leads, suppression, send caps, inbox sync | Small real approved outreach run and opt-out demonstration |
| Conversation and revenue | Calendar and payment adapters, verified events, onboarding | Booking race and webhook authenticity/replay tests |
| Learning and expansion | Attribution, support, retention and later roles | Defensible cost per outcome and improvement evidence |

These increments organize the existing phase work; they do not declare the original gates complete.

## Decisions needed later

Before brand-driven generation: service description, target customer, target geography, approved claims, tone and pricing policy.

Before live outreach: sending identity/domain, provider, account access, permitted prospect source, relevant jurisdictions and a reviewed outreach policy.

Before verified revenue: merchant eligibility and provider choice, plans/currency, webhook setup and onboarding rules.

Credentials can wait during isolated development. Real deliverability, pricing, payment and provider tests cannot be completed with fabricated values.
