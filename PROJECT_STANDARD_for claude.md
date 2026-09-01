# PROJECT_STANDARD.md

Version: 2.1
Last Updated: 2026-08-07

# Core Principles

1. Business Goal มาก่อน Technology
2. ออกแบบก่อน Coding
3. ทำทีละ Phase และรออนุมัติก่อนเริ่มขั้นถัดไป
4. UAT คือแหล่งค้นหาความจริง ไม่ใช่ Unit Test
5. Chat ออกแบบ สถาปัตยกรรม เขียน Prompt และ Review
6. Claude code/Codex พัฒนาโค้ด ทดสอบ และ Commit
7. Push เมื่อ UAT ผ่านและ Working Tree เป็น Clean เท่านั้น
8. ทุก Feature ต้องตอบ Business Requirement
9. หลีกเลี่ยง Scope Creep
10. Simple is Better than Perfect

---

# 1. บทบาท

## Product Owner
- กำหนด Business Goal
- กำหนด Requirement
- ทำ UAT
- อนุมัติ Release
- จัดลำดับความสำคัญของงาน

## Chat
- Technical Architect
- System Analyst
- Project Manager
- QA Reviewer
- Security Reviewer
- Performance Reviewer

หน้าที่:
- วิเคราะห์ Requirement
- ออกแบบ Architecture
- ออกแบบ Database
- ออกแบบ Workflow
- ออกแบบ UI/UX
- เขียน Prompt ให้ Claude code/Codex
- Review งานและผล UAT
- ตัดสินใจ Approved / Not Approved

## Claude code/Codex
หน้าที่:
- Coding
- Refactoring
- Bug Fix
- Migration
- Tests
- Documentation
- Git Commit

---

# 2. Workflow

Requirement
→ Architecture
→ Database
→ Workflow/UI
→ Approval
→ Prompt for Codex
→ Development
→ Commit
→ Run
→ UAT
→ Review
→ Fix (ถ้ามี)
→ Push
→ Merge
→ Release

---

# 3. Project Kickoff

ก่อน Coding ต้องทำ

1. Requirement Analysis
2. Business Goal
3. Scope
4. Risk Assessment
5. Architecture
6. Database Design
7. Workflow
8. UI/UX
9. Roadmap
10. รออนุมัติ

## Runtime Architecture

ก่อน Coding ต้องกำหนดให้ชัดเจนว่าแต่ละ Component ทำงานที่ใด และสื่อสารกันอย่างไร

- Development Application ต้องรันบน Developer Machine ผ่าน IDE หรือ Terminal ของ Project
- Database Server โดยปกติให้บริการ Database เท่านั้น
- Development ต้องไม่จำเป็นต้องใช้ Remote Desktop เข้า Database Server เพียงเพื่อรัน Application
- ห้ามสมมติว่า Database Server เป็น Application Server ด้วย
- Developer Machine, Application Server และ Database Server เป็น Architectural Role ที่แยกจากกัน แม้บาง Environment อาจวางอยู่บนเครื่องเดียวกันเมื่อมีเหตุผลและได้รับอนุมัติ

Development Flow:

Developer Machine → Application → Database Driver/ORM → Network → Database Server

Production Flow:

User → Application Server → Database Server

## Environment Definition

ต้องกำหนด DEV / UAT / PROD ก่อนเริ่ม Implementation โดยแต่ละ Environment ต้องระบุ

- Application Runtime Location
- Database Server
- Database Name
- TCP Port
- Authentication Method
- Application Service Account
- Network และ Firewall Requirement
- Configuration Management
- Deployment Method

## Infrastructure Readiness Gate

ก่อนเริ่ม Feature Development ต้องตรวจสอบและบันทึกหลักฐานว่า

- Repository พร้อมใช้งาน
- Virtual Environment หรือ Runtime Environment พร้อมใช้งาน
- Dependencies ติดตั้งครบ
- Environment Configuration พร้อมใช้งาน
- Secrets ถูกแยกออกจาก Git
- Network Connectivity ผ่าน
- Database Port ผ่าน
- Database Service Account ใช้งานได้
- Database Permissions ถูกต้อง
- Direct Database Connection ผ่าน
- ORM Connection ผ่าน

---

# 4. Git Standard

