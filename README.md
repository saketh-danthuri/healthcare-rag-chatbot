# Healthcare Operations AI Chatbot

Agentic RAG chatbot for healthcare claims operations, built with LangGraph, Azure AI Search, FastAPI, and Next.js.

## Architecture

```
Frontend (Next.js)  -->  Backend (FastAPI)  -->  Azure AI Search (hybrid retrieval)
                              |                          |
                         LangGraph Agent         Vector + BM25 + RRF
                              |
                    Tools: Search, Email, SQL, Escalation
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, Tailwind CSS, TypeScript |
| **Backend** | FastAPI, Python 3.11, LangGraph, LangChain |
| **LLM** | Azure OpenAI (GPT-4o-mini) |
| **Retrieval** | Azure AI Search (hybrid: vector + BM25 + RRF) |
| **Reranking** | Cross-encoder (ms-marco-MiniLM-L-6-v2) |
| **Deployment** | Azure Container Apps (backend), Azure Static Web Apps (frontend) |
| **CI/CD** | GitHub Actions (lint, test, RAG quality gate, auto-deploy) |

## Live Demo

| Component | URL |
|-----------|-----|
| Frontend | [healthcare-ops.azurestaticapps.net](https://black-water-04429680f.4.azurestaticapps.net) |
| Backend API | [healthcare-ops.azurecontainerapps.io](https://healthcare-ops.livelypebble-70fe60f2.eastus2.azurecontainerapps.io) |
| API Docs | [Swagger UI](https://healthcare-ops.livelypebble-70fe60f2.eastus2.azurecontainerapps.io/docs) |

## Quick Start (Local Development)

```bash
# 1. Clone and set up environment
cp .env.example .env  # Fill in Azure credentials

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## CI/CD Pipeline

```
PR to main
    |
    +-- ci.yml (parallel)
    |     +-- Backend CI  --> ruff lint + pytest
    |     |       +-- RAG Quality Gate  --> RAGAS evaluation
    |     +-- Frontend CI --> eslint + next build
    |
Merge to main
    |
    +-- deploy-backend.yml  --> Docker build --> ACR --> Container App
    +-- deploy-frontend.yml --> next build --> Azure Static Web Apps
```

## Project Structure

```
.
+-- backend/                 # FastAPI backend
|   +-- app/
|   |   +-- agent/           # LangGraph agent + tools
|   |   +-- api/             # REST API routes
|   |   +-- retrieval/       # Hybrid search + reranking
|   |   +-- ingestion/       # Document processing pipeline
|   |   +-- evaluation/      # RAG quality evaluation (RAGAS)
|   |   +-- config/          # Settings + prompts
|   +-- tests/               # Unit, integration, e2e tests
|   +-- Dockerfile
+-- frontend/                # Next.js frontend
|   +-- src/components/      # React components
|   +-- src/hooks/           # Custom hooks (chat, health, sessions)
+-- scripts/                 # Index creation + ingestion scripts
+-- Docs/                    # Healthcare runbook documents
+-- .github/workflows/       # CI/CD pipelines
```
