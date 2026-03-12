from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """Abstract base class for all job board scrapers."""

    source_name: str = ""

    @abstractmethod
    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """
        Fetch jobs from the source.

        Returns a list of normalized job dicts with keys:
            external_id, title, company, location, salary_min, salary_max,
            currency, description, url, posted_at, tags
        """
        ...

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Apply defaults to a raw job dict."""
        return {
            "source": self.source_name,
            "external_id": raw.get("external_id", ""),
            "title": raw.get("title", ""),
            "company": raw.get("company", ""),
            "location": raw.get("location", "Remote"),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency"),
            "description": raw.get("description", ""),
            "url": raw.get("url", ""),
            "posted_at": raw.get("posted_at"),
            "tags": raw.get("tags", "[]"),
        }
