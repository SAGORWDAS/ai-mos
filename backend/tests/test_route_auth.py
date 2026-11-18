"""Every future private route must retain identity dependency and reject anonymous access."""

import re

from fastapi.routing import APIRoute

PUBLIC = {
    ("GET", "/healthz"),
    ("POST", "/v1/auth/signup"),
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/recover"),
    ("POST", "/v1/webhooks/payments"),
    ("POST", "/v1/webhooks/resend/{org_id}"),
    ("POST", "/v1/webhooks/stripe/{org_id}"),
    ("GET", "/v1/oauth/google/{org_id}/{provider}/callback"),
    ("GET", "/v1/public/{org_id}/sitemap.xml"),
    ("GET", "/v1/public/{org_id}/{content_id}"),
    ("POST", "/v1/public/{org_id}/{content_id}/enquire"),
}


def has_identity(dependency):
    call = dependency.call
    return (
        getattr(call, "__name__", "") == "identity"
        and getattr(call, "__module__", "") == "app.main"
    ) or any(has_identity(child) for child in dependency.dependencies)


def routes_in(nodes):
    # FastAPI retains included routers lazily; inspect their effective contexts.
    for node in nodes:
        if hasattr(node, "effective_candidates"):
            yield from routes_in(node.effective_candidates())
        elif isinstance(node, APIRoute) or isinstance(
            getattr(node, "original_route", None), APIRoute
        ):
            yield node


def test_every_private_route_requires_identity_and_refuses_anonymous_requests(db_clients):
    a, _ = db_clients
    seen = set()
    failures = []
    for route in routes_in(a.app.routes):
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            key = method, route.path
            seen.add(key)
            if key in PUBLIC:
                continue
            if not has_identity(route.dependant):
                failures.append(f"{key}: missing identity dependency")
            path = re.sub(r"\{[^}]*\}", "00000000-0000-0000-0000-000000000000", route.path)
            response = a.request(method, path, **({"json": {}} if method != "GET" else {}))
            if response.status_code != 401:
                failures.append(f"{key}: anonymous status {response.status_code}")
    assert len(seen) > 100
    documented = {
        (method.upper(), path)
        for path, methods in a.app.openapi()["paths"].items()
        for method in methods
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }
    assert documented <= seen, "Route traversal missed documented endpoints"
    assert PUBLIC <= seen, "Remove stale public exemptions or restore missing routes"
    assert not failures, "\n".join(failures)


def test_unprotected_route_is_detected(db_clients):
    a, _ = db_clients
    route = APIRoute("/v1/regression-only", lambda: {"unsafe": True}, methods=["POST"])
    assert not has_identity(route.dependant)
