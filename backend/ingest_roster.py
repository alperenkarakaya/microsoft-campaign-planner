"""
CLI entry point for roster ingestion (Phase 0), signal enrichment (Phase 1),
and full-pipeline enrichment (Phase 6).

Usage (from the backend/ directory, with the venv active):

  # Step 1 — Import the spreadsheet into the DB (offline, no API needed):
  python ingest_roster.py import path/to/roster.xlsx

  # Step 2 — Resolve @handles to YouTube channel IDs (requires YOUTUBE_API_KEY):
  python ingest_roster.py resolve

  # Step 3 — Compute deterministic signals for all resolved creators (Phase 1):
  python ingest_roster.py enrich

  # Step 4 — Full pipeline: signals + trust + sponsorship for all stale creators:
  python ingest_roster.py pipeline [--force] [--limit N] [--stale-days N]

  # All steps in sequence (import → resolve → full pipeline):
  python ingest_roster.py all path/to/roster.xlsx

Environment variables:
  DATABASE_URL         — PostgreSQL connection string
  YOUTUBE_API_KEY      — YouTube Data API v3 key (needed for resolve + enrich)
  GEMINI_API_KEY       — Gemini API key (needed for trust + sponsorship LLM layers)
  REDIS_URL            — Redis URL for YouTube cache (optional; degrades gracefully)
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Ensure backend/ root is on sys.path for model imports.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal  # noqa: E402
from models import Influencer  # noqa: E402
from utils.roster_importer import parse_roster_xlsx, upsert_roster, resolve_handles  # noqa: E402
from utils.signals import compute_signals_for_channel  # noqa: E402
from utils.enrichment_pipeline import enrich_batch, DEFAULT_STALE_DAYS  # noqa: E402


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_roster")


def cmd_import(xlsx_path: str) -> None:
    """Parse and upsert the roster spreadsheet."""
    if not os.path.isfile(xlsx_path):
        logger.error("File not found: %s", xlsx_path)
        sys.exit(1)

    rows = parse_roster_xlsx(xlsx_path)
    logger.info("Parsed %d rows from %s", len(rows), xlsx_path)

    db = SessionLocal()
    try:
        result = upsert_roster(db, rows)
        logger.info(
            "Import complete: %d created, %d updated, %d skipped",
            result.created, result.updated, result.skipped,
        )
        if result.errors:
            logger.warning("Errors: %s", result.errors)
    finally:
        db.close()


async def cmd_resolve() -> None:
    """Resolve unresolved handles to YouTube channel IDs."""
    db = SessionLocal()
    try:
        result = await resolve_handles(db)
        logger.info(
            "Resolve complete: %d resolved, %d failed",
            result["resolved"], result["failed"],
        )
        if result["failures"]:
            for f in result["failures"]:
                logger.warning("  UNRESOLVED: %s", f)
    finally:
        db.close()


async def cmd_enrich() -> None:
    """Compute deterministic signals for all resolved influencers."""
    db = SessionLocal()
    try:
        influencers = (
            db.query(Influencer)
            .filter(
                Influencer.platform == "youtube",
                ~Influencer.platform_id.like("unresolved:%"),
            )
            .all()
        )

        if not influencers:
            logger.info("No resolved influencers to enrich.")
            return

        logger.info("Enriching %d influencers...", len(influencers))
        enriched = 0
        failed = 0

        for inf in influencers:
            try:
                signals = await compute_signals_for_channel(inf.platform_id)
                if signals is not None:
                    inf.enrichment_signals = signals
                    # Also update basic stats from signals if available.
                    if signals.get("subscriber_count"):
                        inf.followers_count = signals["subscriber_count"]
                    enriched += 1
                    logger.debug("Enriched %s (%s)", inf.source_handle, inf.platform_id)
                else:
                    failed += 1
                    logger.warning("No signals for %s (%s)", inf.source_handle, inf.platform_id)
            except Exception as e:
                failed += 1
                logger.warning("Error enriching %s: %s", inf.source_handle, e)

        db.commit()
        logger.info("Enrichment complete: %d enriched, %d failed", enriched, failed)

    finally:
        db.close()


async def cmd_pipeline(
    *,
    force: bool = False,
    limit: int | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> None:
    """Full enrichment pipeline: signals + trust + sponsorship for stale creators."""
    db = SessionLocal()
    try:
        result = await enrich_batch(
            db,
            stale_days=stale_days,
            only_stale=not force,
            limit=limit,
            force=force,
        )
        logger.info(
            "Pipeline complete: %d total, %d completed, %d partial, %d failed, %d skipped",
            result.total,
            result.completed,
            result.partial,
            result.failed,
            result.skipped,
        )
        for r in result.results:
            status_icon = (
                "OK" if r.status == "completed"
                else "PARTIAL" if r.status == "partial"
                else "FAIL"
            )
            error_info = f" ({r.error})" if r.error else ""
            logger.info(
                "  [%s] %s — signals=%s trust=%s sponsorship=%s%s",
                status_icon, r.handle,
                r.signals_ok, r.trust_ok, r.sponsorship_ok,
                error_info,
            )
    finally:
        db.close()


def _parse_pipeline_args(args: list) -> dict:
    """Parse --force, --limit N, --stale-days N from argv."""
    kwargs = {"force": False, "limit": None, "stale_days": DEFAULT_STALE_DAYS}
    i = 0
    while i < len(args):
        if args[i] == "--force":
            kwargs["force"] = True
        elif args[i] == "--limit" and i + 1 < len(args):
            kwargs["limit"] = int(args[i + 1])
            i += 1
        elif args[i] == "--stale-days" and i + 1 < len(args):
            kwargs["stale_days"] = int(args[i + 1])
            i += 1
        i += 1
    return kwargs


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "import":
        if len(sys.argv) < 3:
            logger.error("Usage: python ingest_roster.py import <path-to-xlsx>")
            sys.exit(1)
        cmd_import(sys.argv[2])

    elif command == "resolve":
        asyncio.run(cmd_resolve())

    elif command == "enrich":
        asyncio.run(cmd_enrich())

    elif command == "pipeline":
        kwargs = _parse_pipeline_args(sys.argv[2:])
        asyncio.run(cmd_pipeline(**kwargs))

    elif command == "all":
        if len(sys.argv) < 3:
            logger.error("Usage: python ingest_roster.py all <path-to-xlsx>")
            sys.exit(1)
        cmd_import(sys.argv[2])
        asyncio.run(cmd_resolve())
        # Use full pipeline instead of Phase-1-only enrich.
        asyncio.run(cmd_pipeline(force=True))

    else:
        logger.error(
            "Unknown command: %s. Use import, resolve, enrich, pipeline, or all.",
            command,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
