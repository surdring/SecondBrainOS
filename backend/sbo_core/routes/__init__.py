from __future__ import annotations

from sbo_core.routes.ingest import router as ingest_router
from .query import router as query_router
from .manage import router as manage_router
from .episodic import router as episodic_router

__all__ = ["ingest_router", "query_router", "manage_router", "episodic_router"]
