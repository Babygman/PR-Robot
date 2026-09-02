"""Generate PDF ของ PR ตาม Template จริงของฟอร์ม FM-PU-02 Rev.2 (Sunstar Chemical Thailand)

ใช้ Jinja2 render HTML แล้วแปลงเป็น PDF ด้วย WeasyPrint (ต้องมี Library ระบบ
libpango/libcairo/libgdk-pixbuf ติดตั้งอยู่แล้วในเครื่อง — ตรวจสอบแล้วว่ามีอยู่ใน
Sandbox พัฒนาทั้งสองฝั่ง Cloud Container และ Device Bash โดยไม่ต้องใช้ Root/Sudo
เพิ่มเติม ถ้า Deploy บน Docker Image ใหม่ ต้องติดตั้ง Package `fonts-noto-core`
(หรือฟอนต์ไทยอื่นที่เทียบเท่า) ไว้ใน Image ด้วย ไม่เช่นนั้นตัวอักษรไทยบางตัว
(เช่น สระอำ) อาจเพี้ยนตอน Fallback ไปใช้ฟอนต์อื่นที่ไม่รองรับภาษาไทยดีพอ

หมายเหตุ Known Limitation (2026-09-02): PDF ที่ Render ออกมาแสดงผลภาษาไทยถูกต้อง
สมบูรณ์ (ตรวจด้วยตาจริงแล้ว) แต่ Text Layer ภายใน PDF (สำหรับ Copy/ค้นหาข้อความ)
อาจสูญเสียสระอำ (ำ) ไปในบางคำ เป็นข้อจำกัดของ WeasyPrint/Pango ระดับ Library
ไม่กระทบการพิมพ์เอกสารเพื่อเซ็นจริงซึ่งเป็น Use Case หลัก
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.models import PurchasingRequisition, User

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_MIN_DISPLAY_ROWS = 6


class _DisplayItem:
    def __init__(
        self,
        item_no: int | None = None,
        account_code: str | None = None,
        description: str | None = None,
        quantity: str | None = None,
        required_date: str | None = None,
        reason: str | None = None,
        ref_po: str | None = None,
    ) -> None:
        self.item_no = item_no
        self.account_code = account_code
        self.description = description
        self.quantity = quantity
        self.required_date = required_date
        self.reason = reason
        self.ref_po = ref_po


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}"


def _fmt_date(value) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def _resolve_names(db: Session, pr: PurchasingRequisition) -> dict[str, str | None]:
    ids = {
        i
        for i in (pr.requested_by_id, pr.reviewed_by_id, pr.approved_by_id, pr.received_by_id)
        if i is not None
    }
    names: dict[int, str] = {}
    if ids:
        names = {u.id: u.name for u in db.query(User).filter(User.id.in_(ids)).all()}
    return {
        "requested_by_name": names.get(pr.requested_by_id),
        "reviewed_by_name": names.get(pr.reviewed_by_id) if pr.reviewed_by_id else None,
        "approved_by_name": names.get(pr.approved_by_id) if pr.approved_by_id else None,
        "received_by_name": names.get(pr.received_by_id) if pr.received_by_id else None,
    }


def render_pr_pdf(db: Session, pr: PurchasingRequisition) -> bytes:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("pr_form.html")

    names = _resolve_names(db, pr)

    class _PrView:
        pass

    pr_view = _PrView()
    pr_view.section = pr.section
    pr_view.division = pr.division
    pr_view.pr_no = pr.pr_no
    pr_view.doc_date = _fmt_date(pr.doc_date)
    pr_view.remark = pr.remark
    pr_view.requested_by_name = names["requested_by_name"]
    pr_view.reviewed_by_name = names["reviewed_by_name"]
    pr_view.approved_by_name = names["approved_by_name"]
    pr_view.received_by_name = names["received_by_name"]

    display_items = [
        _DisplayItem(
            item_no=item.item_no,
            account_code=item.account_code,
            description=item.description,
            quantity=item.quantity,
            required_date=_fmt_date(item.required_date),
            reason=item.reason,
            ref_po=item.ref_po,
        )
        for item in sorted(pr.items, key=lambda i: i.item_no)
    ]
    while len(display_items) < _MIN_DISPLAY_ROWS:
        display_items.append(_DisplayItem(item_no=len(display_items) + 1))

    class _BudgetView:
        pass

    budget_view = _BudgetView()
    bc = pr.budget_control
    budget_view.budget = _fmt_money(bc.budget) if bc else ""
    budget_view.used_before_amount = _fmt_money(bc.used_before_amount) if bc else ""
    budget_view.this_application = _fmt_money(bc.this_application) if bc else ""
    budget_view.balance = _fmt_money(bc.balance) if bc else ""

    html_out = template.render(
        pr=pr_view,
        display_items=display_items,
        budget=budget_view,
        generated_at=_now_str(),
    )
    return HTML(string=html_out, base_url=str(_TEMPLATE_DIR)).write_pdf()


def _now_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
