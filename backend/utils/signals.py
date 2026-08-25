"""
Deterministic signal layer (Phase 1) — per-creator YouTube signals.

All signals here are deterministic and high-confidence: computed from raw
YouTube API data with no LLM involvement. Every signal carries enough
metadata to be auditable; missing data returns None, never a synthetic
default (following the ai_detector.py no-fabrication rule).

Signals computed:
  - subscriber_count, view_count, video_count
  - recent_view_median, recent_view_variance (loyalty proxy)
  - like_to_view_ratio, comment_to_view_ratio (depth ratios)
  - upload_cadence_days, last_upload_days_ago (recency)
  - creator_reply_rate (if obtainable via comments API; None otherwise)
  - sponsorship_detection: paidProductPlacement flag + description parsing

The output dict is stored as Influencer.enrichment_signals JSON blob.

Design choice — JSON blob on Influencer vs dedicated table:
  We store signals as a JSON column on Influencer (matching the pattern of
  InfluencerAnalysis.predicted_outcome). Rationale: these signals are
  1:1 with an influencer, refreshed as a unit, and the schema evolves as
  new signals are added. A dedicated table would be justified only if we
  needed relational queries across individual signal values, which is not
  the case for Phase 1.
"""

import logging
import re
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from utils.youtube_api import YOUTUBE_API_KEY, YOUTUBE_API_BASE, YouTubeAPIError
from utils.youtube_cache import (
    get_cached_videos, cache_videos,
    get_cached_comments, cache_comments,
    CACHE_TTL,
)

logger = logging.getLogger(__name__)

# --- Sponsorship detection patterns -------------------------------------------

# Affiliate / promo patterns in video descriptions.
_SPONSORSHIP_PATTERNS = [
    re.compile(r"\buse\s+code\b", re.IGNORECASE),
    re.compile(r"\bpromo\s*code\b", re.IGNORECASE),
    re.compile(r"\bdiscount\s*code\b", re.IGNORECASE),
    re.compile(r"\bcoupon\s*code\b", re.IGNORECASE),
    re.compile(r"\baffiliate\s*link\b", re.IGNORECASE),
    re.compile(r"\bsponsored\s*by\b", re.IGNORECASE),
    re.compile(r"\bthanks\s+to\s+\w+\s+for\s+sponsoring\b", re.IGNORECASE),
    re.compile(r"\bpartner(?:ship|ed)\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)#ad(?:\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|\s)#sponsored(?:\s|$)", re.IGNORECASE),
]

# Common brand/affiliate URL patterns.
_BRAND_URL_PATTERNS = [
    re.compile(r"https?://(?:www\.)?(?:bit\.ly|goo\.gl|tinyurl\.com|amzn\.to|shrsl\.com|go\.magik\.ly)/", re.IGNORECASE),
    re.compile(r"https?://\S+\?(?:\S*(?:ref|aff|utm_source|partner|code)=)", re.IGNORECASE),
]

# Self-promotion / social-media domains that creators link to for their own
# presence.  These are NOT brand sponsorship signals and must be filtered out
# to avoid false-positive inflation of maturity scores and repeat-sponsor
# counts.
_SELF_PROMO_DOMAINS: set = {
    # Social platforms
    "twitter.com", "x.com", "instagram.com", "facebook.com",
    "tiktok.com", "threads.net", "bsky.app", "tumblr.com",
    # Video / streaming
    "youtube.com", "youtu.be", "twitch.tv", "trovo.live", "kick.com",
    # Community / messaging
    "discord.com", "discord.gg", "discordapp.com", "reddit.com",
    # Donation / tipping
    "patreon.com", "ko-fi.com", "paypal.com", "paypal.me",
    "cashapp.com", "venmo.com", "streamlabs.com", "streamelements.com",
    "throne.com",
    # Link aggregators
    "linktr.ee", "linktree.com",
    # Merch / creator storefronts
    "teespring.com", "redbubble.com", "spreadshop.com",
    # Gaming storefronts (creator profiles, not brand deals)
    "steamcommunity.com", "store.steampowered.com",
    # Art / portfolio
    "deviantart.com",
}

