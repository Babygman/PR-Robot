"""audit log append-only (trigger, not REVOKE)

Electronic Signature Hardening Phase B (Design §3.2.2, 2026-09-15) — Lock สิทธิ์ระดับ
Database ให้ audit_log/system_logs แก้ไข/ลบไม่ได้แม้แต่จาก Bug หรือ Admin ที่เข้าถึง DB
ตรงๆ ผ่าน App

Correction 1 (2026-09-15, ยืนยันจาก Rachin): Design เดิมเสนอ `REVOKE UPDATE, DELETE ...
FROM <app_db_role>` แต่ทดสอบกับ Local Dev DB จริงแล้วพบว่า **ใช้ไม่ได้** — Role
`pr_robot` (Role เดียวกับที่ App เชื่อมต่อ) เป็นเจ้าของ (Owner) ทั้ง 2 ตารางเองอยู่แล้ว
(เพราะเป็น Role เดียวกับที่รัน Migration สร้างตารางขึ้นมา) และใน PostgreSQL เจ้าของตาราง
มีสิทธิ์เต็มเสมอไม่ว่าจะ REVOKE อะไรก็ตาม (Bypass สิทธิ์ตัวเองได้เสมอ ยกเว้นเปลี่ยน Owner
ไปเป็น Role อื่น) — ทดสอบจริงแล้ว REVOKE รันผ่านไม่มี Error แต่ UPDATE/DELETE ด้วย Role
เดิมหลัง REVOKE ยังทำได้ปกติทุกอย่าง (อันตรายกว่าไม่ทำเลย เพราะดูเหมือนปลอดภัยทั้งที่ไม่)

ใช้ Database Trigger แทน — Block ได้จริง 100% ไม่ว่า Role ไหนก็ตาม (รวมถึง Owner เอง)
เพราะ Trigger ทำงานที่ระดับ Table ไม่ใช่ระดับ Privilege

Correction 2 (พบระหว่างทดสอบ Trigger แบบ Block UPDATE/DELETE ทั้งหมดตรงๆ): audit_log.pr_id/
ar_id และ system_logs.actor_id เป็น FK แบบ `ON DELETE SET NULL` — ถ้า PR/AR หรือ User ถูก
Hard Delete จริง (เคยเกิดขึ้นแล้วจริงตอน Deploy PR Approval Level Phase 1 — ลบ PR เก่าทิ้ง
ด้วย SQL DELETE ตรงก่อน Migrate) PostgreSQL จะรัน UPDATE ภายในเพื่อ Null คอลัมน์ FK นั้น
โดยอัตโนมัติ (Referential Integrity Action) ซึ่งจะไปโดน Trigger แบบ Block UPDATE ทั้งหมด
บล็อกไปด้วย ทำให้ DELETE เอกสารต้นทาง/User ล้มเหลวทั้งที่ไม่เกี่ยวกับการเซ็นเลย — แก้โดยให้
Trigger ตรวจ NEW vs OLD เอง: อนุญาตเฉพาะ UPDATE ที่เป็นการ Null คอลัมน์ FK ที่ว่างได้เท่านั้น
(pr_id/ar_id ของ audit_log, actor_id ของ system_logs) ส่วน Field อื่นทุกตัว (action/detail/
timestamp/ip_address ฯลฯ) ห้ามเปลี่ยนเด็ดขาด — DELETE ยัง Block 100% เสมอไม่มีข้อยกเว้น
(แถวไม่เคยหายไปจริง ต่อให้เอกสารต้นทาง/ผู้กระทำถูกลบไปแล้วก็ตาม)

Correction 3 (พบระหว่างทดสอบ): detail เป็น Column Type `json` (ไม่ใช่ `jsonb`) — json ใน
PostgreSQL ไม่มี Operator "=" ตรงๆ ให้ใช้ (`IS DISTINCT FROM` พังด้วย Error เดียวกัน) ต้อง
Cast `::text` ก่อนเทียบเสมอ (ดูใน Function ด้านล่าง)

Correction 4 (พบระหว่างทดสอบ): ตอนแรกอนุญาตให้ pr_id/ar_id/actor_id เปลี่ยนได้อิสระ (ไม่
เช็คเลย) ซึ่งหลวมเกินไป — เปิดช่องให้ UPDATE ตรงๆ ย้าย Log ไปผูกกับ PR/AR/User คนอื่นได้
(ไม่ใช่แค่ Cascade) แก้ให้เช็คด้วยว่า Column พวกนี้เปลี่ยนได้ "ทางเดียว" คือเป็น NULL
เท่านั้น (Cascade จริง) ห้าม Reassign ไปเป็นค่าอื่นเด็ดขาด

ทดสอบครบแล้วกับ Local Dev PostgreSQL 16: (1) INSERT ปกติยังทำงานได้เหมือนเดิม (2) UPDATE
เปลี่ยน action/detail/ฯลฯ ตรงๆ โดน Block จริง (3) DELETE โดน Block จริงเสมอ (4) Hard Delete
PR ที่มี audit_log ผูกอยู่ (pr_id SET NULL Cascade) ทำสำเร็จได้ปกติ ไม่โดน Trigger บล็อก
(5) UPDATE pr_id ตรงๆ ไปเป็น PR อื่น (ไม่ใช่ NULL) โดน Block จริง

Revision ID: b9d4e6f2a8c7
Revises: a7c3f1e9b5d2
Create Date: 2026-09-15
"""
from __future__ import annotations

