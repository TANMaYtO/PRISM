"""Style Checker agent — evaluates code style and conventions.

Checks naming conventions, docstring presence, import ordering, dead code,
type hint coverage, and magic numbers.  Language-aware via file extension.
Processes files one at a time with targeted structural + semantic context
from HybridCodeRetriever.
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from agents.llm_utils import (
    invoke_llm_with_retry,
    is_reviewable_file,
    parse_json_findings,
)
from config import GEMINI_API_KEY, MAX_CONTEXT_TOKENS, MODEL_NAME

logger = logging.getLogger(__name__)

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python (PEP 8, PEP 257)",
    ".js": "JavaScript (ESLint Recommended)",
    ".ts": "TypeScript (ESLint + @typescript-eslint)",
    ".jsx": "React JSX (Airbnb Style Guide)",
    ".tsx": "React TSX (Airbnb Style Guide)",
    ".go": "Go (Effective Go, gofmt)",
    ".rs": "Rust (Clippy, Rust API Guidelines)",
    ".java": "Java (Google Java Style Guide)",
    ".kt": "Kotlin (Kotlin Coding Conventions)",
    ".rb": "Ruby (Ruby Style Guide)",
    ".swift": "Swift (Swift API Design Guidelines)",
    ".cs": "C# (.NET Coding Conventions)",
    ".php": "PHP (PSR-12)",
    ".scala": "Scala (Scala Style Guide)",
}

_SYSTEM_PROMPT = """\
You are a code style and conventions expert reviewing a pull request.
Analyse the diff for **style, readability, and maintainability** issues.

Check for:
- **Naming**: Inconsistent naming conventions (snake_case vs camelCase mismatch)
- **Documentation**: Missing docstrings, outdated comments, unclear function signatures
- **Imports**: Unused imports, wildcard imports, incorrect ordering
- **Dead Code**: Unreachable code, commented-out code, unused variables/functions
- **Type Hints**: Missing type annotations on function signatures and return values
- **Magic Numbers**: Unnamed constants, unexplained numeric literals
- **Complexity**: Functions exceeding ~30 lines, deeply nested conditionals (>3 levels)
- **DRY Violations**: Copy-pasted code blocks that should be refactored
- **Formatting**: Inconsistent indentation, trailing whitespace, line length violations
- **Best Practices**: Language-specific idioms and anti-patterns

Language-specific conventions to apply per file extension:
{language_conventions}

For EACH finding, respond with a JSON object in the array:
{{
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SUGGESTION",
  "file": "<relative file path>",
  "line_start": <int>,
  "line_end": <int>,
  "message": "<description of the style issue and the recommended fix>"
}}

If no issues are found, return an empty JSON array: []

Respond ONLY with a valid JSON array — no markdown fences, no commentary.
"""


def _detect_languages(diff_files: list[Any]) -> str:
    """Build a summary of detected languages and their conventions."""
    extensions = {
        f.filename.rsplit(".", 1)[-1]
        for f in diff_files
        if "." in f.filename
    }
    conventions: list[str] = []
    for ext in sorted(extensions):
        dotted = f".{ext}"
        if dotted in _LANGUAGE_MAP:
            conventions.append(f"- `{dotted}`: {_LANGUAGE_MAP[dotted]}")
    return (
        "\n".join(conventions) if conventions else "- General best practices"
    )


def _detect_language_for_file(filename: str) -> str:
    """Get the language convention string for a single file."""
    suffix = PurePosixPath(filename).suffix
    return _LANGUAGE_MAP.get(suffix, "General best practices")


def _build_prompt(diff: str, context: str) -> str:
    """Compose the user prompt from diff and retriever context."""
    sections = f"## Pull Request Diff\n\n```diff\n{diff}\n```"
    if context:
        sections += (
            f"\n\n## Existing Codebase Style Reference\n\n{context}"
        )
    return sections


def _parse_findings(raw: Any, agent_source: str) -> list[dict[str, Any]]:
    """Parse LLM output into a list of finding dicts."""
    return parse_json_findings(raw, agent_source)


async def run_style_checker(state: dict[str, Any]) -> dict[str, Any]:
    """Check the PR diff for style violations, one file at a time.

    Reads ``pr_data`` and ``retriever`` from state.
    Returns a partial state update with ``style_findings``.
    """
    try:
        pr_data = state["pr_data"]
        retriever = state.get("retriever")

        # Build system prompt with all detected languages
        language_conventions = _detect_languages(pr_data.diff_files)
        system_prompt = _SYSTEM_PROMPT.replace(
            "{language_conventions}", language_conventions
        )

        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=GEMINI_API_KEY,
            temperature=0.1,
            max_output_tokens=MAX_CONTEXT_TOKENS,
        )

        all_findings: list[dict[str, Any]] = []
        combined_prompts: list[str] = []

        for diff_file in pr_data.diff_files:
            if not diff_file.patch or not is_reviewable_file(diff_file.filename):
                continue
            context_str = ""
            if retriever and hasattr(retriever, "get_context"):
                context_str = await retriever.get_context(diff_file)

            combined_prompts.append(
                f"### File: {diff_file.filename}\n\n```diff\n"
                f"{diff_file.patch}\n```\n\nContext:\n{context_str}"
            )

        if not combined_prompts:
            return {"style_findings": []}

        prompt = "## Pull Request Diffs\n\n" + "\n\n".join(combined_prompts)

        raw_output = await invoke_llm_with_retry(
            llm=llm,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        findings = _parse_findings(raw_output, "style_checker")
        all_findings.extend(findings)

        logger.info(
            f"Style Checker found {len(all_findings)} issues across "
            f"{len(pr_data.diff_files)} files"
        )
        return {"style_findings": all_findings}
    except Exception as exc:
        logger.exception(f"Error in style_checker agent: {exc}")
        return {"style_findings": []}
