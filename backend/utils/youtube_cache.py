"""Redis-backed cache for YouTube API responses.

YouTube Data API quota is the main scaling constraint for discovery, so recent
video lookups are cached for a day. The cache degrades gracefully: if Redis is
unavailable, every helper returns "miss"/no-op instead of raising, so discovery
still works (just without the quota savings).
"""

import os
import json
import logging
from typing import Optional, List

import redis

logger = logging.getLogger(__name__)

CACHE_TTL = 86400  # 24h

_redis_client: Optional[redis.Redis] = None


def _client() -> Optional[redis.Redis]:
    """Lazily create a Redis client. Returns None if construction fails."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379"),
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as e:  # pragma: no cover - construction rarely fails
            logger.warning("Redis client init failed: %s", e)
            return None
    return _redis_client


def get_cached_videos(channel_id: str) -> Optional[List[dict]]:
    """Return cached recent videos for a channel, or None on miss/error."""
    client = _client()
    if client is None:
        return None
    try:
        cached = client.get(f"youtube:videos:{channel_id}")
    except Exception as e:
        logger.debug("Redis GET failed for %s: %s", channel_id, e)
        return None
    if cached:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            return None
    return None


def cache_videos(channel_id: str, videos: List[dict]) -> None:
    """Store recent videos for a channel. No-op on error."""
    client = _client()
    if client is None:
        return
    try:
        client.setex(f"youtube:videos:{channel_id}", CACHE_TTL, json.dumps(videos))
    except Exception as e:
        logger.debug("Redis SETEX failed for %s: %s", channel_id, e)


def get_cached_comments(channel_id: str) -> Optional[dict]:
    """Return cached comment samples for a channel, or None on miss/error.

    Returns a dict with:
      - comment_samples: list of {author, text, video_id} dicts
      - per_video_comments: dict mapping video_id -> list of comment dicts
    """
    client = _client()
    if client is None:
        return None
    try:
        cached = client.get(f"youtube:comments:{channel_id}")
    except Exception as e:
        logger.debug("Redis GET comments failed for %s: %s", channel_id, e)
        return None
    if cached:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            return None
    return None


def cache_comments(channel_id: str, comment_data: dict) -> None:
    """Store comment samples for a channel. No-op on error.

    Args:
        channel_id: YouTube channel ID.
        comment_data: dict with 'comment_samples' and 'per_video_comments' keys.
    """
    client = _client()
    if client is None:
        return
    try:
        client.setex(
            f"youtube:comments:{channel_id}", CACHE_TTL, json.dumps(comment_data),
        )
    except Exception as e:
        logger.debug("Redis SETEX comments failed for %s: %s", channel_id, e)
