"""PRISM agents — autonomous PR review sub-agents.

Each agent exposes an async function that conforms to the LangGraph
node protocol: accept a ``ReviewState`` TypedDict and return a partial
state update.
"""

from agents.bug_detector import run_bug_detector
from agents.logic_auditor import run_logic_auditor
from agents.pr_fetcher import run_pr_fetcher
from agents.repo_rag import run_repo_rag
from agents.security_scanner import run_security_scanner
from agents.style_checker import run_style_checker
from agents.synthesizer import run_synthesizer

__all__: list[str] = [
    "run_pr_fetcher",
    "run_repo_rag",
    "run_bug_detector",
    "run_security_scanner",
    "run_logic_auditor",
    "run_style_checker",
    "run_synthesizer",
]
