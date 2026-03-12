import json
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.config import settings

logger = logging.getLogger(__name__)

WELLFOUND_SEARCH_URL = "https://wellfound.com/jobs"

TARGET_ROLES = ["machine-learning", "artificial-intelligence", "data-science", "nlp"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class WellfoundScraper(BaseScraper):
    source_name = "wellfound"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        results = []
        for role in TARGET_ROLES:
            jobs = await self._fetch_role(role)
            results.extend(jobs)

        # Deduplicate by external_id
        seen: set[str] = set()
        unique = []
        for job in results:
            if job["external_id"] not in seen:
                seen.add(job["external_id"])
                unique.append(job)

        logger.info("Wellfound: fetched %d unique jobs", len(unique))
        return unique

    async def _fetch_role(self, role: str) -> list[dict[str, Any]]:
        url = f"{WELLFOUND_SEARCH_URL}?role={role}&remote=true"
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, headers=HEADERS)
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Wellfound fetch failed for role %s: %s", role, e)
            return []

        return self._parse_html(resp.text, role)

    def _parse_html(self, html: str, role: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Wellfound embeds job data in Next.js __NEXT_DATA__ script tag
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if script and script.string:
            try:
                data = json.loads(script.string)
                job_listings = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("jobListings", {})
                    .get("jobs", [])
                )
                for item in job_listings:
                    job = self._parse_next_job(item, role)
                    if job:
                        jobs.append(job)
                return jobs
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: parse HTML job cards
        cards = soup.select("[data-test='job-listing']") or soup.select(".job-listing")
        for card in cards:
            job = self._parse_card(card, role)
            if job:
                jobs.append(job)

        return jobs

    def _parse_next_job(self, item: dict, role: str) -> dict | None:
        try:
            job_id = str(item.get("id", ""))
            title = item.get("title", "")
            company = item.get("startup", {}).get("name", "")
            location = item.get("locationNames", ["Remote"])[0] if item.get("locationNames") else "Remote"
            url = f"https://wellfound.com/jobs/{job_id}"
            description = item.get("description", "")

            salary = item.get("compensation", "") or ""
            salary_match = re.findall(r"\$?([\d,]+)k?", salary.replace(",", ""))
            salary_min = int(salary_match[0]) * 1000 if len(salary_match) > 0 else None
            salary_max = int(salary_match[1]) * 1000 if len(salary_match) > 1 else None

            raw = {
                "external_id": f"wf_{job_id}",
                "title": title,
                "company": company,
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": "USD" if salary_min else None,
                "description": description,
                "url": url,
                "tags": json.dumps([role]),
            }
            return self.normalize(raw)
        except Exception as e:
            logger.debug("Wellfound job parse error: %s", e)
            return None

    def _parse_card(self, card: Any, role: str) -> dict | None:
        try:
            title_el = card.select_one("h2, .job-title, [data-test='job-title']")
            company_el = card.select_one(".company-name, [data-test='company-name']")
            link_el = card.select_one("a[href]")

            if not title_el or not link_el:
                return None

            href = link_el.get("href", "")
            url = href if href.startswith("http") else f"https://wellfound.com{href}"
            job_id = re.search(r"/jobs/(\d+)", url)
            external_id = f"wf_{job_id.group(1)}" if job_id else f"wf_{hash(url)}"

            raw = {
                "external_id": external_id,
                "title": title_el.get_text(strip=True),
                "company": company_el.get_text(strip=True) if company_el else "",
                "location": "Remote",
                "url": url,
                "tags": json.dumps([role]),
            }
            return self.normalize(raw)
        except Exception as e:
            logger.debug("Wellfound card parse error: %s", e)
            return None
