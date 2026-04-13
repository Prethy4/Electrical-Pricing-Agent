from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = "sk-placeholder"
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/chat_agent"
    database_url_sync: str = "postgresql://user:password@localhost:5432/chat_agent"

    # App
    app_title: str = "Chat Agent API"
    app_version: str = "1.0.0"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # File Upload
    max_file_size_mb: int = 20
    upload_dir: str = "uploads"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    return Settings()
