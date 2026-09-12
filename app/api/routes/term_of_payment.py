"""Term of Payment — Master Data Management (AR Redesign, 2026-09-11)

ดู app/models/term_of_payment.py สำหรับที่มา/เหตุผลของ Design — ฟอร์ม AR อ่านรายการ
Active จากที่นี่มาแสดงเป็น Dropdown (GET ?active_only=true) — GET เปิดให้ Login แล้ว
เรียกได้ทุกคน (User ทั่วไปที่สร้าง AR ต้องอ่านรายการนี้ได้) ส่วน Create/Update/Delete
เป็น Admin เท่านั้น (จัดการผ่านหน้า /app/term-of-payment)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models import TermOfPaymentOption, User
from app.schemas.term_of_payment import (
    TermOfPaymentOptionCreate,
    TermOfPaymentOptionRead,
    TermOfPaymentOptionUpdate,
)
from app.services.system_log import get_client_ip, log_event, stringify_changes

router = APIRouter(prefix="/term-of-payment-options", tags=["term-of-payment"])


@router.get("", response_model=list[TermOfPaymentOptionRead])
def list_term_of_payment_options(
    active_only: bool = Query(
        default=False,
        description="true = คืนเฉพาะรายการ Active — ใช้เติม Dropdown ในฟอร์ม AR",
    ),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[TermOfPaymentOption]:
    query = db.query(TermOfPaymentOption)
    if active_only:
        query = query.filter(TermOfPaymentOption.is_active.is_(True))
    return query.order_by(TermOfPaymentOption.name).all()


@router.post("", response_model=TermOfPaymentOptionRead, status_code=status.HTTP_201_CREATED)
def create_term_of_payment_option(
    body: TermOfPaymentOptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TermOfPaymentOption:
    option = TermOfPaymentOption(name=body.name.strip())
    db.add(option)
    try:
        db.flush()
        log_event(
            db,
            actor_id=current_user.id,
            action="term_of_payment.created",
            entity_type="term_of_payment",
            entity_id=option.id,
            detail={"name": option.name},
            ip_address=get_client_ip(request),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "มีรายการชื่อนี้อยู่แล้ว") from exc
    db.refresh(option)
    return option


@router.patch("/{option_id}", response_model=TermOfPaymentOptionRead)
def update_term_of_payment_option(
    option_id: int,
    body: TermOfPaymentOptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TermOfPaymentOption:
    option = db.get(TermOfPaymentOption, option_id)
    if option is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการนี้")
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()
    before = {key: getattr(option, key) for key in updates}
    for key, value in updates.items():
        setattr(option, key, value)
    log_event(
        db,
        actor_id=current_user.id,
        action="term_of_payment.updated",
        entity_type="term_of_payment",
        entity_id=option.id,
        detail={"name": option.name, "changes": stringify_changes(before, updates)},
        ip_address=get_client_ip(request),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "มีรายการชื่อนี้อยู่แล้ว") from exc
    db.refresh(option)
    return option


@router.delete("/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_term_of_payment_option(
    option_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    """ลบออกจากรายการ Master ได้ตรงๆ ไม่มี Foreign Key ผูกกับ AR เลย (ดู Docstring
    app/models/term_of_payment.py) — AR เก่าที่เคยเลือกชื่อนี้ไว้ยังคงเก็บ Text เดิมอยู่
    ไม่หายไปไหน แค่จะไม่มีให้เลือกซ้ำในฟอร์มสร้าง/แก้ไข AR ใหม่เท่านั้น"""
    option = db.get(TermOfPaymentOption, option_id)
    if option is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการนี้")
    log_event(
        db,
        actor_id=current_user.id,
        action="term_of_payment.deleted",
        entity_type="term_of_payment",
        entity_id=option.id,
        detail={"name": option.name},
        ip_address=get_client_ip(request),
    )
    db.delete(option)
    db.commit()
