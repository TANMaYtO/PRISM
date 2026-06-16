"""Security Scanner agent — identifies security vulnerabilities in PR diffs.

Uses the OWASP Top 10 as a structured prompt framework to detect injection
flaws, hardcoded secrets, insecure deserialization, path traversal, SSRF,
broken authentication, and more.
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
        logger.warning("Security scanner returned invalid JSON: %s…", cleaned[:200])
        return []

    if not isinstance(findings, list):
        return []

    for finding in findings:
        finding["agent_source"] = agent_source

    return findings


async def run_security_scanner(state: dict[str, Any]) -> dict[str, Any]:
    """Scan the PR diff for security vulnerabilities.

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

    context_docs: list[Document] = []
    if retriever:
        # Focus context retrieval on security-sensitive patterns
        security_queries = [
            "authentication authorization middleware",
            "database query SQL input validation",
            "file upload path handling",
            "API key secret token password",
            "CORS headers security configuration",
        ]
        for query in security_queries:
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

    logger.info("Running security scan on %d files", len(pr_data.diff_files))

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    findings = _parse_findings(response.content, "security_scanner")
    logger.info("Security scanner found %d issues", len(findings))

    return {"security_findings": findings}
