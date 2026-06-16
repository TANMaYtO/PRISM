"""FastAPI application for the PRISM autonomous PR review system.

Provides REST endpoints for submitting PR reviews and running benchmarks.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.client import get_client
from api.routes.benchmark import router as benchmark_router
from api.routes.review import router as review_router
from config import SUPABASE_URL

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-25s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    logger.info("🔷 PRISM starting up …")
    try:
        await get_client()
        logger.info(f"Connected to Supabase at {SUPABASE_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase connection: {e}")
        
    logger.info("SSE streaming enabled on POST /review")
    yield
    logger.info("🔷 PRISM shutting down …")


# ── App factory ──────────────────────────────────────────────────────

app = FastAPI(
    title="PRISM — Autonomous PR Reviewer",
    description=(
        "Multi-agent PR review system powered by LangGraph and Gemini. "
        "Analyses pull requests for bugs, security vulnerabilities, "
        "logic errors, and style violations."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────

app.include_router(review_router, prefix="/review", tags=["Review"])
app.include_router(benchmark_router, prefix="/benchmark", tags=["Benchmark"])


# ── Health check ─────────────────────────────────────────────────────


@app.get("/", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {
        "status": "healthy",
        "service": "prism",
        "version": "0.1.0",
    }
