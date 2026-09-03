# PR-Robot — Project Kickoff & Design Document

Version: 0.1 (Draft — รออนุมัติ)
Date: 2026-09-01
Status: **รอ Product Owner อนุมัติก่อนเริ่ม Phase 1**

อ้างอิงตาม `PROJECT_STANDARD.md` v2.1 — เอกสารนี้คือผลลัพธ์ของขั้นตอน
Requirement Analysis → Architecture → Database → Workflow → Roadmap
ก่อนเริ่ม Coding

---

## 1. Project Kickoff Template

| หัวข้อ | รายละเอียด |
|---|---|
| Project Name | PR-Robot |
| Business Goal | ลดเวลาและความผิดพลาดในการกรอกใบขอซื้อ (Purchasing Requisition) ของ Sunstar Chemical (Thailand) โดยใช้ AI อ่านข้อมูลจากเอกสารต้นทาง (ใบเสนอราคา, ใบรับของ) แล้วช่วยกรอกฟอร์มอัตโนมัติ พร้อมเก็บประวัติเพื่อสืบค้นย้อนหลัง |
| Objectives | 1) อัปโหลดเอกสารต้นทาง → AI สกัดข้อมูล 2) ตรวจทาน/แก้ไขก่อนบันทึกเสมอ (Human-in-the-loop) 3) Generate PR ตาม Template จริง (PDF) 4) เก็บประวัติ + ค้นหาได้ 5) Workflow อนุมัติ 4 บทบาท พร้อม Login |
| Target Users | ฝ่ายจัดซื้อ/ธุรการ Sunstar Chemical (Thailand): ผู้ขอซื้อ (Requester), ผู้ตรวจทาน (Reviewer), ผู้อนุมัติ (Approver), ผู้รับของ (Receiver) |
| Technology Stack | Python (FastAPI) + PostgreSQL (Docker) + Google Gemini API (Free Tier) |
| Operating System | Dev: macOS (MacBook Air) / Deploy: Ubuntu 26.04 LTS (SCTUBUNTU01) |
| Programming Language | Python 3.x |
| Database | PostgreSQL (Docker) |
| Source Control | Git + GitHub (`https://github.com/Babygman/PR-Robot`) |
| Coding Tool | VS Code |
| AI Coding Tool | Claude Code / Codex |
| Deployment | Docker Compose → Portainer → Nginx Proxy Manager บน SCTUBUNTU01 (10.206.1.107) |
| Timeline | แบ่งเป็น Phase ตาม Roadmap ด้านล่าง — ยังไม่ประเมินวันที่แน่นอน รอ Product Owner กำหนด |
| Out of Scope (Phase 1) | ไม่เชื่อม ERP/D365FO, ไม่ทำ Mobile App, ไม่ทำ Auto Email/Notification, ไม่ทำ Purchase Order (PO) — ทำเฉพาะ Purchasing Requisition (PR) |
| Success Criteria | (1) AI สกัดข้อมูลถูกต้อง ≥ 80% โดยไม่ต้องแก้ไข (วัดตอน UAT) (2) เวลาสร้าง PR ลดลงเทียบกับกรอกมือ (3) ค้นหาประวัติ PR ย้อนหลังได้ตาม Section/Division/วันที่/เลขที่ PR |

### Environment Definition

| Environment | Application Runtime | Database | Port | Auth | Config | Deploy Method |
|---|---|---|---|---|---|---|
| DEV | MacBook Air → VS Code Terminal → `uvicorn --reload` | PostgreSQL local (Docker Desktop) | 5432 | `.env` local | `.env` (ไม่ commit) | รันตรงจาก Terminal |
| UAT | Docker Container บน SCTUBUNTU01 (Stack แยกจาก PROD) | PostgreSQL container แยก DB จาก PROD | ผ่าน Nginx Proxy Manager | Login ระบบ + Basic Auth ชั่วคราว (กัน Public เข้าถึง) | Docker env vars / secret file | Docker Compose ผ่าน Portainer |
| PROD | Docker Container บน SCTUBUNTU01 | PostgreSQL container แยก DB จาก UAT | ผ่าน Nginx Proxy Manager (HTTPS) | Login ระบบ | Docker env vars / secret file | Docker Compose ผ่าน Portainer |

หมายเหตุ: Database Server ให้บริการเฉพาะ Database ตามมาตรฐาน — Application รันแยก Container คนละตัวเสมอ ไม่รวมกับ DB Container

---

## 2. Risk Assessment

| ความเสี่ยง | ผลกระทบ | แนวทางจัดการ |
|---|---|---|
| Google Gemini Free Tier มี Rate Limit | อัปโหลดเอกสารช่วงเวลาเดียวกันเยอะอาจถูกปฏิเสธชั่วคราว | ระบบต้องกรอกฟอร์มด้วยมือได้เสมอเมื่อ AI ใช้งานไม่ได้ (ไม่ Block งาน) |
| ความแม่นยำของ AI ไม่ 100% (เอกสารลายมือ/สแกนคุณภาพต่ำ) | ข้อมูลผิดถ้าไม่มีการตรวจสอบ | บังคับขั้นตอน "ตรวจทานก่อนบันทึก" ทุกครั้ง ห้าม Auto-submit ตรงจาก AI |
| ข้อมูลในเอกสาร (ราคา/คู่ค้า) เป็นข้อมูลธุรกิจที่ Sensitive ถูกส่งออกไปยัง Google API ภายนอก | ความเสี่ยงด้าน Data Privacy | ต้องแจ้ง Product Owner รับทราบก่อน Deploy จริง และพิจารณาไม่ส่งข้อมูลที่อ่อนไหวเกินจำเป็น |
| แบบฟอร์มหน้า 2-3 ยังไม่ได้รับ | Schema/ฟิลด์อาจต้องปรับหลังได้รับเอกสารเพิ่ม | ออกแบบ Schema เผื่อขยาย (Phase 1 ใช้เฉพาะหน้า 1 ที่มีข้อมูลครบ) |

---

## 3. Architecture

### 3.1 Components

1. **Web Frontend** — FastAPI + Jinja2 (Server-rendered, Responsive): หน้า Login, Upload เอกสาร, ตรวจทาน/แก้ไขข้อมูลที่ AI สกัดได้, รายการ/ประวัติ PR, หน้าอนุมัติตามบทบาท
2. **Backend API (FastAPI)** — Authentication (Session/JWT), จัดการ Upload, เรียก AI Extraction, CRUD ใบ PR, สร้าง PDF, Role-based Access Control, Audit Log
3. **AI Extraction Service** — ส่งไฟล์ (รูป/PDF) ไปยัง Google Gemini API (Free Tier) พร้อม Prompt กำหนดโครงสร้าง JSON ให้ตรงกับฟิลด์ในฟอร์ม PR แล้ว Parse ผลลัพธ์กลับมาเป็นข้อมูลตั้งต้นในฟอร์ม (ผู้ใช้ตรวจทานก่อนบันทึกเสมอ)
4. **PDF Generation Service** — สร้างไฟล์ PR ตาม Template จริงของ Sunstar (Layout เดียวกับภาพตัวอย่างหน้า 1) จากข้อมูลใน Database
5. **Database (PostgreSQL)** — เก็บ User, PR, รายการสินค้า, Budget Control, เอกสารต้นทาง, Audit Log
6. **File Storage** — เก็บไฟล์เอกสารต้นทางที่อัปโหลด และ PDF ที่ Generate แล้ว (Docker Volume)

### 3.2 Data Flow

```
ผู้ใช้ Login → อัปโหลดเอกสารต้นทาง (ใบเสนอราคา/ใบรับของ)
   → Backend เก็บไฟล์ + เรียก Gemini API สกัดข้อมูล
   → แสดงผลในฟอร์มให้ตรวจทาน/แก้ไข (บังคับ Human Review)
   → ผู้ใช้ยืนยัน → ระบบออกเลขที่ PR + บันทึกลง Database
   → Generate PDF ตาม Template
   → เข้าสู่ Workflow อนุมัติ: Requested by → Reviewed by → Approved by → Received by
   → ค้นหา/ดูประวัติ PR ได้ทุกเมื่อ พร้อม Filter (Section, Division, วันที่, เลขที่ PR, สถานะ)
```

### 3.3 Runtime Architecture (Deployment)

