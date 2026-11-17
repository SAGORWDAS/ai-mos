"""Bound request memory before JSON/PDF parsers consume a body, including chunked uploads."""

from fastapi import HTTPException
from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = (
            5_000_000
            if scope["method"] == "POST" and scope["path"].endswith("/ingest-pdf")
            else 65_536
        )
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > limit:
            response = JSONResponse(
                {"detail": "payload_too_large"},
                status_code=413,
                headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        consumed = 0
        exceeded, rejected = False, False

        async def bounded_receive():
            nonlocal consumed, exceeded
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    exceeded = True
                    raise HTTPException(413, "payload_too_large")
            return message

        async def bounded_send(message):
            nonlocal rejected
            if exceeded:
                # Body parsers may translate receive errors to 400. Preserve the size failure.
                if not rejected:
                    rejected = True
                    response = JSONResponse(
                        {"detail": "payload_too_large"},
                        status_code=413,
                        headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"},
                    )
                    await response(scope, receive, send)
                return
            await send(message)

        return await self.app(scope, bounded_receive, bounded_send)
