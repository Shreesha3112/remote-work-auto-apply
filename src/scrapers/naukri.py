import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from src.scrapers.base import BaseScraper
from src.config import settings

logger = logging.getLogger(__name__)

NAUKRI_SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"
NAUKRI_LOGIN_URL = "https://www.naukri.com/central-login-services/v1/login"

SEARCH_KEYWORDS = [
    "generative AI engineer",
    "LLM engineer",
    "ML engineer Bengaluru",
    "AI engineer remote India",
]


class NaukriScraper(BaseScraper):
    source_name = "naukri"

    def __init__(self):
        self._cookies: dict = {}
        self._playwright = None

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch jobs using Playwright to handle JS-heavy Naukri pages."""
        if not settings.naukri_email:
            logger.info("Naukri credentials not set, skipping")
            return []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed. Run: playwright install chromium")
            return []

        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            # Login
            logged_in = await self._login(page)
            if not logged_in:
                await browser.close()
                return []

            # Search for each keyword
            for keyword in SEARCH_KEYWORDS:
                jobs = await self._search(page, keyword)
                results.extend(jobs)

            await browser.close()

        # Deduplicate
        seen: set[str] = set()
        unique = []
        for job in results:
            if job["external_id"] not in seen:
                seen.add(job["external_id"])
                unique.append(job)

        logger.info("Naukri: fetched %d unique jobs", len(unique))
        return unique

    async def _login(self, page: Any) -> bool:
        try:
            await page.goto("https://www.naukri.com/", wait_until="networkidle", timeout=30000)

            # Click login
            await page.click("text=Login", timeout=5000)
            await page.fill('input[placeholder*="Enter Email"]', settings.naukri_email)
            await page.fill('input[placeholder*="Enter Password"]', settings.naukri_password)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Verify login
            if "login" not in page.url:
                logger.info("Naukri login successful")
                return True
            else:
                logger.warning("Naukri login may have failed")
                return False
        except Exception as e:
            logger.error("Naukri login error: %s", e)
            return False

    async def _search(self, page: Any, keyword: str) -> list[dict[str, Any]]:
        try:
            encoded = keyword.replace(" ", "%20")
            url = f"https://www.naukri.com/{encoded}-jobs?k={encoded}&l=bengaluru%2C+remote"
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for job cards
            await page.wait_for_selector(".jobTuple, article.jobTupleHeader", timeout=10000)

            cards = await page.query_selector_all(".jobTuple, article.jobTupleHeader")
            jobs = []
            for card in cards[:20]:  # limit per keyword
                job = await self._parse_card(card, keyword)
                if job:
                    jobs.append(job)
            return jobs
        except Exception as e:
            logger.warning("Naukri search failed for '%s': %s", keyword, e)
            return []

    async def _parse_card(self, card: Any, keyword: str) -> dict | None:
        try:
            title_el = await card.query_selector(".title, .jobTitle")
            company_el = await card.query_selector(".companyInfo, .companyName")
            location_el = await card.query_selector(".location")
            salary_el = await card.query_selector(".salary")
            link_el = await card.query_selector("a.title, a.jobTitle")

            title = await title_el.inner_text() if title_el else ""
            company = await company_el.inner_text() if company_el else ""
            location = await location_el.inner_text() if location_el else "Bengaluru"
            salary_text = await salary_el.inner_text() if salary_el else ""
            href = await link_el.get_attribute("href") if link_el else ""

            if not title or not href:
                return None

            job_id_match = re.search(r"(\d{8,})", href)
            external_id = f"naukri_{job_id_match.group(1)}" if job_id_match else f"naukri_{hash(href)}"

            salary_min, salary_max = self._parse_salary_inr(salary_text)

            raw = {
                "external_id": external_id,
                "title": title.strip(),
                "company": company.strip(),
                "location": location.strip(),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": "INR" if salary_min else None,
                "url": href if href.startswith("http") else f"https://www.naukri.com{href}",
                "tags": json.dumps([keyword]),
            }
            return self.normalize(raw)
        except Exception as e:
            logger.debug("Naukri card parse error: %s", e)
            return None

    def _parse_salary_inr(self, text: str) -> tuple[int | None, int | None]:
        """Parse '8-15 Lacs' or '15-25 Lakh' into INR integers."""
        match = re.search(r"([\d.]+)\s*[-–]\s*([\d.]+)\s*[Ll]a[ck]", text)
        if match:
            try:
                low = int(float(match.group(1)) * 100_000)
                high = int(float(match.group(2)) * 100_000)
                return low, high
            except ValueError:
                pass
        return None, None
