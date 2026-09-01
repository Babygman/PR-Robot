"""Application configuration.

โหลดค่าจาก Environment Variable / ไฟล์ .env เท่านั้น
ห้าม Hard-code Password, Connection String หรือ API Key ในไฟล์นี้
ตาม PROJECT_STANDARD.md ข้อ 8 (Configuration and Secret Management)
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "PR-Robot"
    secret_key: str = "change-me-in-env"

    # ตัวอย่างรูปแบบ: postgresql+psycopg2://user:password@host:5432/dbname
    database_url: str = "postgresql+psycopg2://pr_robot:pr_robot@localhost:5432/pr_robot"

    # Google Gemini API (Free Tier) — ใช้สำหรับสกัดข้อมูลจากเอกสารต้นทาง
    gemini_api_key: str | None = None

    upload_dir: str = "storage/uploads"
    generated_dir: str = "storage/generated"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
