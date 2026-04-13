import os
import aiofiles
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db
from app.db.repositories import SessionRepository, FileRepository
from app.models.schemas import FileUploadResponse
from app.services.file_service import process_pdf, process_csv

router = APIRouter(prefix="/files", tags=["Files"])
settings = get_settings()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/vnd.ms-excel": "csv",  # some clients send this for .csv
    "text/plain": "csv",  # fallback for .csv
}


@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    session_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF or CSV file and attach it to a session.
    The file is immediately processed and embedded for retrieval.
    """
    # ── Validate session ──────────────────────────────────────────────────────
    session_repo = SessionRepository(db)
    session = await session_repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # ── Validate file type ────────────────────────────────────────────────────
    content_type = file.content_type or ""
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        file_type = "pdf"
    elif ext == ".csv":
        file_type = "csv"
    elif content_type in ALLOWED_TYPES:
        file_type = ALLOWED_TYPES[content_type]
    else:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Only PDF and CSV are accepted.",
        )

    # ── Read & size-check ─────────────────────────────────────────────────────
    contents = await file.read()
    if len(contents) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB.",
        )

    # ── Save to disk ──────────────────────────────────────────────────────────
    upload_dir = Path(settings.upload_dir) / str(session_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{os.urandom(8).hex()}_{filename}"
    file_path = upload_dir / safe_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(contents)

    # ── Persist metadata ──────────────────────────────────────────────────────
    file_repo = FileRepository(db)
    db_file = await file_repo.create(
        session_id=session_id,
        filename=filename,
        file_type=file_type,
        file_path=str(file_path),
        file_size=len(contents),
    )

    # ── Process & embed ───────────────────────────────────────────────────────
    try:
        if file_type == "pdf":
            chunk_count = await process_pdf(session_id, str(file_path), filename)
        else:
            chunk_count = await process_csv(session_id, str(file_path), filename)
        await file_repo.mark_processed(db_file.id, chunk_count)
        db_file.processed = True
        db_file.chunk_count = chunk_count
    except Exception as e:
        # Don't fail the upload if embedding fails; flag as unprocessed
        import logging
        logging.getLogger(__name__).error(f"File processing error: {e}")

    return FileUploadResponse.model_validate(db_file)
