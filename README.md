# PRISM

PRISM is an autonomous pull-request intelligence platform that leverages multi-agent architecture to perform comprehensive code reviews. By combining static analysis, semantic retrieval-augmented generation (RAG), and specialized agents, PRISM aims to detect logic flaws, security vulnerabilities, and style inconsistencies with high precision.

## Architecture

PRISM is built upon a parallel multi-agent graph architecture powered by LangGraph and FastAPI. It orchestrates the following components:

- **PR Fetcher**: Interacts with the GitHub API to fetch pull request metadata and code diffs.
- **Repo RAG Engine**: Clones the target repository, builds a semantic FAISS index of the codebase, and provides deep contextual awareness for the agents.
- **Specialized Review Agents**: Four independent agents execute in parallel:
  - **Bug Detector**: Analyzes code for logical errors and state management flaws.
  - **Security Scanner**: Identifies vulnerabilities, hardcoded secrets, and unsafe patterns.
  - **Logic Auditor**: Verifies architectural integrity and business logic correctness.
  - **Style Checker**: Enforces best practices and consistent coding conventions.
- **Synthesizer**: Aggregates, deduplicates, and assigns an overall risk rating based on the parallel findings.

## Benchmark Suite

PRISM includes an automated benchmarking suite to evaluate its performance against human reviewers. The benchmark framework pulls historical pull requests, executes the PRISM pipeline, and compares the AI-generated findings with merged human comments to compute Precision, Recall, and F1-Scores.

## Local Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Supabase instance

### Backend Installation

1. Navigate to the backend directory and set up a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a `.env` file based on `.env.example` and populate it with your credentials:
   - `GEMINI_API_KEY`
   - `GITHUB_TOKEN`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`

3. Start the FastAPI server:
   ```bash
   uvicorn api.main:app --port 8000
   ```

### Frontend Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   npm install
   ```

2. Start the Next.js development server:
   ```bash
   npm run dev
   ```

## Usage

Once both servers are running, navigate to `http://localhost:3000` to submit a pull request for review. The backend utilizes Server-Sent Events (SSE) to stream the agents' progress and findings to the UI in real-time.

To trigger the automated benchmark suite:
```bash
curl -X POST "http://127.0.0.1:8000/benchmark/run" -H "Content-Type: application/json" -d "{\"repo\": \"langchain-ai/langgraph\", \"max_prs\": 20}"
```