ยืนยันจากข้อมูล Server จริงที่ Product Owner ส่งมา (2026-09-01): SCTUBUNTU01 รัน
Docker Standalone 29.7.2 ผ่าน Portainer CE (Community Edition) และมี Nginx Proxy
Manager ติดตั้งพร้อมใช้งานแล้ว (ยังไม่มี Proxy Host ตั้งค่า) — เครื่องมี 8 CPU
Cores / 16.1 GB RAM และมีเป้าหมายรันหลาย App หลาย Database บนเครื่องเดียวกัน
(ไม่ใช่แค่ PR-Robot) จึงต้องออกแบบ Convention ที่ใช้ซ้ำได้กับทุก App ในอนาคต ไม่ใช่
ออกแบบเฉพาะ PR-Robot เท่านั้น

```
Hyper-V
└── SCTUBUNTU01 (10.206.1.107) — Ubuntu, Docker Standalone + Portainer CE
    │
    ├── Network: npm_proxy  (External, สร้างครั้งเดียว, ใช้ร่วมกันทุก App)
    │     └── เชื่อม Web Container ของทุก Stack เข้ากับ Nginx Proxy Manager
    │
    ├── Stack: pr-robot-uat
    │     ├── Network: pr-robot-uat_internal   (เฉพาะ Stack นี้)
    │     ├── Web  (FastAPI) — อยู่ทั้งใน internal และ npm_proxy, ไม่ Publish Port
    │     └── DB   (PostgreSQL) — อยู่ใน internal เท่านั้น, ไม่ Publish Port ออก Host
    │
    ├── Stack: pr-robot-prod  (โครงเดียวกับ uat แยกกันคนละ Stack/Network/Volume)
    │
    └── Stack: <app อื่นในอนาคต>  (App02, App03, ... ใช้ Convention เดียวกัน)
```

**หลักการสำหรับ Host ที่รันหลาย App หลาย Database (ใช้กับทุก App บนเครื่องนี้ ไม่ใช่แค่ PR-Robot):**

1. **1 Stack ต่อ 1 App ต่อ 1 Environment** — เช่น `pr-robot-uat`, `pr-robot-prod` ตรงตาม Diagram ใน PROJECT_STANDARD ข้อ 14 (แยก Logical Stack ต่อระบบ พร้อม DB ของตัวเอง)
2. **2 Docker Network ต่อ Stack:**
   - `internal` — สร้างใหม่ทุก Stack (เช่น `pr-robot-uat_internal`), เชื่อม Web ↔ DB ภายใน Stack เดียวกันเท่านั้น
   - `npm_proxy` — Network เดียว สร้างครั้งเดียว ใช้ร่วมกันทุก Stack, เชื่อม Web Container ของทุก App เข้ากับ Nginx Proxy Manager ให้ Route ตามชื่อ Container ได้โดยไม่ต้อง Publish Port ออกสู่ Host
3. **ห้าม Publish Port ของ Database ออกจาก Host โดยเด็ดขาดใน UAT/PROD** (ไม่มี `ports:` ใน DB Service) — เข้าถึง DB ได้จาก `internal` Network ของ Stack เดียวกันเท่านั้น ต่างจาก Dev ที่เปิด `127.0.0.1:5432` เพื่อความสะดวกบน Local ของ Developer
4. **ตั้ง Resource Limit ทุก Service** (CPU/Memory Limit ผ่าน Portainer UI หรือ Compose `deploy.resources.limits`) กัน App ใด App หนึ่งกิน CPU/RAM จนกระทบ App อื่นบนเครื่องเดียวกัน — เครื่องมีจำกัดที่ 8 Core / 16GB ต้องแบ่งให้ทุก App
5. **Naming Convention** กันชื่อชนกันเมื่อมีหลาย App ใน Portainer เดียวกัน:
   - Stack: `<app>-<env>`
   - Container: `<app>-<env>-<service>` เช่น `pr-robot-uat-web`, `pr-robot-uat-db`
   - Volume: `<app>-<env>-pgdata`
6. **Subdomain ผ่าน Nginx Proxy Manager:** `pr-robot.sct.local` (Prod), `pr-robot-uat.sct.local` (UAT) — ตั้ง Forward Hostname/Port เป็นชื่อ Container Web (เช่น `pr-robot-prod-web`) เพราะ NPM อยู่ใน `npm_proxy` Network เดียวกัน ไม่ต้องอิง IP หรือ Port ที่ Publish จาก Host เลย
7. **Backup แยกตาม Stack:** แต่ละ App มี DB ของตัวเอง จึงต้องมี Job สำรองข้อมูล (`pg_dump`) แยกต่อ Stack ด้วย — ไม่มี Backup กลางที่ครอบคลุมทุก App อัตโนมัติ

**สิ่งที่ต้องทำครั้งเดียวบน Server ก่อน Deploy App แรก (ทำผ่าน SSH หรือ Portainer UI เท่านั้น — Session นี้ไม่มีเครื่องมือเข้าถึง Server 10.206.1.107 โดยตรง):**

```bash
docker network create npm_proxy
```

จากนั้นแก้ Container ของ Nginx Proxy Manager ให้ Attach เข้า Network `npm_proxy` นี้ด้วย
(ถ้ายังไม่ได้อยู่ใน Network เดียวกัน) — ทำผ่าน Portainer → Containers → nginx-proxy-manager
→ Duplicate/Edit → Network เพิ่ม `npm_proxy` หรือแก้ Compose ของ NPM แล้ว Deploy ใหม่

Docker Compose ไฟล์จริงสำหรับ UAT/PROD ของ PR-Robot จะเขียนใน **Phase 8 (Deploy)**
ตาม Roadmap ข้อ 5 — เอกสารนี้บันทึก Convention ไว้ล่วงหน้าเพื่อให้ App อื่นในอนาคต
ใช้ Pattern เดียวกันได้ทันที

---

## 4. Database Design (High-level) — Implemented Phase 2 (2026-09-01)

**Business Decisions ที่ Product Owner ยืนยันแล้ว (มีผลต่อ Schema นี้):**
- ไม่มีแบบฟอร์มหน้า 2-3 — ใช้เฉพาะฟิลด์หน้า 1/3 ไปก่อน อาจ Redesign ทั้งฟอร์มทีหลัง
- `pr_no` เป็น Running Number ต่อเนื่องตลอด ไม่รีเซ็ตรายปี/แผนก — Unique Integer, วิธี
  Generate เลขถัดไปเป็น Business Logic ชั้น Application (Phase 4-5) ไม่ใช่ DB Sequence
- `requested_by_id` / `reviewed_by_id` / `approved_by_id` / `received_by_id` ทั้งหมดคือ
  FK ไปยัง `users` — คือผู้ใช้ที่ Login ตอนทำ Action นั้น ไม่ใช่ช่องกรอกข้อความอิสระ
  ใช้แสดงชื่อตอนพิมพ์ฟอร์มให้เซ็นจริงเท่านั้น

| Table | Field หลัก |
|---|---|
| `users` | id, name, email (unique), password_hash, department, is_active, can_review, can_approve, can_receive, is_admin, created_at |
| `purchasing_requisitions` | id, pr_no (unique), section, division, doc_date, status (`pr_status` enum: draft/reviewed/approved/received), requested_by_id (FK), reviewed_by_id/reviewed_at, approved_by_id/approved_at, received_by_id/received_at, remark, created_at, updated_at |
| `pr_items` | id, pr_id (FK, cascade delete), item_no, account_code, description, quantity, required_date, reason, ref_po |
| `pr_budget_control` | id, pr_id (FK, unique, cascade delete), account_code_1, account_code_2, budget, used_before_amount, this_application, balance |
| `source_documents` | id, pr_id (FK, nullable, set null), file_path, doc_type (`source_doc_type` enum: quotation/receiving_note/other), uploaded_by_id (FK), uploaded_at, ai_extraction_raw_json (JSON), ai_confidence |
| `audit_log` | id, pr_id (FK, nullable, set null), action, actor_id (FK, nullable), timestamp, detail (JSON) |

**Implementation:** SQLAlchemy 2.0 Typed Models ใน `app/models/`, Alembic Migration
`alembic/versions/cdfbb940153e_pr_core_schema.py` (Revises baseline `3e95cf5ab690`)

**Verification (2026-09-01):** `ruff check .` ผ่านสะอาด, `pytest` ผ่าน, ทดสอบ
Upgrade → Downgrade → Upgrade ตาม PROJECT_STANDARD ข้อ 6 ผ่านสมบูรณ์ (SQLite Sandbox),
ทดสอบ ORM Round-trip จริง (สร้าง User → PR → Item → Budget Control → Query กลับ) ผ่าน

---

## 4b. AI Extraction Design — Implemented Phase 4 (2026-09-02)

