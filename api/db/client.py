"""Supabase database client setup."""

from __future__ import annotations

import logging
from supabase import AsyncClient, acreate_client

import config

logger = logging.getLogger(__name__)

_client: AsyncClient | None = None

async def get_client() -> AsyncClient:
    """Return a singleton Supabase AsyncClient."""
    global _client
    if _client is None:
        logger.info("Initializing Supabase AsyncClient")
        _client = await acreate_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client
