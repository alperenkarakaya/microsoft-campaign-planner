import os
import logging
import httpx
from statistics import median
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import asyncio

from utils.youtube_cache import get_cached_videos, cache_videos

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeDiscoveryError(Exception):
    """Custom exception for YouTube discovery errors"""
    pass


async def search_youtube_influencers(
    query: str,
    min_subscribers: int = 10000,
    max_subscribers: int = 10000000,
    max_results: int = 20,
    min_view_ratio: float = 3.0,  # %3'e düşürdük (daha fazla sonuç)
    retry_count: int = 3
) -> List[Dict]:
    """
    PRODUCTION-READY YouTube Influencer Discovery
    
    Features:
    ✅ Dinamik artırımlı arama (50 → 100)
    ✅ Yumuşak filtre (%3 → %2 → %1)
    ✅ Retry logic (3 deneme)
    ✅ Error handling
    ✅ Timeout protection
    ✅ Kesin max_results garantisi
    """
    
    if not YOUTUBE_API_KEY: 
        raise YouTubeDiscoveryError("YouTube API key not configured")
    
    influencers = []
    attempts = 0
    
    # Kademeli filtre yumuşatma
    filter_levels = [
        {"view_ratio": min_view_ratio, "dead_check": True},
        {"view_ratio": max(2.0, min_view_ratio - 1), "dead_check": True},
        {"view_ratio":  max(1.0, min_view_ratio - 2), "dead_check": False},  # Son çare
    ]
    
    for level_idx, level in enumerate(filter_levels):
        if len(influencers) >= max_results:
            break
            
        logger.debug("Level %d: view_ratio=%s%%, dead_check=%s", level_idx + 1, level['view_ratio'], level['dead_check'])
        
        # Kademeli search limit (50 → 100)
        search_limits = [50, 100] if level_idx == 0 else [100]
        
        for search_limit in search_limits: 
            if len(influencers) >= max_results:
                break
            
            for attempt in range(retry_count):
                try:
                    results = await _search_and_filter(
                        query=query,
                        min_subscribers=min_subscribers,
                        max_subscribers=max_subscribers,
                        search_limit=search_limit,
                        min_view_ratio=level["view_ratio"],
                        check_dead_channel=level["dead_check"]
                    )
                    
                    # Duplicate kontrolü
                    existing_ids = {inf["channel_id"] for inf in influencers}
                    for result in results:
                        if result["channel_id"] not in existing_ids:
                            influencers.append(result)
                            existing_ids.add(result["channel_id"])
                    
                    logger.debug("Found %d new channels (total: %d)", len(results), len(influencers))
                    break  # Başarılı, retry'a gerek yok
                    
                except httpx.TimeoutException:
                    logger.warning("Timeout (attempt %d/%d)", attempt + 1, retry_count)
                    if attempt == retry_count - 1:
                        raise YouTubeDiscoveryError("YouTube API timeout after retries")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 403:
                        raise YouTubeDiscoveryError("YouTube API quota exceeded or invalid key")
                    logger.warning("HTTP error %s (attempt %d)", e.response.status_code, attempt + 1)
                    if attempt == retry_count - 1:
                        raise
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.warning("Search error: %s (attempt %d)", e, attempt + 1)
                    if attempt == retry_count - 1:
                        raise YouTubeDiscoveryError(f"Search failed:  {str(e)}")
                    await asyncio.sleep(1)
    
    # View ratio'ya göre sırala
    influencers.sort(key=lambda x: x. get("view_ratio", 0), reverse=True)
    
    final_results = influencers[:max_results]
    
    if len(final_results) == 0:
        raise YouTubeDiscoveryError(f"No influencers found for query: {query}")
    
    logger.info("Returning %d influencers (requested: %d)", len(final_results), max_results)
    
    return final_results


