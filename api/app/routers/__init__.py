"""Routers package."""

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.config import router as config_router
from app.routers.jobs import router as jobs_router
from app.routers.model_status import router as model_status_router
from app.routers.models import router as models_router
from app.routers.setup import router as setup_router

__all__ = ["admin_router", "auth_router", "config_router", "jobs_router", "model_status_router", "models_router", "setup_router"]
