"""Persistence layer for saving and retrieving reviews and benchmarks."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api.db.client import get_client
from api.models import PRReviewResponse, BenchmarkSummary

logger = logging.getLogger(__name__)


async def save_review(
    repo_owner: str, repo_name: str, pr_number: int, review: PRReviewResponse
) -> str:
    """Save a PR review to Supabase and return the inserted UUID."""
    try:
        client = await get_client()
        data = {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "pr_number": pr_number,
            "review_data": review.model_dump(mode="json"),
        }
        result = await client.table("reviews").insert(data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]["id"]
        return ""
    except Exception as e:
        logger.error(f"Failed to save review to Supabase: {e}")
        return ""


async def get_review(review_id: str) -> dict[str, Any] | None:
    """Retrieve a PR review by its UUID."""
    try:
        client = await get_client()
        result = await client.table("reviews").select("*").eq("id", review_id).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to get review {review_id} from Supabase: {e}")
        return None


async def get_recent_reviews(limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve the most recent PR reviews."""
    try:
        client = await get_client()
        result = (
            await client.table("reviews")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        if result.data:
            return result.data
        return []
    except Exception as e:
        logger.error(f"Failed to get recent reviews from Supabase: {e}")
        return []


async def save_benchmark(summary: BenchmarkSummary) -> str:
    """Save a benchmark summary to Supabase and return the inserted UUID."""
    try:
        client = await get_client()
        data = {
            "summary_data": summary.model_dump(mode="json"),
        }
        result = await client.table("benchmarks").insert(data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]["id"]
        return ""
    except Exception as e:
        logger.error(f"Failed to save benchmark to Supabase: {e}")
        return ""
