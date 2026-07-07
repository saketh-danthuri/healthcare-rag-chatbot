"""
ingest_local.py - Local Document Ingestion
===========================================
Loads every document in the Docs/ folder, chunks it, embeds each chunk with the
local sentence-transformers model, and upserts them into the local ChromaDB
collection. No Azure / cloud accounts required.

Usage:
    cd backend && ./.venv/bin/python ../scripts/ingest_local.py
    # optional: point at a different docs folder
    ./.venv/bin/python ../scripts/ingest_local.py /path/to/docs
"""

import logging
import sys
from pathlib import Path

# Make the backend package importable when run from the repo root.
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

from app.ingestion.embedder import run_full_ingestion  # noqa: E402


def main() -> None:
    docs_path = sys.argv[1] if len(sys.argv) > 1 else None
    stats = run_full_ingestion(docs_path)
    print("\n=== Ingestion complete ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
