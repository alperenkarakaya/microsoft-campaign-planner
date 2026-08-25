import os
import logging
from typing import Dict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeAPIError(Exception):
    """Raised when the YouTube Data API fails after retries or returns no data."""


# Retry on network/timeout errors and transient 5xx; do NOT retry 4xx (auth/quota).
_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
)
async def _yt_get(client: httpx.AsyncClient, path: str, params: Dict) -> Dict:
    """GET helper with retry on transient errors. Raises YouTubeAPIError on non-2xx."""
    response = await client.get(f"{YOUTUBE_API_BASE}{path}", params=params)
    if response.status_code != 200:
        # 4xx (quota, bad key, not found): don't retry — fail loud.
        raise YouTubeAPIError(f"YouTube API {response.status_code}: {response.text[:200]}")
    return response.json()


async def get_youtube_channel_data(channel_id: str) -> Dict:
    """Fetch a channel's stats + a quick engagement-rate proxy from recent videos."""
    if not YOUTUBE_API_KEY:
        raise YouTubeAPIError("YouTube API key not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        channel_data = await _yt_get(client, "/channels", {
            "part": "snippet,statistics,brandingSettings",
            "id": channel_id,
            "key": YOUTUBE_API_KEY,
        })

        if not channel_data.get("items"):
            raise YouTubeAPIError("Channel not found")

        item = channel_data["items"][0]
        snippet = item["snippet"]
        statistics = item["statistics"]

        videos_response = await _yt_get(client, "/search", {
            "part": "id",
            "channelId": channel_id,
            "order": "date",
            "maxResults": 10,
            "type": "video",
            "key": YOUTUBE_API_KEY,
        })

        video_ids = [v["id"]["videoId"] for v in videos_response.get("items", [])]

        engagement_rate = 0.0
        if video_ids:
            videos_stats = await _yt_get(client, "/videos", {
                "part": "statistics",
                "id": ",".join(video_ids),
                "key": YOUTUBE_API_KEY,
            })

            total_engagement = 0
            total_views = 0
            for video in videos_stats.get("items", []):
                stats = video["statistics"]
                total_views += int(stats.get("viewCount", 0))
                total_engagement += int(stats.get("likeCount", 0)) + int(stats.get("commentCount", 0))
            if total_views > 0:
                engagement_rate = (total_engagement / total_views) * 100

        return {
            "channel_id": channel_id,
            "username": snippet.get("customUrl", channel_id),
            "title": snippet["title"],
            "description": snippet.get("description", ""),
            "thumbnail": snippet["thumbnails"]["high"]["url"],
            "subscriber_count": int(statistics.get("subscriberCount", 0)),
            "video_count": int(statistics.get("videoCount", 0)),
            "view_count": int(statistics.get("viewCount", 0)),
            "engagement_rate": round(engagement_rate, 2),
            "country": snippet.get("country"),
            "category": item.get("brandingSettings", {}).get("channel", {}).get("keywords", ""),
            "verified": snippet.get("customUrl") is not None,
            "published_at": snippet["publishedAt"],
        }


async def search_youtube_channels(query: str, max_results: int = 10) -> list:
    if not YOUTUBE_API_KEY:
        raise YouTubeAPIError("YouTube API key not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        data = await _yt_get(client, "/search", {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
        })

    return [
        {
            "channel_id": item["id"]["channelId"],
            "title": item["snippet"]["title"],
            "description": item["snippet"]["description"],
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
        }
        for item in data.get("items", [])
    ]
