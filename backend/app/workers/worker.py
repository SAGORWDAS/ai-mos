import asyncio
import json
import logging
import logging.config
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.deployment import enforce_configuration, enforce_database
from app.growth.runtime import Runtime


async def main():
    settings = get_settings()
    enforce_configuration(settings)
    engine = create_async_engine(
        settings.worker_database_url or settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    runtime = Runtime(async_sessionmaker(engine, expire_on_commit=False), settings)
    try:
        if settings.app_env == "validation":
            await enforce_database(engine, worker=True)
        await runtime.loop()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.config.dictConfig(
        json.loads(
            (Path(__file__).resolve().parents[1] / "logging.json").read_text(encoding="utf-8")
        )
    )
    asyncio.run(main())
