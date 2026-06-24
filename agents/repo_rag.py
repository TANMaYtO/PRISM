"""Repo RAG agent -- hybrid retrieval with CodeGraph + FAISS.

Clones the repository, builds a structural code graph via tree-sitter
and a FAISS semantic index via HuggingFace local embeddings.
The ``HybridCodeRetriever`` exposes a per-file ``get_context`` method
that combines call-graph analysis with similarity search for maximum
review context quality.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from git import Repo
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from agents.code_graph import CodeGraph
from agents.pr_fetcher import FileDiff
from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL_NAME,
    FAISS_CACHE_DIR,
    GITHUB_TOKEN,
    MAX_CONTEXT_TOKENS,
    SUPPORTED_EXTENSIONS,
    TEMP_CLONE_DIR,
)

logger = logging.getLogger(__name__)


# ── File ingestion ───────────────────────────────────────────────────


def _collect_source_files(repo_path: Path) -> list[Document]:
    """Walk the repo tree and load supported source files as Documents."""
    documents: list[Document] = []

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        # Check path relative to repo root so we don't accidentally skip the clone dir itself
        try:
            relative = file_path.relative_to(repo_path)
        except ValueError:
            continue

        # Skip hidden dirs (.git, .venv, etc.)
        if any(part.startswith(".") for part in relative.parts):
            continue
        # Skip common non-source dirs
        if any(
            part in {"node_modules", "__pycache__", "venv", "dist", "build"}
            for part in relative.parts
        ):
            continue

        try:
            content = file_path.read_text(
                encoding="utf-8", errors="ignore"
            )
            if not content.strip():
                continue
            relative = file_path.relative_to(repo_path).as_posix()
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "source": relative,
                        "language": file_path.suffix,
                    },
                )
            )
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Skipping %s: %s", file_path, exc)

    return documents


def _clone_repo(owner: str, repo_name: str, branch: str) -> Path:
    """Shallow-clone the repository to a cached directory."""
    TEMP_CLONE_DIR.mkdir(parents=True, exist_ok=True)
    clone_dir = TEMP_CLONE_DIR / f"{owner}_{repo_name}_{branch}"
    
    if clone_dir.exists() and (clone_dir / ".git").exists():
        logger.info("Using cached repo clone at %s", clone_dir)
        return clone_dir

    clone_url = (
        f"https://{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git"
    )

    logger.info(
        "Cloning %s/%s (branch: %s) → %s",
        owner,
        repo_name,
        branch,
        clone_dir,
    )
    Repo.clone_from(
        clone_url,
        str(clone_dir),
        branch=branch,
        depth=1,
        single_branch=True,
    )
    return clone_dir


# ── Hybrid retriever ─────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text using a simple heuristic."""
    return len(text) // 4


def _get_cache_dir(owner: str, repo_name: str, branch: str) -> Path:
    """Return the absolute cache directory for a given repo + branch."""
    return FAISS_CACHE_DIR / f"{owner}_{repo_name}_{branch}"


