import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db, get_session
from src.models import Job, UserProfile
from src.scrapers.remoteok import RemoteOKScraper
from src.scrapers.wellfound import WellfoundScraper
from src.scrapers.naukri import NaukriScraper
from src.scrapers.instahyre import InstaHyreScraper
from src.matcher.filters import passes_filter, extract_tags
from src.matcher.llm_scorer import score_jobs_batch
from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scrape", tags=["scrape"])

# Track ongoing scrape state
_scrape_state = {
    "running": False,
    "last_run": None,
    "last_result": None,
}

SCRAPERS = {
    "remoteok": RemoteOKScraper,
    "wellfound": WellfoundScraper,
    "naukri": NaukriScraper,
    "instahyre": InstaHyreScraper,
}


class ScrapeRequest(BaseModel):
    sources: list[str] = ["remoteok", "wellfound", "naukri", "instahyre"]
    score: bool = True


@router.post("")
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger a scraping + scoring run in the background."""
    if _scrape_state["running"]:
        raise HTTPException(status_code=409, detail="Scrape already running")

    # Validate sources
    invalid = set(request.sources) - set(SCRAPERS.keys())
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown sources: {invalid}")

    background_tasks.add_task(
        _run_scrape_pipeline,
        sources=request.sources,
        score=request.score,
    )
    return {"status": "started", "sources": request.sources}


@router.get("/status")
async def scrape_status():
    """Get current scrape status."""
    return {
        "running": _scrape_state["running"],
        "last_run": _scrape_state["last_run"],
        "last_result": _scrape_state["last_result"],
    }


async def _run_scrape_pipeline(sources: list[str], score: bool) -> None:
    """Full pipeline: fetch → filter → dedup → persist → score."""
    _scrape_state["running"] = True
    _scrape_state["last_result"] = None

    stats = {"fetched": 0, "filtered": 0, "new": 0, "scored": 0, "errors": []}

    try:
        # 1. Fetch jobs from all sources
        all_jobs_raw = []
        for source in sources:
            scraper_cls = SCRAPERS[source]
            scraper = scraper_cls()
            try:
                jobs = await scraper.fetch_jobs()
                all_jobs_raw.extend(jobs)
                logger.info("%s: fetched %d jobs", source, len(jobs))
            except Exception as e:
                logger.error("Scraper %s failed: %s", source, e)
                stats["errors"].append(f"{source}: {e}")

        stats["fetched"] = len(all_jobs_raw)

        # 2. Load profile for filtering
        with get_session() as session:
            profile = session.query(UserProfile).filter(UserProfile.id == 1).first()

        # 3. Filter + dedup + persist new jobs
        new_jobs: list[Job] = []
        with get_session() as session:
            for raw in all_jobs_raw:
                if profile and not passes_filter(raw, profile):
                    continue
                stats["filtered"] += 1

                # Dedup by (source, external_id)
                exists = (
                    session.query(Job)
                    .filter(
                        Job.source == raw["source"],
                        Job.external_id == raw["external_id"],
                    )
                    .first()
                )
                if exists:
                    continue

                tags = extract_tags(raw)
                job = Job(
                    source=raw["source"],
                    external_id=raw["external_id"],
                    title=raw["title"],
                    company=raw["company"],
                    location=raw["location"],
                    salary_min=raw.get("salary_min"),
                    salary_max=raw.get("salary_max"),
                    currency=raw.get("currency"),
                    description=raw.get("description", ""),
                    url=raw["url"],
                    posted_at=raw.get("posted_at"),
                    fetched_at=datetime.now(timezone.utc),
                    tags=json.dumps(tags),
                )
                session.add(job)
                session.flush()  # get the ID
                new_jobs.append(job)
                stats["new"] += 1

        logger.info("Pipeline: %d new jobs persisted", stats["new"])

        # 4. Score new jobs with LLM
        if score and new_jobs and profile:
            try:
                from src.llm.client import llm_client
                if await llm_client.is_available():
                    results = await score_jobs_batch(
                        new_jobs,
                        profile,
                        concurrency=settings.scrape_concurrency,
                    )
                    with get_session() as session:
                        for job, score_val, reasoning in results:
                            db_job = session.query(Job).filter(Job.id == job.id).first()
                            if db_job:
                                db_job.score = score_val
                                db_job.score_reasoning = reasoning
                    stats["scored"] = len(results)
                    logger.info("Scored %d jobs", stats["scored"])
                else:
                    logger.warning("vLLM not available, skipping scoring")
            except Exception as e:
                logger.error("Scoring batch failed: %s", e)
                stats["errors"].append(f"scoring: {e}")

    except Exception as e:
        logger.error("Scrape pipeline error: %s", e)
        stats["errors"].append(str(e))
    finally:
        _scrape_state["running"] = False
        _scrape_state["last_run"] = datetime.now(timezone.utc).isoformat()
        _scrape_state["last_result"] = stats
        logger.info("Scrape pipeline complete: %s", stats)
