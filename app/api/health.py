from fastapi import APIRouter
from app.db.database import check_db_connection
from app.core.config import get_settings

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/health")
async def health_check():
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_title,
        "version": settings.app_version,
        "database": "connected" if db_ok else "unreachable",
    }
