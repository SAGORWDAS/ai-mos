# Structured operational events

The provided API and worker launchers use app/logging.json. Application events are JSON lines with allowlisted IDs, action/decision codes, status, route template and duration. No prompts, message bodies, credentials or request headers enter these events. HTTP events use route templates rather than raw paths or query strings; raw Uvicorn access logs are disabled. Deployment ingress/proxy logging needs the same query-string policy.

Command tasks use the command ID as the workflow trace. Standalone tasks use their own ID. HTTP request IDs remain separate, and usage records retain request/task IDs. Tool refusals and task events also persist in the tenant-scoped audit table; PostgreSQL grants prohibit application updates/deletes to audit records. Detailed private task failures are not copied into public operational events.

Read local API events in the private .run/api.log file. Compose emits them to the container's standard output. Keep log access and retention restricted. External log aggregation, alert routing, disk limits and production SLOs are operator configuration, not proven by local event tests.
