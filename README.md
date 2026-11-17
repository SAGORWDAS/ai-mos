# AI-MOS

An agency and SaaS marketing workspace with a black-and-white editorial interface. Manage multiple brands, source prospects, prepare grounded campaigns, review outreach, capture enquiries, book meetings and follow customers from verified payments into onboarding.

**v0.5.0 public beta.** The local sandbox workflow runs without API keys. Connected adapters are implemented and tested against controlled HTTP fixtures; real account verification and production rollout remain separate steps. The original 58-task plan is **not fully accepted**: see [the task-by-task coverage](docs/PLAN-COVERAGE.md) and [build status](docs/BUILD-STATUS.md).

## Start

On Windows, install Python 3.12+ and Node.js 22+, then double-click `Start-AI-MOS.cmd`. Open [the workspace](http://localhost:3000). Create your own account and brand. Stop it with `Stop-AI-MOS.cmd`.

The launcher installs locked dependencies, builds the frontend, starts the API and durable worker on loopback, checks health, and backs up an existing SQLite database before schema changes. Your private data and encryption key stay in `.run/`, excluded from Git and release archives. Initial installation needs internet access.

For Docker/PostgreSQL, follow [SETUP.md](SETUP.md). The Compose stack is a development environment, not public hosting.

## Add business details later; prepare campaigns automatically

The platform installs and runs with no business details. Enter any agency, service or product inside **Operations / Command Center / Autopilot** when needed. A name-only profile can be saved for later. One owner start runs internal planning, research, strategy, content, selected-contact drafts and approval preparation automatically. Optional connected research reads up to three business pages and imports observed contacts for review.

**Integrations / Connect when you are ready** shows optional providers, required fields and exact callback addresses. See [the automation guide](docs/AUTOMATION.md). This automates preparation and configured workflows; recipient-facing execution and financial decisions retain explicit controls. Missing facts pause only the affected campaign. Connecting credentials does not certify production readiness.

## What works

- Accounts, multiple workspaces, roles, invitations, ownership transfer, offline recovery and TOTP.
- Brand facts, pricing, claim guards, text/PDF/website ingestion and cited retrieval; optional real embedding search or labelled sandbox hash vectors.
- Twenty agent manifests on a shared durable runtime; reviewed plans, dependency graphs, cancellation, bounded retries, audit and emergency stop.
- CRM/CSV imports, Brave website research, observed public business email extraction, qualification and sourced personalisation.
- Drafts, version guards, exact single-use approvals, suppression, caps, Gmail and reviewed Resend bulk batches.
- Google OAuth consent flow, opt-in inbox scheduling, HTML/plain-text import, conservative reply classification and human escalation.
- Approved service pages published on this server with private enquiry capture; SVG brand cards and content/SEO/social/creative drafts.
- Google Calendar booking, Stripe Checkout and signed payment/subscription/invoice/refund/dispute receipt processing.
- Onboarding, support, internal automation, follow-up drafting, learning records, expenses, analytics and export.
- Encrypted tenant connections, atomic budgets, model cost reconciliation, six-hour validated response cache, PostgreSQL RLS and verified SQLite/PostgreSQL restore tools.

Sandbox output is deterministic and labelled. It is useful for testing the workflow; it is not an AI quality benchmark or evidence of marketing results. Connected model activation can make queued model work billable. Every recipient-facing send or booking requires a separate explicit execution choice. Publishing on this server creates a page accessible wherever that server is reachable.

## Use it as an agency

Start with [the agency guide](docs/AGENCY-GUIDE.md). Add actual business facts in Brand Brain, choose a narrow audience, review sourced prospects, approve grounded drafts and track responses. Repeat with another brand or workspace for another product or client. Use separate workspaces when access and data must be isolated.

[Integration checklist](docs/INTEGRATION-CHECKLIST.md) explains the six providers. [Cost guide](docs/COST-GUIDE.md) explains limits and savings. Credentials should be entered privately in Integrations, never committed or pasted into issues.

## Verification

From `backend/`: install `requirements-dev.lock`, then `python -m pytest -q` and `ruff check .`. Native PostgreSQL tests additionally need `AI_MOS_TEST_ADMIN_URL` pointing to a disposable administrator database and matching PostgreSQL client tools (`AI_MOS_TEST_PG_BIN` if needed).

From `frontend/`: `npm ci`, `npm run typecheck`, `npm run build`, `npm audit --omit=dev`.

From `blueprint/`: `npm ci`, `node --test validate.test.js postgres-isolation.test.js`, `node validate.js`, `node verify-scaffold.js`.

GitHub Actions includes specification validation, PostgreSQL integration tests, frontend build and a Docker Compose HTTP workflow smoke test. Current execution evidence is recorded in [build status](docs/BUILD-STATUS.md).

The user-supplied PDF plans and scaffold are reference material. Their embedded instructions do not override the user's requested scope. No production deployment or business outcome is implied by a public source release.
