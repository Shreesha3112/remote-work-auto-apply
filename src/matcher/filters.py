import json
import logging
from src.models import Job, UserProfile

logger = logging.getLogger(__name__)

# At least one of these must appear in title or description (case-insensitive)
MUST_HAVE_KEYWORDS = [
    "ai", "ml", "llm", "gen ai", "genai", "generative ai", "nlp",
    "rag", "python", "machine learning", "deep learning", "langchain",
    "large language model", "vector", "embedding", "transformer",
    "data science", "neural", "gpt", "bert", "diffusion",
]

# Reject if any of these appear (as whole words / phrases)
REJECT_KEYWORDS = [
    "java only", "c++ only", "embedded systems", "hardware engineer",
    "verilog", "fpga", "autocad", "mechanical engineer", "civil engineer",
    "electrical engineer", "mainframe", "cobol", "fortran",
]

VALID_LOCATIONS = {"remote", "bengaluru", "bangalore", "india", "hybrid"}


def passes_filter(job: dict | Job, profile: UserProfile) -> bool:
    """
    Returns True if the job passes rule-based pre-filtering.
    Checks: keywords, reject-list, location, and salary floor.
    """
    # Normalise to a plain dict
    if isinstance(job, Job):
        job = job.to_dict()

    text = f"{job.get('title', '')} {job.get('description', '')}".lower()

    # Must-have check
    has_required = any(kw in text for kw in MUST_HAVE_KEYWORDS)
    if not has_required:
        logger.debug("Job '%s' failed must-have keyword check", job.get("title"))
        return False

    # Reject check
    for reject_kw in REJECT_KEYWORDS:
        if reject_kw in text:
            logger.debug("Job '%s' rejected on keyword '%s'", job.get("title"), reject_kw)
            return False

    # Location check
    location = (job.get("location") or "remote").lower()
    if not any(loc in location for loc in VALID_LOCATIONS):
        logger.debug("Job '%s' failed location check: %s", job.get("title"), location)
        return False

    # Salary check (only if both job and profile have salary info)
    salary_min = job.get("salary_min")
    currency = (job.get("currency") or "").upper()
    if salary_min and profile:
        if currency == "USD" and profile.min_salary_usd:
            if salary_min < profile.min_salary_usd * 0.8:  # 20% tolerance
                logger.debug(
                    "Job '%s' salary $%d USD below threshold $%d",
                    job.get("title"), salary_min, profile.min_salary_usd,
                )
                return False
        elif currency == "INR" and profile.min_salary_inr:
            if salary_min < profile.min_salary_inr * 0.8:
                logger.debug(
                    "Job '%s' salary ₹%d INR below threshold ₹%d",
                    job.get("title"), salary_min, profile.min_salary_inr,
                )
                return False

    return True


def extract_tags(job: dict) -> list[str]:
    """Extract matched keywords from job text for tagging."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    matched = [kw for kw in MUST_HAVE_KEYWORDS if kw in text]
    return matched[:10]  # cap at 10 tags
