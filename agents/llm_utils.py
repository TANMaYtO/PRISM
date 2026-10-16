"""Shared utilities for LLM invocation, retry handling, and finding parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

# Files that should not be reviewed by LLM agents (lockfiles, generated, minified)
_SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".lock",
        ".min.js",
        ".min.css",
        ".map",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".zip",
        ".tar",
        ".gz",
        ".pdf",
    }
)

_SKIP_FILENAMES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Cargo.lock",
        "Pipfile.lock",
        "composer.lock",
        "go.sum",
    }
)


def is_reviewable_file(filename: str) -> bool:
    """Return True if the file should be reviewed by analysis agents."""
    lower_name = filename.lower()
    base_name = lower_name.split("/")[-1].split("\\")[-1]

    if base_name in _SKIP_FILENAMES:
        return False

    for ext in _SKIP_EXTENSIONS:
        if lower_name.endswith(ext):
            return False

    return True


async def invoke_llm_with_retry(
    llm: ChatGoogleGenerativeAI,
    messages: list[dict[str, str]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
) -> str:
    """Invoke an LLM with exponential backoff on transient errors."""
    delay = initial_delay
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = await llm.ainvoke(messages)
            raw = response.content

            if isinstance(raw, list):
                if raw and isinstance(raw[0], dict) and "text" in raw[0]:
                    return str(raw[0]["text"])
                return str(raw)

            return str(raw).strip()
        except Exception as exc:
            last_exception = exc
            logger.warning(
                f"LLM call attempt {attempt}/{max_retries} failed: {exc}. "
                f"Retrying in {delay:.1f}s..."
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 2.0

    logger.error(f"All {max_retries} LLM attempts failed: {last_exception}")
    return ""


def parse_json_findings(raw: Any, agent_source: str) -> list[dict[str, Any]]:
    """Robustly parse LLM output into a list of finding dictionaries."""
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and "text" in raw[0]:
            raw = raw[0]["text"]
        else:
            raw = str(raw)

    if not isinstance(raw, str):
        raw = str(raw)

    cleaned = raw.strip()
    findings: Any = None

    # Step 1: Direct JSON parse
    try:
        findings = json.loads(cleaned)
    except Exception:
        # Step 2: Markdown fence extraction
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts[1::2]:
                candidate = part.strip()
                if candidate.startswith(("json", "JSON")):
                    candidate = candidate[4:].strip()
                try:
                    findings = json.loads(candidate)
                    if isinstance(findings, list):
                        break
                except Exception:
                    continue

        # Step 3: Bracket search fallback
        if not isinstance(findings, list):
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    findings = json.loads(cleaned[start : end + 1])
                except Exception:
                    findings = []

    if not isinstance(findings, list):
        return []

    validated_findings: list[dict[str, Any]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue

        severity = str(item.get("severity", "LOW")).upper()
        if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "SUGGESTION"}:
            severity = "LOW"

        try:
            line_start = max(1, int(item.get("line_start", 1)))
        except (ValueError, TypeError):
            line_start = 1

        try:
            line_end = max(line_start, int(item.get("line_end", line_start)))
        except (ValueError, TypeError):
            line_end = line_start

        validated_findings.append(
            {
                "severity": severity,
                "file": str(item.get("file", "unknown")),
                "line_start": line_start,
                "line_end": line_end,
                "message": str(item.get("message", "No description provided.")),
                "agent_source": agent_source,
            }
        )

    return validated_findings
