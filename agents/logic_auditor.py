"""Logic Auditor agent — evaluates algorithmic correctness.

Analyses diffs for complexity regressions, incorrect boundary conditions,
broken invariants, missing edge cases, and algorithmic issues.  Uses RAG
to retrieve related code for cross-file analysis.
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
You are an algorithms and systems expert reviewing a pull request for
**algorithmic and logical correctness**.

Focus on:
- Time/space complexity regressions (e.g. O(n²) replacing O(n))
- Incorrect boundary conditions (off-by-one in loops, ranges, slices)
- Broken loop invariants or pre/post-conditions
- Missing edge cases (empty inputs, single elements, MAX_INT, unicode)
- Incorrect recursion (missing base case, stack overflow risk)
- Data structure misuse (wrong container type, ordering assumptions)
- Concurrency issues (TOCTOU, deadlocks, missing atomicity)
- Numerical precision / overflow / underflow errors
- Incorrect state machine transitions
- API contract violations (callee / caller assumptions mismatch)

For EACH finding, respond with a JSON object in the array:
{
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SUGGESTION",
  "file": "<relative file path>",
  "line_start": <int>,
  "line_end": <int>,
  "message": "<detailed description with the correct approach>"
}

If no issues are found, return an empty JSON array: []

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
        f"## Related Codebase Context\n\n{context_text}"
    )


def _parse_findings(raw: str, agent_source: str) -> list[dict[str, Any]]:
    """Parse LLM output into a list of finding dicts."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        findings = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Logic auditor returned invalid JSON: %s…", cleaned[:200])
        return []

    if not isinstance(findings, list):
        return []

    for finding in findings:
        finding["agent_source"] = agent_source

    return findings


async def run_logic_auditor(state: dict[str, Any]) -> dict[str, Any]:
    """Audit the PR diff for algorithmic correctness issues.

    Reads ``pr_data`` and ``retriever`` from state.
    Returns a partial state update with ``logic_findings``.
    """
    pr_data = state["pr_data"]
    retriever = state.get("retriever")

    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=MAX_CONTEXT_TOKENS,
    )

    # Retrieve context specifically around changed functions / classes
    context_docs: list[Document] = []
    if retriever:
        for diff_file in pr_data.diff_files:
            # Extract function/class names from added lines for targeted retrieval
            added_identifiers: list[str] = []
            for hunk in diff_file.hunks:
                for line in hunk.added_lines:
                    stripped = line.strip()
                    if stripped.startswith(("def ", "class ", "function ", "func ")):
                        name = stripped.split("(")[0].split()[-1]
                        added_identifiers.append(name)

            if added_identifiers:
                query = (
                    f"Functions and classes: {', '.join(added_identifiers)} "
                    f"in {diff_file.filename}"
                )
            else:
                query = f"Logic and algorithms in {diff_file.filename}"
            docs = await retriever.ainvoke(query)
            context_docs.extend(docs)

    # Deduplicate
    seen_sources: set[str] = set()
    unique_docs: list[Document] = []
    for doc in context_docs:
        source = doc.metadata.get("source", "")
        if source not in seen_sources:
            seen_sources.add(source)
            unique_docs.append(doc)

    prompt = _build_prompt(pr_data.raw_diff, unique_docs[:15])

    logger.info("Running logic audit on %d files", len(pr_data.diff_files))

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    findings = _parse_findings(response.content, "logic_auditor")
    logger.info("Logic auditor found %d issues", len(findings))

    return {"logic_findings": findings}
