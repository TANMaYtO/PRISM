"""Centralised configuration for PRISM.

Loads environment variables via python-dotenv and validates that all
required secrets are present at import time so failures surface early.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────────
_ENV_PATH: Path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _require_env(key: str) -> str:
    """Return the value of an environment variable or raise early."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {key}. "
            f"Set it in your .env file or export it directly."
        )
    return value


# ── Required secrets ─────────────────────────────────────────────────
GEMINI_API_KEY: str = _require_env("GEMINI_API_KEY")
GITHUB_TOKEN: str = _require_env("GITHUB_TOKEN")
SUPABASE_URL: str = _require_env("SUPABASE_URL")
SUPABASE_KEY: str = _require_env("SUPABASE_KEY")

# ── Model / RAG defaults (overridable via env) ──────────────────────
# LangChain / Google GenAI configuration
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── Misc constants ───────────────────────────────────────────────────
_PROJECT_ROOT: Path = Path(__file__).resolve().parent
TEMP_CLONE_DIR: Path = _PROJECT_ROOT / ".tmp_clones"
BENCHMARK_RESULTS_DIR: Path = _PROJECT_ROOT / "benchmark" / "results"
FAISS_CACHE_DIR: Path = _PROJECT_ROOT / ".faiss_cache"

# Disable HF Hub network pings for faster PR instantiations
os.environ["HF_HUB_OFFLINE"] = "1"
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
        ".java", ".kt", ".c", ".cpp", ".h", ".hpp", ".rb",
        ".swift", ".cs", ".php", ".scala", ".sh", ".yaml",
        ".yml", ".toml", ".json", ".md", ".sql",
    }
)
