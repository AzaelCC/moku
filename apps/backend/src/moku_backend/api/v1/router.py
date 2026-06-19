"""API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from moku_backend.api.v1.health import router as health_router
from moku_backend.api.v1.recommendations import router as recommendations_router

router = APIRouter()
router.include_router(health_router)
router.include_router(recommendations_router)