Branch:
- main
- feature/*
- hotfix/*

Push เมื่อ
- UAT ผ่าน
- Tests ผ่าน
- Working Tree Clean
- Chat Approved

---

# 5. Database

- ใช้ Alembic Migration
- ห้ามแก้ Production Schema ตรง
- ทดสอบ Upgrade → Downgrade → Upgrade

## Database Connectivity Validation

ต้องตรวจสอบการเชื่อมต่อตามลำดับ และเก็บผลของแต่ละ Layer เป็นหลักฐาน

1. Network
2. TCP Port
3. Database Server
4. Database Login
5. Database Permissions
6. Database Driver
7. Direct Driver Connection
8. ORM Connection
9. Application Connection

---

# 6. Testing

ทุกครั้งต้องรัน
- Pytest
- Ruff
- Template Compile
- SQL Smoke Test (ถ้ามี)
- Manual UAT

---

# 7. UAT

Product Owner:
- ทดสอบจริง
- ส่ง Screenshot
- ส่ง Comment

Chat:
- จัดประเภท Bug / Improvement / Expected / Question
- เขียน Prompt ให้ Codex

Claude code/Codex:
- แก้เฉพาะงานที่ได้รับอนุมัติ

---

# 8. Security Checklist

ตรวจอย่างน้อย
- SQL Injection
- XSS
- CSRF
- Authentication
- Authorization
- Secret Management

## Authentication Separation

- Database Service Account ใช้โดย Application สำหรับเชื่อมต่อ Database
- Application User Account ใช้โดยบุคคลสำหรับ Login เข้า Application
- ห้ามสรุปว่า Application Login ล้มเหลวเพราะ Database Login ล้มเหลวโดยอัตโนมัติ ต้องตรวจสอบแต่ละ Authentication Layer แยกกัน

## Configuration and Secret Management

- ห้าม Hard-code Password, Connection String, API Key, Secret Key หรือ Production Credential
- ใช้ `.env` หรือ Secret-management Mechanism ที่เหมาะสมกับ Environment
- `.env` ที่มี Secret ต้องถูก exclude ด้วย `.gitignore`
- ห้าม Commit Credential จริงลง Source Control
- Credential อาจมี Reserved Character เช่น `@`, `:`, `/`, `?`, `#`, `%`, `&` และ `+`
- URL-based Connection String ต้อง Encode Reserved Character อย่างถูกต้อง
- ห้ามเปลี่ยน Password เพียงเพราะมี Special Character เว้นแต่มีหลักฐานยืนยันว่าเป็นสาเหตุ

---

# 9. Performance

ตรวจ
- Dashboard
- API
- SQL Query

ห้ามเกิด Performance Regression

---

# 10. Documentation

อัปเดตทุก Sprint
- README.md
- RELEASE.md
- CHANGELOG.md (ถ้ามี)
- เอกสารที่เกี่ยวข้อง

## Dependency Baseline

- กำหนดและบันทึก Dependency ทั้งหมดของ Project
- Dependency ต้องติดตั้งซ้ำได้จาก Dependency File ของ Project เช่น `requirements.txt`, lockfile หรือ Manifest ที่เทียบเท่า
- ห้ามพึ่งพา Package ที่ติดตั้งด้วยตนเองแต่ไม่มีการบันทึกไว้

---

# 11. Environment Rule

ทุกคำสั่งต้องระบุ
- เครื่อง
- IDE
- Terminal
- Database
- Git Branch

Execution Location ต้องระบุให้ชัดเจนในทุกคำสั่งและ Troubleshooting Instruction เช่น

- Developer Machine → IDE → Project Terminal → Virtual Environment
- Application Server → System Shell
- Database Server → Database Administration Tool

## Evidence-Based Troubleshooting

ตรวจสอบปัญหาทีละ Layer ตามลำดับ

Network → Port → Database Server → Database Account → Driver → ORM → Application → Authentication → Business Logic → UI

เมื่อ Layer ใดพิสูจน์แล้วว่าทำงานถูกต้อง ห้ามแก้ไข Layer นั้นอีกโดยไม่มีหลักฐานใหม่ที่ชี้ว่าปัญหาอยู่ใน Layer ดังกล่าว

---

# 12. Definition of Done

ถือว่าเสร็จเมื่อ
- UAT ผ่าน
- Tests ผ่าน
- Documentation ครบ
- Push สำเร็จ
- Working Tree Clean

---

# 13. Lessons Learned

เมื่อจบ Project ให้สรุป
- สิ่งที่ทำได้ดี
- สิ่งที่ต้องปรับปรุง
- Roadmap Version ถัดไป

---

# 14. Project Kickoff Template

Project Name:

Business Goal:

Objectives:

Target Users:

Technology Stack:

Operating System:

Programming Language:

Database:

Source Control:

Coding Tool:

AI Coding Tool:

Deployment:

Timeline:

Out of Scope:

Success Criteria:

DEV Environment:

UAT Environment:

PROD Environment:

Application Runtime Location:

Database Server / Name / TCP Port:

Database Authentication Method:

Application Service Account:

Network / Firewall Requirements:

Configuration Management:

Deployment Method:

Dependency File:

## Production Architecture

- Production Deployment Architecture ต้องออกแบบและได้รับอนุมัติก่อน Deploy
- ห้ามใช้ Development Server เช่น Flask Development Server เป็น Production Server
- Production Application ต้องรันด้วย Production-grade Runtime หรือ Application Server ที่เหมาะสมกับ Technology Stack

## Development and Deployment Work Location

| งาน                                     | ทำที่ไหน                           |
| --------------------------------------- | ---------------------------------- |
| เขียน/แก้ Code                          | Claude code/Codex บน MacBook Air               |
| Git / Commit / Push                     | Claude code/Codex + GitHub                     |
| Automated Test / pytest / Ruff          | MacBook Air / Claude code/Codex                |
| รัน Flask ระหว่าง Development           | MacBook Air → VS Code Terminal     |
| เปิดเว็บเพื่อทดสอบ                      | MacBook Air → Browser              |
| Database                                | postgresql โดยใช้ Docker                    |
| Migration / Seed ที่กระทบ Database จริง | เชื่อมไป Database บน postgresql |
| Production Deployment                   | ` Docker`    
| Production Web Service                  | Docker ตอนนี้ใช้อยู่บน Ubuntu และ install PORTAINER.IO,Nginx Proxy manger ไว้ใช้งานแล้วเพื่อเป็น dashboard            |

https://sctubuntu01.sct.local/ Docker run อยู่ที่นี่ บน ubuntu ip address 10.206.1.107
PORTAINER.IO คือ https://sctubuntu01.sct.local:9443/
Nginx Proxy Manager คือ http://sctubuntu01.sct.local:81/

SCTUBUNTU01
10.206.1.107
│
├── Ubuntu 26.04 LTS             ✅
├── Static IP / DNS / Hostname   ✅
├── SSH + UFW                    ✅
├── Docker Engine 29.7.2         ✅
├── Docker Compose v5.5.0        ✅
│
├── Portainer CE                 ✅
│   └── :9443
│
└── Nginx Proxy Manager          ✅
    ├── :81   Management
    ├── :80   HTTP
    └── :443  HTTPS


Docker Compose → Portainer → DNS → Nginx Proxy Manager → URL

แต่ละระบบแยก Logical Stack เช่น:
App A
├── Web
└── DB-A

App B
├── Web
└── DB-B


สำหรับสถานการณ์ที่ต้องการ หนึ่ง Linux Server + หลาย Internal Apps + Multi-container + GUI Management:

Ubuntu
   +
Docker Engine
   +
Docker Compose
   +
Portainer
   +
Nginx Proxy Manager


Architecture ที่ผมเสนอ
Hyper-V
└── SCTUBUNTU01
    10.206.1.107
    Ubuntu 26.04 LTS
        │
        ├── Docker Engine
        │
        ├── Portainer
        │     └── Docker Management GUI
        │
        ├── Nginx Proxy Manager
        │     └── Reverse Proxy / HTTPS
        │
        ├── Stack: Preweight
        │     ├── Web
        │     ├── Worker
        │     └── Redis
        │
        ├── Stack: App02
        │     ├── Web
        │     └── DB
        │
        └── Stack: App03
              ├── Web
              └── DB














---

# 15. Permanent Delivery Responsibilities

## Project Owner

- Defines requirements and approves business decisions and scope.
- Performs final manual UAT and reports UAT results.
- Is not responsible for source editing, Terminal commands, Git operations, database work,
  migrations, deployment, or technical setup.

## Chat

- Maintains project and business context.
- Analyzes requirements and UAT feedback, including distinguishing defects from missing
  requirements.
- Designs the implementation direction and produces complete Claude code/Codex prompts.
- Reviews Claude code/Codex results and guides the Project Owner through browser UAT.
- Does not transfer technical implementation work to the Project Owner.

## Claude code/Codex

- Operates on the real repository and implements source changes.
- Handles Terminal, Git, database, migrations, automated tests, and technical verification.
- Prepares UAT/mock data and handles application restart, deployment, and setup as applicable.
- Leaves the system ready for the Project Owner's final manual UAT.

## Standard Delivery Workflow

Requirement
→ Chat analysis/design
→ Project Owner approval where required by this standard
→ Chat produces Claude code/Codex Prompt
→ Claude/Codex implements, verifies, and prepares UAT
→ Project Owner performs browser UAT
→ Chat evaluates the UAT result
→ Next approved cycle

Technical tasks assigned to Codex must never be transferred back to the Project Owner merely
because Codex can provide commands for the Project Owner to run.

## Recurring Technical Credentials

- Recurring technical credentials must use secure machine-local credential storage appropriate
  to the operating environment.
- Claude code/Codex must not repeatedly transfer password-entry tasks to the Project Owner.
- Secrets must never be printed, logged, committed to source control, or placed in project
  documentation.
- If a required credential is absent, the operation must stop and report the missing credential
  as a blocker instead of bypassing authentication or weakening security controls.
