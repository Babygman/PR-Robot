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

    # Google Gemini API (Free Tier) — ใช้สำหรับสกัดข้อมูลจากเอกสารต้นทาง (Phase 4)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"  # ปรับได้ผ่าน .env ตาม Quota จริงของ Key

    # อัตราแลกเปลี่ยน USD -> THB โดยประมาณ สำหรับหน้า "ค่าใช้จ่าย AI" (2026-09-04) —
    # ปรับเองเป็นระยะผ่าน .env ไม่ใช่ Real-time (ไม่ยิง Network เรียก Currency API ทุก
    # Request) ค่าที่บันทึกไว้ในแต่ละ Transaction เป็น Snapshot ของ Rate ณ ตอนนั้นอยู่แล้ว
    gemini_usd_to_thb_rate: float = 33.0

    upload_dir: str = "storage/uploads"
    generated_dir: str = "storage/generated"

    # --- Auth (Phase 3) ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 ชั่วโมงทำงาน, ปรับได้ผ่าน .env


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
