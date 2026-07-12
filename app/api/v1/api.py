"""
api/v1/api.py — The main API router registry.

This module aggregates all feature-specific routers into a single v1 router,
which is then mounted by the FastAPI application factory.
"""
from fastapi import APIRouter

from app.api.v1.routers import health, providers, research, notion, sessions, observability

api_router = APIRouter()

# Health routes (liveness/readiness)
api_router.include_router(health.router)

# Feature routes
api_router.include_router(sessions.router)
api_router.include_router(providers.router)
api_router.include_router(research.router)
api_router.include_router(notion.router)
api_router.include_router(observability.router)
