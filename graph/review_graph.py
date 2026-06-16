"""LangGraph StateGraph definition for the PRISM review pipeline.

Defines ``ReviewState``, builds the multi-agent graph with parallel
fan-out to the four review agents, and exposes the compiled runnable.

Flow:
  fetch_pr → build_rag → [bug_detector, security_scanner,
                           logic_auditor, style_checker]  → synthesizer → END
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated, Any, AsyncGenerator, TypedDict

from langgraph.graph import END, StateGraph

from agents.bug_detector import run_bug_detector
from agents.logic_auditor import run_logic_auditor
from agents.pr_fetcher import run_pr_fetcher
from agents.repo_rag import run_repo_rag
from agents.security_scanner import run_security_scanner
from agents.style_checker import run_style_checker
from agents.synthesizer import run_synthesizer

logger = logging.getLogger(__name__)


# ── State schema ─────────────────────────────────────────────────────
# Using TypedDict with Annotated reducers for list-merge semantics.


class ReviewState(TypedDict, total=False):
    """Shared state flowing through the PRISM review graph.

    Keys populated at each stage:
    - fetch_pr     → repo_owner, repo_name, pr_number, pr_data, diff_files
    - build_rag    → retriever, clone_dir
    - bug_detector → bug_findings
    - security_scanner → security_findings
    - logic_auditor    → logic_findings
    - style_checker    → style_findings
    - synthesizer      → final_review
    """

    repo_owner: str
    repo_name: str
    pr_number: int
    pr_data: Any
    diff_files: list
    retriever: Any
    clone_dir: str
    code_graph: Any
    bug_findings: Annotated[list, operator.add]
    security_findings: Annotated[list, operator.add]
    logic_findings: Annotated[list, operator.add]
    style_findings: Annotated[list, operator.add]
    final_review: Any


# ── Graph builder ────────────────────────────────────────────────────


def build_review_graph() -> Any:
    """Construct and compile the PRISM multi-agent review graph.

    Returns a compiled LangGraph ``CompiledGraph`` that can be invoked
    with an initial state containing ``repo_owner``, ``repo_name``, and
    ``pr_number``.
    """
    graph = StateGraph(ReviewState)

    # ── Register nodes ───────────────────────────────────────────
    graph.add_node("fetch_pr", run_pr_fetcher)
    graph.add_node("build_rag", run_repo_rag)
    graph.add_node("bug_detector", run_bug_detector)
    graph.add_node("security_scanner", run_security_scanner)
    graph.add_node("logic_auditor", run_logic_auditor)
    graph.add_node("style_checker", run_style_checker)
    graph.add_node("synthesizer", run_synthesizer)

    # ── Sequential: fetch → RAG ──────────────────────────────────
    graph.set_entry_point("fetch_pr")
    graph.add_edge("fetch_pr", "build_rag")

    # ── Parallel fan-out: RAG → 4 review agents ──────────────────
    graph.add_edge("build_rag", "bug_detector")
    graph.add_edge("build_rag", "security_scanner")
    graph.add_edge("build_rag", "logic_auditor")
    graph.add_edge("build_rag", "style_checker")

    # ── Fan-in: 4 review agents → synthesizer ────────────────────
    graph.add_edge(
        ["bug_detector", "security_scanner", "logic_auditor", "style_checker"],
        "synthesizer",
    )

    # ── Terminal ─────────────────────────────────────────────────
    graph.add_edge("synthesizer", END)

    compiled = graph.compile()
    logger.info("PRISM review graph compiled successfully")
    return compiled


# ── Convenience runner ───────────────────────────────────────────────


async def run_review(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
) -> dict[str, Any]:
    """Execute the full review pipeline end-to-end.

    Returns the final graph state containing ``final_review``.
    """
    graph = build_review_graph()
    initial_state: dict[str, Any] = {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "bug_findings": [],
        "security_findings": [],
        "logic_findings": [],
        "style_findings": [],
    }

    logger.info(
        "Starting PRISM review for %s/%s#%d",
        repo_owner,
        repo_name,
        pr_number,
    )

    result = await graph.ainvoke(initial_state)
    return result


async def run_review_stream(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
) -> AsyncGenerator[dict[str, Any], None]:
    """Execute the review pipeline and stream events in real-time."""
    graph = build_review_graph()
    initial_state: dict[str, Any] = {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "bug_findings": [],
        "security_findings": [],
        "logic_findings": [],
        "style_findings": [],
    }

    logger.info(
        "Starting PRISM review stream for %s/%s#%d", repo_owner, repo_name, pr_number
    )

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                if name == "fetch_pr":
                    yield {
                        "event": "status",
                        "data": f"Fetching PR #{pr_number} from {repo_owner}/{repo_name}...",
                    }
                elif name == "build_rag":
                    yield {
                        "event": "status",
                        "data": "Building code knowledge graph and FAISS index...",
                    }
                elif name in (
                    "bug_detector",
                    "security_scanner",
                    "logic_auditor",
                    "style_checker",
                ):
                    # display name maps e.g. bug_detector -> Bug Detector
                    display_name = name.replace("_", " ").title()
                    yield {"event": "status", "data": f"Running {display_name}..."}

            elif kind == "on_chain_end":
                if name in (
                    "bug_detector",
                    "security_scanner",
                    "logic_auditor",
                    "style_checker",
                ):
                    # Agent finished, extract findings
                    output_state = event.get("data", {}).get("output")
                    if output_state:
                        findings_key = f"{name.split('_')[0]}_findings"
                        findings = output_state.get(findings_key, [])
                        for f in findings:
                            yield {"event": "finding", "data": f}

                        yield {
                            "event": "agent_done",
                            "data": {
                                "agent": name,
                                "count": len(findings),
                            },
                        }

                elif name == "synthesizer":
                    output_state = event.get("data", {}).get("output")
                    if output_state and "final_review" in output_state:
                        final_review = output_state["final_review"]
                        yield {
                            "event": "complete",
                            "data": final_review.model_dump_json(),
                        }

    except Exception as exc:
        logger.exception("Error in review stream")
        yield {"event": "error", "data": str(exc)}