# Pre-compiled regex to extract the domain from a URL for stoplist checks.
_URL_DOMAIN_RE = re.compile(
    r"https?://(?:www\.)?([a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)", re.IGNORECASE,
)


def _url_is_self_promo(url: str) -> bool:
    """Return True if *url* belongs to a self-promotion / social domain."""
    m = _URL_DOMAIN_RE.search(url)
    if not m:
        return False
    domain = m.group(1).lower()
    # Check exact match first, then check if the domain ends with a
    # stoplist entry (handles subdomains like "store.steampowered.com").
    if domain in _SELF_PROMO_DOMAINS:
        return True
    for sd in _SELF_PROMO_DOMAINS:
        if domain.endswith("." + sd):
            return True
    return False


def detect_sponsorship_signals(description: str) -> Dict[str, Any]:
    """Detect sponsorship indicators in a video description.

    Returns a dict with:
      - has_promo_code: bool — "use code" / "promo code" / etc.
      - has_affiliate_link: bool — shortened/tracked URLs
      - has_sponsorship_mention: bool — "sponsored by" / "#ad" / etc.
      - matched_patterns: list of pattern labels that fired (audit trail)

    Self-promotion links (social media, donation platforms, merch stores)
    are excluded from affiliate-link detection to avoid false positives.
    Non-URL patterns ("sponsored by BRAND", "#ad") are kept regardless.

    Does NOT score or judge the sponsorship quality — that is Phase 3.
    """
    if not description:
        return {
            "has_promo_code": False,
            "has_affiliate_link": False,
            "has_sponsorship_mention": False,
            "matched_patterns": [],
        }

    matched = []
    has_promo = False
    has_affiliate = False
    has_mention = False

    for pat in _SPONSORSHIP_PATTERNS:
        if pat.search(description):
            label = pat.pattern
            matched.append(label)
            # Classify the match.
            lower_pat = label.lower()
            if "code" in lower_pat:
                has_promo = True
            elif "affiliate" in lower_pat or "link" in lower_pat:
                has_affiliate = True
            else:
                has_mention = True

    for pat in _BRAND_URL_PATTERNS:
        for m in pat.finditer(description):
            url_text = m.group(0)
            if _url_is_self_promo(url_text):
                logger.debug("Ignoring self-promo URL in sponsorship detection: %s", url_text)
                continue
            matched.append(pat.pattern)
            has_affiliate = True

    return {
        "has_promo_code": has_promo,
        "has_affiliate_link": has_affiliate,
        "has_sponsorship_mention": has_mention,
        "matched_patterns": matched,
    }


def compute_upload_cadence(
    published_dates: List[datetime],
) -> Dict[str, Optional[float]]:
    """Compute upload frequency from a list of publish timestamps.

    Returns:
      - cadence_days_median: median days between uploads (None if < 2 videos)
      - cadence_days_mean: mean days between uploads (None if < 2 videos)
      - last_upload_days_ago: days since most recent upload (None if empty)
    """
    if not published_dates:
        return {
            "cadence_days_median": None,
            "cadence_days_mean": None,
            "last_upload_days_ago": None,
        }

    sorted_dates = sorted(published_dates, reverse=True)
    now = datetime.now(timezone.utc)

    # Ensure all dates are timezone-aware for comparison.
    aware_dates = []
    for d in sorted_dates:
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        aware_dates.append(d)

    last_upload_days = (now - aware_dates[0]).total_seconds() / 86400

    if len(aware_dates) < 2:
        return {
            "cadence_days_median": None,
            "cadence_days_mean": None,
            "last_upload_days_ago": round(last_upload_days, 1),
        }

    gaps = []
    for i in range(len(aware_dates) - 1):
        gap = (aware_dates[i] - aware_dates[i + 1]).total_seconds() / 86400
        gaps.append(gap)

    return {
        "cadence_days_median": round(statistics.median(gaps), 1),
        "cadence_days_mean": round(statistics.mean(gaps), 1),
        "last_upload_days_ago": round(last_upload_days, 1),
    }


