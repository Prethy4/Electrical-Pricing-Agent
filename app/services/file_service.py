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
import pandas as pd
from typing import List, Tuple
from uuid import UUID
from app.services.csv_schema_inference import infer_csv_schema
from app.services.context_builder import build_context_tree
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

try:
    from pdf2image import convert_from_path
    import pytesseract
except ImportError:
    convert_from_path = None
    pytesseract = None

from app.pdf_structured import process_pdf_structured
from app.services.pdf_mapper import extract_pdf_articles
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory store: session_id (str) → FAISS index
_vector_stores: dict[str, FAISS] = {}
# In-memory store: session_id (str) → {article_code: data}
_article_stores: dict[str, dict] = {}

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
    """Parse a PDF using layout-aware tools, embed chunks, and store in the session vector store."""
    logger.info(f"PRODUCT_EXTRACTION_START | Session: {session_id} | File: {filename}")
    
    # Use the structured parser for high-fidelity extraction
    structured_chunks = await process_pdf_structured(file_path)
    
    # Combine text for fallback/chunking check or use directly as Documents
    full_text = "\n\n".join([c["content"] for c in structured_chunks if c["content"]])

    # OCR Fallback: If pypdf yielded no text, it's likely a scanned image
    if not full_text.strip() or len(full_text.strip()) < 50:
        logger.info(f"Attempting OCR for scanned PDF: {filename}")
        if convert_from_path and pytesseract:
            try:
                # Convert PDF pages to images
                images = convert_from_path(file_path)
                ocr_text = []
                for img in images:
                    # Extract text using Tesseract (using French/English)
                    text = pytesseract.image_to_string(img, lang='fra+eng')
                    ocr_text.append(text)
                full_text = "\n\n".join(ocr_text)
                
                # FIX: Create a structured chunk from OCR text so it gets indexed
                if full_text.strip():
                    structured_chunks = [{
                        "content": full_text,
                        "type": "section",
                        "metadata": {"source": filename, "method": "ocr"}
                    }]
            except Exception as e:
                logger.error(f"OCR failed for {filename}: {e}")
        else:
            logger.warning("OCR libraries (pytesseract/pdf2image) missing. Cannot process scanned PDF.")

    if not full_text.strip():
        logger.warning(f"PDF_RESULT | No text extracted for {filename}")
        return 0

    # Re-build article-based index after potential OCR
    article_map = extract_pdf_articles(structured_chunks)
    _upsert_articles(str(session_id), article_map)

    # Create documents from structured chunks to preserve metadata
    docs = []
    for chunk in structured_chunks:
        if not chunk["content"]:
            continue
        
        # Ensure each chunk is within token limits for embedding
        sub_chunks = text_splitter.split_text(chunk["content"])
        for text in sub_chunks:
            docs.append(Document(
                page_content=text,
                metadata={
                    **chunk["metadata"],
                    "element_type": chunk["type"],
                    "session_id": str(session_id)
                }
            ))

    logger.info(f"PDF_RESULT | Created {len(docs)} structured chunks for {filename}")
    return _upsert_docs(str(session_id), docs)


