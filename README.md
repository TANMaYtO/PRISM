# PRISM: Autonomous Pull-Request Intelligence Platform

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()

PRISM is a state-of-the-art, multi-agent AI system designed to conduct deep, comprehensive code reviews. By combining semantic Retrieval-Augmented Generation (RAG) with parallel specialized agents, PRISM moves beyond simple syntax checking to identify profound logic flaws, security vulnerabilities, and architectural inconsistencies in pull requests.

## Table of Contents
- [Architecture](#architecture)
- [Multi-Agent Graph Execution](#multi-agent-graph-execution)
- [Benchmark Framework](#benchmark-framework)
- [Directory Structure](#directory-structure)
- [Installation and Setup](#installation-and-setup)
- [Configuration](#configuration)
- [Usage](#usage)

---

## Architecture

PRISM relies on **LangGraph** to coordinate parallel execution and **FastAPI** to serve Server-Sent Events (SSE) for real-time dashboard updates. 

When a review is requested, PRISM performs the following:
1. **Extraction**: Pulls down the raw code diff and metadata via the GitHub API.
2. **Contextualization (Repo RAG)**: Clones the target repository, parses the entire Abstract Syntax Tree (AST), and builds a FAISS-backed semantic index to provide historical and architectural context.
3. **Analysis**: Four distinct LLM agents evaluate the codebase simultaneously.
4. **Synthesis**: The findings are deduplicated, aggregated, and assigned an overall risk severity.

### Multi-Agent Graph Execution

The core of PRISM is its directed acyclic graph (DAG) execution model, which guarantees high concurrency without deadlocks.

```mermaid
graph TD
    A[Trigger Review] --> B[PR Fetcher]
    B --> C[Repo RAG Engine]
    
    C --> D[Bug Detector]
    C --> E[Security Scanner]
    C --> F[Logic Auditor]
    C --> G[Style Checker]
    
    D --> H[Synthesizer]
    E --> H
    F --> H
    G --> H
    
    H --> I[Supabase Persistence]
    I --> J[End Review]

    classDef fetch fill:#2a3b4c,stroke:#5a7b9c,color:#fff
    classDef rag fill:#4c3b2a,stroke:#9c7b5a,color:#fff
    classDef agent fill:#2c4c3b,stroke:#5c9c7b,color:#fff
    classDef synth fill:#4c2a3b,stroke:#9c5a7b,color:#fff

    class B fetch
    class C rag
    class D,E,F,G agent
    class H synth
```

---

## Benchmark Framework

To ensure the highest standard of review quality, PRISM ships with an automated benchmarking suite. This pipeline allows organizations to evaluate PRISM against historical human code reviews.

```mermaid
sequenceDiagram
    participant User
    participant Controller as Benchmark Evaluator
    participant GitHub as GitHub API
    participant Graph as Review Graph
    participant DB as Supabase DB

    User->>Controller: POST /benchmark/run {max_prs: 20}
    Controller->>GitHub: Fetch historical PRs with comments
    GitHub-->>Controller: Return PR Dataset
    loop For Each PR
        Controller->>Graph: Trigger Graph Execution
        Graph-->>Controller: Return Synthesized Findings
        Controller->>Controller: Compare AI vs Human (Precision/Recall/F1)
    end
    Controller->>DB: Store final metrics
    Controller-->>User: Benchmark Completed
```

---

## Directory Structure

```text
PRISM/
├── agents/             # Logic for RAG, specialized reviewers, and synthesizer
├── api/
│   ├── routes/         # FastAPI endpoints (Review, Benchmark)
│   ├── db/             # Supabase schema and client operations
│   └── main.py         # Application entry point
├── benchmark/          # Historical PR collection and F1-score evaluation suite
├── frontend/           # Next.js web application and UI components
├── graph/              # LangGraph compilation and state management
└── config.py           # Environment and model configurations
```

---

## Installation and Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Active Supabase instance

### Backend Installation

1. Navigate to the backend directory and initialize a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Frontend Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install frontend dependencies:
   ```bash
   npm install
   ```

---

## Configuration

Duplicate the `.env.example` file and rename it to `.env` in the root backend directory. The following credentials are required:

```ini
# Google Generative AI configurations
GEMINI_API_KEY=your_gemini_api_key

# GitHub Authentication
GITHUB_TOKEN=your_github_personal_access_token

# Supabase Credentials
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
```

*Note: PRISM automatically falls back to `gemini-3.1-flash-lite` within `config.py` for optimal throughput and quota utilization. Ensure your Google Cloud Project has access to this model tier.*

---

## Usage

### 1. Start the Backend API
```bash
uvicorn api.main:app --port 8000
```

### 2. Start the Frontend Application
```bash
cd frontend
npm run dev
```

### 3. Submitting a Pull Request
Navigate to `http://localhost:3000` in your web browser. Input a target repository and Pull Request ID. The dashboard will utilize Server-Sent Events (SSE) to render the parallel execution of agents and stream the final findings.

### 4. Running the Benchmark
To evaluate PRISM's performance on historical data, execute the following command in a secondary terminal:

```bash
curl -X POST "http://127.0.0.1:8000/benchmark/run" \
     -H "Content-Type: application/json" \
     -d "{\"repo\": \"langchain-ai/langgraph\", \"max_prs\": 20}"
```
The results will be available within the `/benchmark` route of the frontend application upon completion.
