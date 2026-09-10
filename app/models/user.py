"""User model — ผู้ใช้ระบบทุกคน Login แล้วเป็น "Requester" ได้เสมอ (ไม่ต้องมี Flag)

Scope Revision (Phase 9, 2026-09-03): ตัด can_review/can_approve/can_receive ออก
ทั้งหมด — ระบบไม่มี Workflow อนุมัติในตัวเองแล้ว (Reviewed/Approved/Received by
เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกไปนอกระบบล้วนๆ ตาม Business Decision ที่คุยกันใหม่
2026-09-03 หลัง Product Owner Feedback ว่า Design เดิมผิดตั้งแต่แรก) เหลือแค่
is_admin สำหรับจัดการ User เท่านั้น

Budget Control (Phase 10, 2026-09-09): ย้อนกลับ Scope Revision ข้างต้นเฉพาะจุด — เพิ่ม
Workflow อนุมัติ "หักงบประมาณ" ของ AR กลับมา (ดู app/models/budget.py) เพิ่ม 2 Field:
- `position`: ตำแหน่งงาน เก็บไว้แสดงผลเท่านั้น ไม่มีผลต่อ Logic การอนุมัติ (ผู้อนุมัติ
  แต่ละ Level ผูกกับตัวบุคคลเจาะจงใน BudgetApprovalLevel.approver_user_id ไม่ใช่ Position)
- `is_fa`: Role กลาง ไม่ผูกกับ Department — คนที่ True (1) Upload/จัดการ Excel งบประมาณได้
  (2) เป็นผู้ทำขั้นตอนสุดท้าย "FA Acknowledge" ให้ AR ของทุกแผนกได้ (ดู
  app/services/budget_workflow.py) — `department` ยังคง Nullable เหมือนเดิม (ไม่บังคับ
  ระดับ DB) เพราะผู้อนุมัติบาง Level ไม่มีแผนก (Cross-department) ได้ — บังคับมี
  Department เฉพาะตอน "สร้าง AR" เท่านั้น (Validate ที่ app/api/routes/approval_requests.py)

My Approvals (Phase B/2, 2026-09-10, ตาม Mockup v4 ที่ผู้ใช้ Confirm แล้ว): เพิ่ม 2 Field
- `can_view_approvals`: เปิดเมนู "การอนุมัติของฉัน" (Sidebar Submenu ขยายลง 4 หมวด) ให้
  User คนนี้เห็น — is_admin/is_fa เห็นเมนูนี้เสมออยู่แล้วโดยไม่ต้องเปิด Field นี้ (เป็น
  Role ที่มีสิทธิ์อนุมัติอยู่แล้วโดยนิยาม) Field นี้มีไว้สำหรับ "ผู้อนุมัติ Level ปกติ" ที่
  ไม่ใช่ Admin/FA แต่ถูกตั้งเป็น approver_user_id ใน BudgetApprovalLevel ของแผนกใดแผนกหนึ่ง
  — Admin เป็นคนกดเปิดให้จากหน้า "จัดการ User" (ดู app/api/routes/approval_requests.py:
  get_my_approval_counts/list_my_approvals_route สำหรับ Gate จริง)
- `approver_only`: True = ซ่อนเมนูอื่นทั้งหมดใน Sidebar เหลือแค่ "การอนุมัติของฉัน" อย่าง
  เดียว (Feedback จริงจากผู้ใช้: "User ที่มีหน้าที่ Approve อย่างเดียว ก็จะเห็น My approve
  อย่างเดียว") — ไม่ผูกกับ can_view_approvals/is_admin/is_fa เลย เป็น Flag แสดงผล Sidebar
  ล้วนๆ (ดู app/static/app.js: requireLogin) ไม่มีผลต่อ Permission ฝั่ง Backend ใดๆ
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_approvals: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approver_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
