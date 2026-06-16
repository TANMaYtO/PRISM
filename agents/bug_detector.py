"""Bug Detector agent — analyses PR diffs for logic bugs.

Prompts Gemini to identify bugs including off-by-one errors, null
dereferences, race conditions, resource leaks, unhandled exceptions,
and incorrect control flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.documents import Document
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


def _build_prompt(diff: str, context_docs: list[Document]) -> str:
    """Compose the user prompt from diff and RAG context."""
    context_text = "\n\n".join(
        f"--- {doc.metadata.get('source', 'unknown')} ---\n{doc.page_content}"
        for doc in context_docs
    )
    return (
        f"## Pull Request Diff\n\n```diff\n{diff}\n```\n\n"
        f"## Codebase Context\n\n{context_text}"
    )


def _parse_findings(raw: str, agent_source: str) -> list[dict[str, Any]]:
    """Parse LLM output into a list of finding dicts."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        findings = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Bug detector returned invalid JSON: %s…", cleaned[:200])
        return []

    if not isinstance(findings, list):
        return []

    for finding in findings:
        finding["agent_source"] = agent_source

    return findings


async def run_bug_detector(state: dict[str, Any]) -> dict[str, Any]:
    """Analyse the PR diff for logic bugs.

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

    # Retrieve relevant codebase context
    context_docs: list[Document] = []
    if retriever:
        for diff_file in pr_data.diff_files:
            query = f"Code related to {diff_file.filename}"
            docs = await retriever.ainvoke(query)
            context_docs.extend(docs)

    # Deduplicate context docs by source
    seen_sources: set[str] = set()
    unique_docs: list[Document] = []
    for doc in context_docs:
        source = doc.metadata.get("source", "")
        if source not in seen_sources:
            seen_sources.add(source)
            unique_docs.append(doc)

    prompt = _build_prompt(pr_data.raw_diff, unique_docs[:15])

    logger.info("Running bug detection on %d files", len(pr_data.diff_files))

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    findings = _parse_findings(response.content, "bug_detector")
    logger.info("Bug detector found %d issues", len(findings))

    return {"bug_findings": findings}
