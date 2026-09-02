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

Docker Compose ไฟล์จริงสำหรับ UAT/PROD ของ PR-Robot จะเขียนใน **Phase 7 (Deploy)**
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
apt) — **สิ่งที่ต้องทำต่อ:** เมื่อสร้าง Dockerfile จริงใน Phase 7 (Deploy UAT/PROD)
ต้องติดตั้ง Font ไทยไว้ใน Image ด้วย ไม่เช่นนั้นจะ Fallback ไปใช้ Font ที่ไม่รองรับ
ภาษาไทยดีพอ — บันทึกไว้ใน Open Items แล้ว

## 5. Roadmap (แบ่ง Phase ตามมาตรฐาน — รออนุมัติก่อนเริ่มแต่ละ Phase)

| Phase | เนื้อหา | Output |
|---|---|---|
| 0 | Kickoff & Design (เอกสารนี้) | เอกสารนี้ + อนุมัติจาก Product Owner |
| 1 | Infra Readiness: Init Repo, Docker Compose (Dev DB), Alembic baseline, โครง FastAPI project, `.env.example` | Repo พร้อม Dev Environment รันได้ |
| 2 | Database Schema + Migration จริงตามข้อ 4 | **เสร็จแล้ว (2026-09-01)** — Schema ใช้งานได้ ผ่าน Alembic Upgrade/Downgrade/Upgrade + ORM Round-trip จริง |
| 3 | Authentication & Role-based Access (Login, จัดการ User/Role) | **เสร็จแล้ว (2026-09-01)** — Login/Logout/Me ผ่าน HttpOnly Cookie + JWT, Role-based Access Control (can_review/can_approve/can_receive/is_admin), Admin สร้าง/ดูรายชื่อ User ได้, สคริปต์ Bootstrap Admin คนแรก |
| 4 | Upload + AI Extraction (Gemini) + หน้าตรวจทาน/แก้ไขข้อมูล | **เสร็จแล้ว (2026-09-02)** — Upload PDF/รูปภาพ → Gemini สกัดข้อมูลแบบ Structured JSON → บันทึก reviewed_data เมื่อผู้ใช้แก้ไข (ดู 4b.) |
| 5 | บันทึก PR + Generate PDF ตาม Template จริง | **เสร็จแล้ว (2026-09-02)** — POST/GET/PATCH /prs + GET /prs/{id}/pdf ตรงตามฟอร์ม FM-PU-02 (ดู 4c.) |
| 6 | Workflow อนุมัติ (Reviewed/Approved/Received) + ประวัติ/ค้นหา PR | ครบ Flow ตั้งแต่ขอซื้อถึงรับของ + History Search |
| 7 | UAT รวม + Security Review + Deploy จริงบน SCTUBUNTU01 | ระบบใช้งานจริงบน UAT/PROD |
| 8 | Documentation (README/RELEASE) + Lessons Learned | เอกสารครบตามมาตรฐานข้อ 10 และ 13 |

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
  Dockerfile จริง — จำเป็นตอน Phase 7 ไม่เช่นนั้น PDF จะ Fallback ไป Font ที่ไม่รองรับ
  ภาษาไทยดีพอ (ดู 4c.)

**ยังรออยู่:**
- [ ] รายชื่อ User เริ่มต้นและบทบาทจริง (ใครมีสิทธิ์ can_review / can_approve / can_receive / is_admin) — กลไก Bootstrap Admin คนแรกทำเสร็จแล้วใน Phase 3 (`app/scripts/create_admin.py`) แต่ยังไม่ได้รับรายชื่อ User จริงจาก Product Owner เพื่อสร้างในระบบ
- [ ] Sub-domain สำหรับ UAT/PROD ที่จะตั้งใน Nginx Proxy Manager — จำเป็นตอน Phase 7

