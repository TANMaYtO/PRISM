# ── PRISM — Autonomous PR Reviewer ────────────────────────────────
FROM python:3.11-slim AS base

# git is required by GitPython for repo cloning
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ───────────────────────────────────────────
COPY . .

# ── Runtime ───────────────────────────────────────────────────────
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
