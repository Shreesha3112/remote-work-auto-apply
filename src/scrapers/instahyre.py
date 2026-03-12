import json
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.config import settings

logger = logging.getLogger(__name__)

INSTAHYRE_SEARCH_URL = "https://www.instahyre.com/candidate/opportunities/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.instahyre.com/",
}

SEARCH_PARAMS = [
    {"skills": "python,machine-learning", "location": "bangalore"},
    {"skills": "python,nlp", "location": "bangalore"},
    {"skills": "llm,generative-ai", "location": "remote"},
]


class InstaHyreScraper(BaseScraper):
    source_name = "instahyre"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        results = []

        async with httpx.AsyncClient(
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers=HEADERS,
        ) as client:
            for params in SEARCH_PARAMS:
                jobs = await self._fetch_with_params(client, params)
                results.extend(jobs)

        # Deduplicate
        seen: set[str] = set()
        unique = []
        for job in results:
            if job["external_id"] not in seen:
                seen.add(job["external_id"])
                unique.append(job)

        logger.info("InstaHyre: fetched %d unique jobs", len(unique))
        return unique

    async def _fetch_with_params(
        self, client: httpx.AsyncClient, params: dict
    ) -> list[dict[str, Any]]:
        try:
            resp = await client.get(INSTAHYRE_SEARCH_URL, params=params)
            resp.raise_for_status()
            return self._parse_html(resp.text, params)
        except httpx.HTTPError as e:
            logger.warning("InstaHyre fetch failed for %s: %s", params, e)
            return []

    def _parse_html(self, html: str, params: dict) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try JSON-LD or embedded data
        script_tags = soup.find_all("script", type="application/ld+json")
        for script in script_tags:
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        job = self._parse_json_ld(item, params)
                        if job:
                            jobs.append(job)
                elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                    job = self._parse_json_ld(data, params)
                    if job:
                        jobs.append(job)
            except json.JSONDecodeError:
                continue

        if jobs:
            return jobs

        # Fallback: parse HTML cards
        cards = (
            soup.select(".opportunity-card")
            or soup.select(".job-card")
            or soup.select("[class*='opportunity']")
        )
        for card in cards:
            job = self._parse_card(card, params)
            if job:
                jobs.append(job)

        return jobs

    def _parse_json_ld(self, item: dict, params: dict) -> dict | None:
        if item.get("@type") != "JobPosting":
            return None
        try:
            url = item.get("url", "")
            job_id = re.search(r"/(\d+)", url)
            external_id = f"ih_{job_id.group(1)}" if job_id else f"ih_{hash(url)}"

            salary_obj = item.get("baseSalary", {})
            salary_value = salary_obj.get("value", {}) if isinstance(salary_obj, dict) else {}
            salary_min = salary_value.get("minValue") if isinstance(salary_value, dict) else None
            salary_max = salary_value.get("maxValue") if isinstance(salary_value, dict) else None
            currency = salary_obj.get("currency") if isinstance(salary_obj, dict) else None

            raw = {
                "external_id": external_id,
                "title": item.get("title", ""),
                "company": item.get("hiringOrganization", {}).get("name", ""),
                "location": item.get("jobLocation", {}).get("address", {}).get("addressLocality", "Bengaluru"),
                "salary_min": int(salary_min) if salary_min else None,
                "salary_max": int(salary_max) if salary_max else None,
                "currency": currency,
                "description": item.get("description", ""),
                "url": url,
                "tags": json.dumps(list(params.get("skills", "").split(","))),
            }
            return self.normalize(raw)
        except Exception as e:
            logger.debug("InstaHyre JSON-LD parse error: %s", e)
            return None

    def _parse_card(self, card: Any, params: dict) -> dict | None:
        try:
            title_el = card.select_one("h2, h3, .job-title, .opportunity-title")
            company_el = card.select_one(".company-name, .employer")
            link_el = card.select_one("a[href]")

            if not title_el or not link_el:
                return None

            href = link_el.get("href", "")
            url = href if href.startswith("http") else f"https://www.instahyre.com{href}"
            job_id = re.search(r"/(\d+)", href)
            external_id = f"ih_{job_id.group(1)}" if job_id else f"ih_{hash(url)}"

            raw = {
                "external_id": external_id,
                "title": title_el.get_text(strip=True),
                "company": company_el.get_text(strip=True) if company_el else "",
                "location": "Bengaluru",
                "url": url,
                "tags": json.dumps(list(params.get("skills", "").split(","))),
            }
            return self.normalize(raw)
        except Exception as e:
            logger.debug("InstaHyre card parse error: %s", e)
            return None
