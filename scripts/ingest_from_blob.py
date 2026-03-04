"""
ingest_from_blob.py - Ingest Documents from Azure Blob Storage
================================================================
Downloads documents from Azure Blob Storage, chunks them, generates
embeddings, and indexes them into Azure AI Search.

This is the production ingestion pattern: documents live in Blob Storage
(not baked into the Docker image), and this script processes them.

Usage:
    python scripts/ingest_from_blob.py

    # Or ingest from local Docs/ folder (for development):
    python scripts/ingest_from_blob.py --local

Required env vars:
    AZURE_SEARCH_ENDPOINT
    AZURE_SEARCH_API_KEY
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_API_KEY
    AZURE_BLOB_CONNECTION_STRING  (unless --local)
    AZURE_BLOB_CONTAINER_NAME     (unless --local)
"""

import argparse
import os
import sys
import tempfile

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def download_blobs_to_local(
    connection_string: str, container_name: str, local_dir: str
) -> int:
    """Download all blobs from Azure Blob Storage to a local directory.

    Returns the number of files downloaded.
    """
    from azure.storage.blob import ContainerClient

    container_client = ContainerClient.from_connection_string(
        connection_string, container_name
    )

    count = 0
    for blob in container_client.list_blobs():
        # Recreate folder structure locally
        local_path = os.path.join(local_dir, blob.name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        print(f"  Downloading: {blob.name} ({blob.size:,} bytes)")
        blob_client = container_client.get_blob_client(blob)
        with open(local_path, "wb") as f:
            data = blob_client.download_blob().readall()
            f.write(data)
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into Azure AI Search"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Ingest from local Docs/ folder instead of Azure Blob Storage",
    )
    parser.add_argument(
        "--docs-path",
        type=str,
        default=None,
        help="Custom local docs path (default: ../Docs)",
    )
    args = parser.parse_args()

    # Determine the docs path
    if args.local:
        docs_path = args.docs_path or os.path.join(
            os.path.dirname(__file__), "..", "Docs"
        )
        docs_path = os.path.abspath(docs_path)
        print(f"Ingesting from local path: {docs_path}")
    else:
        # Download from Azure Blob Storage to a temp directory
        connection_string = os.environ.get("AZURE_BLOB_CONNECTION_STRING", "")
        container_name = os.environ.get("AZURE_BLOB_CONTAINER_NAME", "documents")

        if not connection_string:
            print("ERROR: Set AZURE_BLOB_CONNECTION_STRING env var (or use --local)")
            sys.exit(1)

        temp_dir = tempfile.mkdtemp(prefix="healthcare-docs-")
        print(f"Downloading documents from Azure Blob Storage ({container_name})...")
        file_count = download_blobs_to_local(
            connection_string, container_name, temp_dir
        )
        print(f"Downloaded {file_count} files to {temp_dir}")
        docs_path = temp_dir

    # Run the full ingestion pipeline
    from app.ingestion.embedder import run_full_ingestion

    print("\nStarting ingestion pipeline...")
    stats = run_full_ingestion(docs_path)

    print("\n=== Ingestion Complete ===")
    print(f"  Documents loaded: {stats['documents_loaded']}")
    print(f"  Chunks created:   {stats['chunks_created']}")
    print(f"  Chunks indexed:   {stats['chunks_indexed']}")
    print(f"  Source path:      {stats['docs_path']}")


if __name__ == "__main__":
    main()
