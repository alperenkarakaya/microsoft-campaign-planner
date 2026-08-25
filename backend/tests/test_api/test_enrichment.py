"""Tests for the enrichment admin endpoints (Phase 6).

Covers:
  - POST /trigger: auth required, returns job_id immediately
  - GET /status: auth required, returns enrichment state overview
  - GET /job/{job_id}: returns job status
  - Background job is enqueued (mocked), never blocks the HTTP handler.

All tests are fully OFFLINE — no YouTube/Gemini calls.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from models import Influencer
from database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_influencer(
    db,
    *,
    username="creator1",
    platform_id="UC_test_1",
    source_handle="creator1",
    last_enriched_at=None,
    enrichment_status=None,
    enrichment_error=None,
):
    inf = Influencer(
        platform="youtube",
        platform_id=platform_id,
        username=username,
        display_name=f"Display {username}",
        source_handle=source_handle,
        followers_count=10_000,
        engagement_rate=5.0,
        category="gaming",
        country="US",
        last_enriched_at=last_enriched_at,
        enrichment_status=enrichment_status,
        enrichment_error=enrichment_error,
    )
    db.add(inf)
    db.flush()
    db.refresh(inf)
    return inf


# ---------------------------------------------------------------------------
# Tests: POST /trigger
# ---------------------------------------------------------------------------

class TestEnrichmentTrigger:

    def test_requires_auth(self, client):
        r = client.post("/api/v1/enrichment/trigger")
        assert r.status_code == 401

    def test_returns_job_id_immediately(self, auth_client):
        """Trigger should return immediately with a job_id, not block."""
        # Mock BackgroundTasks.add_task to prevent the actual job from running
        with patch(
            "routers.enrichment._run_enrichment_job"
        ) as mock_run:
            r = auth_client.post("/api/v1/enrichment/trigger")

        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert "message" in body

    def test_accepts_parameters(self, auth_client):
        """Trigger should accept stale_days, only_stale, limit, force params."""
        with patch("routers.enrichment._run_enrichment_job"):
            r = auth_client.post(
                "/api/v1/enrichment/trigger",
                params={
                    "stale_days": 3,
                    "only_stale": False,
                    "limit": 10,
                    "force": True,
                },
            )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"


# ---------------------------------------------------------------------------
# Tests: GET /status
# ---------------------------------------------------------------------------

class TestEnrichmentStatus:

    def test_requires_auth(self, client):
        r = client.get("/api/v1/enrichment/status")
        assert r.status_code == 401

    def test_empty_roster(self, auth_client):
        r = auth_client.get("/api/v1/enrichment/status")
        assert r.status_code == 200
        body = r.json()
        assert body["total_resolved"] == 0
        assert body["never_enriched"] == 0
        assert body["creators"] == []

    def test_shows_creator_statuses(self, auth_client):
        db = next(get_db())
        try:
            _seed_influencer(
                db,
                username="enriched_creator",
                platform_id="UC_enriched",
                source_handle="enriched",
                last_enriched_at=datetime.now(timezone.utc),
                enrichment_status="completed",
            )
            _seed_influencer(
                db,
                username="stale_creator",
                platform_id="UC_stale",
                source_handle="stale",
                last_enriched_at=None,
                enrichment_status=None,
            )
            _seed_influencer(
                db,
                username="failed_creator",
                platform_id="UC_failed",
                source_handle="failed",
                enrichment_status="failed",
                enrichment_error="signals: API unavailable",
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/enrichment/status")
        assert r.status_code == 200
        body = r.json()
        assert body["total_resolved"] == 3
        assert body["completed"] == 1
        assert body["never_enriched"] == 1
        assert body["failed"] == 1
        assert len(body["creators"]) == 3

    def test_excludes_unresolved_from_counts(self, auth_client):
        db = next(get_db())
        try:
            _seed_influencer(
                db,
                username="resolved",
                platform_id="UC_resolved",
                source_handle="resolved",
            )
            _seed_influencer(
                db,
                username="unresolved",
                platform_id="unresolved:handle",
                source_handle="unresolved",
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/enrichment/status")
        body = r.json()
        # Only the resolved creator should be counted
        assert body["total_resolved"] == 1


# ---------------------------------------------------------------------------
# Tests: GET /job/{job_id}
# ---------------------------------------------------------------------------

class TestEnrichmentJobStatus:

    def test_requires_auth(self, client):
        r = client.get("/api/v1/enrichment/job/nonexistent")
        assert r.status_code == 401

    def test_nonexistent_job(self, auth_client):
        r = auth_client.get("/api/v1/enrichment/job/nonexistent-uuid")
        assert r.status_code == 200
        body = r.json()
        assert "error" in body

    def test_job_shows_after_trigger(self, auth_client):
        """After triggering, the job should be queryable."""
        with patch("routers.enrichment._run_enrichment_job"):
            trigger_resp = auth_client.post("/api/v1/enrichment/trigger")

        job_id = trigger_resp.json()["job_id"]
        r = auth_client.get(f"/api/v1/enrichment/job/{job_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["job_id"] == job_id
        assert body["status"] in ("queued", "running", "completed", "failed")
