"""
File ingestion service.
- PDF  → extract text with pypdf, split into chunks, embed with OpenAI
- CSV  → load with pandas, convert rows to text, embed
All vectors are stored in an in-process FAISS index keyed by session_id.
Replace FAISS with pgvector or another store when scaling out.
"""

import io
import os
import logging
from pathlib import Path
from typing import List, Tuple
from uuid import UUID

import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory store: session_id (str) → FAISS index
_vector_stores: dict[str, FAISS] = {}

embeddings = OpenAIEmbeddings(
    model=settings.openai_embedding_model,
    openai_api_key=settings.openai_api_key,
)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", " ", ""],
)


# ── Public API ────────────────────────────────────────────────────────────────

async def process_pdf(
    session_id: UUID,
    file_path: str,
    filename: str,
) -> int:
    """Parse a PDF, embed chunks, store in the session vector store. Returns chunk count."""
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages_text = [
        page.extract_text() or ""
        for page in reader.pages
    ]
    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        logger.warning(f"PDF {filename} yielded no extractable text.")
        return 0

    docs = text_splitter.create_documents(
        [full_text],
        metadatas=[{"source": filename, "type": "pdf", "session_id": str(session_id)}],
    )
    return _upsert_docs(str(session_id), docs)


async def process_csv(
    session_id: UUID,
    file_path: str,
    filename: str,
) -> int:
    """Parse a CSV, embed row summaries, store in the session vector store. Returns chunk count."""
    df = pd.read_csv(file_path)
    df = df.fillna("")

    # Build a text summary per row; also include a global schema overview
    schema_doc = Document(
        page_content=(
            f"CSV file: {filename}\n"
            f"Columns: {', '.join(df.columns.tolist())}\n"
            f"Row count: {len(df)}\n"
            f"Sample (first 5 rows):\n{df.head(5).to_string(index=False)}"
        ),
        metadata={"source": filename, "type": "csv_schema", "session_id": str(session_id)},
    )

    # Convert each row to a short human-readable string
    row_texts = df.apply(
        lambda row: ", ".join(f"{col}: {val}" for col, val in row.items() if val != ""),
        axis=1,
    ).tolist()

    # Batch rows into chunks to avoid too many tiny docs
    batch_size = 50
    row_docs = []
    for i in range(0, len(row_texts), batch_size):
        batch = row_texts[i : i + batch_size]
        row_docs.append(
            Document(
                page_content="\n".join(batch),
                metadata={
                    "source": filename,
                    "type": "csv_rows",
                    "row_start": i,
                    "row_end": i + len(batch),
                    "session_id": str(session_id),
                },
            )
        )

    all_docs = [schema_doc] + row_docs
    return _upsert_docs(str(session_id), all_docs)


def get_retriever(session_id: UUID, k: int = 4):
    """Return a LangChain retriever for the session, or None if no files uploaded yet."""
    store = _vector_stores.get(str(session_id))
    if store is None:
        return None
    return store.as_retriever(search_kwargs={"k": k})


def has_documents(session_id: UUID) -> bool:
    return str(session_id) in _vector_stores


# ── Internal ──────────────────────────────────────────────────────────────────

def _upsert_docs(session_key: str, docs: List[Document]) -> int:
    if not docs:
        return 0
    existing = _vector_stores.get(session_key)
    if existing is None:
        _vector_stores[session_key] = FAISS.from_documents(docs, embeddings)
    else:
        existing.add_documents(docs)
    return len(docs)
