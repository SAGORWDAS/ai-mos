import asyncio
import logging

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("worker")

HEARTBEAT_SECONDS = 10


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        async with session_factory() as session:
            await session.execute(text("select 1"))
        await redis_client.ping()
        log.info("worker ready; no job handlers registered yet (T-1.5 registers them)")

        while True:
            await redis_client.set("worker:heartbeat", "1", ex=HEARTBEAT_SECONDS * 3)
            await asyncio.sleep(HEARTBEAT_SECONDS)
    finally:
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
