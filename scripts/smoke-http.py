"""Synthetic HTTP smoke check against an explicitly selected development instance."""

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
from uuid import uuid4

base = os.environ.get("AI_MOS_SMOKE_URL", "http://127.0.0.1:8000").rstrip("/")
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, body=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=10) as response:
        return json.load(response)


for attempt in range(120):
    try:
        if call("/healthz")["status"] == "ok":
            break
    except (OSError, urllib.error.URLError):
        time.sleep(1)
else:
    raise SystemExit("API did not become healthy")

call("/v1/auth/signup", {
    "name": "Synthetic CI", "email": uuid4().hex + "@example.test",
    "password": uuid4().hex + "Aa!", "organization_name": "Synthetic smoke workspace",
})
brand = call("/v1/brands", {
    "name": "Synthetic smoke brand", "positioning": "Retail website development",
    "approved_claims": ["We build websites for retailers."],
})
lead = call("/v1/leads/import", {"leads": [{
    "brand_id": brand["id"], "name": "Synthetic contact", "email": "smoke@example.test",
    "source": "Synthetic smoke fixture", "lawful_basis": "consent",
    "basis_evidence": "Synthetic local fixture, no real recipient",
}]})["created"][0]
task = call("/v1/drafts", {"lead_id": lead["id"], "idempotency_key": uuid4().hex})
for attempt in range(60):
    tasks = call("/v1/data/tasks")["items"]
    current = next(row for row in tasks if row["id"] == task["id"])
    if current["status"] == "succeeded":
        break
    if current["status"] in {"failed", "blocked"}:
        raise SystemExit("Worker failed: " + current["error_code"])
    time.sleep(1)
else:
    raise SystemExit("Worker did not complete")
draft = call("/v1/data/outreach_drafts")["items"][0]
approval = call(f"/v1/drafts/{draft['id']}/request-approval", {})
call(f"/v1/approvals/{approval['id']}/decision", {"decision": "approved"})
call("/v1/effects/execute", {"approval_id": approval["id"], "idempotency_key": uuid4().hex})
messages = call("/v1/data/messages")["items"]
assert len(messages) == 1 and messages[0]["simulated"] is True
print("HTTP smoke passed: account, brand, CRM, durable draft, approval, sandbox send")
