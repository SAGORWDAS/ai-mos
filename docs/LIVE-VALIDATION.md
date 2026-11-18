# Controlled live validation

Use this path to validate the implemented agency workflow on your own accounts. It is separate from production acceptance and does not complete the remaining PDF features or representative AI benchmarks. Business details are entered in the platform, not required to build or install it.

## Operator deployment

Use a dedicated pilot hostname and server with Docker Compose. Point the hostname's DNS at that server and allow public ports 80/443. Keep the pilot private by distributing its signup code only to intended testers. Existing password login, offline recovery and optional TOTP apply; the code does not verify email ownership or provide managed identity.

The stack uses an optimized Next build, separate migrator/API/worker database identities, persistent PostgreSQL and Caddy TLS storage. Database/API ports are not exposed on the host. API/worker containers do not receive the migrator credentials. Caddy provisions public certificates once real DNS, reachability and persistent storage are in place; see its [automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).

From the repository root, with the existing Python environment (or install the locked backend dependencies first):

```powershell
.venv\Scripts\python.exe scripts\prepare-validation.py --domain pilot.your-domain.com --review DEPLOY-REVIEW-001
docker compose --env-file .env.validation -f infra/docker-compose.validation.yml config -q
docker compose --env-file .env.validation -f infra/docker-compose.validation.yml up -d --build
docker compose --env-file .env.validation -f infra/docker-compose.validation.yml exec api python -m app.deployment --check-db
docker compose --env-file .env.validation -f infra/docker-compose.validation.yml exec worker python -m app.deployment --check-db --worker
```

Replace the hostname and review reference with your actual deployment information. On Linux, use `.venv/bin/python`. The generator exclusively creates a new `.env.validation`; it never overwrites an existing file or prints secrets. Preserve that file privately, especially its encryption key, and restrict its filesystem access. The review reference is an operator acknowledgement, not an independent certification. Do not run `compose config` without `-q` in shared logs because expanded configuration contains secrets.

`APP_ENV=validation` refuses unsafe configuration and checks the real database role, schema, forced RLS, table ownership, audit grants and queue permissions before startup. It does not create or repair schema with the runtime login. Run migrations through the dedicated migrator. `APP_ENV=production` remains refused pending the separate production review. This path does not require changing the existing local sandbox.

Before applying an upgrade, preview it with the dedicated migration connection using `python -m app.migrate plan`. This command lists applied/pending files and checksums without changing schema or provisioning roles. PostgreSQL development also requires real migrations; model-driven table creation is limited to the local SQLite demonstration.

Upgrading an existing v0.10.0 pilot: add a new private random `PAYMENT_WEBHOOK_SECRET` (at least 32 characters) to its existing `.env.validation`. This signs only the sandbox webhook path; real Stripe signing secrets remain in encrypted provider settings. Preserve the existing Fernet key and database passwords. Do not regenerate or replace the entire environment file.

Open the HTTPS hostname, create an account using the private `VALIDATION_ACCESS_CODE` from the environment file, and set up recovery/TOTP in Team & settings. The signup code is not a password and should not be published. Rotate it when pilot enrolment ends. Account passwords, provider credentials and encryption keys must never be recorded as validation evidence.

## In-app setup

1. Enter the actual offer, ideal customers and approved claims in Brand Brain or the one-brief setup. Unknown prices may stay blank; the system must not invent them.
2. Open Integrations and expand **Live validation center**. Choose prospect discovery plus email, or email with imported contacts. The latter does not require a search-provider account.
3. Connect only the needed providers. Core discovery uses Brave, AI uses OpenRouter, and individual email uses Gmail. Calendar, Stripe, publishing and ads are optional. Callback addresses are displayed in setup; register those exact HTTPS addresses with the provider. Saving is followed by verification and separate owner activation.
4. Set a small model budget and daily email cap in Usage & cost, and a suitable USD request allowance in OpenRouter setup. Verify the selected model catalog. Enter a consenting seed contact and its contactability evidence in CRM. A discovered public address alone does not establish permission to contact it.
5. Refresh validation checks. A prepared status permits beginning controlled drills; it is not a certificate of quality or production approval. No readiness check sends a message or spends provider credit.

## Run the drills

| Drill | Procedure and evidence |
|---|---|
| Model and cost | Generate a small reviewed sample from actual approved facts. Check output, citations, refusal behavior and the actual usage receipt. Build representative labelled examples before accepting an accuracy claim; a few synthetic examples do not prove the PDF benchmarks. |
| Email domain | Verify the sending provider's actual SPF/DKIM/DMARC setup. Send exact approved drafts only to consenting seed inboxes. Inspect inbox/spam placement, receipts, bounce and complaint handling. A provider `sent` receipt alone is not delivery evidence. |
| Opt-out and stop | Send an opt-out from a seed contact, sync it, and confirm suppression prevents another send. Pause the workspace and confirm new work stops. The switch cannot recall an in-flight provider request or pause an already active external ad; use the ad's separate Pause control. |
| Calendar (optional) | Check timezone and free/busy, approve one exact proposal, and inspect the provider receipt. Exercise conflicting requests and an uncertain result. Other apps can still race for the same external slot; record any failure. |
| Payments (optional) | Start with your provider's test mode. Check signed matching events, replay, renewal, refund/dispute and conversion records. A redirect is not payment. Any real purchase or refund remains an explicit owner action. |
| Recovery | Back up the pilot database and private configuration, restore to an isolated destination, verify account recovery and tenant isolation, and retain the drill report. Do not replace the active database during a drill. |

Record each external result with a reference and a short explanation in the validation center. Entries are owner-reported, append-only history. A new entry can supersede a failed or mistaken observation; earlier history remains. Setup/business changes, a software release or 30 days make earlier reports stale. They do not automatically authorize sends, approve a model, or unlock production. Download the report for review.

Connected receipt observations exclude sandbox rows and cover the last 14 days. They are historical counts, not proof of the current connection version, inbox placement or business quality. Unknown model charges and uncertain effects require reconciliation before further testing; never blindly replay an uncertain external action.

## Verification boundaries

Local tests cover the controlled HTTPS application configuration, secure cookies, private signup, owner permissions, tenant isolation and refusal when forced RLS is weakened. Hosted CI also builds and starts the separate validation stack, checks its restricted API/worker preflight, optimized web, private signup and completed sandbox graph, and validates the Caddy configuration. CI uses an isolated Docker bridge with synthetic accounts; it does not certify public DNS, a real certificate, provider grants or real inbox placement. Those require the actual pilot deployment and accounts.

Remaining original-plan engineering and external acceptance gates remain listed in [PLAN-COVERAGE.md](PLAN-COVERAGE.md). Starting validation of existing features does not make the complete platform production-ready or establish a 99% automation rate.