**Flow:** ผู้ใช้ Login แล้วอัปโหลดเอกสารต้นทาง (ใบเสนอราคา/ใบรับของ ไฟล์ PDF/PNG/JPEG/WEBP
ไม่เกิน 15MB) ผ่าน `POST /documents/upload` → ระบบบันทึกไฟล์ + สร้าง Record ใน
`source_documents` → เรียก Gemini สกัดข้อมูลทันที (Synchronous) → คืนผลลัพธ์ให้ผู้ใช้ดู
ถ้า Gemini เรียกไม่สำเร็จ (Network/Quota/Key ผิด) จะไม่ทำให้ Request ล้มเหลว — บันทึก
`extraction_error` ไว้แทน ผู้ใช้ Key ข้อมูลเองได้ในขั้น Review

**Extraction Schema** (`ExtractionResult`, ใช้เป็นทั้ง Response Schema ที่ส่งให้ Gemini
แบบ Structured Output และ Schema ของข้อมูลที่ผู้ใช้แก้ไข): `vendor_name`, `document_no`,
`document_date`, `items[]` (description/quantity/unit/unit_price/amount), `notes`,
`ai_confidence` (ประเมินโดย AI เอง 0-1 — เป็นค่าประมาณ ไม่ใช่ค่า Calibrate จริง)

**Business Decision (2026-09-02):** `unit_price`/`amount` เก็บไว้เป็นข้อมูลอ้างอิงเท่านั้น
เพราะ Schema ของ `pr_items` (Phase 2) ไม่มีช่องราคา มีแต่ `pr_budget_control` ระดับ
Account Code

**Schema เพิ่มเติมใน `source_documents`** (Migration `f2b89a3880f2`, Revises
`cdfbb940153e`): `extraction_error` (Text), `reviewed_data` (JSON), `reviewed_by_id` (FK
users), `reviewed_at` — แยกออกจาก `ai_extraction_raw_json` เดิมโดยเจตนา เพื่อรักษาผลดิบ
จาก AI ไว้เป็น Audit Trail เสมอ ไม่ถูกเขียนทับตอนผู้ใช้แก้ไขข้อมูล

**Endpoints:** `POST /documents/upload`, `GET /documents`, `GET /documents/{id}`,
`PATCH /documents/{id}/review` (ทุก Endpoint ต้อง Login) — บันทึก AuditLog ทุกครั้งที่
Upload/Review

**Tech:** SDK `google-genai` (ตัวเก่า `google-generativeai` เลิกใช้แล้ว — ยืนยันจาก Google
AI Docs และ GitHub `googleapis/python-genai` จริงวันที่ 2026-09-02) เรียกผ่าน
`client.models.generate_content()` พร้อม `response_json_schema` Model กำหนดผ่าน
`.env` (`GEMINI_MODEL`, Default `gemini-2.5-flash`) ไม่ Hardcode

**Verification (2026-09-02):** `ruff check .` ผ่านสะอาด, `pytest` ผ่านทั้งหมด 18/18
(รวม 7 Test ใหม่ของ Phase 4 — Mock Gemini Client ไม่ยิง Network จริง), Alembic
Upgrade → Downgrade → Upgrade → Downgrade → Upgrade ผ่านสมบูรณ์ (SQLite Sandbox, ใช้
`op.batch_alter_table()` ให้ Migration พกพาข้าม Dialect ได้), FastAPI Boot + OpenAPI
Schema ตรวจแล้วว่า Register ครบ 4 Routes, ทดสอบ Fail-fast เมื่อไม่มี API Key จริง

**ข้อจำกัดที่ต้องระบุตรงๆ:** Sandbox ที่ใช้พัฒนา (ทั้ง Cowork Container และ Device Bash)
ถูก Block Network Egress ไปยัง `generativelanguage.googleapis.com` ด้วย Policy ระดับ
Organization (ยืนยันด้วย `curl -v` เห็น `403 blocked-by-allowlist` ชัดเจน) ทำให้ไม่สามารถ
ยิง Request จริงไปหา Gemini API เพื่อพิสูจน์ Response จริงได้ในสภาพแวดล้อมนี้ — Code การ
เรียก Gemini อ้างอิงจาก README ตัวจริงของ `googleapis/python-genai` (Verified 2026-09-02)
แต่ยังไม่ผ่านการยิง Request จริงสักครั้ง จำเป็นต้อง Live Test เพิ่มเติมในสภาพแวดล้อมที่มี
Internet จริง (เช่น เครื่อง Mac ของผู้ใช้ หรือ SCTUBUNTU01) ก่อนเชื่อถือได้ 100%

---

## 4c. บันทึก PR + Generate PDF — Implemented Phase 5 (2026-09-02)

**PR Numbering:** ตาราง `pr_number_counters` (Migration `f6511609ec30`) มีแถวเดียวเสมอ
(id=1) จองเลขถัดไปแบบ Atomic ด้วย `UPDATE ... RETURNING` (ดู
`app/services/pr_numbering.py`) — ไม่พึ่ง `SELECT ... FOR UPDATE` (SQLite ไม่รองรับ)
จึงพกพาข้าม Postgres/SQLite ได้ ตรงตาม Business Decision 2026-09-01 (ต่อเนื่องตลอด
ไม่รีเซ็ต)

**Endpoints:** `POST /prs` (สร้าง Draft พร้อม Item + Budget Control, จองเลข PR
อัตโนมัติ, Requested by = ผู้ Login เสมอ, ผูก `source_document_ids` เข้ากับ PR ถ้ามี),
`GET /prs`, `GET /prs/{id}`, `PATCH /prs/{id}` (แก้ไขได้เฉพาะ Status = draft),
`GET /prs/{id}/pdf` (Generate PDF)

**PDF Generation:** Jinja2 Template (`app/templates/pr_form.html`) + WeasyPrint —
ออกแบบให้ตรงกับฟอร์มจริง FM-PU-02 Rev.2 ของ Sunstar Chemical (Thailand) ที่ Product
Owner ส่งมา (เทียบ Layout ทีละส่วน: Header/Company Block, No./Date, Section/Division,
ตาราง Item 7 คอลัมน์, Budget Control, Remark, ลายเซ็น 4 ช่อง) — **เบี่ยงเบนจากต้นฉบับ
โดยเจตนา:** ไม่ใส่เลขที่พิมพ์ล่วงหน้า "0290", ป้าย "Original" และ "PAGE 1/3" เพราะเป็น
ร่องรอยของกระดาษ Carbonless หลายชั้นที่พิมพ์ไว้ล่วงหน้า ไม่เกี่ยวกับ PDF ที่ระบบสร้างขึ้นใหม่
ทุกครั้ง — คงไว้เฉพาะ "Code: FM-PU-02 / Revision: 2" ที่ Footer เพราะเป็นข้อมูลควบคุม
เอกสารจริง

**Verification (2026-09-02):** `ruff check .` ผ่านสะอาด, `pytest` ผ่านทั้งหมด 30/30
(รวม 12 Test ใหม่ของ Phase 5 — ครอบคลุม PR Numbering ต่อเนื่อง, ผูก Source Document,
แก้ไขเฉพาะ Draft, Reject การแก้ไข PR ที่ผ่าน Workflow ไปแล้ว, PDF Endpoint คืนค่า
`application/pdf` ที่ถูกต้อง), Alembic Upgrade → Downgrade → Upgrade → Downgrade →
Upgrade ผ่านสมบูรณ์ (SQLite Sandbox) — พบและแก้ Bug จริงระหว่างทดสอบ: แก้ไข Budget
Control เดิมด้วยการสร้าง Object ใหม่ทับตรงๆ ทำให้ SQLAlchemy พยายาม Insert แถวใหม่ก่อน
Delete แถวเก่า ชน Unique Constraint บน `pr_id` (One-to-One Relationship) — แก้โดย
Mutate แถวเดิมแทนเมื่อมีอยู่แล้ว

