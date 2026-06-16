"""Repo RAG agent — clones the repository and builds a FAISS index.

Performs a shallow clone of the target repository, splits source files
into chunks with ``RecursiveCharacterTextSplitter``, and builds a FAISS
vector store using Google Generative AI embeddings.  The resulting
retriever is stored in graph state for downstream agents to query
codebase context.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from git import Repo
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    GEMINI_API_KEY,
    GITHUB_TOKEN,
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
        # Skip hidden dirs (.git, .venv, etc.)
        if any(part.startswith(".") for part in file_path.parts):
            continue
        # Skip common non-source dirs
        if any(
            part in {"node_modules", "__pycache__", "venv", "dist", "build"}
            for part in file_path.parts
        ):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            relative = file_path.relative_to(repo_path).as_posix()
            documents.append(
                Document(
                    page_content=content,
                    metadata={"source": relative, "language": file_path.suffix},
                )
            )
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Skipping %s: %s", file_path, exc)

    return documents


def _clone_repo(owner: str, repo_name: str, branch: str) -> Path:
    """Shallow-clone the repository to a temporary directory."""
    TEMP_CLONE_DIR.mkdir(parents=True, exist_ok=True)
    clone_dir = Path(tempfile.mkdtemp(dir=TEMP_CLONE_DIR))
    clone_url = (
        f"https://{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git"
    )

    logger.info("Cloning %s/%s (branch: %s) → %s", owner, repo_name, branch, clone_dir)
    Repo.clone_from(
        clone_url,
        str(clone_dir),
        branch=branch,
        depth=1,
        single_branch=True,
    )
    return clone_dir


# ── Agent node ───────────────────────────────────────────────────────


async def run_repo_rag(state: dict[str, Any]) -> dict[str, Any]:
    """Clone the repo and build a FAISS vector store.

    Reads ``pr_data`` from state (needs ``owner``, ``repo``, ``base_ref``).
    Returns a partial state update with ``retriever`` and ``clone_dir``.
    """
    pr_data = state["pr_data"]
    owner: str = pr_data.owner
    repo_name: str = pr_data.repo
    branch: str = pr_data.base_ref

    clone_dir: Path | None = None

    try:
        clone_dir = _clone_repo(owner, repo_name, branch)

        # Collect and chunk source files
        raw_docs = _collect_source_files(clone_dir)
        logger.info("Collected %d source files from repo", len(raw_docs))

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\nclass ", "\ndef ", "\n\n", "\n", " "],
        )
        chunks = splitter.split_documents(raw_docs)
        logger.info("Split into %d chunks (size=%d, overlap=%d)", len(chunks), CHUNK_SIZE, CHUNK_OVERLAP)

        # Build FAISS index
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=GEMINI_API_KEY,
        )

        if not chunks:
            logger.warning("No source documents found — retriever will be empty")
            vectorstore = FAISS.from_texts(
                ["Empty repository — no source files found."],
                embeddings,
            )
        else:
            vectorstore = FAISS.from_documents(chunks, embeddings)

        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 8},
        )

        return {
            "retriever": retriever,
            "clone_dir": str(clone_dir),
        }

    finally:
        # Clean up cloned repo to save disk space
        if clone_dir and clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)
            logger.debug("Cleaned up clone directory: %s", clone_dir)
