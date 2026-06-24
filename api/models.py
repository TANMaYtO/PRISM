"""Pydantic v2 schemas for the PRISM API.

Defines request/response models and the core ``AgentFinding`` structure
shared by every review agent in the graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────


class SeverityLevel(str, Enum):
    """Finding severity — ordered from most to least critical."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SUGGESTION = "SUGGESTION"


class RiskRating(str, Enum):
    """Overall PR risk after synthesis."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    CLEAN = "CLEAN"


class AgentSource(str, Enum):
    """Identifies which review agent produced a finding."""

    BUG_DETECTOR = "bug_detector"
    SECURITY_SCANNER = "security_scanner"
    LOGIC_AUDITOR = "logic_auditor"
    STYLE_CHECKER = "style_checker"
    SYNTHESIZER = "synthesizer"


# ── Request Models ───────────────────────────────────────────────────


class PRReviewRequest(BaseModel):
    """Payload accepted by ``POST /review``."""

    repo_owner: str = Field(
        ...,
        description="GitHub repository owner (user or organisation).",
        examples=["langchain-ai"],
    )
    repo_name: str = Field(
        ...,
        description="GitHub repository name.",
        examples=["langgraph"],
    )
    pr_number: int = Field(
        ...,
        gt=0,
        description="Pull-request number to review.",
        examples=[42],
    )
    branch: str | None = Field(
        default=None,
        description="Optional branch override for the base ref.",
    )


# ── Finding Model ────────────────────────────────────────────────────


class AgentFinding(BaseModel):
    """A single issue or suggestion surfaced by a review agent."""

    severity: SeverityLevel
    file: str = Field(
        ...,
        description="Relative path of the affected file.",
        examples=["src/utils/parser.py"],
    )
    line_start: int = Field(
        ...,
        ge=1,
        description="First line of the affected range (1-indexed).",
    )
    line_end: int = Field(
        ...,
        ge=1,
        description="Last line of the affected range (1-indexed).",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the finding.",
    )
    agent_source: AgentSource = Field(
        ...,
        description="The agent that produced this finding.",
    )


# ── Response Models ──────────────────────────────────────────────────


class SeverityStats(BaseModel):
    """Counts of findings grouped by severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    suggestion: int = 0


class PRReviewResponse(BaseModel):
    """Complete review result returned by ``POST /review``."""

    repo: str = Field(
        ...,
        description="Full repo identifier (owner/name).",
        examples=["langchain-ai/langgraph"],
    )
    pr_number: int
    summary: str = Field(
        ...,
        description="Executive summary of the review.",
    )
    risk_rating: RiskRating
    findings: list[AgentFinding] = Field(default_factory=list)
    stats: SeverityStats = Field(default_factory=SeverityStats)
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ── Benchmark Models ─────────────────────────────────────────────────


class BenchmarkRunRequest(BaseModel):
    """Trigger a benchmark evaluation run."""

    max_prs: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of PRs to evaluate.",
    )
    repo: str = Field(
        default="langchain-ai/langgraph",
        description="Target repo for benchmark collection.",
    )


class BenchmarkResult(BaseModel):
    """Scores from a single benchmark run."""

    pr_number: int
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1_score: float = Field(ge=0.0, le=1.0)
    severity_weighted_score: float = Field(ge=0.0, le=1.0)
    human_findings_count: int
    prism_findings_count: int
    prism_findings: list[dict[str, Any]] = Field(default_factory=list)
    human_comments: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkSummary(BaseModel):
    """Aggregated benchmark results."""

    total_prs: int
    avg_precision: float
    avg_recall: float
    avg_f1: float
    avg_severity_weighted: float
    results: list[BenchmarkResult] = Field(default_factory=list)
    run_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