**Visual QA จริง:** Render PDF ตัวอย่างด้วยข้อมูลจำลอง เปิดดูด้วยตาจริง (ไม่ใช่แค่ตรวจ
Code) เทียบกับฟอร์มต้นฉบับ — ภาษาไทยแสดงผลถูกต้องสมบูรณ์รวมสระซับซ้อน (เช่น สระอำ)
เมื่อใช้ฟอนต์ Noto Sans Thai — **Known Limitation:** Text Layer ภายใน PDF (สำหรับ
Copy/ค้นหาข้อความ) สูญเสียสระอำในบางคำ เป็นข้อจำกัดระดับ Library ของ WeasyPrint/Pango
ไม่กระทบการแสดงผล/พิมพ์ซึ่งเป็น Use Case หลัก — Sandbox พัฒนาไม่มีฟอนต์ไทยติดตั้งไว้
เดิม (มีแค่ Font ตระกูล TLWG) ต้องติดตั้ง `fonts-noto-core` เพิ่มเอง (ยืนยันว่าใช้ได้จริง
ทั้ง Cloud Container และ Device Bash โดยไม่ต้องใช้ Root/Sudo เพิ่มเติมนอกเหนือจาก
apt) — **สิ่งที่ต้องทำต่อ:** เมื่อสร้าง Dockerfile จริงใน Phase 8 (Deploy UAT/PROD)
ต้องติดตั้ง Font ไทยไว้ใน Image ด้วย ไม่เช่นนั้นจะ Fallback ไปใช้ Font ที่ไม่รองรับ
ภาษาไทยดีพอ — บันทึกไว้ใน Open Items แล้ว

## 4d. Workflow อนุมัติ + ประวัติ/ค้นหา — Implemented Phase 6 (2026-09-02)

**Workflow:** เดินหน้าทางเดียวตามลำดับตรงตาม `PRStatus` ที่ออกแบบไว้ตั้งแต่ Phase 2 —
`draft --review--> reviewed --approve--> approved --receive--> received` ผ่าน
`POST /prs/{id}/review`, `/approve`, `/receive` แต่ละ Endpoint ตรวจสอบทั้งสิทธิ์
(`require_can_review`/`require_can_approve`/`require_can_receive` จาก Phase 3) และ
สถานะปัจจุบันต้องตรงตามลำดับเท่านั้น (409 ถ้าข้ามขั้นหรือทำซ้ำ) — Reviewed/Approved/
Received by = ผู้ Login ตอนกดปุ่มเสมอ (Business Decision 2026-09-01) รับ `note`
ทางเลือกเพื่อบันทึกลง Audit Log

**ยังไม่มี Reject/ตีกลับ:** Schema `PRStatus` ปัจจุบันมีแค่ 4 สถานะเดินหน้าทางเดียว
ไม่มีสถานะ "ตีกลับ" หรือ "ปฏิเสธ" — ถ้าต้องการต้องคุยเรื่อง Schema เพิ่ม (เพิ่ม Status
ใหม่ + Migration + ตัดสินใจว่าตีกลับแล้วกลับไปที่ไหน) บันทึกเป็น Open Item ไว้

**ประวัติ/ค้นหา:** `GET /prs/{id}/history` คืนค่า Audit Log ทั้งหมดของ PR นั้น
เรียงตามเวลา พร้อมชื่อผู้กระทำ (Resolve จาก User ID) — `GET /prs` ขยาย Filter เพิ่ม
`status_filter`, `pr_no`, `q` (ค้นหาใน Section/Division/Remark), `doc_date_from/to`,
`requested_by_me`, `limit`/`offset` (Pagination) — `PRRead` (Response ของ
Create/Get/Update/Review/Approve/Receive) เพิ่มชื่อผู้กระทำ 4 บทบาท
(`requested_by_name` ฯลฯ) ให้อ่านง่ายขึ้นโดยไม่ต้องเทียบ User ID เอง

**Verification (2026-09-02):** `ruff check .` ผ่านสะอาด, `pytest` ผ่านทั้งหมด 43/43
(รวม 13 Test ใหม่ของ Phase 6 — ครอบคลุม Happy Path ครบ 4 สถานะ, ข้ามขั้นไม่ได้, ทำซ้ำ
ไม่ได้, ไม่มีสิทธิ์ทำไม่ได้ (403), แก้ไข PR ที่ผ่าน Review แล้วไม่ได้ (409), ค้นหา/กรอง
ทุกแบบ), Alembic Upgrade → Downgrade → Upgrade ยืนยันซ้ำ (ไม่มี Schema เปลี่ยนใน
Phase นี้)

## 4e. Web Frontend ขั้นต่ำ — Implemented Phase 7 (2026-09-02)

**สาเหตุที่เพิ่ม Phase นี้:** Roadmap เดิมข้าม Frontend ไปตรง Phase Deploy ทั้งที่ตอนเริ่ม
โปรเจกต์เลือกไว้ชัดเจนว่าต้องการ "Upload ผ่านหน้าเว็บ" — เมื่อพบช่องว่างนี้ได้หยุดถาม
Product Owner ก่อนแทนที่จะเดาเอง (2026-09-02) และได้รับคำตอบให้สร้าง Frontend ขั้นต่ำ
ก่อน Deploy

**สถาปัตยกรรม:** Server-rendered Jinja2 HTML Shell (ไม่มี Build Step, ไม่มี JS
Framework) อยู่ใต้ FastAPI Route Prefix `/app` (แยกจาก JSON API เดิมชัดเจน เช่น
`/app/prs/{id}` หน้าเว็บ vs `/prs/{id}` JSON API — กัน Path ชนกัน) ข้อมูลทั้งหมดโหลด/
บันทึกผ่าน `fetch()` ไปยัง JSON API เดิมของ Phase 3-6 จาก Browser โดยตรง — **ไม่มีการ
แก้ไข Backend API เลยแม้แต่บรรทัดเดียว** ในเชิง Behavior (มีแค่เพิ่ม Route ใหม่ + Mount
Static Files ใน `app/main.py`)

**Auth ฝั่ง Client ทั้งหมด:** หน้า Route คืน HTML เสมอไม่ว่าจะ Login หรือยัง — ไม่ Enforce
ที่ Server เพื่อไม่ต้อง Duplicate Logic ตรวจสิทธิ์ระหว่าง Server/Client — `static/app.js`
มี `requireLogin()` เรียก `GET /auth/me` ตอนโหลดหน้า ถ้า 401 จะ Redirect ไป `/app/login`
เอง

**หน้าที่มี:** `login.html`, `dashboard.html` (List + Filter: ค้นหา/สถานะ/เลขที่ PR/ช่วง
วันที่/เฉพาะที่ฉันสร้าง), `pr_edit.html` (ใช้ร่วมกันทั้งสร้าง/แก้ไข — Prefill รายการจาก
เอกสารที่ตรวจทานแล้วถ้ามาจากปุ่ม "ไปสร้าง PR จากเอกสารนี้"), `pr_detail.html` (ดู PR +
ปุ่ม Workflow ตามสิทธิ์ผู้ใช้ + ประวัติ + ลิงก์ดาวน์โหลด PDF), `upload.html` (อัปโหลด +
แสดงผลตรวจทานจาก AI หรือกรอกเองถ้า AI ล้มเหลว)

**Verification (2026-09-02) — 2 รอบ ตามมาตรฐาน "ต้องทดสอบจริง":**

1. **Unit/Smoke Test (Scratch venv):** `ruff check .` ผ่านสะอาด, Alembic
   Upgrade → Downgrade → Upgrade → Downgrade → Upgrade ผ่านซ้ำ (ไม่มี Schema เปลี่ยน
   ใน Phase นี้), `pytest` ผ่านทั้งหมด **51/51** (43 เดิม + 8 Smoke Test ใหม่ของทุก Page
   Route ใน `tests/test_pages.py` — ยืนยัน HTTP 200 + Content-Type ถูกต้อง + เนื้อหาที่
   คาดหวังในแต่ละหน้า, ยืนยัน `StaticFiles` Mount ใช้งานได้จริงโดยไม่ต้องเพิ่ม `aiofiles`
   เป็น Dependency ใหม่)

