"""Sealed PDF — Electronic Signature Hardening Phase C (Design §3.2.3, 2026-09-16)

ณ จุดที่ PR/AR ถึงสถานะ Final จริง (ดู Docstring บน
PurchasingRequisition.sealed_pdf_path / ApprovalRequest.sealed_pdf_path สำหรับนิยาม
"Final จริง" ของแต่ละฝั่ง — ไม่เหมือนกัน) Render PDF **ครั้งเดียว** (ฝัง Signature Log
ที่ดึงจาก audit_log ซึ่ง Append-only แล้วตั้งแต่ Phase B ลงในตัว PDF เองด้วย) บันทึกไฟล์
ลง settings.generated_dir คำนวณ SHA-256 จาก Bytes ที่ Generate ก่อนเขียนไฟล์เป๊ะๆ (ไม่
Hash หลังอ่านไฟล์กลับมา กัน Encoding/Line-ending เพี้ยน) แล้วเก็บ Path/Hash ไว้บนตัวแถว
PR/AR เอง — ไม่ Commit เอง (Caller เป็นคน Commit พร้อมกับการเปลี่ยนสถานะใน Transaction
เดียวกัน เหมือน Pattern ของ pr_budget_workflow/budget_workflow ทุกไฟล์ในโปรเจกต์นี้)

Signature Log ที่ฝังในตัว PDF (ชื่อ/ตำแหน่ง/วันที่-เวลา/IP — ดู Design §3.2.3) ดึงจาก
Action ที่เป็น "การเซ็น" จริงบน audit_log เท่านั้น (มี detail["signer"] + ip_address
เสมอตั้งแต่ Phase A) เรียงตามเวลาจริง — ไม่รวม Action ประเภทปฏิเสธ (Reject) เพราะแถวที่
ถูก Seal คือแถวที่ไปถึง Final ได้จริงเท่านั้น (แถวที่เคยถูกปฏิเสธไปแล้วต้อง Revise เป็น
แถวใหม่เสมอ ไม่มีทาง Resubmit บนแถวเดิมที่เคย Reject ได้ ดู budget_workflow.py Docstring
ข้อ 3) และไม่รวม Action Marker ซ้ำ ("pr.finalized"/"ar.finalized" — Timestamp/Actor
เดียวกับ Action จริงที่อยู่ก่อนหน้าเป๊ะ นับซ้ำจะทำให้ Signature Log มี 2 แถวสำหรับ
เหตุการณ์เดียวกัน)

หมายเหตุสำคัญ: Hash ไม่ได้ฝังลงในตัว PDF เอง (Chicken-and-egg — Hash คำนวณจาก Bytes ของ
PDF ที่ Generate เสร็จแล้ว จะย้อนไปฝังใน Bytes เดิมที่ใช้คำนวณไม่ได้) เก็บไว้แค่ในคอลัมน์
Database (sealed_pdf_hash) สำหรับ Admin ใช้ตรวจสอบว่าไฟล์บน Disk ตรงกับตอน Seal จริง
หรือไม่เท่านั้น
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ApprovalRequest, AuditLog, PurchasingRequisition

# Action ที่ถือว่าเป็น "การเซ็น" ที่ต้องขึ้น Signature Log ในตัว PDF Seal — Label ใช้
# ภาษาอังกฤษให้ตรง Style เดิมของฟอร์ม (pr_form.html/ar_form.html เป็นภาษาอังกฤษล้วน)
_PR_LOG_ACTIONS = {
    "pr.submitted_for_approval": "Submitted for Approval",
    "pr.budget_level_approved": "Approved",
}
_AR_LOG_ACTIONS = {
    "ar.submitted_for_approval": "Submitted for Approval",
    "ar.budget_level_approved": "Approved",
    "ar.budget_fa_acknowledged": "F&A Acknowledged",
}


def _fmt_timestamp(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M UTC")


def _build_signature_log(
    db: Session, *, pr_id: int | None, ar_id: int | None, actions: dict[str, str]
) -> list[dict]:
    stmt = select(AuditLog).where(AuditLog.action.in_(actions.keys())).order_by(AuditLog.timestamp)
    stmt = (
        stmt.where(AuditLog.pr_id == pr_id)
        if pr_id is not None
        else stmt.where(AuditLog.ar_id == ar_id)
    )
    rows = db.execute(stmt).scalars().all()

    log: list[dict] = []
    for row in rows:
        if not row.ip_address:
            continue
        detail = row.detail or {}
        signer = detail.get("signer") or {}
        label = actions[row.action]
        level_no = detail.get("level_no")
        if row.action.endswith("budget_level_approved") and level_no is not None:
            label = f"{label} — Level {level_no}"
        log.append(
            {
                "action_label": label,
                "name": signer.get("name") or "",
                "position": signer.get("position"),
                "timestamp": _fmt_timestamp(row.timestamp),
                "ip_address": row.ip_address,
            }
        )
    return log


def _write_sealed_pdf(pdf_bytes: bytes, filename: str) -> tuple[str, str]:
    generated_dir = Path(settings.generated_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)
    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
    (generated_dir / filename).write_bytes(pdf_bytes)
    return filename, sha256_hash


def seal_pr(db: Session, pr: PurchasingRequisition) -> None:
    """เรียกตอน pr.status เปลี่ยนเป็น FINALIZED จริง (ดู
    app/api/routes/purchasing_requisitions.py: submit_pr_for_approval/approve_pr_level)
    ไม่ Commit เอง — ไม่มีผลถ้าเคย Seal ไปแล้ว (Idempotent กันเรียกซ้ำโดยไม่ตั้งใจ)"""
    if pr.sealed_pdf_path:
        return
    from app.services.pr_pdf import render_pr_pdf  # กัน Circular Import

    signature_log = _build_signature_log(db, pr_id=pr.id, ar_id=None, actions=_PR_LOG_ACTIONS)
    pdf_bytes = render_pr_pdf(db, pr, signature_log=signature_log)
    filename, sha256_hash = _write_sealed_pdf(pdf_bytes, f"pr-{pr.id}.pdf")
    pr.sealed_pdf_path = filename
    pr.sealed_pdf_hash = sha256_hash
    pr.sealed_at = datetime.now(timezone.utc)


def seal_ar(db: Session, ar: ApprovalRequest) -> None:
    """เรียกตอน FA Acknowledge ผ่านจริง (ดู
    app/api/routes/approval_requests.py: fa_acknowledge_ar) — นี่คือจุด Final จริงของ AR
    ไม่ใช่ตอน ar.status เปลี่ยนเป็น FINALIZED (เร็วกว่านั้น ดู Docstring บน
    ApprovalRequest.sealed_pdf_path) ไม่ Commit เอง — ไม่มีผลถ้าเคย Seal ไปแล้ว"""
    if ar.sealed_pdf_path:
        return
    from app.services.ar_pdf import render_ar_pdf  # กัน Circular Import

    signature_log = _build_signature_log(db, pr_id=None, ar_id=ar.id, actions=_AR_LOG_ACTIONS)
    pdf_bytes = render_ar_pdf(db, ar, signature_log=signature_log)
    filename, sha256_hash = _write_sealed_pdf(pdf_bytes, f"ar-{ar.id}.pdf")
    ar.sealed_pdf_path = filename
    ar.sealed_pdf_hash = sha256_hash
    ar.sealed_at = datetime.now(timezone.utc)


def read_sealed_pdf(sealed_pdf_path: str) -> bytes:
    """อ่านไฟล์ที่ Seal ไว้กลับมาเป็น Bytes ตรงๆ (ใช้แทน Re-render จาก Template) — ไม่
    Verify Hash ซ้ำทุกครั้งที่ดาวน์โหลด (Performance — คนอ่านเป็นพันครั้ง Hash ไม่เคย
    เปลี่ยนถ้าไม่มีใครไปยุ่งกับไฟล์บน Disk ตรงๆ) sealed_pdf_hash ในคอลัมน์ DB มีไว้ให้
    Admin ตรวจสอบเองเป็นครั้งคราวเท่านั้น"""
    path = Path(settings.generated_dir) / sealed_pdf_path
    return path.read_bytes()
