"""
Enrichment admin endpoints (Phase 6).

Provides two endpoints:
  1. POST /trigger — enqueue a batch enrichment job (returns immediately
     with a job handle; the work runs in a FastAPI BackgroundTask).
  2. GET /status — read the current enrichment run state across the roster.

Both are auth-guarded via get_current_user.

Background execution strategy:
  We use FastAPI BackgroundTasks — the lightest option for this repo.
  Justification: the repo already uses BackgroundTasks in brands.py, Redis
  is present but has no task broker setup (no arq/RQ/Celery), and the
  enrichment batch is a single-process sequential job (YouTube quota caps
  concurrency anyway). Introducing a heavy broker for a 121-creator roster
  would be over-engineering. BackgroundTasks spawn after the response is sent,
  so no HTTP handler blocks on the full batch.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db, SessionLocal
from models import Influencer, User
from schemas import (
    EnrichmentTriggerResponse,
    EnrichmentStatusResponse,
    EnrichmentCreatorStatus,
)
from utils.security import get_current_user
from utils.enrichment_pipeline import enrich_batch, DEFAULT_STALE_DAYS

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job tracker. For a 121-creator single-instance app this is
# sufficient. A production multi-process deployment would use Redis or a DB
# table, but that is out of scope for Phase 6.
_jobs: Dict[str, Dict[str, Any]] = {}


def _run_enrichment_job(
    job_id: str,
    *,
    stale_days: int,
    only_stale: bool,
    limit: Optional[int],
    force: bool,
) -> None:
    """Synchronous wrapper that runs the async enrichment batch.

    Called by FastAPI BackgroundTasks (which runs in a thread). Opens its own
    DB session (BackgroundTasks run after the response is sent, so the
    request-scoped session is gone).
    """
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    db = SessionLocal()
    try:
        result = asyncio.run(
            enrich_batch(
                db,
                stale_days=stale_days,
                only_stale=only_stale,
                limit=limit,
                force=force,
            )
        )
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        _jobs[job_id]["result"] = {
            "total": result.total,
            "completed": result.completed,
            "partial": result.partial,
            "failed": result.failed,
            "skipped": result.skipped,
        }
    except Exception as e:
        logger.exception("Enrichment job %s failed", job_id)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = f"{type(e).__name__}: {e}"
    finally:
        db.close()


@router.post("/trigger", response_model=EnrichmentTriggerResponse)
async def trigger_enrichment(
    background_tasks: BackgroundTasks,
    stale_days: int = Query(
        default=DEFAULT_STALE_DAYS, ge=0,
        description="Re-enrich creators whose last enrichment is older than this many days.",
    ),
    only_stale: bool = Query(
        default=True,
        description="If true, only process stale/never-enriched creators.",
    ),
    limit: Optional[int] = Query(
        default=None, ge=1,
        description="Max creators to process (null = all matching).",
    ),
    force: bool = Query(
        default=False,
        description="If true, ignore staleness and re-enrich everything.",
    ),
    current_user: User = Depends(get_current_user),
):
    """Trigger a batch enrichment job.

    Returns immediately with a job_id. The enrichment runs in the background
    (never blocks this HTTP handler). Query GET /status or GET /job/{job_id}
    for progress.
    """
    job_id = str(uuid.uuid4())

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "triggered_by": current_user.username,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "stale_days": stale_days,
            "only_stale": only_stale,
            "limit": limit,
            "force": force,
        },
    }

    background_tasks.add_task(
        _run_enrichment_job,
        job_id,
        stale_days=stale_days,
        only_stale=only_stale,
        limit=limit,
        force=force,
    )

    logger.info(
        "Enrichment job %s triggered by %s (stale_days=%d, only_stale=%s, limit=%s, force=%s)",
        job_id, current_user.username, stale_days, only_stale, limit, force,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Enrichment job enqueued. Query GET /status for progress.",
    }


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get status of a specific enrichment job."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found", "job_id": job_id}
    return job


@router.get("/status", response_model=EnrichmentStatusResponse)
async def enrichment_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get an overview of enrichment state across the roster.

    Returns counts of creators by enrichment_status and a list of
    per-creator statuses.
    """
    # Aggregate counts by status
    status_counts = (
        db.query(
            Influencer.enrichment_status,
            func.count(Influencer.id),
        )
        .filter(
            Influencer.platform == "youtube",
            ~Influencer.platform_id.like("unresolved:%"),
        )
        .group_by(Influencer.enrichment_status)
        .all()
    )

    counts = {status: count for status, count in status_counts}

    total_resolved = sum(counts.values())
    never_enriched = counts.get(None, 0)
    completed = counts.get("completed", 0)
    partial = counts.get("partial", 0)
    failed = counts.get("failed", 0)
    running = counts.get("running", 0)

    # Per-creator status (lightweight: no big JSON blobs)
    creators = (
        db.query(
            Influencer.id,
            Influencer.source_handle,
            Influencer.username,
            Influencer.enrichment_status,
            Influencer.last_enriched_at,
            Influencer.enrichment_error,
        )
        .filter(
            Influencer.platform == "youtube",
            ~Influencer.platform_id.like("unresolved:%"),
        )
        .order_by(Influencer.last_enriched_at.asc().nulls_first())
        .limit(200)
        .all()
    )

    creator_statuses = [
        {
            "influencer_id": c.id,
            "handle": c.source_handle or c.username,
            "enrichment_status": c.enrichment_status,
            "last_enriched_at": c.last_enriched_at.isoformat() if c.last_enriched_at else None,
            "enrichment_error": c.enrichment_error,
        }
        for c in creators
    ]

    # Latest job info
    latest_job = None
    if _jobs:
        latest_job = max(_jobs.values(), key=lambda j: j.get("triggered_at", ""))

    return {
        "total_resolved": total_resolved,
        "never_enriched": never_enriched,
        "completed": completed,
        "partial": partial,
        "failed": failed,
        "running": running,
        "creators": creator_statuses,
        "latest_job": latest_job,
    }
