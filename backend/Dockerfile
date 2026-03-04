# ============================================
# Backend Dockerfile
# ============================================
# WHY multi-stage: Stage 1 installs dependencies (cached layer).
# Stage 2 copies app code (changes frequently). This means code
# changes don't re-download all dependencies - builds are fast.

FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies for document processing
# - antiword: .doc file extraction
# - poppler-utils: PDF processing fallback
# - gcc/build-essential: compile native Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    antiword \
    poppler-utils \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download cross-encoder model during build (avoids 2-3s cold start)
# WHY: sentence-transformers downloads the model on first use.
# Doing it at build time means the container starts instantly.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run with uvicorn
# WHY --host 0.0.0.0: Binds to all interfaces so Docker can route traffic in
# WHY --workers 1: Single worker for simplicity. Scale horizontally with
#   Azure Container Apps replicas instead of multiple workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
