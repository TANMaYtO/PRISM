"""Hugging Face Spaces entrypoint for PRISM.

Launches the PRISM FastAPI backend on port 7860 for Gradio SDK spaces.
"""

from __future__ import annotations

import os
import uvicorn
from api.main import app


def run_server() -> None:
    """Start the Uvicorn server on the configured port."""
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
