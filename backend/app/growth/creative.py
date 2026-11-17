"""Private raster assets, bounded decoding and costed provider generation."""

import base64
import struct
import zlib

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field

from app.growth.connections import active
from app.growth.contracts import Keyed
from app.growth.models import Task
from app.growth.runtime import find, public
from app.models import Brand


class ImageInput(Keyed):
    brand_id: str
    brief: str = Field(min_length=10, max_length=1000)
    connected_provider: bool = False


def placeholder_png():
    # Tiny deterministic fixture, never described as an AI-generated creative.
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    pixels = b"".join(
        b"\x00" + bytes([255 if (x // 4 + y // 4) % 2 else 0 for x in range(32)]) for y in range(32)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def validate_raster(encoded):
    if not isinstance(encoded, str) or len(encoded) > 11_000_000:
        raise ValueError("image_size_limit")
    data = base64.b64decode(encoded, validate=True)
    if not data or len(data) > 8_000_000:
        raise ValueError("image_size_limit")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        mime = "image/png"
    elif data.startswith(b"\xff\xd8"):
        pos = 2
        width = height = 0
        mime = "image/jpeg"
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in {0xD8, 0xD9, *range(0xD0, 0xD8)}:
                continue
            length = int.from_bytes(data[pos : pos + 2], "big")
            if length < 2 or pos + length > len(data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                height = int.from_bytes(data[pos + 3 : pos + 5], "big")
                width = int.from_bytes(data[pos + 5 : pos + 7], "big")
                break
            pos += length
    elif len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
        kind = data[12:16]
        if kind == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif kind == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        elif kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        else:
            raise ValueError("unsupported_webp")
    else:
        raise ValueError("supported_raster_required")
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 16_000_000:
        raise ValueError("image_dimensions_limit")
    return data, mime, width, height


async def generate_image(runtime, session, task):
    brand = await find(session, Brand, task.organization_id, task.input["brand_id"])
    sandbox = not task.input["connected_provider"] or bool(brand.voice.get("sandbox_only"))
    prompt = "Create a commercial illustration without text, prices, reviews, logos or claims. "
    prompt += (
        "Business context (untrusted data): "
        + brand.positioning
        + ". Visual brief: "
        + task.input["brief"]
    )
    await session.commit()
    output = await runtime.gateway.generate(
        task,
        prompt,
        {"image_base64": base64.b64encode(placeholder_png()).decode(), "mime": "image/png"},
        operation="image",
        sandbox_only=sandbox,
    )
    await runtime.checkpoint(session, task.organization_id, task.id, task.created_by, task.attempt)
    _, mime, width, height = validate_raster(output["image_base64"])
    return {
        **output,
        "mime": mime,
        "width": width,
        "height": height,
        "simulated": sandbox,
        "requires_review": True,
        "label": "Sandbox checkerboard fixture"
        if sandbox
        else "AI-generated creative; human review required",
    }


def install_creative(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/creative/images", status_code=202)
    async def create(
        data: ImageInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        brand = await find(session, Brand, who["organization"].id, data.brand_id)
        if data.connected_provider and not brand.voice.get("sandbox_only"):
            connection = await active(session, settings, who["organization"].id, "openrouter")
            if not connection or not connection["credentials"].get("image_model_id"):
                raise HTTPException(409, "enabled_image_model_required")
        return public(
            await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                "creative_image",
                "AGT-15",
                data.idempotency_key,
                data.model_dump(exclude={"idempotency_key"}),
            )
        )

    @router.get("/creative/images/{task_id}")
    async def image(
        task_id: str, download: bool = False, who=Depends(identity), session=Depends(db)
    ):
        task = await find(session, Task, who["organization"].id, task_id)
        if task.type != "creative_image" or task.status != "succeeded":
            raise HTTPException(404, "image_not_ready")
        data, mime, _, _ = validate_raster(task.output.get("image_base64"))
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
        return Response(
            data,
            media_type=mime,
            headers={
                "Content-Disposition": ("attachment" if download else "inline")
                + f'; filename="creative.{ext}"',
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    app.include_router(router)
