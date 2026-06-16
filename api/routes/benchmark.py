"""Benchmark route — GET /benchmark and POST /benchmark/run endpoints.

Returns stored benchmark results or triggers a new evaluation run
comparing PRISM findings against human reviewer comments.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from api.models import BenchmarkRunRequest, BenchmarkSummary
from api.db.client import get_client
from api.db.persistence import save_benchmark
from config import BENCHMARK_RESULTS_DIR

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_latest_results() -> BenchmarkSummary | None:
    """Load the most recent benchmark results JSON file."""
    BENCHMARK_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_files = sorted(
        BENCHMARK_RESULTS_DIR.glob("benchmark_*.json"),
        reverse=True,
    )
    if not result_files:
        return None

    latest = result_files[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        return BenchmarkSummary(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse benchmark file %s: %s", latest, exc)
        return None


async def _run_benchmark_task(max_prs: int, repo: str) -> None:
    """Background task that runs the benchmark pipeline."""
    try:
        from benchmark.collector import collect_reviewed_prs
        from benchmark.evaluator import evaluate_prism

        logger.info(
            "Starting benchmark run: repo=%s, max_prs=%d", repo, max_prs
        )

        owner, name = repo.split("/")
        prs = await collect_reviewed_prs(
            owner=owner, repo_name=name, max_prs=max_prs
        )
        logger.info("Collected %d PRs with human reviews", len(prs))

        summary = await evaluate_prism(prs)
        logger.info("Saving benchmark summary to Supabase")
        await save_benchmark(summary)
        
        logger.info("Benchmark run completed")

    except Exception:
        logger.exception("Benchmark run failed")


@router.get(
    "",
    response_model=BenchmarkSummary | None,
    summary="Get latest benchmark results",
    description="Returns the most recent benchmark evaluation results.",
)
async def get_benchmark() -> BenchmarkSummary:
    """Return the latest stored benchmark results."""
    try:
        client = await get_client()
        result = (
            await client.table("benchmarks")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return BenchmarkSummary(**result.data[0]["summary_data"])
    except Exception as exc:
        logger.error("Failed to load benchmark from Supabase: %s", exc)

    logger.info("Falling back to local disk for benchmark results")
    results = _load_latest_results()
    if results is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No benchmark results found. "
                "Trigger a run via POST /benchmark/run."
            ),
        )
    return results


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a benchmark run",
    description=(
        "Starts a background benchmark evaluation. Results will be "
        "available via GET /benchmark once the run completes."
    ),
)
async def trigger_benchmark(
    request: BenchmarkRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Launch a benchmark run in the background."""
    background_tasks.add_task(
        _run_benchmark_task, request.max_prs, request.repo
    )
    return {
        "status": "accepted",
        "message": (
            f"Benchmark run started for {request.repo} "
            f"(max {request.max_prs} PRs). "
            f"Check GET /benchmark for results."
        ),
    }
