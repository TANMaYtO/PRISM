"""Hugging Face Spaces entrypoint for PRISM.

Launches the PRISM FastAPI backend on port 7860 for Gradio SDK spaces.
"""

from __future__ import annotations

import os
import uvicorn
from api.main import app

try:
    import gradio as gr

    demo = gr.Interface(
        fn=lambda: "PRISM Autonomous PR Reviewer API is online. Access REST endpoints at /review and /benchmark.",
        inputs=[],
        outputs="text",
        title="PRISM — Autonomous PR Reviewer Backend",
        description="FastAPI + LangGraph multi-agent autonomous pull request reviewer.",
    )
    app = gr.mount_gradio_app(app, demo, path="/status")
except Exception:
    pass


def run_server() -> None:
    """Start the Uvicorn server on the configured port."""
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