def compute_engagement_depth(
    videos: List[Dict],
) -> Dict[str, Optional[float]]:
    """Compute like-to-view and comment-to-view depth ratios.

    Uses the MEDIAN across videos (not mean) to resist outlier inflation.

    Returns:
      - like_to_view_ratio: median(likes/views) across videos (None if no valid data)
      - comment_to_view_ratio: median(comments/views) across videos (None if no valid data)
      - sample_size: number of videos with views > 0
    """
    like_ratios = []
    comment_ratios = []

    for v in videos:
        views = int(v.get("views", 0) or 0)
        if views <= 0:
            continue
        likes = int(v.get("likes", 0) or 0)
        comments = int(v.get("comments", 0) or 0)
        like_ratios.append(likes / views)
        comment_ratios.append(comments / views)

    if not like_ratios:
        return {
            "like_to_view_ratio": None,
            "comment_to_view_ratio": None,
            "sample_size": 0,
        }

    return {
        "like_to_view_ratio": round(statistics.median(like_ratios), 6),
        "comment_to_view_ratio": round(statistics.median(comment_ratios), 6),
        "sample_size": len(like_ratios),
    }


def compute_view_consistency(
    view_counts: List[int],
) -> Dict[str, Optional[float]]:
    """Compute recent-view median and variance as a loyalty proxy.

    Low variance = loyal base that watches consistently.
    High variance = algorithm-driven spikes (one viral video inflates averages).

    Returns:
      - recent_view_median: int or None
      - recent_view_variance: float or None (population variance)
      - recent_view_stdev: float or None (population standard deviation)
      - recent_view_cv: float or None (coefficient of variation = stdev/mean)
      - sample_size: int
    """
    if not view_counts:
        return {
            "recent_view_median": None,
            "recent_view_variance": None,
            "recent_view_stdev": None,
            "recent_view_cv": None,
            "sample_size": 0,
        }

    valid = [v for v in view_counts if v >= 0]
    if not valid:
        return {
            "recent_view_median": None,
            "recent_view_variance": None,
            "recent_view_stdev": None,
            "recent_view_cv": None,
            "sample_size": 0,
        }

    med = int(statistics.median(valid))
    mean_val = statistics.mean(valid)

    if len(valid) >= 2:
        var = statistics.pvariance(valid)
        stdev = statistics.pstdev(valid)
        cv = round(stdev / mean_val, 4) if mean_val > 0 else None
    else:
        var = None
        stdev = None
        cv = None

    return {
        "recent_view_median": med,
        "recent_view_variance": round(var, 2) if var is not None else None,
        "recent_view_stdev": round(stdev, 2) if stdev is not None else None,
        "recent_view_cv": cv,
        "sample_size": len(valid),
    }


