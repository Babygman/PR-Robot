#!/bin/sh
# PR-Robot — Container Entrypoint (Phase 8)
# รัน Alembic Migration ให้ Database Schema เป็นปัจจุบันก่อนเสมอ แล้วค่อย Start
# Process จริง (Uvicorn ตาม CMD ปกติ หรือ Override เป็นคำสั่งอื่นก็ได้ เช่น
# `docker compose run app python app/scripts/create_admin.py`)
set -e

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] Starting: $*"
exec "$@"
