"""Bug Detector agent — analyses PR diffs for logic bugs.

Prompts Gemini to identify bugs including off-by-one errors, null
dereferences, race conditions, resource leaks, unhandled exceptions,
and incorrect control flow.  Processes files one at a time with
targeted structural + semantic context from HybridCodeRetriever.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from config import GEMINI_API_KEY, MAX_CONTEXT_TOKENS, MODEL_NAME

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior software engineer performing a meticulous code review.
Analyse the provided pull-request diff and surrounding codebase context
for **logic bugs**.

Focus on:
- Off-by-one and boundary errors
- Null / None dereference risks
- Race conditions and thread-safety issues
- Resource leaks (files, connections, locks)
- Unhandled exceptions or error paths
- Incorrect boolean logic or control flow
- Type mismatches or implicit conversions
- Incorrect use of APIs or standard library

For EACH finding, respond with a JSON object in the array:
{
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SUGGESTION",
  "file": "<relative file path>",
  "line_start": <int>,
  "line_end": <int>,
  "message": "<clear description of the bug and suggested fix>"
}

If no bugs are found, return an empty JSON array: []

Respond ONLY with a valid JSON array — no markdown fences, no commentary.
"""


def _build_prompt(diff: str, context: str) -> str:
    """Compose the user prompt from diff and retriever context."""
    sections = f"## Pull Request Diff\n\n```diff\n{diff}\n```"
    if context:
        sections += f"\n\n## Codebase Context\n\n{context}"
    return sections


def _parse_findings(raw: Any, agent_source: str) -> list[dict[str, Any]]:
    """Parse LLM output into a list of finding dicts."""
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and "text" in raw[0]:
            raw = raw[0]["text"]
        else:
            raw = str(raw)
    
    if not isinstance(raw, str):
        raw = str(raw)

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        findings = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "Bug detector returned invalid JSON: %s…", cleaned[:200]
        )
        return []

    if not isinstance(findings, list):
        return []

    for finding in findings:
        finding["agent_source"] = agent_source

    return findings


async def run_bug_detector(state: dict[str, Any]) -> dict[str, Any]:
    """Analyse the PR diff for logic bugs, one file at a time.

    Reads ``pr_data`` and ``retriever`` from state.
    Returns a partial state update with ``bug_findings``.
    """
    pr_data = state["pr_data"]
    retriever = state.get("retriever")

    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=MAX_CONTEXT_TOKENS,
    )

    all_findings: list[dict[str, Any]] = []

    combined_prompts = []
    for diff_file in pr_data.diff_files:
        if not diff_file.patch:
            continue
        context_str = ""
        if retriever and hasattr(retriever, "get_context"):
            context_str = await retriever.get_context(diff_file)
        
        combined_prompts.append(f"""### File: {diff_file.filename}\n\n```diff\n{diff_file.patch}\n```\n\nContext:\n{context_str}""")

    if not combined_prompts:
        return {"bug_findings": []}

    prompt = "## Pull Request Diffs\n\n" + "\n\n".join(combined_prompts)

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    findings = _parse_findings(response.content, "bug_detector")
    all_findings.extend(findings)

    logger.info(
        "Bug Detector found %d issues across %d files",
        len(all_findings),
        len(pr_data.diff_files),
    )
    return {"bug_findings": all_findings}