async def fetch_creator_reply_rate(
    channel_id: str,
    video_ids: List[str],
    *,
    max_videos: int = 5,
    max_comments_per_video: int = 20,
    capture_comments: bool = False,
) -> Optional[Dict[str, Any]]:
    """Estimate the creator's reply rate to top-level comments.

    Uses the YouTube commentThreads API. Returns None if:
      - API key is missing
      - Comments are disabled on videos
      - Quota/availability prevents retrieval

    Returns:
      - reply_rate: float (0-1) — fraction of top-level comments that got a
        creator reply
      - total_threads_sampled: int
      - creator_replies_found: int
      - videos_sampled: int
      - comment_samples: list of {author, text, video_id} dicts (only when
        capture_comments=True; empty list otherwise). These are the top-level
        comments already fetched for reply-rate — capturing them costs zero
        extra quota.
      - per_video_comments: dict mapping video_id -> list of comment dicts
        (only when capture_comments=True). Enables callers to split comments
        by sponsored vs organic video without re-fetching.
    """
    if not YOUTUBE_API_KEY:
        return None

    if not video_ids:
        return None

    sample_ids = video_ids[:max_videos]
    total_threads = 0
    creator_replies = 0
    videos_sampled = 0
    comment_samples: List[Dict[str, Any]] = []
    per_video_comments: Dict[str, List[Dict[str, Any]]] = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for vid_id in sample_ids:
            try:
                resp = await client.get(
                    f"{YOUTUBE_API_BASE}/commentThreads",
                    params={
                        "part": "snippet,replies",
                        "videoId": vid_id,
                        "maxResults": max_comments_per_video,
                        "order": "relevance",
                        "key": YOUTUBE_API_KEY,
                    },
                )

                if resp.status_code == 403:
                    # Comments disabled or quota exceeded; degrade gracefully.
                    logger.debug("Comments unavailable for video %s (403)", vid_id)
                    continue
                if resp.status_code != 200:
                    logger.debug("commentThreads returned %s for %s", resp.status_code, vid_id)
                    continue

                threads = resp.json().get("items", [])
                if not threads:
                    continue

                videos_sampled += 1
                vid_comments: List[Dict[str, Any]] = []

                for thread in threads:
                    total_threads += 1
                    # Check if the channel owner replied.
                    snippet = thread.get("snippet", {})
                    top_comment = snippet.get("topLevelComment", {}).get("snippet", {})
                    # Replies may be in thread["replies"]["comments"].
                    replies = thread.get("replies", {}).get("comments", [])
                    for reply in replies:
                        reply_channel = reply.get("snippet", {}).get("authorChannelId", {}).get("value", "")
                        if reply_channel == channel_id:
                            creator_replies += 1
                            break  # Count at most one creator reply per thread.

                    # Capture the top-level comment text for downstream
                    # trust/sponsorship analysis — zero extra API cost.
                    if capture_comments and top_comment:
                        comment_dict = {
                            "author": top_comment.get("authorDisplayName", ""),
                            "text": top_comment.get("textDisplay", ""),
                            "video_id": vid_id,
                        }
                        comment_samples.append(comment_dict)
                        vid_comments.append(comment_dict)

                if capture_comments and vid_comments:
                    per_video_comments[vid_id] = vid_comments

            except Exception as e:
                logger.debug("Error fetching comments for %s: %s", vid_id, e)
                continue

    if total_threads == 0:
        return None

    result: Dict[str, Any] = {
        "reply_rate": round(creator_replies / total_threads, 4),
        "total_threads_sampled": total_threads,
        "creator_replies_found": creator_replies,
        "videos_sampled": videos_sampled,
    }

    if capture_comments:
        result["comment_samples"] = comment_samples
        result["per_video_comments"] = per_video_comments

    return result


