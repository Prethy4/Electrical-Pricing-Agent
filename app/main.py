from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings 
from app.db.database import init_db
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.files import router as files_router
from app.api.health import router as health_router

logging.basicConfig(
    level=logging.DEBUG, # Changed from INFO to DEBUG
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
# Force silence noisy third-party libraries (watchfiles and sqlalchemy)
for logger_name in ["watchfiles.main", "watchfiles", "sqlalchemy.engine", "sqlalchemy.pool"]:
    target_logger = logging.getLogger(logger_name)
    target_logger.setLevel(logging.WARNING)
    target_logger.propagate = False
    
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database …")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Modular extraction agent for PDF/CSV processing.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router, prefix="/api/v1/health", tags=["Health"])
app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])
app.include_router(sessions_router, prefix="/api/v1", tags=["Sessions"])
app.include_router(files_router, prefix="/api/v1", tags=["Files"])

if __name__ == "__main__":
    import uvicorn
    # Example: Use a port from settings if you define one, otherwise default to 8000
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(settings.port) if hasattr(settings, 'port') else 8000, reload=True)
