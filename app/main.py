"""PR-Robot — FastAPI entrypoint."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.pages import router as pages_router
from app.api.routes.purchasing_requisitions import router as prs_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.db.session import engine

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.app_name)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(documents_router)
app.include_router(prs_router)
app.include_router(pages_router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


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