class HybridCodeRetriever:
    """Combined structural (CodeGraph) + semantic (FAISS) retriever.

    Provides per-file context retrieval that merges call-graph analysis
    with embedding-based similarity search for rich review context.
    """

    def __init__(
        self,
        repo_path: Path,
        clone_dir: Path,
        owner: str,
        repo_name: str,
        branch: str,
    ) -> None:
        """Initialize with repo path for graph and FAISS building."""
        self.repo_path = repo_path
        self.clone_dir = clone_dir
        self.owner = owner
        self.repo_name = repo_name
        self.branch = branch
        self.code_graph: CodeGraph = CodeGraph()
        self._vectorstore: FAISS | None = None
        self._chunk_sources: set[str] = set()

    async def build(self) -> None:
        """Build both CodeGraph and FAISS index.

        Step 1: Build CodeGraph (sync, fast, no API calls)
        Step 2: Load or build FAISS index using local HuggingFace embeddings
        """
        # Step 1: Structural graph
        t0 = time.perf_counter()
        self.code_graph.build(self.repo_path)
        t1 = time.perf_counter()
        logger.info("CodeGraph built in %.2fs", t1 - t0)

        # Step 2: Semantic FAISS index (cached locally)
        t2 = time.perf_counter()

        logger.info("Loading local HuggingFace embeddings: %s", EMBEDDING_MODEL_NAME)
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"local_files_only": True},
        )

        cache_dir = _get_cache_dir(self.owner, self.repo_name, self.branch)

        if cache_dir.exists() and (cache_dir / "index.faiss").exists():
            logger.info("Loading cached FAISS index from %s", cache_dir)
            self._vectorstore = FAISS.load_local(
                str(cache_dir),
                embeddings,
                allow_dangerous_deserialization=True,
            )
            self._chunk_sources = {
                doc.metadata.get("source", "")
                for doc in self._vectorstore.docstore._dict.values()
            }
            logger.info(
                "Loaded %d cached vectors",
                len(self._vectorstore.docstore._dict),
            )
        else:
            raw_docs = _collect_source_files(self.repo_path)
            logger.info(
                "Collected %d source files from repo", len(raw_docs)
            )

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
                separators=["\nclass ", "\ndef ", "\n\n", "\n", " "],
            )
            chunks = splitter.split_documents(raw_docs)
            logger.info(
                "Split into %d chunks (size=%d, overlap=%d)",
                len(chunks),
                CHUNK_SIZE,
                CHUNK_OVERLAP,
            )

            self._chunk_sources = {
                doc.metadata.get("source", "")
                for doc in chunks
            }

            if not chunks:
                logger.warning(
                    "No source documents found -- retriever will be empty"
                )
                self._vectorstore = FAISS.from_texts(
                    ["Empty repository -- no source files found."],
                    embeddings,
                )
            else:
                logger.info("Building FAISS index with %d chunks locally (this may take a few minutes)...", len(chunks))
                self._vectorstore = FAISS.from_documents(
                    chunks, embeddings
                )

            # Save the newly built index
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._vectorstore.save_local(str(cache_dir))
            logger.info("Saved FAISS index to %s", cache_dir)

        t3 = time.perf_counter()
        logger.info("FAISS index loaded/built in %.2fs", t3 - t2)

    async def get_context(self, changed_file: FileDiff) -> str:
        """Get combined structural + semantic context for one file.

        Returns a labelled string combining call-graph analysis and
        similarity search results, respecting MAX_CONTEXT_TOKENS.
        Structural context gets priority if budget is tight.
        """
        structural_text = self._get_structural_context(changed_file)
        semantic_text = await self._get_semantic_context(
            changed_file, structural_text
        )

        return self._merge_contexts(structural_text, semantic_text)

    def _get_structural_context(
        self, changed_file: FileDiff
    ) -> str:
        """Extract structural context via CodeGraph."""
        if not changed_file.patch:
            return ""

        changed_symbols = self.code_graph.extract_changed_symbols(
            changed_file.patch
        )

        if not changed_symbols and not changed_file.filename:
            return ""

        context = self.code_graph.get_structural_context(
            changed_files=[changed_file.filename],
            changed_symbols=list(changed_symbols),
        )

        return context if context else ""

    async def _get_semantic_context(
        self,
        changed_file: FileDiff,
        structural_text: str,
    ) -> str:
        """Retrieve semantic context via FAISS similarity search."""
        if not self._vectorstore:
            return ""

        # Build query from filename + changed symbols
        changed_symbols = self.code_graph.extract_changed_symbols(
            changed_file.patch or ""
        )
        symbol_str = " ".join(changed_symbols) if changed_symbols else ""
        query = f"{changed_file.filename} {symbol_str}".strip()

        if not query:
            return ""

        retriever = self._vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 6},
        )
        
        # Local embeddings so no rate limits or backoff needed
        try:
            docs: list[Document] = await retriever.ainvoke(query)
        except Exception as exc:
            logger.error("Error in local semantic retrieval: %s", str(exc))
            return ""

        # Filter out chunks already covered by structural context
        structural_files = self._extract_filepaths(structural_text)
        filtered_docs: list[Document] = []
        for doc in docs:
            source = doc.metadata.get("source", "")
            if source not in structural_files:
                filtered_docs.append(doc)

        if not filtered_docs:
            return ""

        parts: list[str] = []
        for doc in filtered_docs:
            source = doc.metadata.get("source", "unknown")
            parts.append(
                f"--- {source} ---\n{doc.page_content}"
            )

        return "\n\n".join(parts)

    def _extract_filepaths(self, text: str) -> set[str]:
        """Extract file paths from structural context text."""
        paths: set[str] = set()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("--- ") and stripped.endswith(" ---"):
                path = stripped[4:-4].strip()
                if path:
                    paths.add(path)
            elif stripped.startswith("File: "):
                path = stripped[6:].strip()
                if path:
                    paths.add(path)
        return paths

    def _merge_contexts(
        self, structural: str, semantic: str
    ) -> str:
        """Merge structural and semantic contexts within token budget.

        Structural context gets priority if the budget is tight.
        """
        if not structural and not semantic:
            return ""

        budget = MAX_CONTEXT_TOKENS
        result_parts: list[str] = []

        # Structural context gets priority
        if structural:
            structural_tokens = _estimate_tokens(structural)
            if structural_tokens <= budget:
                result_parts.append(
                    "[STRUCTURAL CONTEXT -- call graph analysis]\n"
                    f"{structural}"
                )
                budget -= structural_tokens
            else:
                # Truncate structural to fit budget
                char_limit = budget * 4
                truncated = structural[:char_limit]
                result_parts.append(
                    "[STRUCTURAL CONTEXT -- call graph analysis]\n"
                    f"{truncated}"
                )
                budget = 0

        # Fill remaining budget with semantic context
        if semantic and budget > 0:
            semantic_tokens = _estimate_tokens(semantic)
            if semantic_tokens <= budget:
                result_parts.append(
                    "[SEMANTIC CONTEXT -- similarity search]\n"
                    f"{semantic}"
                )
            else:
                char_limit = budget * 4
                truncated = semantic[:char_limit]
                result_parts.append(
                    "[SEMANTIC CONTEXT -- similarity search]\n"
                    f"{truncated}"
                )

        return "\n\n".join(result_parts)


# ── Agent node ───────────────────────────────────────────────────────


async def run_repo_rag(state: dict[str, Any]) -> dict[str, Any]:
    """Clone the repo and build a HybridCodeRetriever.

    Reads ``pr_data`` from state (needs ``owner``, ``repo``, ``base_ref``).
    Returns a partial state update with ``retriever``, ``code_graph``,
    and ``clone_dir``.
    """
    pr_data = state["pr_data"]
    owner: str = pr_data.owner
    repo_name: str = pr_data.repo
    branch: str = pr_data.base_ref

    clone_dir = _clone_repo(owner, repo_name, branch)

    hybrid = HybridCodeRetriever(
        repo_path=clone_dir,
        clone_dir=clone_dir,
        owner=owner,
        repo_name=repo_name,
        branch=branch,
    )
    await hybrid.build()

    return {
        "retriever": hybrid,
        "code_graph": hybrid.code_graph,
        "clone_dir": str(clone_dir),
    }
