import xml.etree.ElementTree as ET
from io import BytesIO

import httpx
import pytest
from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth.ingestion import fetch_text, public_address


def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 200 Td (Supplied retailer website development facts.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def test_pdf_import_is_scoped_deduplicated_and_does_not_approve_claims(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, _ = brand_and_lead(a)
    path = f"/v1/brands/{brand['id']}/ingest-pdf?title=Supplied%20facts"
    first = a.post(path, content=pdf_bytes(), headers={"Content-Type": "application/pdf"})
    assert first.status_code == 201, first.text
    assert a.post(path, content=pdf_bytes()).json()["id"] == first.json()["id"]
    assert b.post(path, content=pdf_bytes()).status_code == 404
    assert a.post(path, content=b"not a pdf").status_code == 422
    assert "Supplied retailer" in str(
        a.post(f"/v1/brands/{brand['id']}/search", json={"query": "retailer website"}).json()
    )
    assert a.get(f"/v1/brands/{brand['id']}").json()["approved_claims"] == brand["approved_claims"]


@pytest.mark.asyncio
async def test_web_import_pins_public_dns_and_blocks_redirect_to_private_address():
    calls = []

    async def resolve(host):
        return "8.8.8.8" if host == "public.example.test" else "127.0.0.1"

    def handle(request):
        calls.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "public.example.test"
        assert request.extensions["sni_hostname"] == "public.example.test"
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    with pytest.raises(HTTPException) as error:
        await fetch_text("https://public.example.test", httpx.MockTransport(handle), resolve)
    assert error.value.status_code == 422 and len(calls) == 1

    def success(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<h1>Real supplied service</h1><script>steal()</script><p>Retailer websites.</p>",
        )

    text, url = await fetch_text(
        "https://public.example.test", httpx.MockTransport(success), resolve
    )
    assert "Real supplied service" in text and "steal" not in text
    for invalid in [
        "http://localhost",
        "https://user:password@public.example.test",
        "https://public.example.test:8000/",
        "https://[invalid",
    ]:
        with pytest.raises(HTTPException):
            await fetch_text(invalid, httpx.MockTransport(success), resolve)


@pytest.mark.asyncio
async def test_mixed_public_private_dns_is_rejected(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(HTTPException):
        await public_address("mixed.example.test")


def publish(client, brand):
    assert (
        client.post(
            "/v1/content/generate",
            json={
                "brand_id": brand["id"],
                "type": "landing_page",
                "topic": "Our website development service",
                "idempotency_key": key(),
            },
        ).status_code
        == 202
    )
    drain(client)
    item = rows(client, "content_items")[0]
    approval = client.post(f"/v1/content/{item['id']}/request-approval").json()
    assert (
        client.post(
            f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"}
        ).status_code
        == 200
    )
    result = client.post(
        "/v1/effects/execute",
        json={"approval_id": approval["id"], "idempotency_key": key(), "execution_mode": "local"},
    )
    assert result.status_code == 200, result.text
    return item


def test_owned_publication_requires_approval_collects_private_enquiry_and_unpublishes(clients):
    a, b = clients
    owner = signup(a)
    brand, _ = brand_and_lead(a)
    item = publish(a, brand)
    path = f"/v1/public/{owner['organization']['id']}/{item['id']}"
    assert b.get(path).status_code == 200
    assert b.get(path).headers["content-security-policy"].startswith("default-src 'none'")
    assert b.get(path.replace(owner["organization"]["id"], "another")).status_code == 404
    data = {
        "name": "Website visitor",
        "email": "enquiry@example.test",
        "message": "I would like a website for my retail business.",
        "request_reply": True,
    }
    assert b.post(path + "/enquire", json=data).status_code == 200
    assert b.post(path + "/enquire", json=data).status_code == 200
    lead = next(lead for lead in rows(a, "leads") if lead["email"] == data["email"])
    assert lead["lawful_basis"] == "not_established"
    assert len([m for m in rows(a, "messages") if m["lead_id"] == lead["id"]]) == 1
    assert b.get("/v1/data/leads").status_code == 401
    assert a.post(f"/v1/content/{item['id']}/unpublish").status_code == 200
    assert b.get(path).status_code == 404


def test_public_drafts_hidden_and_svg_escapes_brand_text(clients):
    a, b = clients
    owner = signup(a)
    brand, _ = brand_and_lead(a)
    assert b.get(f"/v1/public/{owner['organization']['id']}/unknown").status_code == 404
    asset = a.get(f"/v1/brands/{brand['id']}/creative.svg")
    assert asset.status_code == 200
    assert ET.fromstring(asset.content).tag.endswith("svg")
    assert "attachment" in asset.headers["content-disposition"]
    assert b.get(f"/v1/brands/{brand['id']}/creative.svg").status_code == 401