2. **Browser E2E จริง (Playwright + Chromium):** รันแอปจริงผ่าน `uvicorn` (SQLite
   ชั่วคราว) แล้วขับเคลื่อน Browser จริงทำ Flow เต็ม: Login จริง → สร้าง PR ผ่านฟอร์มจริง
   → Review → Approve → Receive (ผ่านปุ่มจริงบนหน้าเว็บ ไม่ใช่เรียก API ตรง) → ดาวน์โหลด
   PDF จริงแล้วตรวจ Byte Header + ขนาดไฟล์ → เปิดดู PDF ที่ Render จริงด้วยตาเพื่อยืนยัน
   ภาษาไทยแสดงผลถูกต้อง (Section/Division/Description/Reason ภาษาไทย + ชื่อผู้ใช้ 4
   บทบาทถูก Auto-fill จากผู้ Login จริง) — ทดสอบเพิ่มเติมที่หน้า Upload ว่าเมื่อ Gemini
   API เรียกไม่สำเร็จ (Sandbox Block Network ไปยัง Google จริง ได้ Error 403 จาก Proxy
   จริง ไม่ใช่ Mock) หน้าเว็บแสดงข้อความ Error ภาษาไทยและยังให้กรอกข้อมูลเองต่อได้ ไม่ค้าง
   หรือ Crash — **ผลลัพธ์: ผ่านทุกจุดที่ทดสอบ (21/21 Assertion)**

   **พบ 1 รายการที่ตรวจสอบแล้วไม่ใช่ Bug:** ระหว่าง E2E เจอ Console Message
   `Failed to load resource: 404` หนึ่งครั้ง — ตรวจสอบด้วยการดัก Network Response จริง
   ของหน้าเว็บทั้ง Flow พบว่าไม่มี Request ใดของแอปเราเองที่ได้ 404 (Response ที่ผิดพลาด
   มีแค่ `401` จาก `/auth/me` ตอนยังไม่ Login ซึ่งเป็นพฤติกรรมที่ถูกต้องตามออกแบบ) —
   สรุปว่าเป็น Noise จาก Sandbox เอง (Chromium พยายามเรียก Google Domain เช่น
   `content-autofill.googleapis.com` ที่ถูก Egress Proxy ขององค์กร Block) ไม่ใช่ปัญหาจาก
   Code ของเรา — บันทึกไว้เพื่อความโปร่งใส ไม่ได้ปิดบัง

**ข้อจำกัดที่ทราบ (Known Limitations):**
- ไม่มี CSS Framework — ใช้ Custom CSS ขั้นต่ำ (`app/static/style.css`) เน้นใช้งานได้
  ก่อน ความสวยงามเป็นรอง เหมาะสำหรับ Internal Tool ระยะแรก
- Auth บังคับฝั่ง Client เท่านั้น (ตามที่ออกแบบไว้ข้างต้น) — หน้า HTML เปิดดู Source ได้
  โดยไม่ต้อง Login แต่ข้อมูลจริงทั้งหมดยังถูก JSON API ป้องกันด้วย Cookie/JWT เหมือนเดิม
  (ไม่ใช่ช่องโหว่ เพราะไม่มีข้อมูลจริงอยู่ใน HTML Shell)
- ยังไม่มี Favicon (Browser จะขึ้น 404 เงียบๆ ที่ `/favicon.ico` — Cosmetic ไม่กระทบ
  การทำงาน)
- ยังไม่ได้ทดสอบบน Browser จริงของผู้ใช้ (Chrome/Safari/Edge บนเครื่องจริง) มีแค่
  Chromium Headless ใน Sandbox — ควรให้ Product Owner ลองใช้จริงใน UAT (Phase 8)

## 4f. Phase 8 — Production Readiness: Dockerfile + Security Review (2026-09-02, กำลังดำเนินการ)

**สถานะ:** ทำเสร็จเฉพาะส่วนที่ทำได้ใน Sandbox แล้ว (Dockerfile, docker-compose.prod.yml,
Security Review, อัปเกรด Dependency ตามผลสแกนจริง) — ส่วน Deploy จริงบน SCTUBUNTU01
ยังไม่เริ่ม รอ Subdomain จาก Product Owner + ทำทีละคำสั่งผ่าน SSH ตามที่ตกลงกันไว้

### Dockerfile + docker-compose.prod.yml

Multi-stage Build (`builder` ติดตั้ง Dependency ลง venv แยก, `runtime` มีแค่ Library ที่
จำเป็นจริง) รันด้วย User ที่ไม่ใช่ Root (`prrobot`), มี HEALTHCHECK เรียก `/health`,
`docker-entrypoint.sh` รัน `alembic upgrade head` ก่อน Start ทุกครั้งอัตโนมัติ —
ติดตั้ง `fonts-noto-core` ใน Image ตามที่บันทึกเป็น Open Item ไว้ตั้งแต่ Phase 5/7
(ยืนยันชื่อ Package ถูกต้องแล้วเทียบกับ apt Index จริง — ดูหัวข้อข้อจำกัดด้านล่าง)

`docker-compose.prod.yml` ใช้ไฟล์เดียวกัน Deploy ได้ทั้ง UAT/PROD ผ่าน
`docker compose -p pr-robot-<env> --env-file .env.<env>` ตรงตาม Convention ที่วางไว้
ล่วงหน้าในข้อ 3.3 (Network `npm_proxy` ภายนอก + `internal` แยกต่อ Stack, ไม่ Publish
Port Database, Resource Limit ต่อ Service) — Template `.env.prod.example` ระบุ Field
ที่ต้องกรอกจริงบน Server (ไม่ Commit ค่าจริงขึ้น Git)

### Security Review — พบและแก้ไขจริง 1 รายการสำคัญ

**[แก้แล้ว] HTML/CSS Injection ใน PDF ผ่าน Field ที่ผู้ใช้ควบคุมได้ (Critical):**
ตรวจโค้ด `app/services/pr_pdf.py` พบว่า Jinja2 `Environment()` ที่ใช้ Render Template
ก่อนส่งให้ WeasyPrint ไม่ได้เปิด `autoescape` — Field อย่าง Description/Reason/
Section/Division/Remark มาจาก Gemini AI สกัดข้อมูลจากเอกสารที่อัปโหลด (ควบคุมโดย
ผู้ไม่หวังดีได้ผ่านเอกสารปลอม) หรือผู้ใช้พิมพ์ตรงๆ ก็ได้ — เมื่อรวมกับช่องโหว่ SSRF ที่
รู้จักแล้วใน WeasyPrint (`default_url_fetcher` ไม่ป้องกัน Redirect ไป Internal
Network/Cloud Metadata อย่างสมบูรณ์ — PYSEC-2026-2034 พบจาก `pip-audit`) จะทำให้ PDF
Generation กลายเป็นช่องทาง SSRF จริงได้ (ฝัง `<link rel="attachment"
href="http://169.254.169.254/...">` ผ่าน Description) — **แก้แล้ว** ด้วย
`autoescape=select_autoescape(["html"])` และเขียน Regression Test พิสูจน์จริงใน
`tests/test_pr_pdf_security.py` (ยืนยันว่า Payload อันตรายถูก Escape เป็นข้อความ
เฉยๆ ไม่ใช่ Tag ที่ Render จริง และข้อความไทย/อังกฤษปกติยังแสดงผลถูกต้องเหมือนเดิม)
— หน้าเว็บ Phase 7 (`app/api/routes/pages.py`) ใช้ FastAPI `Jinja2Templates` ซึ่ง
เปิด Autoescape เป็นค่าเริ่มต้นอยู่แล้ว ไม่ได้รับผลกระทบ

**[ยืนยันแล้วว่าไม่มีปัญหา]** Cookie Login เป็น HttpOnly + SameSite=Lax +
Secure (เปิดอัตโนมัติเมื่อ `APP_ENV` ไม่ใช่ dev/test) อยู่แล้วตั้งแต่ Phase 3, Upload
File ตรวจ Content-Type Allowlist + ขนาดสูงสุด 15MB + ไม่เชื่อ Filename ผู้ใช้ (ใช้
UUID สุ่มตั้งชื่อไฟล์เก็บจริง ตัดความเสี่ยง Path Traversal), Bootstrap Admin Script
รับ Credential ผ่าน Argument เท่านั้น ไม่ Hard-code, ไม่มี CORS Middleware เปิดไว้
(ไม่จำเป็นเพราะ Frontend/API อยู่ Origin เดียวกัน), RBAC ตรวจสิทธิ์ครบทุก Endpoint
ที่ควรมี

**[Dependency Scan จริงด้วย `pip-audit`]** พบ 25 ช่องโหว่ใน 7 Package — อัปเกรดแล้ว
5 ตัว (`fastapi` 0.115.6→0.141.1 ต้องยกใหญ่ตามเพื่อดึง `starlette` เวอร์ชันที่แก้ Host
Header Vulnerability เพราะเวอร์ชันเดิมล็อก `starlette<0.42` ซึ่งไม่มี Patch ให้เลย,
`python-multipart` 0.0.20→0.0.31, `jinja2` 3.1.5→3.1.6, `python-dotenv` 1.0.1→1.2.2,
`python-jose` 3.3.0→3.4.0) เหลือ 9 ช่องโหว่ใน 3 Package ที่ประเมินแล้วว่าความเสี่ยงต่ำ
สำหรับระบบนี้โดยเฉพาะ (ไม่ใช่ไม่มีช่องโหว่จริง แต่ Attack Path ที่จำเป็นไม่ตรงกับการใช้งาน
จริงของเรา):
- `weasyprint` SSRF (PYSEC-2026-2034) — Mitigate แล้วด้วย Autoescape ด้านบน
  (ปิดช่องทางเดียวที่ผู้ใช้จะฝัง URL เข้าไปได้) ยังไม่อัปเกรด Major Version (63.1→68.0
  ห่างกัน 5 เวอร์ชัน) เพราะเสี่ยงกระทบ Thai PDF Rendering ที่ตรวจสอบละเอียดไว้แล้วตั้งแต่
  Phase 5 — บันทึกเป็น Open Item ให้ทดสอบแยกต่างหากทีหลัง ไม่ใช่ตอนก่อน Deploy
