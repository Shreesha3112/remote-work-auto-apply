import json
import logging
from typing import Any

from src.models import Job, UserProfile
from src.llm.client import llm_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a career advisor helping a Gen AI / ML engineer evaluate job opportunities.
Score the job opportunity for the candidate and respond with ONLY valid JSON — no markdown, no extra text.

Output format:
{
  "score": <integer 0-100>,
  "reasoning": "<2-3 sentence explanation>",
  "pros": ["<pro 1>", "<pro 2>", "<pro 3>"],
  "cons": ["<con 1>", "<con 2>"]
}

Scoring criteria:
- Skills match (40%): How well do the required skills match the candidate's skills?
- Salary fit (20%): Is the salary at or above the candidate's minimum?
- Remote eligibility (15%): Is the role remote or in the candidate's preferred locations?
- Growth potential (15%): Does the role offer career growth for the candidate's goals?
- Seniority fit (10%): Does the seniority level match the candidate's experience?"""


def _build_user_prompt(job: Job, profile: UserProfile) -> str:
    skills = json.loads(profile.skills) if profile.skills else []
    target_roles = json.loads(profile.target_roles) if profile.target_roles else []

    salary_context = ""
    if profile.min_salary_usd:
        salary_context += f"Min salary: ${profile.min_salary_usd:,}/yr USD"
    if profile.min_salary_inr:
        salary_context += f" / ₹{profile.min_salary_inr:,}/yr INR"

    job_salary = ""
    if job.salary_min:
        job_salary = f"{job.salary_min:,}"
        if job.salary_max:
            job_salary += f"–{job.salary_max:,}"
        if job.currency:
            job_salary += f" {job.currency}/yr"
    else:
        job_salary = "Not specified"

    return f"""## Candidate Profile
{profile.profile_summary}

Skills: {", ".join(skills)}
Experience: {profile.experience_years} years
Current role: {profile.current_role}
Target roles: {", ".join(target_roles)}
{salary_context}

## Job Description
Title: {job.title} at {job.company}
Location: {job.location}
Salary: {job_salary}

{job.description[:3000]}"""


async def score_job(job: Job, profile: UserProfile) -> tuple[float, str]:
    """
    Score a job against a user profile using the vLLM.

    Returns (score: float 0-100, reasoning: str as raw JSON string)
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(job, profile)},
    ]

    try:
        raw = await llm_client.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        result = _parse_score_response(raw)
        score = float(result.get("score", 50))
        score = max(0.0, min(100.0, score))
        return score, raw
    except Exception as e:
        logger.error("LLM scoring failed for job '%s': %s", job.title, e)
        return 50.0, json.dumps({"score": 50, "reasoning": f"Scoring failed: {e}", "pros": [], "cons": []})


def _parse_score_response(raw: str) -> dict[str, Any]:
    """Parse and validate the LLM JSON response."""
    # Strip any markdown code fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse JSON from: {text[:200]}")

    if "score" not in data:
        raise ValueError("Missing 'score' field in LLM response")

    return data


async def score_jobs_batch(
    jobs: list[Job],
    profile: UserProfile,
    concurrency: int = 3,
) -> list[tuple[Job, float, str]]:
    """Score multiple jobs with limited concurrency."""
    import asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def score_one(job: Job) -> tuple[Job, float, str]:
        async with semaphore:
            score, reasoning = await score_job(job, profile)
            return job, score, reasoning

    tasks = [score_one(job) for job in jobs]
    return await asyncio.gather(*tasks)
