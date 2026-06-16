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

from config import GEMINI_API_KEY, MAX_CONTEXT_TOKENS, MODEL_NAME

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior application security engineer conducting a security
review of a pull request.  Analyse the diff and codebase context for
**security vulnerabilities** using the OWASP Top 10 (2021) as your
structured framework:

1. **A01 — Broken Access Control**: Missing auth checks, IDOR, privilege escalation
2. **A02 — Cryptographic Failures**: Weak algorithms, hardcoded secrets, insecure key management
3. **A03 — Injection**: SQL injection, XSS, command injection, LDAP injection, template injection
4. **A04 — Insecure Design**: Missing rate limiting, insecure defaults, business logic flaws
5. **A05 — Security Misconfiguration**: Debug endpoints, overly permissive CORS, verbose errors
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
            "Security scanner returned invalid JSON: %s…",
            cleaned[:200],
        )
        return []

    if not isinstance(findings, list):
        return []

    for finding in findings:
        finding["agent_source"] = agent_source

    return findings


async def run_security_scanner(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Scan the PR diff for security vulnerabilities, one file at a time.

    Reads ``pr_data`` and ``retriever`` from state.
    Returns a partial state update with ``security_findings``.
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
        return {"security_findings": []}

    prompt = "## Pull Request Diffs\n\n" + "\n\n".join(combined_prompts)

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    findings = _parse_findings(response.content, "security_scanner")
    all_findings.extend(findings)

    logger.info(
        "Security Scanner found %d issues across %d files",
        len(all_findings),
        len(pr_data.diff_files),
    )
    return {"security_findings": all_findings}
