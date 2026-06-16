"""PR Fetcher agent — pulls PR metadata and diff from GitHub.

Uses PyGithub to retrieve the pull-request title, body, changed files,
and unified diff.  The output is written into the shared graph state so
downstream agents can operate on structured diff data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from github import Github
from github.PullRequest import PullRequest

from config import GITHUB_TOKEN

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DiffHunk:
    """A single hunk inside a file diff."""

    header: str
    added_lines: list[str]
    removed_lines: list[str]
    raw: str


@dataclass(frozen=True, slots=True)
class FileDiff:
    """Parsed diff for one file in the PR."""

    filename: str
    status: str  # added | removed | modified | renamed
    additions: int
    deletions: int
    patch: str
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PRData:
    """Structured representation of a GitHub pull request."""

    owner: str
    repo: str
    number: int
    title: str
    body: str
    base_ref: str
    head_ref: str
    diff_files: list[FileDiff]
    raw_diff: str


# ── Diff parser ──────────────────────────────────────────────────────


def _parse_patch_into_hunks(patch: str | None) -> list[DiffHunk]:
    """Split a unified diff patch string into individual hunks."""
    if not patch:
        return []

    hunks: list[DiffHunk] = []
    current_header = ""
    current_lines: list[str] = []

    for line in patch.splitlines():
        if line.startswith("@@"):
            if current_header:
                hunks.append(_build_hunk(current_header, current_lines))
            current_header = line
            current_lines = []
        else:
            current_lines.append(line)

    if current_header:
        hunks.append(_build_hunk(current_header, current_lines))

    return hunks


def _build_hunk(header: str, lines: list[str]) -> DiffHunk:
    """Construct a DiffHunk from raw lines."""
    return DiffHunk(
        header=header,
        added_lines=[ln[1:] for ln in lines if ln.startswith("+")],
        removed_lines=[ln[1:] for ln in lines if ln.startswith("-")],
        raw="\n".join([header, *lines]),
    )


# ── Agent node ───────────────────────────────────────────────────────


async def run_pr_fetcher(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch PR metadata and diff from GitHub.

    Reads ``repo_owner``, ``repo_name``, and ``pr_number`` from state.
    Returns a partial state update with ``pr_data`` and ``diff_files``.
    """
    owner: str = state["repo_owner"]
    repo_name: str = state["repo_name"]
    pr_number: int = state["pr_number"]

    logger.info(
        "Fetching PR #%d from %s/%s", pr_number, owner, repo_name
    )

    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(f"{owner}/{repo_name}")
    pr: PullRequest = repo.get_pull(pr_number)

    # Build structured diff for every changed file
    diff_files: list[FileDiff] = []
    raw_patches: list[str] = []

    for f in pr.get_files():
        patch = f.patch or ""
        hunks = _parse_patch_into_hunks(patch)
        diff_files.append(
            FileDiff(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=patch,
                hunks=hunks,
            )
        )
        if patch:
            raw_patches.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{patch}")

    raw_diff = "\n\n".join(raw_patches)

    pr_data = PRData(
        owner=owner,
        repo=repo_name,
        number=pr_number,
        title=pr.title,
        body=pr.body or "",
        base_ref=pr.base.ref,
        head_ref=pr.head.ref,
        diff_files=diff_files,
        raw_diff=raw_diff,
    )

    logger.info(
        "Fetched %d changed files (%d additions, %d deletions)",
        len(diff_files),
        sum(f.additions for f in diff_files),
        sum(f.deletions for f in diff_files),
    )

    gh.close()

    return {
        "pr_data": pr_data,
        "diff_files": diff_files,
    }
