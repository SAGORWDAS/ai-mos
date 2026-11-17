def test_declared_oversize_rejected_before_auth_or_parsing(clients):
    a, _ = clients
    response = a.post("/v1/auth/login", content=b"{}", headers={"content-length": "70000"})
    assert response.status_code == 413
    assert response.json()["detail"] == "payload_too_large"


def test_chunked_upload_stops_consumption_before_full_payload(clients):
    a, _ = clients

    async def exercise():
        consumed = 0
        messages = []

        async def receive():
            nonlocal consumed
            consumed += 1
            return {"type": "http.request", "body": b"x" * 32768, "more_body": consumed < 50}

        async def send(message):
            messages.append(message)

        await a.app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/v1/auth/login",
                "raw_path": b"/v1/auth/login",
                "query_string": b"",
                "root_path": "",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        assert (
            next(
                message["status"]
                for message in messages
                if message["type"] == "http.response.start"
            )
            == 413
        )
        assert consumed == 3

    a.portal.call(exercise)
