import json
import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import UserProfile
from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    skills: list[str] | None = None
    experience_years: float | None = None
    current_role: str | None = None
    target_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    min_salary_usd: int | None = None
    min_salary_inr: int | None = None
    profile_summary: str | None = None


@router.get("")
async def get_profile(db: Session = Depends(get_db)):
    """Get the user profile. Creates from YAML if not in DB yet."""
    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not profile:
        profile = _load_profile_from_yaml(db)
    return _profile_to_response(profile)


@router.put("")
async def update_profile(body: ProfileUpdate, db: Session = Depends(get_db)):
    """Update user profile fields."""
    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not profile:
        profile = _load_profile_from_yaml(db)

    if body.skills is not None:
        profile.skills = json.dumps(body.skills)
    if body.experience_years is not None:
        profile.experience_years = body.experience_years
    if body.current_role is not None:
        profile.current_role = body.current_role
    if body.target_roles is not None:
        profile.target_roles = json.dumps(body.target_roles)
    if body.preferred_locations is not None:
        profile.preferred_locations = json.dumps(body.preferred_locations)
    if body.min_salary_usd is not None:
        profile.min_salary_usd = body.min_salary_usd
    if body.min_salary_inr is not None:
        profile.min_salary_inr = body.min_salary_inr
    if body.profile_summary is not None:
        profile.profile_summary = body.profile_summary

    db.commit()
    db.refresh(profile)

    # Sync back to YAML
    _save_profile_to_yaml(profile)

    return _profile_to_response(profile)


def _load_profile_from_yaml(db: Session) -> UserProfile:
    """Load profile from YAML file into DB."""
    yaml_path = settings.profile_path
    profile = UserProfile(id=1)

    if yaml_path.exists():
        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}

            profile.skills = json.dumps(data.get("skills", []))
            profile.experience_years = float(data.get("experience_years", 0))
            profile.current_role = data.get("current_role", "")
            profile.target_roles = json.dumps(data.get("target_roles", []))
            profile.preferred_locations = json.dumps(
                data.get("preferred_locations", ["Remote", "Bengaluru"])
            )
            profile.min_salary_usd = int(data.get("min_salary_usd", 0))
            profile.min_salary_inr = int(data.get("min_salary_inr", 0))
            profile.profile_summary = data.get("profile_summary", "")
        except Exception as e:
            logger.warning("Could not load profile YAML: %s", e)

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _save_profile_to_yaml(profile: UserProfile) -> None:
    """Persist profile back to YAML for version control."""
    yaml_path = settings.profile_path
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "skills": json.loads(profile.skills or "[]"),
        "experience_years": profile.experience_years,
        "current_role": profile.current_role,
        "target_roles": json.loads(profile.target_roles or "[]"),
        "preferred_locations": json.loads(profile.preferred_locations or "[]"),
        "min_salary_usd": profile.min_salary_usd,
        "min_salary_inr": profile.min_salary_inr,
        "profile_summary": profile.profile_summary,
    }
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _profile_to_response(profile: UserProfile) -> dict:
    return {
        "skills": json.loads(profile.skills or "[]"),
        "experience_years": profile.experience_years,
        "current_role": profile.current_role,
        "target_roles": json.loads(profile.target_roles or "[]"),
        "preferred_locations": json.loads(profile.preferred_locations or "[]"),
        "min_salary_usd": profile.min_salary_usd,
        "min_salary_inr": profile.min_salary_inr,
        "profile_summary": profile.profile_summary,
    }
