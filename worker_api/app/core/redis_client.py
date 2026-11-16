"""
Redis client for caching and rate limiting
"""

import logging
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Redis client (optional - None if REDIS_URL not set)
redis_client: Optional[redis.Redis] = None

if settings.REDIS_URL:
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("Redis client initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Redis client: {e}")
        redis_client = None
else:
    logger.info("Redis URL not configured - caching disabled")


def get_redis() -> Optional[redis.Redis]:
    """
    Get Redis client instance

    Usage:
        from app.core.redis_client import get_redis
        redis = get_redis()
        if redis:
            redis.set("key", "value")
    """
    return redis_client
