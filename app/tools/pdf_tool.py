import os
import json
from pathlib import Path
import asyncio
from typing import Dict, Any, List
try:
    import pypdf
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    pypdf = None

try:
    from pdf2image import convert_from_path
    import pytesseract
except ImportError:
    convert_from_path = None
    pytesseract = None

from app.core.config import get_settings
from app.db.vector_store import VectorStoreManager

settings = get_settings()

async def manage_pdf_data(session_id: str, filename: str) -> str:
    """
    Extracts text via OCR/Direct, chunks it for the Knowledge Base, 
    and returns metadata.
    """
    file_path = Path(settings.upload_dir) / session_id / filename
    
    if not file_path.exists():
        return f"Error: File '{filename}' not found."
    
    if pypdf is None:
        return "Error: pypdf library not installed. Run 'pip install pypdf'."

    try:
        reader = pypdf.PdfReader(str(file_path))
        num_pages = len(reader.pages)
        
        extracted_text = ""
        method = "none"

        # 1. Prioritize OCR (pytesseract) as requested
        if convert_from_path and pytesseract:
            try:
                # Offload CPU-bound image conversion
                images = await asyncio.to_thread(convert_from_path, str(file_path))
                if images:
                    ocr_pages = []
                    for img in images:
                        ocr_pages.append(await asyncio.to_thread(pytesseract.image_to_string, img, lang='fra'))
                    extracted_text = "\n".join(ocr_pages).strip()
                    method = "ocr_tesseract"
            except Exception as ocr_err:
                print(f"OCR Error: {ocr_err}")

        # 2. Fallback to standard extraction if OCR is unavailable or yielded no text
        if not extracted_text:
            text_list = await asyncio.to_thread(lambda: [p.extract_text() or "" for p in reader.pages])
            extracted_text = "\n".join(text_list).strip()
            method = "pypdf"

        # Clean up excessive f8fafcspace and limit to a larger context window (e.g., 10,000 chars)
        # 3. Chunking for Knowledge Base
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
        chunks = text_splitter.split_text(extracted_text)
        
        # 4. Save to Vector Store for professional RAG
        vs_manager = VectorStoreManager(session_id)
        vs_manager.add_documents(chunks, {"filename": filename, "type": "pdf"})

        res = {
            "filename": filename,
            "total_pages": num_pages,
            "chunk_count": len(chunks), 
            "extraction_method": method,
            "status": "success" if chunks else "failed"
        }
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)