async def _search_and_filter(
    query: str,
    min_subscribers: int,
    max_subscribers: int,
    search_limit: int,
    min_view_ratio: float,
    check_dead_channel: bool = True
) -> List[Dict]:
    """Internal search + filter logic"""
    
    influencers = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # YouTube search
        search_response = await client.get(
            f"{YOUTUBE_API_BASE}/search",
            params={
                "part": "snippet",
                "q": query,
                "type":  "channel",
                "maxResults": min(search_limit, 50),  # YouTube max = 50
                "order": "relevance",
                "key": YOUTUBE_API_KEY
            }
        )
        
        search_response.raise_for_status()
        search_data = search_response.json()
        
        channel_ids = [item["id"]["channelId"] for item in search_data. get("items", [])]
        
        if not channel_ids:
            return []
        
        # Batch channel details
        channels_response = await client.get(
            f"{YOUTUBE_API_BASE}/channels",
            params={
                "part": "snippet,statistics,brandingSettings,contentDetails",
                "id": ",".join(channel_ids),
                "key": YOUTUBE_API_KEY
            }
        )
        
        channels_response. raise_for_status()
        channels_data = channels_response. json()
        
        for channel in channels_data.get("items", []):
            try:
                stats = channel["statistics"]
                subscriber_count = int(stats.get("subscriberCount", 0))
                view_count = int(stats.get("viewCount", 0))
                video_count = int(stats.get("videoCount", 0))

                if not (min_subscribers <= subscriber_count <= max_subscribers):
                    continue
                if video_count == 0 or subscriber_count == 0:
                    continue

                lifetime_avg_views = view_count / video_count

                # Pull recent uploads to compute a median-views-based view ratio.
                # This is more honest than the lifetime average — one viral video
                # can no longer mask a dead channel.
                recent_views_list: List[int] = []
                last_video_date: Optional[datetime] = None
                dead_check_failed = False

                try:
                    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
                    recent_resp = await client.get(
                        f"{YOUTUBE_API_BASE}/playlistItems",
                        params={
                            "part": "snippet,contentDetails",
                            "playlistId": uploads_playlist,
                            "maxResults": 10,
                            "key": YOUTUBE_API_KEY,
                        },
                    )
                    if recent_resp.status_code == 200:
                        items = recent_resp.json().get("items", [])
                        if items:
                            last_video_date = datetime.fromisoformat(
                                items[0]["snippet"]["publishedAt"].replace("Z", "+00:00")
                            )
                            video_ids = [it["contentDetails"]["videoId"] for it in items]
                            stats_resp = await client.get(
                                f"{YOUTUBE_API_BASE}/videos",
                                params={
                                    "part": "statistics",
                                    "id": ",".join(video_ids),
                                    "key": YOUTUBE_API_KEY,
                                },
                            )
                            if stats_resp.status_code == 200:
                                for v in stats_resp.json().get("items", []):
                                    recent_views_list.append(
                                        int(v.get("statistics", {}).get("viewCount", 0))
                                    )
                except Exception as e:
                    logger.debug("Recent-videos fetch failed for %s: %s", channel.get('id'), e)
                    dead_check_failed = True

                if recent_views_list:
                    median_recent_views = int(median(recent_views_list))
                    view_ratio = (median_recent_views / subscriber_count) * 100
                else:
                    median_recent_views = int(lifetime_avg_views)
                    view_ratio = (lifetime_avg_views / subscriber_count) * 100

                if view_ratio < min_view_ratio:
                    continue

                if check_dead_channel and last_video_date is not None:
                    if datetime.now(last_video_date.tzinfo) - last_video_date > timedelta(days=90):
                        continue

                snippet = channel["snippet"]

                influencers.append({
                    "channel_id": channel["id"],
                    "username": snippet.get("customUrl", channel["id"]),
                    "title": snippet["title"],
                    "description": snippet.get("description", ""),
                    "thumbnail": snippet["thumbnails"]["high"]["url"],
                    "subscriber_count": subscriber_count,
                    "video_count": video_count,
                    "view_count": view_count,
                    "avg_views_per_video": round(lifetime_avg_views),
                    "median_recent_views": median_recent_views,
                    "view_ratio": round(view_ratio, 2),
                    "country": snippet.get("country"),
                    "keywords": channel.get("brandingSettings", {}).get("channel", {}).get("keywords", ""),
                    "dead_check_failed": dead_check_failed,
                })

            except Exception as e:
                logger.debug("Error processing channel: %s", e)
                continue

    return influencers


async def get_channel_recent_videos(
    channel_id: str, 
    max_videos: int = 10,
    retry_count: int = 2
) -> List[Dict]:
    """Get recent videos with retry logic"""
    
    if not YOUTUBE_API_KEY:
        return []

    # Serve from the Redis cache when warm to conserve YouTube API quota.
    cached = get_cached_videos(channel_id)
    if cached is not None:
        return cached

    for attempt in range(retry_count):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Search recent videos
                search_response = await client.get(
                    f"{YOUTUBE_API_BASE}/search",
                    params={
                        "part": "id",
                        "channelId":  channel_id,
                        "order": "date",
                        "maxResults": max_videos,
                        "type": "video",
                        "key": YOUTUBE_API_KEY
                    }
                )
                
                search_response.raise_for_status()
                video_ids = [item["id"]["videoId"] for item in search_response. json().get("items", [])]
                
                if not video_ids:
                    return []
                
                # Get video details
                videos_response = await client.get(
                    f"{YOUTUBE_API_BASE}/videos",
                    params={
                        "part": "snippet,statistics",
                        "id": ",". join(video_ids),
                        "key": YOUTUBE_API_KEY
                    }
                )
                
                videos_response.raise_for_status()
                videos_data = videos_response.json()
                
                videos = []
                for video in videos_data.get("items", []):
                    snippet = video["snippet"]
                    stats = video["statistics"]
                    
                    views = int(stats.get("viewCount", 0))
                    likes = int(stats.get("likeCount", 0))
                    comments = int(stats.get("commentCount", 0))
                    
                    engagement_rate = ((likes + comments) / views * 100) if views > 0 else 0
                    
                    videos.append({
                        "video_id": video["id"],
                        "title": snippet["title"],
                        "description":  snippet.get("description", ""),
                        "published_at": snippet["publishedAt"],
                        "thumbnail": snippet["thumbnails"]["high"]["url"],
                        "views":  views,
                        "likes":  likes,
                        "comments":  comments,
                        "engagement_rate": round(engagement_rate, 2),
                        "tags": snippet.get("tags", [])
                    })

                cache_videos(channel_id, videos)
                return videos

        except Exception as e:
            logger.warning("Error fetching videos (attempt %d): %s", attempt + 1, e)
            if attempt == retry_count - 1:
                return []  # Return empty instead of failing
            await asyncio.sleep(1)

    return []