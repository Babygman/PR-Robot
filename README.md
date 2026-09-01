# PR-Robot

ระบบช่วยกรอกใบขอซื้อ (Purchasing Requisition) ของ Sunstar Chemical (Thailand)
Co., Ltd. โดยใช้ AI อ่านข้อมูลจากเอกสารต้นทาง (ใบเสนอราคา, ใบรับของ) มากรอกฟอร์ม
อัตโนมัติ พร้อมเก็บประวัติเรียกดูย้อนหลัง

รายละเอียด Business Goal / Architecture / Database Design / Roadmap ทั้งหมด
อยู่ที่ [`docs/00_KICKOFF_AND_DESIGN.md`](docs/00_KICKOFF_AND_DESIGN.md)
โปรเจกต์นี้อยู่ภายใต้ `PROJECT_STANDARD.md` v2.1

สถานะปัจจุบัน: **Phase 1 — Infra Readiness** (ยังไม่มีหน้าเว็บ/ฟีเจอร์ใช้งานจริง)

---

## Tech Stack

- Backend: Python 3.11+ / FastAPI
- Database: PostgreSQL (รันผ่าน Docker สำหรับ Dev)
- Migration: Alembic
- AI Extraction: Google Gemini API (Free Tier)
- PDF Generation: WeasyPrint (Phase 5)

---

## Setup (รันบน MacBook Air ผ่าน VS Code Terminal ของโปรเจกต์)

### 1. Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

> หมายเหตุ: `weasyprint` (ใช้ตอน Phase 5) ต้องมี System Library ของ Pango/Cairo
> บน macOS ติดตั้งด้วย `brew install pango` หากยังไม่มี

### 2. Environment Configuration

```bash
cp .env.example .env
# แก้ .env ใส่ GEMINI_API_KEY และค่าที่ต้องการ (ห้าม Commit ไฟล์ .env)
```

### 3. Database (Docker)

```bash
docker compose up -d
docker compose logs -f db      # รอจนเห็น "database system is ready to accept connections"
```

### 4. Alembic — สร้างตารางตาม Baseline

```bash
alembic upgrade head
```

### 5. รัน Application (Dev)

```bash
uvicorn app.main:app --reload
```

ทดสอบ:
- Liveness: http://127.0.0.1:8000/health
- Database Readiness: http://127.0.0.1:8000/health/db

### 6. Tests / Lint

```bash
pytest
ruff check .
```

---

## Infrastructure Readiness Gate — สถานะ (ตาม PROJECT_STANDARD.md ข้อ 3)

| รายการ | สถานะ | หมายเหตุ |
|---|---|---|
| Repository พร้อมใช้งาน | ✅ | git init แล้ว, remote = GitHub Babygman/PR-Robot |
| Dependencies ถูกบันทึกใน Dependency File | ✅ | requirements.txt / requirements-dev.txt ติดตั้งผ่านแล้วในสภาพแวดล้อมทดสอบ |
| Environment Configuration พร้อมใช้งาน | ✅ | `.env.example` พร้อม, ต้อง copy เป็น `.env` และกรอกค่าจริงเอง |
| Secrets ถูกแยกออกจาก Git | ✅ | `.env` อยู่ใน `.gitignore` |
| Alembic Baseline | ✅ | `alembic/versions/<hash>_baseline.py` (upgrade/downgrade ว่าง รอ Phase 2 ใส่ Schema จริง) |
| Application Code (FastAPI/Alembic/SQLAlchemy) ทำงานถูกต้องจริง | ✅ | ตรวจใน Sandbox แยกต่างหาก: `alembic upgrade head` รันจริงกับ SQLite (Postgres ติดตั้งไม่ได้ใน Sandbox นี้ — ไม่มี root, ไม่มี Wheel ของ pgserver สำหรับ Linux aarch64), สร้างตาราง `alembic_version` สำเร็จ, `uvicorn` รันแอปจริง, `curl /health` และ `/health/db` ตอบ 200 พร้อม Query ฐานข้อมูลจริงสำเร็จ |
| `docker-compose.yml` Schema ถูกต้อง | ✅ | Parse ผ่าน PyYAML, มี `services.db`, `healthcheck`, Named Volume ครบ |
| Migration + Driver ทำงานจริงกับ PostgreSQL จริง (ไม่ใช่ SQLite) | ✅ | ยืนยันแล้ว 2026-09-01 บน Docker จริงที่ SCTUBUNTU01: `alembic upgrade head` รันกับ postgres:16-alpine จริง สำเร็จ (`3e95cf5ab690 (head)`), เชื่อมต่อผ่าน psycopg2 จริง (`LIVE POSTGRES VERSION: PostgreSQL 16.15`) — Container/Network ที่ใช้ทดสอบถูกลบทิ้งหมดแล้วหลัง Test, ไม่กระทบ Stack อื่นบนเครื่อง |
| Docker Desktop บน MacBook Air ของคุณเอง | ⏳ ไม่บังคับ | ยังไม่เคยตรวจจริง แต่ความเสี่ยงต่ำมากแล้ว เพราะ Code เดียวกันนี้พิสูจน์แล้วว่าใช้ได้กับ PostgreSQL จริงบน Docker เครื่องอื่น (SCTUBUNTU01) — ไม่ Block การไป Phase 2 |

