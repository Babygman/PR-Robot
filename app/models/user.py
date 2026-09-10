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

My Approvals (Phase B/2, 2026-09-10, ตาม Mockup v4 ที่ผู้ใช้ Confirm แล้ว):
- `can_view_approvals`: เปิดเมนู "การอนุมัติของฉัน" (Sidebar Submenu ขยายลง 4 หมวด) ให้
  User คนนี้เห็น — Field นี้มีไว้สำหรับ "ผู้อนุมัติ Level ปกติ" ที่ถูกตั้งเป็น
  approver_user_id ใน BudgetApprovalLevel ของแผนกใดแผนกหนึ่ง — Admin เป็นคนกดเปิดให้จาก
  หน้า "จัดการ User" (ดู app/core/deps.py: require_can_view_approvals สำหรับ Gate จริง)

  Correction (Full RBAC, 2026-09-10): เดิม is_admin/is_fa เห็นเมนูนี้เสมอโดยอัตโนมัติ —
  ผู้ใช้แจ้งว่าเข้าใจผิด "FA ยังหมายถึง FA Acknowledge อยู่" เท่านั้น ไม่ได้แปลว่ามีสิทธิ์
  เข้าเมนู My Approvals ด้วยอัตโนมัติ — ตัด is_fa ออกจากเงื่อนไขนี้แล้ว เหลือแค่ is_admin
  หรือ can_view_approvals เท่านั้น (Admin ที่ต้องการให้ FA คนหนึ่งใช้ My Approvals ได้จริง
  ต้องติ๊กทั้ง FA และ "Approve" (can_view_approvals) ให้ 2 อันแยกกัน)

Full RBAC — 9 เมนู (Correction 2026-09-10, ตาม Matrix Admin/FA/Approve/PR/AR/ALL ที่ผู้ใช้
ยืนยัน): ตัด `approver_only` ออก (ไม่ได้ใช้แล้ว — Mockup ล่าสุดไม่มีคอลัมน์นี้) เพิ่ม 3 Field
ใหม่:
- `can_view_pr`: เปิดเมนู "รายการ PR"/"สร้าง PR ใหม่" ให้เห็น — ขอบเขตจำกัดเฉพาะ PR ที่
  ตัวเองสร้างเท่านั้น (requested_by_id ตรงกับตัวเอง) เว้นแต่ is_admin หรือ can_view_all
  ดู Enforcement จริงที่ app/api/routes/purchasing_requisitions.py (_check_pr_access)
- `can_view_ar`: เปิดเมนู "Approval Request" ให้เห็น — ขอบเขตจำกัดเฉพาะ AR ที่ตัวเองสร้าง
  เท่านั้น เว้นแต่ is_admin/can_view_all หรือเป็นผู้มีบทบาทอนุมัติ (can_view_approvals/
  is_fa — ต้องเห็น AR ของคนอื่นที่รอตัวเองอนุมัติผ่านเมนู My Approvals ได้) ดู Enforcement
  จริงที่ app/api/routes/approval_requests.py (_check_ar_access)
- `can_view_all`: ขยายขอบเขต PR/AR ข้างต้นให้เห็น "ทั้งหมด" แทนที่จะเห็นเฉพาะของตัวเอง
  (สิทธิ์ดูภาพรวมล้วนๆ ไม่ใช่ Admin — ไม่มีสิทธิ์จัดการ User/Budget Level/FA Acknowledge)
  และเปิดเมนู "Log" ให้เห็นด้วย (เห็นได้เหมือน is_admin/is_fa) — ไม่ได้แปลว่ามีสิทธิ์สร้าง
  PR/AR ใหม่ (การสร้างยังต้องติ๊ก can_view_pr/can_view_ar เองตามปกติ — ดู Docstring
  app/api/routes/purchasing_requisitions.py และ approval_requests.py)

Migration Default (b6a1... my_approvals_full_rbac): User Active เดิมทุกคนตอน Migrate จะได้
can_view_pr/can_view_ar/can_view_all = True ให้อัตโนมัติทั้งหมด เพราะระบบเดิมไม่เคยมีการ
จำกัดขอบเขตเลย (ทุกคนเห็น PR/AR ของทุกคนอยู่แล้ว) — ป้องกันไม่ให้ Deploy ครั้งนี้ตัดสิทธิ์ที่
ทุกคนใช้งานอยู่ทันที Admin ไปติ๊กเอาออกทีหลังสำหรับคนที่ต้องการจำกัดให้เห็นแค่ของตัวเอง
User ใหม่ที่สร้างหลังจากนี้ Default เป็น False ทั้งหมด (ต้องติ๊กเปิดเอง)
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
    can_view_pr: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_ar: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