async def compute_signals_for_channel(
    channel_id: str,
    *,
    max_recent_videos: int = 10,
    fetch_comments: bool = True,
) -> Optional[Dict[str, Any]]:
    """Compute all Phase 1 deterministic signals for a single channel.

    Reuses the YouTube client and Redis cache. Returns None if the channel
    cannot be reached at all (no API key, channel not found). Individual
    sub-signals return None when their specific data is unavailable.

    The returned dict is the enrichment_signals blob stored on Influencer.
    """
    if not YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY not set; cannot compute signals.")
        return None

    async with httpx.AsyncClient(timeout=20.0) as client:
        # --- Channel stats ---------------------------------------------------
        try:
            ch_resp = await client.get(
                f"{YOUTUBE_API_BASE}/channels",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "id": channel_id,
                    "key": YOUTUBE_API_KEY,
                },
            )
            if ch_resp.status_code != 200:
                logger.warning("Channel fetch failed for %s: %s", channel_id, ch_resp.status_code)
                return None

            ch_items = ch_resp.json().get("items", [])
            if not ch_items:
                logger.warning("Channel %s not found", channel_id)
                return None
        except Exception as e:
            logger.warning("Error fetching channel %s: %s", channel_id, e)
            return None

        channel = ch_items[0]
        stats = channel.get("statistics", {})
        snippet = channel.get("snippet", {})

        subscriber_count = int(stats.get("subscriberCount", 0))
        view_count = int(stats.get("viewCount", 0))
        video_count = int(stats.get("videoCount", 0))

        # --- Recent videos (reuse cache) ------------------------------------
        cached = get_cached_videos(channel_id)
        videos: List[Dict] = []
        video_ids: List[str] = []
        published_dates: List[datetime] = []

        if cached is not None:
            videos = cached
        else:
            try:
                uploads_playlist = (
                    channel.get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads")
                )
                if uploads_playlist:
                    pl_resp = await client.get(
                        f"{YOUTUBE_API_BASE}/playlistItems",
                        params={
                            "part": "snippet,contentDetails",
                            "playlistId": uploads_playlist,
                            "maxResults": max_recent_videos,
                            "key": YOUTUBE_API_KEY,
                        },
                    )
                    if pl_resp.status_code == 200:
                        pl_items = pl_resp.json().get("items", [])
                        v_ids = [it["contentDetails"]["videoId"] for it in pl_items]
                        if v_ids:
                            # Batch fetch video stats
                            vs_resp = await client.get(
                                f"{YOUTUBE_API_BASE}/videos",
                                params={
                                    "part": "snippet,statistics,status",
                                    "id": ",".join(v_ids),
                                    "key": YOUTUBE_API_KEY,
                                },
                            )
                            if vs_resp.status_code == 200:
                                for v in vs_resp.json().get("items", []):
                                    v_stats = v.get("statistics", {})
                                    v_snippet = v.get("snippet", {})
                                    v_status = v.get("status", {})
                                    vid_views = int(v_stats.get("viewCount", 0))
                                    vid_likes = int(v_stats.get("likeCount", 0))
                                    vid_comments = int(v_stats.get("commentCount", 0))

                                    engagement_rate = (
                                        ((vid_likes + vid_comments) / vid_views * 100)
                                        if vid_views > 0 else 0
                                    )

                                    vid_data = {
                                        "video_id": v["id"],
                                        "title": v_snippet.get("title", ""),
                                        "description": v_snippet.get("description", ""),
                                        "published_at": v_snippet.get("publishedAt", ""),
                                        "thumbnail": v_snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                                        "views": vid_views,
                                        "likes": vid_likes,
                                        "comments": vid_comments,
                                        "engagement_rate": round(engagement_rate, 2),
                                        "tags": v_snippet.get("tags", []),
                                        "paid_product_placement": v_status.get("madeForKids") is not None and v_status.get("madeForKids") is False,
                                    }

                                    # Check paidProductPlacement via status part.
                                    # The field is contentDetails.contentRating or
                                    # status.selfDeclaredMadeForKids. The actual
                                    # paidPromotion flag is in status (not always
                                    # available via API). We store what we can get.
                                    if "paidProductPlacementDetails" in v.get("status", {}):
                                        vid_data["paid_product_placement"] = (
                                            v["status"]["paidProductPlacementDetails"].get("hasPaidProductPlacement", False)
                                        )
                                    else:
                                        vid_data["paid_product_placement"] = None

                                    videos.append(vid_data)

                                cache_videos(channel_id, videos)

            except Exception as e:
                logger.debug("Recent video fetch failed for %s: %s", channel_id, e)

        # Extract structured data from videos.
        for v in videos:
            video_ids.append(v.get("video_id", ""))
            pub = v.get("published_at", "")
            if pub:
                try:
                    dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    published_dates.append(dt)
                except (ValueError, TypeError):
                    pass

        view_counts = [int(v.get("views", 0)) for v in videos]

        # --- Compute sub-signals -----------------------------------------
        view_consistency = compute_view_consistency(view_counts)
        engagement_depth = compute_engagement_depth(videos)
        upload_cadence = compute_upload_cadence(published_dates)

        # Sponsorship detection across recent videos.
        sponsorship_hits = []
        videos_with_paid_placement = 0
        videos_checked_for_placement = 0
        for v in videos:
            desc_signals = detect_sponsorship_signals(v.get("description", ""))
            if any([
                desc_signals["has_promo_code"],
                desc_signals["has_affiliate_link"],
                desc_signals["has_sponsorship_mention"],
            ]):
                sponsorship_hits.append({
                    "video_id": v.get("video_id"),
                    "title": v.get("title", "")[:80],
                    "signals": desc_signals,
                })

            # paidProductPlacement flag (YouTube self-declaration).
            pp = v.get("paid_product_placement")
            if pp is not None:
                videos_checked_for_placement += 1
                if pp:
                    videos_with_paid_placement += 1

        sponsorship_summary = {
            "videos_with_description_signals": len(sponsorship_hits),
            "total_videos_checked": len(videos),
            "videos_with_paid_placement_flag": videos_with_paid_placement,
            "videos_checked_for_placement": videos_checked_for_placement,
            "hits": sponsorship_hits[:5],  # Keep top 5 for audit; don't bloat JSON.
        }

        # Creator reply rate (quota-heavy; may return None).
        # When fetch_comments is True, also capture comment text/author
        # for downstream trust + sponsorship analysis at zero extra quota
        # cost — the commentThreads API response already contains them.
        reply_rate_data = None
        captured_comment_data: Optional[Dict[str, Any]] = None
        if fetch_comments and video_ids:
            # Check Redis cache for previously captured comments first.
            cached_comments = get_cached_comments(channel_id)
            try:
                reply_rate_data = await fetch_creator_reply_rate(
                    channel_id, video_ids,
                    max_videos=5,
                    max_comments_per_video=20,
                    capture_comments=True,
                )
                # Extract and cache comment samples if freshly fetched.
                if reply_rate_data and reply_rate_data.get("comment_samples"):
                    captured_comment_data = {
                        "comment_samples": reply_rate_data.pop("comment_samples"),
                        "per_video_comments": reply_rate_data.pop("per_video_comments", {}),
                    }
                    cache_comments(channel_id, captured_comment_data)
                elif reply_rate_data:
                    # Reply rate succeeded but no comments captured (e.g.
                    # all threads had empty text). Remove the keys so they
                    # don't pollute the persisted reply_rate_data.
                    reply_rate_data.pop("comment_samples", None)
                    reply_rate_data.pop("per_video_comments", None)
                    # Fall back to cached comments if available.
                    captured_comment_data = cached_comments
                else:
                    # reply_rate_data is None (no threads at all).
                    captured_comment_data = cached_comments
            except Exception as e:
                logger.debug("Reply rate fetch failed for %s: %s", channel_id, e)
                # Fall back to cached comments if available.
                captured_comment_data = cached_comments

        # --- Assemble the enrichment blob --------------------------------
        signals = {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "channel_id": channel_id,

            # Core stats
            "subscriber_count": subscriber_count,
            "view_count": view_count,
            "video_count": video_count,

            # View consistency (loyalty proxy)
            "view_consistency": view_consistency,

            # Engagement depth
            "engagement_depth": engagement_depth,

            # Upload cadence / recency
            "upload_cadence": upload_cadence,

            # Creator reply rate (None if unavailable)
            "creator_reply_rate": reply_rate_data,

            # Sponsorship detection
            "sponsorship_detection": sponsorship_summary,

            # Source metadata for audit
            "source": "YouTube Data API v3",
            "videos_sampled": len(videos),
        }

        # Attach captured comment data as a transient key (prefixed with
        # underscore). The enrichment pipeline pops this before persisting
        # the signals to the Influencer model so it doesn't bloat the
        # stored JSON. If no comments were captured, the key is omitted.
        if captured_comment_data:
            signals["_comment_data"] = captured_comment_data

        return signals
