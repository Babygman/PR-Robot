"""PR-Robot — FastAPI entrypoint."""
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict:
    """Liveness check — ไม่แตะ Database"""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/health/db")
def health_db() -> dict:
    """Readiness check — ตรวจ ORM Connection ไปยัง Database จริง
    (Infrastructure Readiness Gate ตาม PROJECT_STANDARD.md ข้อ 3)
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