from alembic import op

revision = "b9d4e6f2a8c7"
down_revision = "a7c3f1e9b5d2"
branch_labels = None
depends_on = None

_FUNCTION_NAME = "prevent_log_mutation"

_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'audit_log/system_logs are append-only — DELETE on % is not permitted',
            TG_TABLE_NAME;
    END IF;

    -- TG_OP = 'UPDATE': การ UPDATE ที่ยอมรับได้มีแบบเดียวคือ FK ON DELETE SET NULL
    -- Cascade ตอนเอกสารต้นทาง/ผู้กระทำถูก Hard Delete (ดู Docstring บนสุดของไฟล์นี้
    -- ข้อ Correction 2) — Field อื่นนอกจากคอลัมน์ FK ที่ระบุ ห้ามเปลี่ยนเด็ดขาด
    -- หมายเหตุ: Cast detail::text ก่อนเทียบ เพราะ Column เป็น Type json (ไม่ใช่ jsonb) —
    -- json ใน PostgreSQL ไม่มี Operator "=" ให้ใช้ตรงๆ (IS DISTINCT FROM ก็ใช้ตัวเดียวกัน)
    -- ต้อง Cast เป็น text ก่อนเทียบเสมอ
    -- pr_id/ar_id/actor_id อนุญาตให้เปลี่ยนได้ "ทางเดียว" คือเปลี่ยนเป็น NULL เท่านั้น
    -- (Cascade จริง) ห้าม Reassign ไปเป็นค่าอื่นที่ไม่ใช่ NULL เด็ดขาด (ทั้งจาก NULL ไปเป็น
    -- ค่า และจากค่าหนึ่งไปอีกค่าหนึ่ง) กันกรณี UPDATE ตรงๆ ย้าย Log ไปผูกกับเอกสารอื่น
    IF TG_TABLE_NAME = 'audit_log' THEN
        IF NEW.action IS DISTINCT FROM OLD.action
           OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
           OR NEW.detail::text IS DISTINCT FROM OLD.detail::text
           OR NEW.timestamp IS DISTINCT FROM OLD.timestamp
           OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
           OR (NEW.pr_id IS DISTINCT FROM OLD.pr_id AND NEW.pr_id IS NOT NULL)
           OR (NEW.ar_id IS DISTINCT FROM OLD.ar_id AND NEW.ar_id IS NOT NULL)
        THEN
            RAISE EXCEPTION
                'audit_log is append-only — pr_id/ar_id may only be cleared to NULL by cascade, no other field may change';
        END IF;
    ELSIF TG_TABLE_NAME = 'system_logs' THEN
        IF NEW.action IS DISTINCT FROM OLD.action
           OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
           OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
           OR NEW.detail::text IS DISTINCT FROM OLD.detail::text
           OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
           OR NEW.created_at IS DISTINCT FROM OLD.created_at
           OR (NEW.actor_id IS DISTINCT FROM OLD.actor_id AND NEW.actor_id IS NOT NULL)
        THEN
            RAISE EXCEPTION
                'system_logs is append-only — actor_id may only be cleared to NULL by cascade, no other field may change';
        END IF;
    ELSE
        RAISE EXCEPTION 'append-only: UPDATE on % is not permitted', TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_FUNCTION_SQL)
    for table in ("audit_log", "system_logs"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_NAME}();
            """
        )


def downgrade() -> None:
    for table in ("audit_log", "system_logs"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}();")
