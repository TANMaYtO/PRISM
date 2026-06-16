"""Review route — POST /review endpoint.

Accepts a ``PRReviewRequest``, invokes the LangGraph review graph,
and returns a ``PRReviewResponse`` with all findings.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.db.persistence import get_recent_reviews, get_review, save_review
from api.models import PRReviewRequest, PRReviewResponse
from graph.review_graph import run_review_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    summary="Review a pull request (SSE Stream)",
    description=(
        "Submit a GitHub PR for autonomous review. PRISM will fetch the PR, "
        "build a RAG index of the repository, run four specialised analysis "
        "agents in parallel, and stream events back via SSE. "
        "After completion, it saves the final review to Supabase."
    ),
)
async def create_review(repo_owner: str, repo_name: str, pr_number: int) -> StreamingResponse:
    """Execute a full PRISM review and stream SSE events."""
    logger.info(
        "Review requested: %s/%s#%d",
        repo_owner,
        repo_name,
        pr_number,
    )
    
    # Recreate the request object locally to minimize refactoring
    request = PRReviewRequest(repo_owner=repo_owner, repo_name=repo_name, pr_number=pr_number)

    async def event_generator() -> AsyncGenerator[str, None]:
        final_review_data: Any = None
        try:
            async for payload in run_review_stream(
                repo_owner=request.repo_owner,
                repo_name=request.repo_name,
                pr_number=request.pr_number,
            ):
                event_type = payload.get("event", "message")
                data = payload.get("data", "")

                if event_type == "complete":
                    final_review_data = data

                if isinstance(data, dict):
                    data_str = json.dumps(data)
                elif hasattr(data, "model_dump_json"):
                    data_str = data.model_dump_json()
                elif hasattr(data, "model_dump"):
                    data_str = json.dumps(data.model_dump(mode="json"))
                else:
                    data_str = json.dumps(data)

                yield f"event: {event_type}\ndata: {data_str}\n\n"

            if final_review_data:
                logger.info("Persisting review to Supabase")
                if isinstance(final_review_data, str):
                    review_obj = PRReviewResponse.model_validate_json(final_review_data)
                else:
                    review_obj = PRReviewResponse.model_validate(final_review_data)

                review_id = await save_review(
                    repo_owner=request.repo_owner,
                    repo_name=request.repo_name,
                    pr_number=request.pr_number,
                    review=review_obj,
                )
                if review_id:
                    yield f"event: persisted\ndata: {{\"id\": \"{review_id}\"}}\n\n"

        except Exception as exc:
            logger.exception("Review stream generator failed")
            yield f"event: error\ndata: {json.dumps(str(exc))}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "s",
    summary="Get recent reviews",
)
async def list_recent_reviews(limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve the most recent PR reviews."""
    try:
        return await get_recent_reviews(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent reviews")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recent reviews",
        ) from exc


@router.get(
    "/{review_id}",
    summary="Get a specific review",
)
async def read_review(review_id: str) -> dict[str, Any]:
    """Retrieve a PR review by its UUID."""
    try:
        review = await get_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found",
            )
        return review
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch review %s", review_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch review",
        ) from exc