- `pyasn1`/`ecdsa` (DoS จาก ASN.1 Parsing / Timing Attack บน ECDSA) — เป็น
  Dependency ของ `python-jose[cryptography]` แต่ระบบเราใช้ HS256 (Symmetric HMAC)
  เซ็น JWT เท่านั้น ไม่เคย Parse ASN.1/ใช้ ECDSA Key เลยในโค้ดจริง (`app/core/
  security.py`) จึง Attack Path ที่ต้องมีอยู่จริง (Decode ASN.1/Key จากภายนอกที่ไม่
  น่าเชื่อถือ) ไม่เกิดขึ้นในระบบนี้ — `python-jose` เองก็ล็อก `pyasn1<0.5.0` ไว้ทำให้
  บังคับอัปเกรดแยกไม่ได้อยู่แล้ว, `ecdsa` ทาง Upstream ประกาศไม่แก้ (Side-channel
  ถือว่านอกขอบเขต)

**Verification (2026-09-02):** หลังแก้/อัปเกรดแล้ว รันซ้ำครบชุดใน Scratch venv —
`ruff check .` สะอาด, Alembic Upgrade→Downgrade→Upgrade ผ่าน, `pytest` ผ่าน **53/53**
(เพิ่ม 2 Test ใหม่เฉพาะช่องโหว่นี้ใน `tests/test_pr_pdf_security.py`) — และรัน Playwright
E2E ซ้ำอีกรอบ (คนละรอบจาก Phase 7) เจาะจงพิสูจน์ว่าการยก `fastapi`/`starlette` ครั้งใหญ่
(Starlette 0.41.3 → 1.6.0 ผ่าน Dependency Resolution) ไม่กระทบพฤติกรรมจริง: Login
ด้วย Cookie, Multipart File Upload (Package ที่อัปเกรดตรงๆ), StaticFiles Mount,
Jinja2Templates ยังทำงานถูกต้องทั้งหมด ผ่าน Flow เต็มอีกครั้ง 10/10 จุดตรวจสอบ

### ข้อจำกัดที่พบระหว่างทำ Phase นี้ (บันทึกตามจริง)

**ยังไม่สามารถ Build/รัน Docker Image จริงใน Sandbox ได้:** Egress Proxy ของ
Sandbox บล็อก Container Registry ทุกตัวที่ลองแล้ว (Docker Hub, public.ecr.aws,
quay.io — ทั้งหมดคืน `403 Forbidden`) รูปแบบเดียวกับที่ Block
`generativelanguage.googleapis.com` ใน Phase 4 — จึง Build Image จาก Dockerfile
จริงไม่ได้ในนี้ ตรวจสอบเท่าที่ทำได้แทน: (1) เทียบชื่อ apt Package ทุกตัวใน Dockerfile
กับ apt Index จริงของ Ubuntu 24.04 (Package Family เดียวกับ Debian Slim ที่เป็น Base
Image) ยืนยันว่ามีอยู่จริงทุกตัว (`libpango-1.0-0`, `libpangoft2-1.0-0`,
`libgdk-pixbuf-2.0-0`, `shared-mime-info`, `fonts-noto-core`, `curl`,
`build-essential`, `libpq-dev`) (2) Python Dependency ชุดเดียวกับที่จะติดตั้งใน Image
(`requirements.txt`) ผ่านการทดสอบเต็มรูปแบบแล้วในข้อบนนี้ (3) ตรวจโค้ด Dockerfile/
entrypoint ด้วยตาอย่างละเอียดทีละบรรทัด — **สิ่งที่ยังพิสูจน์ไม่ได้จนกว่าจะถึง
SCTUBUNTU01 จริง (มี Internet ปกติ):** Image Build จบสำเร็จจริงหรือไม่, ขนาด Image,
Runtime Library ครบตามที่ WeasyPrint ต้องการจริงหรือไม่ (โดยเฉพาะถ้า Debian Slim มี
ชื่อ Package ต่างจาก Ubuntu ที่ตรวจสอบไว้) — **แผนคือ Build + รัน Health Check +
ทดสอบ PDF ภาษาไทยจริงเป็นขั้นตอนแรกบน SCTUBUNTU01 ก่อนเข้าสู่ UAT Walkthrough**
ไม่ปิดบังว่าเป็นข้อจำกัดจริง ไม่ใช่ "ตรวจแล้วผ่าน" เหมือน Dependency อื่น

## 4g. Scope Revision — ตัด Workflow อนุมัติออก + Multi-document Upload — Implemented Phase 9 (2026-09-03)

**สาเหตุ:** หลัง Deploy UAT สำเร็จครบ Phase 8 (Container Healthy, Migration สะอาด,
Login ใช้งานได้จริง) Product Owner ทดลองใช้งานจริงแล้วให้ Feedback ตรงไปตรงมาว่า
โปรแกรม "ไม่ได้ตามที่อยากได้เลย ห่างไกลจากที่คิดไว้มาก" และเมื่อถามต่อว่าจุดไหน
คำตอบคือ **"ออกแบบผิดตั้งแต่แรก"** — ไม่ใช่ Bug หรือรายละเอียดเล็กน้อย แต่เป็น Concept
พื้นฐานของ Workflow อนุมัติทั้งระบบ (Phase 3 RBAC + Phase 6 Workflow) ที่วางไว้ผิดตั้งแต่
Phase 0/2 แม้จะผ่านการอนุมัติจาก Product Owner ทุก Gate มาแล้วก็ตาม

**วิธียืนยัน Requirement ใหม่:** ไม่รีบแก้โค้ดทันทีจาก Feedback ที่ยังกว้างเกินไป — ถาม
คำถามปลายปิดหลายรอบ + ขอตัวอย่างเอกสารจริง 2 ไฟล์ (ใบเสนอราคาจาก Supplier จริง +
PR ที่กรอกมือจริงจากเอกสารนั้น) มาวิเคราะห์เทียบกันโดยตรง ก่อนสรุป Scope ใหม่และเริ่ม
เขียนโค้ด — ตัวอย่างจริงยืนยันว่า Description ในฟอร์ม PR ที่กรอกมือ ผู้ใช้ Copy
`PRODUCT NAME` + `PRODUCT DESCRIPTION` + `COLOR` (คนละคอลัมน์ในใบเสนอราคา) มารวมกัน
เป็นบรรทัดเดียว เช่น `"SILICONE PAPER / BS-W 1000MM.XL300M. / (Color: Blonde)"` และ
Quantity รวม `quantity` + `unit` เช่น `"2 Roll"`

**สรุป Requirement ที่ถูกต้อง (ยืนยันจากผู้ใช้ทุกข้อ):**

1. **ไม่มี Workflow อนุมัติในระบบอีกต่อไป** — Reviewed by / Approved by / Received by
   เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกจากระบบไปใช้งานนอกระบบทั้งหมด ไม่มี Action ใดใน
   ระบบที่ผลิตข้อมูล 3 ช่องนี้ได้อีกต่อไป — ผู้ใช้พิมพ์ PR แล้วเอาไปขอลายเซ็นเอง
2. **PR เหลือ 2 สถานะ:** `draft` (แก้ไขได้ปกติ) และ `finalized` (ล็อกแก้ไขไม่ได้) —
   เปลี่ยนสถานะอัตโนมัติตอนกดพิมพ์/ดาวน์โหลด PDF ครั้งแรก ไม่ต้องมีปุ่ม "เสร็จสิ้น" แยก
3. **AI อ่านเอกสารต้นทางได้หลายไฟล์พร้อมกัน** (อัปโหลดพร้อมกันหลายไฟล์) แล้วรวมรายการ
   สินค้าจากทุกไฟล์เป็น Item List เดียวของ PR — ไม่ใช่ทีละไฟล์แบบเดิม
