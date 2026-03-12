import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from src.database import get_db
from src.models import Job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class StatusUpdate(BaseModel):
    status: str


VALID_STATUSES = {"pending", "reviewed", "shortlisted", "applied", "rejected"}


@router.get("")
async def list_jobs(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List jobs with optional filters."""
    query = db.query(Job)

    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if min_score is not None:
        query = query.filter(Job.score >= min_score)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Job.title.ilike(search_term),
                Job.company.ilike(search_term),
                Job.description.ilike(search_term),
            )
        )

    total = query.count()
    jobs = (
        query.order_by(Job.score.desc().nullslast(), Job.fetched_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "jobs": [_job_summary(j) for j in jobs],
    }


@router.get("/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get full job details including description and LLM reasoning."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    data = job.to_dict()
    # Parse score_reasoning JSON if available
    if job.score_reasoning:
        try:
            data["score_detail"] = json.loads(job.score_reasoning)
        except (json.JSONDecodeError, TypeError):
            data["score_detail"] = None
    return data


@router.patch("/{job_id}/status")
async def update_job_status(
    job_id: str,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    """Update a job's status (shortlist / reject / apply)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
        )

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = body.status
    db.commit()
    db.refresh(job)
    return {"id": job.id, "status": job.status}


def _job_summary(job: Job) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "url": job.url,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "score": job.score,
        "status": job.status,
        "tags": job.tags,
    }
