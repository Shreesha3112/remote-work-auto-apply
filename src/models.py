import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Float, DateTime, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(Text, nullable=False)          # remoteok, wellfound, naukri, instahyre
    external_id = Column(Text, nullable=False)      # board-specific ID for dedup
    title = Column(Text, nullable=False)
    company = Column(Text, nullable=False)
    location = Column(Text, default="Remote")
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    currency = Column(Text, nullable=True)          # USD, EUR, INR
    description = Column(Text, default="")
    url = Column(Text, nullable=False)
    posted_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    score = Column(Float, nullable=True)            # 0-100
    score_reasoning = Column(Text, nullable=True)
    status = Column(Text, default="pending")        # pending, reviewed, shortlisted, applied, rejected
    tags = Column(Text, default="[]")              # JSON array of matched keywords

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "currency": self.currency,
            "description": self.description,
            "url": self.url,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "score": self.score,
            "score_reasoning": self.score_reasoning,
            "status": self.status,
            "tags": self.tags,
        }


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, default=1)
    skills = Column(Text, default="[]")              # JSON array
    experience_years = Column(Float, default=0.0)
    current_role = Column(Text, default="")
    target_roles = Column(Text, default="[]")        # JSON array
    preferred_locations = Column(Text, default='["Remote", "Bengaluru"]')  # JSON
    min_salary_usd = Column(Integer, default=0)
    min_salary_inr = Column(Integer, default=0)
    profile_summary = Column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skills": self.skills,
            "experience_years": self.experience_years,
            "current_role": self.current_role,
            "target_roles": self.target_roles,
            "preferred_locations": self.preferred_locations,
            "min_salary_usd": self.min_salary_usd,
            "min_salary_inr": self.min_salary_inr,
            "profile_summary": self.profile_summary,
        }
