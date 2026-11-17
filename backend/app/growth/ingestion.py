"""Bounded PDF/HTML extraction and public HTTPS fetching with pinned DNS resolution."""

import asyncio
import ipaddress
import json
import os
import socket
import subprocess
import sys
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from pypdf import PdfReader


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag == "a":
            from urllib.parse import unquote

            target = dict(attrs).get("href") or ""
            if target.lower().startswith("mailto:"):
                self.parts.append(unquote(target[7:].split("?", 1)[0]))

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "br", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(content):
    parser = TextHTML()
    parser.feed(content)
    return "\n".join(line.strip() for line in " ".join(parser.parts).splitlines() if line.strip())[
        :200000
    ]


def pdf_text(content):
    if not content.startswith(b"%PDF-"):
        raise HTTPException(422, "invalid_pdf")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise HTTPException(422, "encrypted_pdf_not_supported")
        if len(reader.pages) > 100:
            raise HTTPException(422, "pdf_limit_100_pages")
        parts = []
        for page in reader.pages:
            if len(page.get_contents().get_data() if page.get_contents() else b"") > 5_000_000:
                raise HTTPException(422, "pdf_page_too_complex")
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > 200000:
                raise HTTPException(422, "document_text_limit_200000")
        text = "\n".join(parts).strip()
        if len(text) < 10:
            raise HTTPException(422, "pdf_text_missing_ocr_required")
        return text
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "pdf_cannot_be_read") from None


def isolated_pdf_text(content):
    safe_env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
        }
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.growth.pdf_worker"],
            input=content,
            capture_output=True,
            timeout=15,
            env=safe_env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            raise ValueError()
        data = json.loads(result.stdout)
        if data.get("error"):
            raise HTTPException(422, data["error"])
        return data["text"]
    except (ValueError, KeyError, subprocess.TimeoutExpired):
        raise HTTPException(422, "pdf_processing_limit_or_invalid_document") from None


async def public_address(host):
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
        addresses = {item[4][0] for item in records}
        if not addresses or any(
            not ipaddress.ip_address(value).is_global
            or ipaddress.ip_address(value).is_multicast
            or ipaddress.ip_address(value).is_reserved
            for value in addresses
        ):
            raise ValueError()
        return sorted(addresses)[0]
    except (OSError, ValueError):
        raise HTTPException(422, "public_https_address_required") from None


async def fetch_text(url, transport=None, resolver=public_address):
    async with httpx.AsyncClient(
        timeout=12, follow_redirects=False, trust_env=False, transport=transport
    ) as client:
        for _ in range(4):
            try:
                parsed = urlsplit(url)
                port = parsed.port
                host = (parsed.hostname or "").encode("idna").decode()
            except (ValueError, UnicodeError):
                raise HTTPException(422, "public_https_address_required") from None
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or port not in {None, 443}
            ):
                raise HTTPException(422, "public_https_address_required")
            address = await resolver(host)
            if (
                not ipaddress.ip_address(address).is_global
                or ipaddress.ip_address(address).is_multicast
                or ipaddress.ip_address(address).is_reserved
            ):
                raise HTTPException(422, "public_https_address_required")
            authority = "[" + address + "]" if ":" in address else address
            pinned = urlunsplit(("https", authority, parsed.path or "/", parsed.query, ""))
            try:
                async with client.stream(
                    "GET",
                    pinned,
                    headers={"Host": host, "User-Agent": "AI-MOS/0.4 source-ingestion"},
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    kind = response.headers.get("content-type", "").split(";")[0].lower()
                    if kind not in {"text/html", "text/plain"}:
                        raise HTTPException(422, "html_or_plain_text_required")
                    chunks = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise HTTPException(413, "web_document_too_large")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode("utf-8", "replace")
                    result = html_text(body) if kind == "text/html" else body[:200000]
                    if len(result.strip()) < 10:
                        raise HTTPException(422, "document_text_missing")
                    return result, url
            except httpx.HTTPError:
                raise HTTPException(502, "source_fetch_failed") from None
    raise HTTPException(422, "too_many_redirects")
