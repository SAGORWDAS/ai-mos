"""Every API route must refuse an unauthenticated request.

Replaces the hand-kept path list in test_boundaries: a new route is covered the
moment it is registered, and a route that forgets Depends(identity) fails here
instead of in production.

Two properties are asserted:
  1. no non-public route returns a success status without a session;
  2. every GET route returns exactly 401 (the identity dependency runs before
     any handler, so nothing else is an acceptable answer).

Mutating routes are allowed 401/403/404/422 rather than only 401, because body
validation can run before the dependency and still refuses the request.
"""

import re

from fastapi.routing import APIRoute

PUBLIC_EXACT = {
    "/healthz",
    "/v1/auth/signup",
    "/v1/auth/login",
}
PUBLIC_PREFIXES = ("/v1/public/", "/v1/webhooks/")

SUCCESS = range(200, 400)
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


def concrete(path):
    return re.sub(r"\{[^}]*\}", PLACEHOLDER, path)


def private_routes(app):
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in PUBLIC_EXACT or route.path.startswith(PUBLIC_PREFIXES):
            continue
        yield route


def test_route_inventory_is_discovered(clients):
    routes = list(private_routes(clients[0].app))
    assert len(routes) >= 40, f"only {len(routes)} private routes discovered; import or wiring broken"
    assert not [route for route in routes if not route.methods], "a route advertises no methods"


def test_no_private_route_succeeds_without_a_session(clients):
    a, _ = clients
    failures = []
    for route in private_routes(a.app):
        path = concrete(route.path)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            options = {"json": {}} if method in {"POST", "PUT", "PATCH"} else {}
            response = a.request(method, path, **options)
            if response.status_code in SUCCESS or response.status_code >= 500:
                failures.append(f"{method} {route.path} -> {response.status_code}")
    assert not failures, "Routes answered without a session:\n  " + "\n  ".join(failures)


def test_get_routes_answer_exactly_401(clients):
    a, _ = clients
    failures = []
    for route in private_routes(a.app):
        if "GET" not in route.methods:
            continue
        response = a.get(concrete(route.path))
        if response.status_code != 401:
            failures.append(f"GET {route.path} -> {response.status_code}")
    assert not failures, "GET routes must return 401 unauthenticated:\n  " + "\n  ".join(failures)
