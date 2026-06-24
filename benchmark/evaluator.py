"""Benchmark evaluator — scores PRISM against human reviewers.

Runs PRISM against collected PRs and compares the automated findings
to human reviewer comments.  Computes precision, recall, F1, and
severity-weighted scores.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from api.models import BenchmarkResult, BenchmarkSummary
from config import BENCHMARK_RESULTS_DIR
from graph.review_graph import run_review

logger = logging.getLogger(__name__)

# Severity weights for weighted scoring
_SEVERITY_WEIGHTS: dict[str, float] = {
    "CRITICAL": 5.0,
    "HIGH": 3.0,
    "MEDIUM": 2.0,
    "LOW": 1.0,
    "SUGGESTION": 0.5,
}


def _file_match(prism_file: str, human_file: str) -> bool:
    """Check if two file paths refer to the same file (fuzzy)."""
    if not prism_file or not human_file:
        return False
    # Exact match
    if prism_file == human_file:
        return True
    # One path ends with the other (handles prefix differences)
    if prism_file.endswith(human_file) or human_file.endswith(prism_file):
        return True
    # Basename match as last resort
    import os
    if os.path.basename(prism_file) == os.path.basename(human_file):
        return True
    return False


def _compute_overlap(
    prism_findings: list[dict[str, Any]],
    human_comments: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Compute true positives, false positives, and false negatives.

    A PRISM finding is considered a true positive if it matches a human
    comment on the same file. Line matching is ignored since GitHub stores hunk positions.
    """
    matched_human: set[int] = set()
    true_positives = 0

    for pf in prism_findings:
        pf_file = pf.get("file", "")
        found_match = False

        for idx, hc in enumerate(human_comments):
            if idx in matched_human:
                continue
            hc_file = hc.get("file", "")

            if _file_match(pf_file, hc_file):
                true_positives += 1
                matched_human.add(idx)
                found_match = True
                break

    false_positives = len(prism_findings) - true_positives
    false_negatives = len(human_comments) - len(matched_human)

    return true_positives, false_positives, false_negatives


def _compute_metrics(
    tp: int, fp: int, fn: int
) -> tuple[float, float, float]:
    """Compute precision, recall, and F1 from confusion counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return precision, recall, f1


def _severity_weighted_score(
    prism_findings: list[dict[str, Any]],
    human_comments: list[dict[str, Any]],
    tp: int,
) -> float:
    """Compute a severity-weighted accuracy score."""
    if not prism_findings:
        return 0.0

    total_weight = sum(
        _SEVERITY_WEIGHTS.get(f.get("severity", "LOW"), 1.0)
        for f in prism_findings
    )
    matched_weight = tp * 2.0  # Assume average weight for matches
    return min(1.0, matched_weight / total_weight) if total_weight > 0 else 0.0


async def evaluate_prism(
    collected_prs: list[Any],
) -> BenchmarkSummary:
    """Run PRISM against collected PRs and score findings.

    Returns a ``BenchmarkSummary`` and saves results to disk.
    """
    results: list[BenchmarkResult] = []

    for pr in collected_prs:
        owner = pr.owner if hasattr(pr, "owner") else pr.get("owner", "")
        repo = pr.repo if hasattr(pr, "repo") else pr.get("repo", "")
        number = pr.number if hasattr(pr, "number") else pr.get("number", 0)
        human_comments = (
            [asdict(c) if hasattr(c, "__dataclass_fields__") else c for c in pr.human_comments]
            if hasattr(pr, "human_comments")
            else pr.get("human_comments", [])
        )

        logger.info("Evaluating PR #%d (%s/%s)", number, owner, repo)

        try:
            result_state = await run_review(
                repo_owner=owner,
                repo_name=repo,
                pr_number=number,
            )

            final_review = result_state.get("final_review")
            if final_review is None:
                logger.warning("No review produced for PR #%d", number)
                continue

            # Convert findings to dicts for comparison
            prism_findings = [
                {
                    "file": f.file,
                    "line_start": f.line_start,
                    "severity": f.severity.value,
                    "message": f.message,
                }
                for f in final_review.findings
            ]

            tp, fp, fn = _compute_overlap(prism_findings, human_comments)
            precision, recall, f1 = _compute_metrics(tp, fp, fn)
            severity_score = _severity_weighted_score(
                prism_findings, human_comments, tp
            )

            result = BenchmarkResult(
                pr_number=number,
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1_score=round(f1, 4),
                severity_weighted_score=round(severity_score, 4),
                human_findings_count=len(human_comments),
                prism_findings_count=len(prism_findings),
                prism_findings=prism_findings,
                human_comments=human_comments,
            )
            results.append(result)

            logger.info(
                "PR #%d — P: %.2f  R: %.2f  F1: %.2f  SW: %.2f",
                number,
                precision,
                recall,
                f1,
                severity_score,
            )

        except Exception:
            logger.exception("Failed to evaluate PR #%d", number)
            continue
            
        logger.info("Sleeping for 60s to completely avoid API rate limits/503s...")
        import asyncio
        await asyncio.sleep(60)

    # Compute aggregated metrics
    summary = BenchmarkSummary(
        total_prs=len(results),
        avg_precision=round(
            sum(r.precision for r in results) / len(results), 4
        )
        if results
        else 0.0,
        avg_recall=round(
            sum(r.recall for r in results) / len(results), 4
        )
        if results
        else 0.0,
        avg_f1=round(
            sum(r.f1_score for r in results) / len(results), 4
        )
        if results
        else 0.0,
        avg_severity_weighted=round(
            sum(r.severity_weighted_score for r in results) / len(results), 4
        )
        if results
        else 0.0,
        results=results,
        run_at=datetime.now(timezone.utc),
    )

    # Persist to disk
    BENCHMARK_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = BENCHMARK_RESULTS_DIR / f"benchmark_{timestamp}.json"
    output_path.write_text(
        summary.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("Benchmark results saved to %s", output_path)

    return summary
