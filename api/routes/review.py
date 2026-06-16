"""Review route — POST /review endpoint.

Accepts a ``PRReviewRequest``, invokes the LangGraph review graph,
and returns a ``PRReviewResponse`` with all findings.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status

from api.models import PRReviewRequest, PRReviewResponse
from graph.review_graph import run_review

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=PRReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Review a pull request",
    description=(
        "Submit a GitHub PR for autonomous review. PRISM will fetch the PR, "
        "build a RAG index of the repository, run four specialised analysis "
        "agents in parallel, and return a synthesised review."
    ),
)
async def create_review(request: PRReviewRequest) -> PRReviewResponse:
    """Execute a full PRISM review on the specified pull request."""
    logger.info(
        "Review requested: %s/%s#%d",
        request.repo_owner,
        request.repo_name,
        request.pr_number,
    )

    start = time.perf_counter()

    try:
        result: dict[str, Any] = await run_review(
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            pr_number=request.pr_number,
        )
    except ValueError as exc:
        logger.error("Validation error during review: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid PR parameters: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Review pipeline failed for %s/%s#%d", request.repo_owner, request.repo_name, request.pr_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review pipeline failed: {type(exc).__name__}: {exc}",
        ) from exc

    elapsed = time.perf_counter() - start
    review: PRReviewResponse = result["final_review"]

    logger.info(
        "Review completed in %.1fs — risk: %s, findings: %d",
        elapsed,
        review.risk_rating.value,
        len(review.findings),
    )

    return review
