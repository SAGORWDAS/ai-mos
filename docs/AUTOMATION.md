# Set up once, add businesses when needed

Business facts are runtime inputs. You do not need to give the developer a business name, offer, audience, prices or API credentials to install or test AI-MOS. An empty workspace remains usable. Any workspace owner can enter business details inside the application when starting work, and can add another business later.

For the shortest setup, use **Overview / Start with a short business brief**. One replay-safe operation creates the business and starts preparation. See [DAY-ONE.md](DAY-ONE.md).

## Start a business campaign

Open **Operations / Command Center / Autopilot**. Use an existing Brand Brain profile, or choose **Add a business now or later**. A name alone is enough to save a draft profile. Offer, audience and approved facts can be completed later in Brand Brain. The app never fills unknown commercial facts with invented claims.

When ready, select the business, describe the objective, choose the target/window, optionally select up to twenty reviewed contacts, and click **Start automatic preparation**. This authorizes internal preparation for that request. An enabled model connection can incur model charges within the current budget.

Autopilot generates the plan, authorizes its bounded internal graph, runs evidence research, strategy, content and reporting, drafts for selected contacts, and assembles the final approval queue. Follow progress in Plans & tasks. You do not approve every internal task. Duplicate start requests and replayed preparation jobs do not duplicate the saved plan or approvals. Pause, role changes, disabled agents, budget exhaustion and failed dependencies still stop affected work.

Optional connected prospect research uses your enabled Brave connection, then reads up to three suggested HTTPS business pages using the safe fetcher. Observed same-domain email addresses are imported with provenance and **contactability not established**. Inaccessible pages are reported as skipped. Publication of an address does not establish permission to market to it. Observed contacts are scored and drafted automatically; review contactability before sending. The system does not invent consent.

If offer, audience or approved facts are missing, only that campaign asks for information; no paid generation is queued and the platform stays available.

## Connect providers later

Open **Integrations / Connect when you are ready**. Each optional service shows its purpose, required inputs, current status and callback address where applicable. Configure only what you use. Saving starts disabled; verify the selected account, then explicitly enable it. Credentials are entered privately in the app, not sent to the developer. Google OAuth and callback registration still require your own provider account/application.

Refresh setup checks after connection changes. The deployment section separates local configuration from real-account validation. A verified API key proves access, not deliverability, model quality, merchant eligibility or production readiness.

## What continues automatically

| Work | Behavior |
|---|---|
| Internal campaign preparation | Runs after one owner start; no per-task approval |
| Prospect research | Optional enabled-provider search plus bounded observed-contact import |
| Selected-contact outreach | Drafts automatically and requests exact-copy approval |
| Gmail reply import | Runs on the owner-enabled schedule while the worker is available |
| Suppression | Opt-out/bounce/complaint records block later sends |
| Follow-ups | Enabled sequences queue bounded drafts; stop on reply/opt-out/conversion |
| Payments and customers | Verified signed events update payment/customer/subscription/onboarding state |
| Internal business rules | Enabled rules score leads, notify owners and prepare onboarding |
| Costs and recovery | Budgets, cache reuse, attempt ledger, bounded retries and reconciliation holds apply |

Reviewed WordPress.com/LinkedIn member publication, recipient-facing sends/bookings and bulk campaigns retain explicit execution controls. Spending changes, refunds, disputes and contractual decisions remain owner responsibilities. This release automates campaign preparation and existing configured workflows; it does not claim unrestricted autonomous business operation or guarantee clients.

Production remains separately gated on the remaining engineering review, hosting/security setup, representative AI-quality tests and live provider drills. Adding business details or connecting credentials does not by itself satisfy those gates. See PLAN-COVERAGE.md for the original-plan status.
