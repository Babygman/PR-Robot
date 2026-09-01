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
| Virtual Environment บนเครื่องจริง | ⏳ รอ | ต้องสร้างบน MacBook Air จริงตามขั้นตอนข้างต้น (สภาพแวดล้อมที่ใช้ตรวจสอบไฟล์เป็นแค่ Sandbox ไม่ใช่เครื่องจริง) |
| Docker / Database Server ทำงานจริง | ⏳ รอ | ต้องรัน `docker compose up -d` บนเครื่องจริง (Docker ไม่สามารถเข้าถึงได้จาก Sandbox ที่ใช้เตรียมไฟล์นี้) |
| Direct Database Connection / ORM Connection ผ่าน | ⏳ รอ | ตรวจสอบได้ด้วย `alembic upgrade head` และเปิด `/health/db` หลังรัน Docker แล้ว |

