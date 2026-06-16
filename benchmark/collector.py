"""Benchmark collector — scrapes merged PRs with human review comments.

Targets the ``langchain-ai/langgraph`` repository (configurable) to collect
PRs that have human review comments.  Extracts review comments mapped to
file/line locations and saves them as structured JSON for evaluation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from github import Github
from github.PullRequestComment import PullRequestComment

from config import BENCHMARK_RESULTS_DIR, GITHUB_TOKEN

logger = logging.getLogger(__name__)


@dataclass
class HumanComment:
    """A human review comment mapped to a file location."""

    body: str
    file: str
    line: int
    reviewer: str
    created_at: str


@dataclass
class CollectedPR:
    """A PR with its associated human review comments."""

    number: int
    title: str
    owner: str
    repo: str
    merged_at: str
    human_comments: list[HumanComment] = field(default_factory=list)


async def collect_reviewed_prs(
    owner: str = "langchain-ai",
    repo_name: str = "langgraph",
    max_prs: int = 10,
) -> list[CollectedPR]:
    """Scrape merged PRs that have inline human review comments.

    Returns a list of ``CollectedPR`` objects with structured comment data.
    """
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(f"{owner}/{repo_name}")

    collected: list[CollectedPR] = []

    # Iterate through recently closed PRs that were merged
    pulls = repo.get_pulls(state="closed", sort="updated", direction="desc")
    scanned = 0

    for pr in pulls:
        if scanned >= max_prs * 20:  # Scan up to 20x to find enough
            break
        scanned += 1

        if not pr.merged:
            continue

        # Get review comments (inline comments on diff lines)
        review_comments: list[PullRequestComment] = list(
            pr.get_review_comments()
        )
        if not review_comments:
            continue

        human_comments: list[HumanComment] = []
        for comment in review_comments:
            # Skip bot comments
            if comment.user and comment.user.type == "Bot":
                continue

            human_comments.append(
                HumanComment(
                    body=comment.body,
                    file=comment.path or "",
                    line=comment.position or comment.original_position or 0,
                    reviewer=comment.user.login if comment.user else "unknown",
                    created_at=comment.created_at.isoformat(),
                )
            )

        if not human_comments:
            continue

        merged_at = pr.merged_at.isoformat() if pr.merged_at else ""

        collected.append(
            CollectedPR(
                number=pr.number,
                title=pr.title,
                owner=owner,
                repo=repo_name,
                merged_at=merged_at,
                human_comments=human_comments,
            )
        )

        logger.info(
            "Collected PR #%d: %d human comments", pr.number, len(human_comments)
        )

        if len(collected) >= max_prs:
            break

    gh.close()

    # Save collected data
    BENCHMARK_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = BENCHMARK_RESULTS_DIR / f"collected_{timestamp}.json"
    output_path.write_text(
        json.dumps(
            [asdict(pr) for pr in collected],
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    logger.info("Saved %d collected PRs to %s", len(collected), output_path)

    return collected
