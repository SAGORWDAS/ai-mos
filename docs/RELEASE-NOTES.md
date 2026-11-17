# AI-MOS v0.4.0 - public beta

A reusable agency and SaaS marketing workspace with a restrained black-and-white interface. Run the complete local sandbox workflow without provider credentials.

Included: brand facts and cited retrieval, reviewed plans and durable jobs, CRM and prospect research, grounded outreach with approvals/suppression/caps, Gmail/Calendar OAuth, Resend bulk receipts, approved service pages with private enquiries, Stripe payment/subscription lifecycle, onboarding/support/automation, analytics and expenses.

Cost controls include atomic budgets, zero-cost sandbox, validated response caching, batched/reused embeddings and unknown-charge reconciliation. Security foundations include workspace roles, TOTP/offline recovery, encrypted connections, shared throttles, PostgreSQL RLS and verified backup/restore tools.

Validation: 84 tests passed locally and in hosted CI. Specification, frontend build and Docker Compose HTTP workflow checks passed. Dependency audits found no known vulnerabilities at verification time.

**The original 58-task production plan is not fully accepted.** Real provider/account tests, model benchmarks, full campaign attribution, external social publishing, some specialized agent tools and production deployment/security/load validation remain. Actual credentials, business facts, domain/merchant setup and human review are required for live use. No client-acquisition or revenue guarantee is made. Production startup remains gated.

Start with README.md, SETUP.md and docs/AGENCY-GUIDE.md. Exact task-by-task status is in docs/PLAN-COVERAGE.md. Private credentials, local databases and runtime dependencies are excluded from the source archive; they must be configured or installed locally.
