import shutil
from typing import List, Annotated, Optional
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.tools.csv_tool import list_session_files
from app.db.database import get_db
from app.db.repositories import FileRepository
from app.services.file_service import process_pdf, process_csv

router = APIRouter()
settings = get_settings()

@router.post("/upload/{session_id}")
async def upload_files(
    session_id: UUID, 
    files: Annotated[List[UploadFile], File(description="Select multiple PDF and CSV files")],
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads multiple files (e.g., PDF and CSV) to the storage directory 
    associated with a specific session.
    """
    # Ensure the session directory exists
    session_dir = Path(settings.upload_dir) / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    uploaded_filenames = []
    file_repo = FileRepository(db)

    for file in files:
        if not file.filename:
            continue
            
        file_path = session_dir / file.filename
        try:
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            # Trigger indexing based on file type
            chunk_count = 0
            if file.filename.lower().endswith(".pdf"):
                chunk_count = await process_pdf(session_id, str(file_path), file.filename)
            elif file.filename.lower().endswith(".csv"):
                chunk_count = await process_csv(session_id, str(file_path), file.filename)

            # Save to Database
            db_file = await file_repo.create(
                session_id=session_id,
                filename=file.filename,
                file_type="pdf" if file.filename.lower().endswith(".pdf") else "csv",
                file_path=str(file_path),
                file_size=file_path.stat().st_size
            )
            if chunk_count > 0:
                await file_repo.mark_processed(db_file.id, chunk_count)

            uploaded_filenames.append(file.filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file {file.filename}: {str(e)}")

    return {
        "filenames": uploaded_filenames,
        "session_id": session_id,
        "status": "success",
        "count": len(uploaded_filenames)
    }

@router.get("/list/{session_id}")
async def get_files(session_id: str):
    """
    Retrieves a list of all files uploaded for the given session.
    """
    files = list_session_files(session_id)
    return {"session_id": session_id, "files": files}

@router.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """
    Downloads a specific file from the session's upload directory.
    """
    file_path = Path(settings.upload_dir) / session_id / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")
    
    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')
