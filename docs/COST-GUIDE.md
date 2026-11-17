# Keeping AI costs low

- Build and test in sandbox first: deterministic templates, no paid model calls and no external sends.
- Configure one model suitable for structured JSON, then run a small real quality/cost test before activation. Exact provider prices and model quality are not invented by the app.
- Set a small monthly budget and daily sending cap. Setting the model budget to zero blocks model work, including cached generation. The initial USD 2 monthly limit is a local default, not a suggested business budget.
- Identical validated requests reuse output for six hours by default. Changed instructions, source facts, approved observations, model or execution mode produce different cache keys. Invalid or unvalidated output is not cached. Usage & cost shows cache hits and avoided real provider calls; owners can clear the cache. `MODEL_CACHE_SECONDS=0` disables it.
- Embedding indexing reuses existing vectors for the selected model and batches at most 32 chunks per request. Sandbox hash vectors are a free workflow test, not semantic AI. Keyword retrieval remains available without embeddings.
- Durable task identity prevents regenerating an already committed draft/plan/content item during crash recovery. Concurrent cache misses can still make separate calls; atomic reservations limit total committed spend.
- Every model attempt has a ledger row. Known cost is recorded even if the returned content fails validation. An uncertain charge retains its reservation. Owners reconcile from OpenRouter generation evidence when available, or enter an actual receipt and cost. Never enter zero merely to free the budget.
- Model reservations are limits on admission, not guarantees of the provider's final bill. Actual settled cost can exceed a reservation; the ledger records it. Search, sending, payment fees, hosting and human review are outside the model budget. Brave verification itself makes one search request and can consume credits. Search is capped at 100 attempts per workspace/day; record actual provider expense separately.
- Model calls and cache entries are scoped to a workspace. Separate client workspaces do not share cached content. No hosted cache service or Redis subscription is required.

The app reports recorded costs and keeps currencies separate for revenue. It does not invent FX rates, fully loaded CAC, savings percentages or a promise of profitability.
