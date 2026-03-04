"""
create_search_index.py - Create Azure AI Search Index Schema
==============================================================
Run this ONCE before ingestion to create the search index with the correct
field definitions, analyzers, and vector configuration.

Usage:
    python scripts/create_search_index.py

Required env vars:
    AZURE_SEARCH_ENDPOINT - e.g., https://searchservice-1772652333512.search.windows.net
    AZURE_SEARCH_API_KEY  - Admin key from Azure portal
"""

import os
import sys

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

# Configuration
SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "healthcare-runbooks")

VECTOR_DIMENSIONS = 1536  # text-embedding-3-small


def create_index():
    """Create the healthcare-runbooks search index."""
    if not SEARCH_ENDPOINT or not SEARCH_API_KEY:
        print("ERROR: Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY env vars")
        sys.exit(1)

    print(f"Creating index '{INDEX_NAME}' at {SEARCH_ENDPOINT}...")

    # Define fields
    fields = [
        SimpleField(
            name="chunk_id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="en.lucene",  # English BM25 analyzer (free BM25!)
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name="healthcare-vector-profile",
        ),
        SimpleField(
            name="source_file",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="doc_type",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchableField(
            name="job_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="section",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="page_number",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SimpleField(
            name="folder",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="source_path",
            type=SearchFieldDataType.String,
            filterable=False,
        ),
        SimpleField(
            name="file_type",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
    ]

    # Vector search configuration
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="healthcare-hnsw-config",
                parameters={
                    "m": 4,  # Bi-directional links per node
                    "efConstruction": 400,  # Index build quality
                    "efSearch": 500,  # Search quality
                    "metric": "cosine",
                },
            ),
        ],
        profiles=[
            VectorSearchProfile(
                name="healthcare-vector-profile",
                algorithm_configuration_name="healthcare-hnsw-config",
            ),
        ],
    )

    # Create the index
    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )

    client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    result = client.create_or_update_index(index)
    print(f"Index '{result.name}' created/updated successfully!")
    print(f"  Fields: {len(result.fields)}")
    print(f"  Vector dimensions: {VECTOR_DIMENSIONS}")
    print("  Analyzer: en.lucene (BM25)")


if __name__ == "__main__":
    create_index()
