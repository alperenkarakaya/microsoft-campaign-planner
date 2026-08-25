"""
Enrichment orchestration pipeline (Phase 6).

Connects the pieces built in Phases 1-3 into a single pipeline that, for each
creator in the roster:

  1. Pulls YouTube data (reuses discovery/comment helpers + Redis cache).
  2. Runs Phase 1 signals -> persists to Influencer.enrichment_signals.
  3. Runs Phase 2 trust_scorer -> persists trust_breakdown.
  4. Runs Phase 3 sponsorship_analyzer -> persists sponsorship_profile.

Trust and sponsorship are INTRINSIC (brand-agnostic). They are stored on a
brand-agnostic InfluencerAnalysis row (brand_profile_id = NULL). This matches
the existing model convention: InfluencerAnalysis already has nullable
brand_profile_id, and roster.py's read path already queries for the most
recent analysis row with trust/sponsorship data regardless of brand_profile_id.
No schema change needed for this.

Design choices:
  - brand_profile_id NULL for intrinsic analysis: avoids a new table; the
    existing InfluencerAnalysis model and roster.py read path already support
    this (roster.py searches for rows that have trust_breakdown or
    sponsorship_profile populated, ordered by analyzed_at desc).
  - Each sub-step is independently failure-isolated: one creator failing does
    not abort the batch; a failed sub-step yields None / lower confidence and
    records the error, never fabricates.
  - "stale-only" selection: only (re)enriches creators whose last_enriched_at
    is NULL or older than the configured staleness threshold.

Quota consciousness:
  - Reuses Redis-cached video data from youtube_cache.
  - Comments are sampled (max 5 videos x 20 threads) per signals.py.
  - Comment text is captured from the same commentThreads API call that
    signals.py already makes for reply-rate — zero additional quota cost.
  - Captured comments are cached in Redis (youtube_cache.cache_comments)
    and reused across re-enrichment runs.
  - Does NOT re-fetch if cache is warm.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import Influencer, InfluencerAnalysis
from utils.signals import compute_signals_for_channel
from utils.trust_scorer import compute_trust_score
from utils.sponsorship_analyzer import compute_sponsorship_profile
from utils.youtube_cache import get_cached_videos, get_cached_comments

logger = logging.getLogger(__name__)

# Default staleness: re-enrich if last_enriched_at is older than this.
DEFAULT_STALE_DAYS = 7


@dataclass
class EnrichmentResult:
    """Result of enriching a single creator."""
    influencer_id: int
    handle: Optional[str]
    signals_ok: bool = False
    trust_ok: bool = False
    sponsorship_ok: bool = False
    error: Optional[str] = None
    status: str = "pending"  # "completed" | "partial" | "failed"


@dataclass
class BatchEnrichmentResult:
    """Summary of a batch enrichment run."""
    total: int = 0
    completed: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[EnrichmentResult] = field(default_factory=list)


async def enrich_single_creator(
    db: Session,
    influencer: Influencer,
    *,
    force: bool = False,
) -> EnrichmentResult:
    """Run the full enrichment pipeline for a single creator.

    Steps:
      1. Phase 1 — compute_signals_for_channel -> Influencer.enrichment_signals
      2. Phase 2 — compute_trust_score -> InfluencerAnalysis.trust_breakdown
      3. Phase 3 — compute_sponsorship_profile -> InfluencerAnalysis.sponsorship_profile

    Each step is independently failure-isolated. A failed sub-step produces
    None / lower confidence, never fabricated data.

    Args:
        db: SQLAlchemy session (caller manages commit/rollback).
        influencer: Influencer ORM object with a resolved platform_id.
        force: If True, re-enrich even if not stale.

    Returns:
        EnrichmentResult with per-step status.
    """
    result = EnrichmentResult(
        influencer_id=influencer.id,
        handle=influencer.source_handle or influencer.username,
    )

    channel_id = influencer.platform_id
    if not channel_id or channel_id.startswith("unresolved:"):
        result.status = "failed"
        result.error = "unresolved channel ID"
        influencer.enrichment_status = "failed"
        influencer.enrichment_error = "unresolved channel ID"
        return result

    # Mark as running
    influencer.enrichment_status = "running"
    influencer.enrichment_error = None

    errors: List[str] = []

    # --- Step 1: Phase 1 signals ---
    try:
        signals = await compute_signals_for_channel(
            channel_id,
            max_recent_videos=10,
            fetch_comments=True,
        )
        if signals is not None:
            influencer.enrichment_signals = signals
            if signals.get("subscriber_count"):
                influencer.followers_count = signals["subscriber_count"]
            result.signals_ok = True
            logger.debug("Signals OK for %s", result.handle)
        else:
            errors.append("signals: returned None (API unavailable or channel not found)")
            logger.warning("No signals for %s (%s)", result.handle, channel_id)
    except Exception as e:
        errors.append(f"signals: {type(e).__name__}: {e}")
        logger.warning("Signal computation failed for %s: %s", result.handle, e)

    # --- Prepare data for Phases 2 & 3 ---
    # Use the freshly-computed signals if available, otherwise fall back to
    # whatever was already stored on the influencer.
    current_signals = influencer.enrichment_signals

    # Pop transient comment data from signals before it gets persisted.
    # signals.py attaches _comment_data (captured from commentThreads at
    # zero extra quota cost) so we can feed trust_scorer + sponsorship_analyzer.
    comment_data: Optional[Dict] = None
    if current_signals:
        comment_data = current_signals.pop("_comment_data", None)

    # If no comment data came from the fresh signals run, try the Redis
    # cache (comments may have been cached by a prior enrichment run).
    if comment_data is None and current_signals and current_signals.get("channel_id"):
        comment_data = get_cached_comments(current_signals["channel_id"])

    # Extract flat comment list for trust_scorer (expects List[Dict] with
    # 'author' and 'text' keys).
    comments: Optional[List[Dict]] = None
    if comment_data and comment_data.get("comment_samples"):
        comments = comment_data["comment_samples"]

    # Get cached videos for sponsorship analyzer (it needs the video list).
    videos: List[Dict] = []
    if current_signals and current_signals.get("channel_id"):
        cached = get_cached_videos(current_signals["channel_id"])
        if cached is not None:
            videos = cached

    # Split comments by sponsored vs organic video for sponsorship_analyzer.
    sponsored_comments: Optional[List[Dict]] = None
    organic_comments: Optional[List[Dict]] = None
    if comment_data and comment_data.get("per_video_comments") and current_signals:
        per_video = comment_data["per_video_comments"]
        spons_detection = current_signals.get("sponsorship_detection") or {}
        hits = spons_detection.get("hits", [])
        sponsored_video_ids = {h.get("video_id") for h in hits}
        # Also include videos with paidProductPlacement flag.
        for v in videos:
            if v.get("paid_product_placement") is True:
                sponsored_video_ids.add(v.get("video_id"))

        sp_comments: List[Dict] = []
        org_comments: List[Dict] = []
        for vid_id, vid_comments in per_video.items():
            if vid_id in sponsored_video_ids:
                sp_comments.extend(vid_comments)
            else:
                org_comments.extend(vid_comments)

        sponsored_comments = sp_comments if sp_comments else None
        organic_comments = org_comments if org_comments else None

    # --- Step 2: Phase 2 trust score ---
    trust_breakdown = None
    try:
        if current_signals:
            trust_breakdown = await compute_trust_score(
                current_signals,
                comments=comments,
            )
            result.trust_ok = True
            logger.debug("Trust OK for %s", result.handle)
        else:
            errors.append("trust: skipped — no enrichment signals available")
    except Exception as e:
        errors.append(f"trust: {type(e).__name__}: {e}")
        logger.warning("Trust computation failed for %s: %s", result.handle, e)

    # --- Step 3: Phase 3 sponsorship profile ---
    sponsorship_profile = None
    try:
        if current_signals:
            sponsorship_profile = await compute_sponsorship_profile(
                current_signals,
                videos,
                sponsored_comments=sponsored_comments,
                organic_comments=organic_comments,
            )
            result.sponsorship_ok = True
            logger.debug("Sponsorship OK for %s", result.handle)
        else:
            errors.append("sponsorship: skipped — no enrichment signals available")
    except Exception as e:
        errors.append(f"sponsorship: {type(e).__name__}: {e}")
        logger.warning("Sponsorship computation failed for %s: %s", result.handle, e)

    # --- Persist trust + sponsorship to a brand-agnostic InfluencerAnalysis row ---
    if trust_breakdown is not None or sponsorship_profile is not None:
        _persist_intrinsic_analysis(
            db, influencer, trust_breakdown, sponsorship_profile,
        )

    # --- Update run-state tracking ---
    now = datetime.now(timezone.utc)

    if result.signals_ok and result.trust_ok and result.sponsorship_ok:
        result.status = "completed"
        influencer.enrichment_status = "completed"
        influencer.enrichment_error = None
        influencer.last_enriched_at = now
    elif result.signals_ok or result.trust_ok or result.sponsorship_ok:
        result.status = "partial"
        influencer.enrichment_status = "partial"
        influencer.enrichment_error = "; ".join(errors) if errors else None
        influencer.last_enriched_at = now  # Still mark as enriched (partially)
    else:
        result.status = "failed"
        influencer.enrichment_status = "failed"
        influencer.enrichment_error = "; ".join(errors) if errors else "all steps failed"

    result.error = "; ".join(errors) if errors else None

    return result


def _persist_intrinsic_analysis(
    db: Session,
    influencer: Influencer,
    trust_breakdown: Optional[Dict[str, Any]],
    sponsorship_profile: Optional[Dict[str, Any]],
) -> None:
    """Create or update a brand-agnostic InfluencerAnalysis row.

    Uses brand_profile_id = NULL to indicate intrinsic (not brand-specific)
    analysis. If an existing brand-agnostic row exists, updates it in place
    rather than creating duplicates.

    The roster.py read path already queries for the most recent analysis row
    with trust/sponsorship data, ordered by analyzed_at desc, so this is
    consistent with the existing consumer.
    """
    # Look for an existing brand-agnostic analysis row for this influencer.
    existing = (
        db.query(InfluencerAnalysis)
        .filter(
            InfluencerAnalysis.influencer_id == influencer.id,
            InfluencerAnalysis.brand_profile_id.is_(None),
        )
        .order_by(InfluencerAnalysis.analyzed_at.desc())
        .first()
    )

    if existing:
        # Update existing row.
        if trust_breakdown is not None:
            existing.trust_breakdown = trust_breakdown
        if sponsorship_profile is not None:
            existing.sponsorship_profile = sponsorship_profile
        existing.analyzed_at = datetime.now(timezone.utc)
    else:
        # Create a new brand-agnostic row.
        # Required fields that aren't relevant for intrinsic analysis get
        # sensible defaults (the model requires them).
        analysis = InfluencerAnalysis(
            influencer_id=influencer.id,
            brand_profile_id=None,
            trust_breakdown=trust_breakdown,
            sponsorship_profile=sponsorship_profile,
            # Fill required non-nullable fields with neutral defaults.
            # These are brand-fit scores and are irrelevant for intrinsic
            # analysis, but the ORM model defines them.
            content_style_match_score=0.0,
            audience_match_score=0.0,
            engagement_quality_score=0.0,
            brand_safety_score=0.0,
            overall_match_score=0.0,
            ai_analysis_summary="Intrinsic enrichment (brand-agnostic)",
            content_tone="n/a",
            analyzed_at=datetime.now(timezone.utc),
        )
        db.add(analysis)


def _select_stale_influencers(
    db: Session,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    only_stale: bool = True,
    limit: Optional[int] = None,
) -> List[Influencer]:
    """Select influencers that need (re)enrichment.

    "Stale" = last_enriched_at is NULL or older than stale_days ago.
    Only includes resolved creators (platform_id not starting with "unresolved:").

    Args:
        db: SQLAlchemy session.
        stale_days: How many days before an enrichment is considered stale.
        only_stale: If True, skip recently-enriched creators.
        limit: Max creators to return (None = all).

    Returns:
        List of Influencer objects.
    """
    query = (
        db.query(Influencer)
        .filter(
            Influencer.platform == "youtube",
            ~Influencer.platform_id.like("unresolved:%"),
        )
    )

    if only_stale:
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        query = query.filter(
            (Influencer.last_enriched_at.is_(None))
            | (Influencer.last_enriched_at < cutoff)
        )

    query = query.order_by(
        # Never-enriched first, then oldest first.
        Influencer.last_enriched_at.asc().nulls_first(),
    )

    if limit is not None:
        query = query.limit(limit)

    return query.all()


async def enrich_batch(
    db: Session,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    only_stale: bool = True,
    limit: Optional[int] = None,
    force: bool = False,
) -> BatchEnrichmentResult:
    """Run the enrichment pipeline over a batch of creators.

    Selects stale/never-enriched creators and enriches them sequentially
    (one at a time to respect YouTube API quota). Each creator is independently
    failure-isolated: one failing does not abort the batch.

    Args:
        db: SQLAlchemy session.
        stale_days: Days before enrichment is considered stale.
        only_stale: If True (default), only enrich stale/never-enriched.
        limit: Max creators to process (None = all matching).
        force: If True, ignore staleness and re-enrich all.

    Returns:
        BatchEnrichmentResult with per-creator outcomes.
    """
    if force:
        only_stale = False

    influencers = _select_stale_influencers(
        db,
        stale_days=stale_days,
        only_stale=only_stale,
        limit=limit,
    )

    batch_result = BatchEnrichmentResult(total=len(influencers))

    if not influencers:
        logger.info("No creators to enrich (all fresh or none resolved).")
        return batch_result

    logger.info("Starting enrichment batch: %d creators", len(influencers))

    for influencer in influencers:
        try:
            result = await enrich_single_creator(
                db, influencer, force=force,
            )
            batch_result.results.append(result)

            if result.status == "completed":
                batch_result.completed += 1
            elif result.status == "partial":
                batch_result.partial += 1
            else:
                batch_result.failed += 1

            # Commit after each creator so partial progress is saved even if
            # the batch is interrupted. Matches ingest_roster.py pattern.
            db.commit()

        except Exception as e:
            # Catch-all: one creator must never abort the batch.
            db.rollback()
            logger.exception("Unexpected error enriching %s", influencer.source_handle)
            batch_result.failed += 1
            batch_result.results.append(EnrichmentResult(
                influencer_id=influencer.id,
                handle=influencer.source_handle or influencer.username,
                status="failed",
                error=f"unexpected: {type(e).__name__}: {e}",
            ))

    logger.info(
        "Enrichment batch complete: %d/%d completed, %d partial, %d failed",
        batch_result.completed, batch_result.total,
        batch_result.partial, batch_result.failed,
    )

    return batch_result
