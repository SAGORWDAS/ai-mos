"""Atomic shared-window auth throttling, independent of web process count or Redis."""

import hashlib
import hmac
import time

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import AuthRateLimit


class AuthLimiter:
    def __init__(self, factory, secret, limit=20):
        self.factory, self.secret, self.limit = factory, secret.encode(), limit
        self.last_cleanup = 0

    async def allow(self, address):
        now = time.time()
        window = int(now // 60)
        key = hmac.new(
            self.secret, (address + ":auth:" + str(window)).encode(), hashlib.sha256
        ).hexdigest()
        async with self.factory() as session:
            insert = sqlite_insert if session.bind.dialect.name == "sqlite" else postgres_insert
            result = await session.execute(
                insert(AuthRateLimit)
                .values(key_hash=key, counter=1, expires_at=(window + 2) * 60)
                .on_conflict_do_update(
                    index_elements=["key_hash"],
                    set_={"counter": AuthRateLimit.counter + 1},
                    where=AuthRateLimit.counter < self.limit,
                )
            )
            if now - self.last_cleanup > 60:
                await session.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at < now))
                self.last_cleanup = now
            await session.commit()
            return result.rowcount == 1
