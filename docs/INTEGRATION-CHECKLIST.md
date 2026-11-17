# Connecting real providers

No credentials are required for sandbox. Save secrets privately in Integrations. Save starts disabled, verification checks the selected account, and an owner explicitly enables it. Placeholders cannot activate. Verification does not certify account eligibility, output quality or deliverability. Disconnect invalidates pending connection use. Avoid committing secrets, tokens or webhook samples containing customer data.

## Business inputs

Supply actual offers, audience/geography, supported claims, pricing/currency, policies and contactability evidence. The system supplies fields and workflows; it cannot invent your commercial facts or jurisdiction-specific outreach policy.

## OpenRouter

Supply API key, credit, exact chat model ID and optional embedding model ID. Set a small budget first. Activation enables billable queued model work. The adapter expects structured JSON and actual returned cost; unknown charges retain reservations for owner reconciliation. A successful authentication check does not prove a model meets your schema, quality or per-call envelope. Run representative, capped real tests. See [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

## Gmail and Google Calendar

Create your Google OAuth application and save client ID/secret plus sender/calendar ID. **Connect Google account** creates a PKCE/state-bound, single-use consent link and displays the exact redirect URI to register. Tokens are encrypted. After exchange the connection remains disabled until explicitly enabled. Existing matching token/refresh-token configuration is also supported.

Use minimum grants for enabled features. Gmail sends and reads known CRM contacts; Calendar reads availability and inserts approved bookings. Configure a reachable HTTPS `PUBLIC_API_URL` for deployed callbacks. Local loopback callbacks may be used for development where Google permits your client configuration. See [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

Inbox scheduling is owner opt-in; it runs only while the worker and enabled verified connection are available. Manual sync is paged. Plain text and HTML alternatives are read; attachments are ignored. Unknown senders are skipped. Classification is conservative heuristics, with human review for uncertain cases. No auto-send mode is enabled. Gmail acceptance is recorded as sent, not inbox delivery. Lost receipts stay uncertain and are reconciled without blind resend.

Configure and verify your sending domain and SPF/DKIM/DMARC; test real inbox placement. Calendar checks availability before insert and uses deterministic IDs. External calendar users can change availability between check and booking; provider-wide locking is not guaranteed.

## Resend bulk email

Supply API key, sender address on an exactly verified domain, and the webhook signing secret. Configure `/v1/webhooks/resend/WORKSPACE-ID` under your reachable API base. Signed Svix callbacks record delivery, bounce and complaint events. Opt-outs/bounces/complaints suppress later actions. Batches contain at most 20 reviewed contacts with recorded consent and require owner approval. Partial or lost receipts become uncertain; inspect the provider console and do not blindly resend. See [Resend batch API](https://resend.com/docs/api-reference/emails/send-batch-emails).

## Brave Search

Supply a Brave Search API subscription key. Verification makes one query and may consume provider credit. Connected research returns website suggestions, not verified customers or marketing permission. Search attempts are capped at 100/workspace/day, with billed amount recorded manually as an expense. Public page enrichment extracts only observed matching-domain addresses. Safe fetching refuses private IPs and validates redirects. See [Brave Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started).

## Stripe

Supply an eligible merchant account, secret key, webhook signing secret and HTTPS success/cancel URLs. Verify account identity and charges capability. Register `/v1/webhooks/stripe/WORKSPACE-ID` under the reachable API base.

Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded`, `charge.dispute.created`, `charge.dispute.closed`.

Checkout creation is queued/idempotent. Only signed matching paid receipts create payments/customers. Test-mode events stay test revenue. Renewals and lifecycle receipts are idempotent; cancellation of one subscription does not cancel another. Refund deltas reduce net revenue. Refunds/disputes create human review notifications; no refund, price change or dispute response is initiated by the app. Unmatched managed events can require reconciliation/retry. Test your selected API version and event shapes with your own account. See [Stripe fulfillment](https://docs.stripe.com/checkout/fulfillment) and [webhook verification](https://docs.stripe.com/webhooks).

## Live acceptance before client use

Run a small approved end-to-end drill for your selected providers: known recipient, opt-out, uncertain receipt, occupied calendar slot, test Checkout, signed retry, renewal/refund/dispute. Then validate real model quality, actual fees, deliverability, backup recovery and HTTPS/security configuration. These cannot be proven with placeholders. Do not switch this development beta directly to unrestricted public production.
