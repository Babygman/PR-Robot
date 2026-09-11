"""User Management — Admin เท่านั้นที่สร้าง/ดู/แก้ไขรายชื่อ User ได้ (Phase 3, ขยาย
Phase 10 2026-09-09 เพิ่ม PATCH สำหรับหน้า /app/users — Budget Control ต้องมีหน้า
จัดการ User จริงเพื่อกำหนด Department/Position/is_fa ให้แต่ละคน — ขยายอีกครั้ง
2026-09-10 ให้ PATCH แก้ email ได้ด้วย เพื่อรองรับ Import User จำนวนมากจากตาราง
Approve Flow/User Register จริงของบริษัทที่ยังไม่มี Email จริงครบทุกคน — สร้างด้วย
Email ชั่วคราวก่อน แล้วให้ Admin แก้เป็น Email จริงทีหลังจากหน้านี้ได้)
ยังไม่มีหน้าเว็บ Self-service สมัครสมาชิก — ตั้งใจให้ Admin เป็นคนเพิ่ม User เข้าระบบเท่านั้น
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AiUsageLog,
    ApprovalRequest,
    ARAttachment,
    ARBudgetApproval,
    AuditLog,
    BudgetApprovalLevel,
    BudgetUploadBatch,
    PurchasingRequisition,
    SourceDocument,
    User,
)
from app.schemas.user import (
    UserCreate,
    UserExcelUploadResult,
    UserPasswordReset,
    UserRead,
    UserUpdate,
)
from app.services.user_excel import build_export_workbook, parse_and_upsert

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    existing = db.query(User).filter(User.email == body.email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้มีผู้ใช้ในระบบแล้ว")

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        department=body.department,
        division=body.division,
        position=body.position,
        is_admin=body.is_admin,
        is_fa=body.is_fa,
        can_view_approvals=body.can_view_approvals,
        can_view_pr=body.can_view_pr,
        can_view_ar=body.can_view_ar,
        can_view_all_pr=body.can_view_all_pr,
        can_view_all_ar=body.can_view_all_ar,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ User นี้")

    updates = body.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] is not None and updates["email"] != user.email:
        clash = db.query(User).filter(User.email == updates["email"], User.id != user.id).first()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้มีผู้ใช้ในระบบแล้ว")

    # exclude_unset=True: อัปเดตเฉพาะ Field ที่ Client ส่งมาจริงๆ (รวมถึงกรณีส่ง null
    # มาตั้งใจล้างค่า เช่น เคลียร์ department ของผู้อนุมัติ Cross-department) — Field ที่
    # ไม่ได้ส่งมาเลยจะไม่ถูกแตะต้อง
    for key, value in updates.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_user_password(
    user_id: int,
    body: UserPasswordReset,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    """Reset รหัสผ่านของ User คนอื่น — Admin เท่านั้น (User Management Redesign,
    2026-09-11 — ปุ่ม "Reset Password" แยกในหน้า /app/users ก่อนหน้านี้ไม่มี Endpoint
    นี้เลย ต้องไปแก้ตรง Database ตรงๆ) ไม่ต้องยืนยันรหัสผ่านเดิม เพราะ Admin เป็นคน
    Reset แทน User ที่ลืมรหัสผ่าน ไม่ใช่ User เปลี่ยนรหัสผ่านตัวเอง"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ User นี้")

    user.password_hash = hash_password(body.password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────── Excel Download/Upload (User Management Redesign, 2026-09-11) ───────────────
@router.get("/export")
def export_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> Response:
    """Export User ทั้งหมดเป็น Excel — ดู app/services/user_excel.py สำหรับรายละเอียด
    คอลัมน์ (ไม่มี password — Re-upload ไฟล์นี้กลับเข้าระบบได้เลยสำหรับแก้ไข User เดิม)"""
    users = db.query(User).order_by(User.id).all()
    content = build_export_workbook(users)
    filename = f"users_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload", response_model=UserExcelUploadResult, status_code=status.HTTP_201_CREATED)
def upload_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> UserExcelUploadResult:
    """Import Excel แบบ Partial-success — จับคู่ด้วย email เจอเดิม = Update (ไม่แตะ
    Password) ไม่เจอ = สร้างใหม่ (ต้องมีคอลัมน์ password ในไฟล์ อย่างน้อย 8 ตัวอักษร) —
    ดู app/services/user_excel.py สำหรับ Format เต็ม"""
    content = file.file.read()
    outcomes, success_rows, error_rows = parse_and_upsert(
        db, filename=file.filename or "", file_bytes=content
    )
    db.commit()
    return UserExcelUploadResult(
        total_rows=len(outcomes),
        success_rows=success_rows,
        error_rows=error_rows,
        errors=[{"row_no": o.row_no, "message": o.message} for o in outcomes if not o.ok],
    )


# ─────────────── Delete User — CRUD ครบ (User Management Redesign, 2026-09-11) ───────────────
def _user_has_history(db: Session, user_id: int) -> str | None:
    """เช็คทุก Foreign Key ที่อ้างถึง users.id ในระบบ (Requested By/Uploaded By/Approver/
    Actor/Reviewed By ฯลฯ) — คืนข้อความเหตุผลแรกที่เจอถ้ามีประวัติ หรือ None ถ้าไม่มีเลย
    ผู้ใช้ยืนยันชัดเจนแล้วว่า "จะลบไม่ได้ หากผู้นั้นเคยทำอะไรในระบบไปแล้ว" (สร้าง PR/AR/
    เป็นผู้อนุมัติ ฯลฯ) — ต้องใช้ปุ่ม Active/Inactive แทนในกรณีนี้"""
    checks: list[tuple[type, str, str]] = [
        (PurchasingRequisition, "requested_by_id", "เคยสร้าง PR ในระบบ"),
        (ApprovalRequest, "requested_by_id", "เคยสร้าง Approval Request ในระบบ"),
        (ARAttachment, "uploaded_by_id", "เคยอัปโหลดเอกสารแนบ AR"),
        (AuditLog, "actor_id", "มีประวัติการกระทำใน Log"),
        (BudgetUploadBatch, "uploaded_by_id", "เคย Upload ไฟล์ Budget"),
        (BudgetApprovalLevel, "approver_user_id", "ถูกตั้งเป็นผู้อนุมัติ Budget Level"),
        (ARBudgetApproval, "acted_by_id", "เคยอนุมัติ/ปฏิเสธ Approval Request"),
        (SourceDocument, "uploaded_by_id", "เคยอัปโหลดเอกสารต้นทาง"),
        (SourceDocument, "reviewed_by_id", "เคยตรวจทานเอกสารต้นทาง"),
        (AiUsageLog, "uploaded_by_id", "มีประวัติการใช้งาน AI"),
    ]
    for model, column_name, reason in checks:
        column = getattr(model, column_name)
        exists = db.query(model.id).filter(column == user_id).first()
        if exists is not None:
            return reason
    return None


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    """ลบ User ถาวร — ลบได้ก็ต่อเมื่อไม่มีประวัติอะไรเลยในระบบเท่านั้น (ยืนยันจากผู้ใช้ —
    ดู _user_has_history) ถ้ามีประวัติ ให้ใช้ปุ่ม Active/Inactive (Toggle) แทนเสมอ"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ User นี้")

    reason = _user_has_history(db, user_id)
    if reason is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"ลบไม่ได้ — {reason} กรุณาใช้ปุ่ม Active/Inactive แทนถ้าต้องการปิดการใช้งาน User นี้",
        )

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
