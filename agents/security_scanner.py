"""Security Scanner agent — identifies security vulnerabilities in PR diffs.

Uses the OWASP Top 10 as a structured prompt framework to detect injection
flaws, hardcoded secrets, insecure deserialization, path traversal, SSRF,
broken authentication, and more.  Processes files one at a time with
targeted structural + semantic context from HybridCodeRetriever.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from agents.llm_utils import (
    invoke_llm_with_retry,
    is_reviewable_file,
    parse_json_findings,
)
from config import GEMINI_API_KEY, MAX_CONTEXT_TOKENS, MODEL_NAME

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior application security engineer conducting a security
review of a pull request.  Analyse the diff and codebase context for
**security vulnerabilities** using the OWASP Top 10 (2021) as your
structured framework:

1. **A01 — Broken Access Control**: Missing auth checks, IDOR, privilege escalation
2. **A02 — Cryptographic Failures**: Weak algorithms, hardcoded secrets
3. **A03 — Injection**: SQL injection, XSS, command injection, template injection
4. **A04 — Insecure Design**: Missing rate limiting, insecure defaults
5. **A05 — Security Misconfiguration**: Debug endpoints, overly permissive CORS
6. **A06 — Vulnerable Components**: Known CVEs in dependencies, outdated packages
7. **A07 — Auth Failures**: Credential stuffing, weak passwords, missing MFA
8. **A08 — Data Integrity Failures**: Insecure deserialization, unsigned updates
9. **A09 — Logging Failures**: Sensitive data in logs, missing audit trails
10. **A10 — SSRF**: Server-side request forgery, unvalidated redirects

Also check for:
- Hardcoded API keys, tokens, passwords, or connection strings
- Path traversal vulnerabilities
- Insecure file uploads
- Missing input validation / sanitisation
- Use of eval(), exec(), or equivalent in any language
- Timing attacks on comparison operations

For EACH finding, respond with a JSON object in the array:
{
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SUGGESTION",
  "file": "<relative file path>",
  "line_start": <int>,
  "line_end": <int>,
  "message": "<description including OWASP category and remediation advice>"
}

If no vulnerabilities are found, return an empty JSON array: []

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
    return parse_json_findings(raw, agent_source)


async def run_security_scanner(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Scan the PR diff for security vulnerabilities, one file at a time.

    Reads ``pr_data`` and ``retriever`` from state.
    Returns a partial state update with ``security_findings``.
    """
    try:
        pr_data = state["pr_data"]
        retriever = state.get("retriever")

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
            return {"security_findings": []}

        prompt = "## Pull Request Diffs\n\n" + "\n\n".join(combined_prompts)

        raw_output = await invoke_llm_with_retry(
            llm=llm,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        findings = _parse_findings(raw_output, "security_scanner")
        all_findings.extend(findings)

        logger.info(
            f"Security Scanner found {len(all_findings)} issues across "
            f"{len(pr_data.diff_files)} files"
        )
        return {"security_findings": all_findings}
    except Exception as exc:
        logger.exception(f"Error in security_scanner agent: {exc}")
        return {"security_findings": []}