async def process_csv(
    session_id: UUID,
    file_path: str,
    filename: str,
) -> int:
    """Hierarchical CSV Ingestion: Reconstructs context tree before indexing."""
    logger.info(f"CSV_HIERARCHICAL_INGESTION_START | File: {filename}")
    
    # Robust encoding detection matching the tool logic
    encoding = 'utf-8'
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            pd.read_csv(file_path, encoding=enc, nrows=5)
            encoding = enc
            break
        except Exception:
            continue
            
    try:
        # Use engine='python' and sep=None for automatic delimiter detection
        df = pd.read_csv(file_path, encoding=encoding, sep=None, engine='python')
    except Exception as e:
        logger.error(f"CSV_INDEXING_ERROR | {filename}: {e}")
        return 0

    df_ingest = df.copy().fillna("")

    # 1. Infer Schema (Detect French Synonyms)
    headers = df_ingest.columns.tolist()
    sample = df_ingest.head(3).to_dict(orient="records")
    schema_info = await infer_csv_schema(headers, sample)
    mapping = schema_info.get("mapping", {})

    # Hierarchical Reconstruction
    raw_rows = df_ingest.to_dict(orient="records")
    hierarchical_rows = build_context_tree(raw_rows, mapping=mapping)

    schema_doc = Document(
        page_content=(
            f"CSV file: {filename}\n"
            f"Row count: {len(df_ingest)}\n"
            f"Raw Columns: {', '.join(df.columns.tolist())}"
        ),
        metadata={"source": filename, "type": "csv_schema", "session_id": str(session_id)},
    )

    row_texts = []
    for hr in hierarchical_rows:
        ctx = " > ".join(hr.get("_context", []))
        art = hr.get("_article_code", "No Code")
        raw_data = ", ".join([f"{k}: {v}" for k, v in hr.items() if not k.startswith('_')])
        row_texts.append(f"ARTICLE: {art}\nCONTEXT: {ctx}\nDATA: {raw_data}")

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

async def process_xlsx(
    session_id: UUID,
    file_path: str,
    filename: str,
) -> int:
    """Hierarchical Excel Ingestion: Similar to CSV but using pandas read_excel."""
    logger.info(f"EXCEL_HIERARCHICAL_INGESTION_START | File: {filename}")
    try:
        # Match header detection logic from csv_tool
        header_check = pd.read_excel(file_path, nrows=20, header=None, engine='openpyxl')
        header_idx = 0
        for i, row in header_check.iterrows():
            row_vals = [str(v).strip().lower() for v in row.values if v is not None]
            if any(k in row_vals for k in ["article", "art.", "code", "réf"]) and \
               any(k in " ".join(row_vals) for k in ["dénomination", "désignation", "unité", "qté", "quantité", "p.u", "somme"]):
                header_idx = i
                break
        
        df = pd.read_excel(file_path, engine='openpyxl', header=header_idx)
    except ImportError:
        logger.error(f"EXCEL_INDEXING_ERROR | {filename}: The 'openpyxl' library is required to process Excel files.")
        return 0
    except Exception as e:
        logger.error(f"EXCEL_INDEXING_ERROR | {filename}: {e}")
        return 0

    df_ingest = df.copy().fillna("")

    # 1. Infer Schema
    headers = df_ingest.columns.astype(str).tolist()
    sample = df_ingest.head(3).to_dict(orient="records")
    schema_info = await infer_csv_schema(headers, sample)
    mapping = schema_info.get("mapping", {})

    # Hierarchical Reconstruction
    raw_rows = df_ingest.to_dict(orient="records")
    hierarchical_rows = build_context_tree(raw_rows, mapping=mapping)

    schema_doc = Document(
        page_content=(
            f"Excel file: {filename}\n"
            f"Row count: {len(df_ingest)}\n"
            f"Columns: {', '.join(headers)}"
        ),
        metadata={"source": filename, "type": "excel_schema", "session_id": str(session_id)},
    )

    row_texts = []
    for hr in hierarchical_rows:
        ctx = " > ".join(hr.get("_context", []))
        art = hr.get("_article_code", "No Code")
        raw_data = ", ".join([f"{k}: {v}" for k, v in hr.items() if not k.startswith('_')])
        row_texts.append(f"ARTICLE: {art}\nCONTEXT: {ctx}\nDATA: {raw_data}")

    # Batch rows into chunks
    batch_size = 50
    row_docs = []
    for i in range(0, len(row_texts), batch_size):
        batch = row_texts[i : i + batch_size]
        row_docs.append(
            Document(
                page_content="\n".join(batch),
                metadata={
                    "source": filename,
                    "type": "excel_rows",
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


def get_article_data(session_id: UUID, article_code: str):
    """Deterministic lookup for specific article data."""
    return _article_stores.get(str(session_id), {}).get(article_code)


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

def _upsert_articles(session_key: str, article_map: dict):
    if session_key not in _article_stores:
        _article_stores[session_key] = {}
    _article_stores[session_key].update(article_map)
