import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.scrapers.base import BaseScraper
from src.config import settings

logger = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"

# Tags to filter for (any match = include)
TARGET_TAGS = {
    "python", "machine-learning", "ai", "llm", "nlp", "deep-learning",
    "data-science", "ml", "gen-ai", "generative-ai", "langchain", "rag",
    "backend", "senior", "engineer",
}


def _parse_salary(job: dict) -> tuple[int | None, int | None, str | None]:
    """Extract salary range from RemoteOK job dict."""
    salary_min = job.get("salary_min") or job.get("salary_min_usd")
    salary_max = job.get("salary_max") or job.get("salary_max_usd")
    try:
        salary_min = int(salary_min) if salary_min else None
        salary_max = int(salary_max) if salary_max else None
    except (ValueError, TypeError):
        salary_min = salary_max = None
    currency = "USD" if (salary_min or salary_max) else None
    return salary_min, salary_max, currency


def _parse_posted_at(epoch: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


class RemoteOKScraper(BaseScraper):
    source_name = "remoteok"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
                response = await client.get(REMOTEOK_API, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("RemoteOK fetch failed: %s", e)
            return []

        try:
            data = response.json()
        except Exception as e:
            logger.error("RemoteOK JSON parse failed: %s", e)
            return []

        # First element is metadata, skip it
        jobs_raw = [item for item in data if isinstance(item, dict) and "id" in item]

        results = []
        for job in jobs_raw:
            tags_raw: list[str] = job.get("tags") or []
            tags_lower = {t.lower() for t in tags_raw}

            # Filter: must have at least one target tag
            if not tags_lower.intersection(TARGET_TAGS):
                continue

            salary_min, salary_max, currency = _parse_salary(job)
            posted_at = _parse_posted_at(job.get("epoch"))

            matched_tags = sorted(tags_lower.intersection(TARGET_TAGS))
            raw = {
                "external_id": str(job.get("id", "")),
                "title": job.get("position", ""),
                "company": job.get("company", ""),
                "location": "Remote",
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": currency,
                "description": job.get("description", ""),
                "url": job.get("url", f"https://remoteok.com/remote-jobs/{job.get('slug', '')}"),
                "posted_at": posted_at,
                "tags": json.dumps(matched_tags),
            }
            results.append(self.normalize(raw))

        logger.info("RemoteOK: fetched %d matching jobs", len(results))
        return results
