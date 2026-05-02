"""User preferences and deploy-mode API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.logging_config import get_logger
from app.models.user import (
    UserORM,
    UserPreferencesORM,
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config/deploy-mode")
async def get_deploy_mode_endpoint(db: Session = Depends(get_db)):
    """Get current deploy mode.

    Reads from site_settings table first, falls back to env var.
    """
    from app.config import get_deploy_mode
    mode = get_deploy_mode(db)
    return {"mode": mode}


@router.get("/user/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's preferences."""
    rows = (
        db.query(UserPreferencesORM)
        .filter(UserPreferencesORM.user_id == current_user.id)
        .all()
    )
    preferences = {row.key: row.value for row in rows}
    return UserPreferencesResponse(preferences=preferences)


@router.put("/user/preferences")
async def update_user_preferences(
    payload: UserPreferencesUpdateRequest,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's preferences."""
    updated = []
    for key, value in payload.preferences.items():
        existing = (
            db.query(UserPreferencesORM)
            .filter(
                UserPreferencesORM.user_id == current_user.id,
                UserPreferencesORM.key == key,
            )
            .first()
        )
        if existing:
            existing.value = value
        else:
            db.add(UserPreferencesORM(user_id=current_user.id, key=key, value=value))
        updated.append(key)
    db.commit()
    logger.info("User %d updated preferences: %s", current_user.id, updated)
    return {"updated": updated}
