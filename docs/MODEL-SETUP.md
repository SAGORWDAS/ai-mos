# AI models and cost controls

The sandbox works without credentials or business details. Enter your offer and customer information in the platform when preparing a campaign.

For connected AI, open Integrations, configure OpenRouter and enter an account key plus exact model selections. Chat is needed for generation; embedding and image selections are optional. The owner verifies the account and then explicitly enables it. Saving placeholder credentials never enables calls.

Account verification also reads the provider catalog for each selected operation. Expand **AI models and prices** to inspect the selections, catalog date and advertised rates. The owner can refresh metadata before enabling the account. Generation automatically refreshes evidence after six days or when verification is missing, with one automatic attempt per hour and shared concurrent refreshes. Verification expires after seven days. A fresh snapshot may survive a transient catalog outage for the unchanged account; expired evidence blocks connected generation. Changing the key or configuration version invalidates old authority.

Set an optional **Per-request AI allowance** in normal USD ($0 to $1, up to six decimal places). Blank uses the deployment default, normally $0.02. Zero refuses new connected generations; existing validated cache results may still be reused at zero new provider cost. The monthly budget is an additional constraint. Its configured limit and daily send cap carry into the next UTC month; spend and reservations do not carry over.

Known text estimates use UTF-8 input bytes plus overhead and the configured maximum output, rather than a low character-count estimate. Requests above the allowance are refused before generation. Chat routing includes advertised price ceilings. Image calls reserve the full allowance; generic advertised image prices do not fully describe resolution or provider tiers. These controls reduce exposure; actual provider charges may differ from an estimate. Unknown costs remain held until reconciled and known receipts retain actual reported costs.

Each attempt stores the model registry reference and a copy of the pricing evidence used at that time. Refreshing the catalog does not rewrite earlier usage rows. API credentials and the internal fingerprint are omitted from registry responses and workspace exports.

Catalog checks confirm identity and advertised pricing, not writing quality, deliverability or business results. Real-account acceptance, representative model evaluations and production operation remain separate gates. The system still refuses production startup pending deployment review.

Provider contracts: [model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties), [provider routing and price limits](https://openrouter.ai/docs/guides/routing/provider-selection). Image estimates do not claim a complete tier-specific quote.
