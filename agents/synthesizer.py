"""Synthesizer agent — aggregates and deduplicates findings.

Merges results from all four review agents, deduplicates overlapping
findings, assigns an overall risk rating, and composes the final
``PRReviewResponse``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from api.models import (
    AgentFinding,
    AgentSource,
    PRReviewResponse,
    RiskRating,
    SeverityLevel,
    SeverityStats,
)
from config import GEMINI_API_KEY, MAX_CONTEXT_TOKENS, MODEL_NAME

logger = logging.getLogger(__name__)

_SEVERITY_RANK: dict[str, int] = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "SUGGESTION": 1,
}

_SUMMARY_PROMPT = """\
You are a senior engineering manager writing the executive summary for
an automated code review.  Given the following deduplicated findings
from four specialised review agents, write a concise 3–5 sentence
summary of the pull request's quality.

Include:
- The overall risk level and why
- The most critical findings (if any)
- A brief recommendation (approve, request changes, or needs discussion)

Findings:
{findings_json}

PR Title: {pr_title}
PR Description: {pr_description}

Respond with ONLY the summary text — no JSON, no markdown headings.
"""


def _deduplicate_findings(
    all_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate findings covering the same file + line range.

    When two findings overlap on the same file and line range, keep the
    one with the higher severity.
    """
    # Key: (file, line_start, line_end)
    best: dict[tuple[str, int, int], dict[str, Any]] = {}

    for finding in all_findings:
        key = (
            finding.get("file", ""),
            finding.get("line_start", 0),
            finding.get("line_end", 0),
        )
        existing = best.get(key)
        if existing is None:
            best[key] = finding
        else:
            existing_rank = _SEVERITY_RANK.get(
                existing.get("severity", ""), 0
            )
            new_rank = _SEVERITY_RANK.get(
                finding.get("severity", ""), 0
            )
            if new_rank > existing_rank:
                # Merge: keep higher severity, combine messages
                merged = {**finding}
                merged["message"] = (
                    f"{finding['message']} "
                    f"[Also flagged by {existing.get('agent_source', 'unknown')}: "
                    f"{existing['message']}]"
                )
                best[key] = merged

    return list(best.values())


def _compute_stats(findings: list[AgentFinding]) -> SeverityStats:
    """Count findings per severity level."""
    stats = SeverityStats()
    for f in findings:
        match f.severity:
            case SeverityLevel.CRITICAL:
                stats.critical += 1
            case SeverityLevel.HIGH:
                stats.high += 1
            case SeverityLevel.MEDIUM:
                stats.medium += 1
            case SeverityLevel.LOW:
                stats.low += 1
            case SeverityLevel.SUGGESTION:
                stats.suggestion += 1
    return stats


def _determine_risk(stats: SeverityStats) -> RiskRating:
    """Derive overall risk rating from finding severity counts."""
    if stats.critical > 0:
        return RiskRating.CRITICAL
    if stats.high >= 3:
        return RiskRating.HIGH
    if stats.high >= 1 or stats.medium >= 5:
        return RiskRating.MODERATE
    if stats.medium >= 1 or stats.low >= 3:
        return RiskRating.LOW
    return RiskRating.CLEAN


def _to_agent_findings(raw: list[dict[str, Any]]) -> list[AgentFinding]:
    """Convert raw finding dicts to validated AgentFinding models."""
    validated: list[AgentFinding] = []
    for item in raw:
        try:
            validated.append(
                AgentFinding(
                    severity=SeverityLevel(item.get("severity", "LOW")),
                    file=item.get("file", "unknown"),
                    line_start=max(1, int(item.get("line_start", 1))),
                    line_end=max(1, int(item.get("line_end", 1))),
                    message=item.get("message", "No description provided."),
                    agent_source=AgentSource(
                        item.get("agent_source", "synthesizer")
                    ),
                )
            )
        except (ValueError, KeyError) as exc:
            logger.warning("Skipping malformed finding: %s — %s", item, exc)
    return validated


async def run_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
    """Aggregate findings from all agents and compose the final review.

    Reads all ``*_findings`` keys from state plus ``pr_data``.
    Returns a partial state update with ``final_review``.
    """
    pr_data = state["pr_data"]

    # Collect findings from all agents
    all_raw: list[dict[str, Any]] = []
    for key in ("bug_findings", "security_findings", "logic_findings", "style_findings"):
        findings = state.get(key, [])
        if isinstance(findings, list):
            all_raw.extend(findings)

    logger.info(
        "Synthesizer received %d total findings from agents", len(all_raw)
    )

    # Deduplicate
    deduped_raw = _deduplicate_findings(all_raw)
    logger.info(
        "After deduplication: %d unique findings", len(deduped_raw)
    )

    # Validate into Pydantic models
    findings = _to_agent_findings(deduped_raw)

    # Sort by severity (most critical first)
    findings.sort(
        key=lambda f: _SEVERITY_RANK.get(f.severity.value, 0),
        reverse=True,
    )

    stats = _compute_stats(findings)
    risk_rating = _determine_risk(stats)

    # Generate executive summary via LLM
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
        max_output_tokens=1024,
    )

    findings_for_prompt = [
        {
            "severity": f.severity.value,
            "file": f.file,
            "line_start": f.line_start,
            "message": f.message[:200],
            "agent": f.agent_source.value,
        }
        for f in findings[:20]  # Cap to avoid token overflow
    ]

    prompt = _SUMMARY_PROMPT.format(
        findings_json=json.dumps(findings_for_prompt, indent=2),
        pr_title=pr_data.title,
        pr_description=pr_data.body[:500] if pr_data.body else "No description.",
    )

    response = await llm.ainvoke(
        [{"role": "user", "content": prompt}]
    )
    summary = response.content.strip()

    # Compose final response
    review = PRReviewResponse(
        repo=f"{pr_data.owner}/{pr_data.repo}",
        pr_number=pr_data.number,
        summary=summary,
        risk_rating=risk_rating,
        findings=findings,
        stats=stats,
        reviewed_at=datetime.now(timezone.utc),
    )

    logger.info(
        "Review complete — risk: %s, findings: %d (C:%d H:%d M:%d L:%d S:%d)",
        risk_rating.value,
        len(findings),
        stats.critical,
        stats.high,
        stats.medium,
        stats.low,
        stats.suggestion,
    )

    return {"final_review": review}