4. **ยังต้องการให้ผู้ใช้ตรวจทาน/แก้ไขข้อมูลที่ AI อ่านมา** แต่ตรวจทานครั้งเดียวที่หน้า
   สร้าง PR (หลังรวมข้อมูลจากทุกเอกสารแล้ว) ไม่ใช่ตรวจทานทีละเอกสารก่อนแบบเดิม
5. **AI แยกฟิลด์ `product_name` / `description` / `color`** ให้ตรงกับคอลัมน์จริงในใบ
   เสนอราคาส่วนใหญ่ แล้วฝั่ง Frontend รวมเป็น Description บรรทัดเดียวตาม Format ที่
   ผู้ใช้เขียนมือจริง (ดูตัวอย่างด้านบน) — Budget Control ยังคงกรอกมือทั้งหมดเหมือนเดิม
   ไม่ใช้ AI สกัด (ยืนยันไม่เปลี่ยนจาก Phase 5)
6. **รองรับเอกสารต้นทาง 4 ประเภท:** ใบเสนอราคา (Quotation), ใบยืมสินค้า (Borrow
   Note — ใหม่), ใบส่งสินค้า (Delivery Note — ใหม่), ใบรับของ (Receiving Note — เดิม) —
   ต้องรองรับ Supplier หลายรายที่ Layout ตารางไม่เหมือนกันเลย (Prompt ต้องอ่านตาม
   ความหมาย ไม่ใช่ตำแหน่งคอลัมน์ตายตัว)
7. **ไม่บังคับเลือกประเภทเอกสารก่อน Upload อีกต่อไป** — AI เดาประเภทเอกสารเองจาก
   เนื้อหา (`detected_doc_type`) ใส่ให้เป็นค่าเริ่มต้น ผู้ใช้แก้ไขทีหลังได้เสมอถ้า AI เดาผิด
   ("ให้ AI copy มาใส่ โดยที่ใส่มาแล้ว user review จะเพิ่มจะลบเอง" — คำตอบผู้ใช้ตรงๆ)
8. **ยังต้อง Login** — เพื่อ Track ว่าใครสร้าง PR ไหน (`requested_by`) และใช้กรอง
   History/ค้นหา แต่ตัด RBAC Flag `can_review`/`can_approve`/`can_receive` ออกทั้งหมด
   เหลือแค่ `is_admin` สำหรับจัดการ User

**สิ่งที่ตัดออกจากระบบจริง (Implemented):**
- `users`: Drop `can_review`, `can_approve`, `can_receive` (เหลือ `is_admin`)
- `purchasing_requisitions`: Drop `reviewed_by_id/at`, `approved_by_id/at`,
  `received_by_id/at` — เหลือ `requested_by_id` อย่างเดียว
- `PRStatus`: 4 ค่า (`draft`/`reviewed`/`approved`/`received`) → 2 ค่า
  (`draft`/`finalized`) — Migrate ข้อมูลเดิมจริง ไม่ทิ้ง (ค่าที่ไม่ใช่ `draft` ทั้งหมด
  Map เป็น `finalized`)
- Endpoint `POST /prs/{id}/review`, `/approve`, `/receive` ถูกลบทั้งหมด — แทนที่ด้วย
  Logic ใน `GET /prs/{id}/pdf`: เปลี่ยนสถานะเป็น `finalized` อัตโนมัติถ้ายังเป็น `draft`
  (Generate PDF สำเร็จก่อนค่อย Finalize กันไม่ให้ Render พังแล้ว PR ถูกล็อกไปด้วย)
- หน้าเว็บ `pr_detail.html` ตัดปุ่ม Review/Approve/Receive และช่องแสดง Reviewed/
  Approved/Received by ออกทั้งหมด — `pr_form.html` (Template PDF) ยังคงช่องเซ็นชื่อ
  4 ช่องไว้ตามฟอร์ม FM-PU-02 เดิม แต่ 3 ช่องหลัง (Reviewed/Approved/Received by)
  Render เป็นช่องว่างเสมอ ไม่ผูกกับข้อมูลในระบบอีกต่อไป — เหลือแค่ "Requested by" ที่
  แสดงชื่อจริง

**สิ่งที่เพิ่มเข้าไปใหม่ (Implemented):**
- `SourceDocType` เพิ่ม `borrow_note`, `delivery_note`; `source_documents.doc_type`
  เปลี่ยนเป็น Nullable (ไม่บังคับตอน Upload) — AI เดาแล้วเติมให้อัตโนมัติหลัง Extract
  สำเร็จ ผู้ใช้แก้ไขทีหลังผ่าน `PATCH /documents/{id}/review` (เพิ่ม Field `doc_type`
  ให้แก้พร้อมกันได้ในคำขอเดียว)
- `ExtractedItem` เพิ่ม `product_name`, `color`; `ExtractionResult` เพิ่ม
  `detected_doc_type` — Prompt Gemini เขียนใหม่ทั้งหมดให้รองรับ Supplier หลายรูปแบบ
  อ่านตามความหมายของแต่ละส่วน ไม่ใช่ตำแหน่งตายตัว
- หน้า Upload (`upload.html`) รองรับเลือกไฟล์พร้อมกันหลายไฟล์ (`<input multiple>`)
  Loop อัปโหลดทีละไฟล์ แสดงผลสรุปสั้นๆ ต่อไฟล์ (ชื่อไฟล์ + ประเภทเอกสารที่ AI เดา
  แก้ไขได้ + จำนวนรายการที่อ่านได้) แล้วเลือกเอกสารที่ต้องการไปสร้าง PR ต่อ
  (`/app/prs/new?source_document_ids=1,2,3` — รองรับหลาย ID คั่นด้วย `,`)
- หน้าสร้าง PR (`pr_edit.html`) รวมรายการสินค้าจากทุกเอกสารที่ติ๊กเลือกไว้แบบ Live
  (เปลี่ยน Checkbox ปุ๊บ คำนวณรายการใหม่ทันที) พร้อมรวม `product_name` + `description`
  + `color` → Description บรรทัดเดียว และ `quantity` + `unit` → Quantity บรรทัดเดียว
  ตาม Format ที่ผู้ใช้เขียนมือจริง — ผู้ใช้แก้ไข/เพิ่ม/ลบรายการเองต่อได้เสมอก่อนบันทึก

**Migration (`a1c3e9f0b2d4_scope_revision_drop_workflow.py`):** ต้อง Drop Default เดิม
ของ Column `status` ก่อน `ALTER COLUMN ... TYPE` เสมอ (Default ผูกกับ OID ของ Enum
Type เดิมอยู่ Cast ไปหา Type ใหม่อัตโนมัติไม่ได้แม้ Value เป็น String เดียวกัน — เจอ
`DatatypeMismatch` จริงตอนทดสอบ แก้แล้วด้วย `ALTER TABLE ... ALTER COLUMN status DROP
DEFAULT` ก่อนสร้าง Type ใหม่ ทั้งใน `upgrade()`/`downgrade()`) — ทดสอบเต็มรูปแบบด้วย
ข้อมูลจำลองครบทั้ง 4 สถานะเดิมบน PostgreSQL 16 จริง (ไม่ใช้ SQLite) ยืนยัน Upgrade →
Downgrade → Upgrade ผ่านและ Remap ข้อมูลถูกต้องทุกครั้ง (`draft`→`draft`,
`reviewed`/`approved`/`received`→`finalized`)

**Verification (2026-09-03):** `ruff check .` สะอาด, `pytest` ผ่านทั้งหมด 51/51 (เขียน
ใหม่/ปรับปรุง `test_pr_workflow.py`, `test_purchasing_requisitions.py`,
`test_auth.py`, `test_documents.py` ให้ตรงกับ Scope ใหม่ — ตัด Test Workflow เดิมออก
ทั้งหมด เพิ่ม Test สถานะ Finalize อัตโนมัติตอนดาวน์โหลด PDF, Test AI เดาประเภทเอกสาร
เอง), Alembic Migration ทดสอบจริงกับ PostgreSQL 16 ตามข้างต้น — Deploy จริงบน
SCTUBUNTU01 สำเร็จ (Migration ขึ้น `a1c3e9f0b2d4` Container Healthy `/health` และ
`/health/db` ตอบ 200 ปกติ)

**Bug จริง 2 รายการที่เจอตอน UAT Walkthrough แรกหลัง Deploy (2026-09-03, แก้แล้ว):**

