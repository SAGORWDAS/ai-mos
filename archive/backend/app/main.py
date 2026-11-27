from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="AI-MOS API", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    checks = {"database": False, "redis": False}
    try:
        async with session_factory() as session:
            await session.execute(text("select 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(await redis_client.ping())
    except Exception:
        pass
    ok = all(checks.values())
    body = {"status": "ok" if ok else "degraded", "checks": checks}
    return JSONResponse(body, status_code=200 if ok else 503)
