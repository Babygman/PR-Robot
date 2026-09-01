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

## 4. Database Design (High-level)

| Table | Field หลัก |
|---|---|
| `users` | id, name, email, password_hash, role (requester / reviewer / approver / receiver / admin), department, is_active |
| `purchasing_requisitions` | id, pr_no, section, division, doc_date, status (draft / reviewed / approved / received), requested_by_id, reviewed_by_id, approved_by_id, received_by_id, remark, created_at, updated_at |
| `pr_items` | id, pr_id (FK), item_no, account_code, description, quantity, required_date, reason, ref_po |
| `pr_budget_control` | id, pr_id (FK), account_code_1, account_code_2, budget, used_before_amount, this_application, balance |
| `source_documents` | id, pr_id (FK, nullable), file_path, doc_type (quotation / receiving_note / other), uploaded_by_id, uploaded_at, ai_extraction_raw_json, ai_confidence |
| `audit_log` | id, pr_id (FK), action, actor_id, timestamp, detail |

หมายเหตุ: ฟิลด์ข้างต้นอ้างอิงจากแบบฟอร์มหน้า 1/3 เท่านั้น (Section, Division, No., Date, Item/Account Code/Description/Quantity/Required Date/Reason/Ref.PO, Budget Control, Remark, Requested/Reviewed/Approved/Received by) — จะปรับเพิ่มเมื่อได้รับหน้า 2-3

---

## 5. Roadmap (แบ่ง Phase ตามมาตรฐาน — รออนุมัติก่อนเริ่มแต่ละ Phase)

| Phase | เนื้อหา | Output |
|---|---|---|
| 0 | Kickoff & Design (เอกสารนี้) | เอกสารนี้ + อนุมัติจาก Product Owner |
| 1 | Infra Readiness: Init Repo, Docker Compose (Dev DB), Alembic baseline, โครง FastAPI project, `.env.example` | Repo พร้อม Dev Environment รันได้ |
| 2 | Database Schema + Migration จริงตามข้อ 4 | Schema ใช้งานได้ ผ่าน Alembic Upgrade/Downgrade |
| 3 | Authentication & Role-based Access (Login, จัดการ User/Role) | ระบบ Login แยกสิทธิ์ 4 บทบาท |
| 4 | Upload + AI Extraction (Gemini) + หน้าตรวจทาน/แก้ไขข้อมูล | อัปโหลดเอกสาร → เห็นข้อมูลที่ AI สกัด → แก้ไขได้ |
| 5 | บันทึก PR + Generate PDF ตาม Template จริง | ได้ไฟล์ PR ที่กรอกครบ พิมพ์ได้ |
| 6 | Workflow อนุมัติ (Reviewed/Approved/Received) + ประวัติ/ค้นหา PR | ครบ Flow ตั้งแต่ขอซื้อถึงรับของ + History Search |
| 7 | UAT รวม + Security Review + Deploy จริงบน SCTUBUNTU01 | ระบบใช้งานจริงบน UAT/PROD |
| 8 | Documentation (README/RELEASE) + Lessons Learned | เอกสารครบตามมาตรฐานข้อ 10 และ 13 |

---

## 6. Open Items — รอข้อมูลเพิ่มจาก Product Owner

- [ ] แบบฟอร์มหน้า 2/3 และ 3/3 ของ Purchasing Requisition (ผู้ใช้แจ้งว่าจะส่งให้เพิ่มเติม)
- [ ] Google Gemini API Key (ต้องขอ Free Tier API Key มาใส่ใน `.env`)
- [ ] รูปแบบเลขที่ PR (Running Number ต่อปี? ต่อ Section?) — เอกสารตัวอย่างมีเลข "0290" ที่มุมขวาบน
- [ ] รายชื่อ User เริ่มต้นและบทบาท (ใครเป็น Requester/Reviewer/Approver/Receiver)
- [ ] Sub-domain สำหรับ UAT/PROD ที่จะตั้งใน Nginx Proxy Manager