1. **`GEMINI_MODEL` เดิม (`gemini-2.5-flash`) เลิกให้บริการกับ API Key ใหม่แล้ว**
   (Gemini ตอบ `404 NOT_FOUND` พร้อมแนะนำ `gemini-3.6-flash` แทน) — ไม่ใช่ Bug โค้ด
   เพราะออกแบบให้ปรับ Model ผ่าน `.env` (`GEMINI_MODEL`) โดยไม่ Hardcode ไว้แล้วตั้งแต่
   Phase 4 (ดู 4b.) แก้แค่แก้ค่าใน `.env.uat` บน Server เป็น `gemini-3.6-flash`
   (ตรวจสอบแล้วว่าเป็น Model จริงที่ใช้งานได้ปัจจุบันผ่าน `ai.google.dev/gemini-api/
   docs/models`) แล้ว Restart Container — ไม่ต้อง Build Image ใหม่
2. **`503 UNAVAILABLE` (Gemini "currently experiencing high demand") เป็นระยะ** —
   Error ชั่วคราวฝั่ง Google เอง ก่อนหน้านี้ระบบไม่ Retry ให้อัตโนมัติ ผู้ใช้ต้อง Upload
   ซ้ำเอง — **แก้แล้ว:** เพิ่ม Auto-Retry แบบ Exponential Backoff ใน
   `GeminiExtractionService.extract()` (สูงสุด 3 ครั้ง รอ 2 วิ แล้ว 4 วิ ระหว่างครั้ง)
   เฉพาะ Error ที่เป็น Rate Limit (429) หรือ Server Error ฝั่ง Google (5xx) หรือ Network
   Timeout/Connection Error เท่านั้น — Error ถาวร (เช่น 404 ข้างบน, 400, 401/403) ไม่
   Retry เพราะ Retry ไปก็ได้ผลเดิมทุกครั้ง เสียเวลาผู้ใช้รอเปล่าๆ — Unit Test ใหม่ครบใน
   `tests/test_gemini_extraction.py` (7 Test — สำเร็จตั้งแต่ครั้งแรก, Retry แล้วสำเร็จ
   ทั้ง 503/429, ไม่ Retry ตอน 404, หมดโควต้า Retry แล้ว Fail จริง, Response ว่าง/
   JSON ผิด Format ไม่ Retry) — Sleep Function Inject ได้เพื่อ Test ไม่ต้องรอจริง

**Verification รอบ 2 (2026-09-03, หลังแก้ Retry):** `ruff check .` สะอาด, `pytest`
ผ่านทั้งหมด 58/58 (เพิ่ม 7 Test ของ `test_gemini_extraction.py`)

## 5. Roadmap (แบ่ง Phase ตามมาตรฐาน — รออนุมัติก่อนเริ่มแต่ละ Phase)

| Phase | เนื้อหา | Output |
|---|---|---|
| 0 | Kickoff & Design (เอกสารนี้) | เอกสารนี้ + อนุมัติจาก Product Owner |
| 1 | Infra Readiness: Init Repo, Docker Compose (Dev DB), Alembic baseline, โครง FastAPI project, `.env.example` | Repo พร้อม Dev Environment รันได้ |
| 2 | Database Schema + Migration จริงตามข้อ 4 | **เสร็จแล้ว (2026-09-01)** — Schema ใช้งานได้ ผ่าน Alembic Upgrade/Downgrade/Upgrade + ORM Round-trip จริง |
| 3 | Authentication & Role-based Access (Login, จัดการ User/Role) | **เสร็จแล้ว (2026-09-01)** — Login/Logout/Me ผ่าน HttpOnly Cookie + JWT, Role-based Access Control (can_review/can_approve/can_receive/is_admin), Admin สร้าง/ดูรายชื่อ User ได้, สคริปต์ Bootstrap Admin คนแรก |
| 4 | Upload + AI Extraction (Gemini) + หน้าตรวจทาน/แก้ไขข้อมูล | **เสร็จแล้ว (2026-09-02)** — Upload PDF/รูปภาพ → Gemini สกัดข้อมูลแบบ Structured JSON → บันทึก reviewed_data เมื่อผู้ใช้แก้ไข (ดู 4b.) |
| 5 | บันทึก PR + Generate PDF ตาม Template จริง | **เสร็จแล้ว (2026-09-02)** — POST/GET/PATCH /prs + GET /prs/{id}/pdf ตรงตามฟอร์ม FM-PU-02 (ดู 4c.) |
| 6 | Workflow อนุมัติ (Reviewed/Approved/Received) + ประวัติ/ค้นหา PR | **เสร็จแล้ว (2026-09-02)** — POST /prs/{id}/review,approve,receive + GET /prs/{id}/history + GET /prs Filter ครบ (ดู 4d.) |
| 7 | Web Frontend ขั้นต่ำ (Login, Upload+ตรวจทาน, สร้าง/ดู/แก้ไข PR, ปุ่ม Workflow, ดาวน์โหลด PDF) | **เสร็จแล้ว (2026-09-02)** — Server-rendered Jinja2 Shell + Vanilla JS ทับ JSON API เดิม (ไม่มี Framework/Build Step) ครบทุกหน้า — Login, Dashboard+ค้นหา/กรอง, สร้าง/แก้ไข PR, ดู PR+ปุ่ม Workflow+ประวัติ+ดาวน์โหลด PDF, Upload+ตรวจทานเอกสาร (ดู 4e.) |
| 8 | UAT รวม + Security Review + Deploy จริงบน SCTUBUNTU01 | **เสร็จแล้ว (2026-09-02)** — Deploy UAT สำเร็จ, Container Healthy, Migration สะอาด, Login ใช้งานได้จริง — ตามด้วย Product Owner Feedback ว่า Design ผิดตั้งแต่แรก นำไปสู่ Phase 9 |
| 9 | Scope Revision: ตัด Workflow อนุมัติออก + Multi-document Upload | **เสร็จแล้ว (2026-09-03, กำลังรอ Deploy ซ้ำบน UAT)** — ตาม Feedback จริงจาก Product Owner (ดู 4g.) |
| 10 | Documentation (README/RELEASE) + Lessons Learned | เอกสารครบตามมาตรฐานข้อ 10 และ 13 |

---

## 6. Open Items

**ตอบแล้ว (2026-09-01):**
- [x] แบบฟอร์มหน้า 2/3, 3/3 — ไม่มี ใช้เฉพาะหน้า 1 ไปก่อน อาจ Redesign ทั้งฟอร์มทีหลัง
- [x] รูปแบบเลขที่ PR — Running Number ต่อเนื่องตลอด ไม่รีเซ็ตรายปี/แผนก
- [x] Requested/Reviewed/Approved/Received by — คือผู้ใช้ที่ Login ทำ Action นั้น ไม่ใช่ช่องกรอกข้อมูล

**ตอบแล้ว (เพิ่มเติม):**
- Google Gemini API Key: ได้รับและตั้งค่าใน `.env` แล้ว (2026-09-02, ไม่ Commit ขึ้น Git) —
  ยังไม่ผ่านการยิง Request จริงเพราะ Sandbox พัฒนา Block Network ไปยัง Google API (ดู
  ข้อจำกัดใน 4b.) ต้อง Live Test เพิ่มเติมนอก Sandbox

- [ ] ติดตั้งฟอนต์ไทย (`fonts-noto-core` หรือเทียบเท่า) ใน Docker Image ตอนสร้าง
  Dockerfile จริง — จำเป็นตอน Phase 8 ไม่เช่นนั้น PDF จะ Fallback ไป Font ที่ไม่รองรับ
  ภาษาไทยดีพอ (ดู 4c.)

- [x] Reject/ตีกลับ PR: **ไม่เกี่ยวข้องอีกต่อไป** — Phase 9 ตัด Workflow อนุมัติในระบบ
  ออกทั้งหมดแล้ว (ดู 4g.) Reviewed/Approved/Received by เป็นลายเซ็นสดบนกระดาษนอกระบบ
  ล้วนๆ ไม่มีสถานะ "ตีกลับ" ให้ต้องออกแบบอีก

**ยังรออยู่:**
- [ ] รายชื่อ User เริ่มต้นจริง (ใครสร้าง PR ได้บ้าง / ใครเป็น `is_admin`) — Phase 9
  ตัด `can_review`/`can_approve`/`can_receive` ออกแล้ว (ไม่มี Role ให้กำหนดอีก) กลไก
  Bootstrap Admin คนแรกทำเสร็จแล้วใน Phase 3 (`app/scripts/create_admin.py`) แต่ยังไม่
  ได้รับรายชื่อ User จริงทั้งหมดจาก Product Owner เพื่อสร้างในระบบ
- [ ] Sub-domain สำหรับ UAT/PROD ที่จะตั้งใน Nginx Proxy Manager — จำเป็นตอน Phase 8

