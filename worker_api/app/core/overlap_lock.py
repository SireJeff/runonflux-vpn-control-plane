"""Redis-backed overlap lock for FDM sync (Phase 4.3).

Prevents concurrent execution of FdmSyncService.sync_all_deployments across
processes (celery beat task + in-process HTTP triggers). Fail-open: if Redis
is unavailable, the lock is a no-op and the sync proceeds unprotected
(matches the codebase Optional-Redis philosophy; a Redis blip must not halt
FDM convergence).
"""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

DEFAULT_TTL = 1200  # 20 min = 2x the 600s beat; > normal 4-5 min sync

# Release only if the lock still belongs to this token (atomic CAS). Prevents
# a slow holder deleting a NEWER owner's lock after the original's TTL expired.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


@asynccontextmanager
async def overlap_lock(key: str, ttl: Optional[int] = None):
    """Async context manager yielding `acquired: bool`.

    Acquire: SET key <token> NX EX ttl (atomic). Token is uuid4 so the holder
    only ever releases its OWN lock.

    Fail-open: if Redis is None or raises at acquire, yields True and logs a
    warning — the sync proceeds unprotected.
    """
    client = get_redis()
    if client is None:
        logger.warning("Overlap lock %s skipped: Redis not configured (fail-open)", key)
        yield True
        return

    lock_ttl = ttl or getattr(settings, "FDM_SYNC_LOCK_TTL_SECONDS", DEFAULT_TTL)
    token = uuid.uuid4().hex

    try:
        acquired = bool(client.set(key, token, nx=True, ex=lock_ttl))
    except redis.RedisError as e:
        logger.warning(
            "Overlap lock %s acquire failed (%s); proceeding fail-open", key, e
        )
        yield True
        return

    if not acquired:
        logger.info("Overlap lock %s held by another runner; skipping", key)
        yield False
        return

    logger.info("Overlap lock %s acquired (ttl=%ss)", key, lock_ttl)
    try:
        yield True
    finally:
        try:
            client.eval(_RELEASE_SCRIPT, 1, key, token)  # type: ignore[arg-type]  # redis-py stub over-constrains eval() KEYS/ARGV positionals
        except redis.RedisError as e:
            # Non-fatal: TTL will eventually expire the key.
            logger.warning(
                "Overlap lock %s release failed (%s); TTL will expire it", key, e
            )
