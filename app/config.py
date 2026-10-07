"""Application configuration.

Simple config that reads DATABASE_URL from environment, defaulting to SQLite.
Makes it easy to swap to Postgres by changing one env var.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./certificates.db"
    storage_dir: str = "storage"
    
    # For SQLite, enable foreign keys (not on by default)
    sqlite_foreign_keys: bool = True
    
    class Config:
        env_file = ".env"


settings = Settings()
