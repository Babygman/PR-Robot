"""Generate PDF ของ Approval Request (AR) ตาม Template จริงของฟอร์ม "APPROVAL
REQUEST" (Sunstar Chemical Thailand, Version 20220404_rev.2) — Pattern เดียวกับ
app/services/pr_pdf.py ทุกประการ (WeasyPrint + Jinja2 Autoescape)

ใช้ Design System เดียวกับ pr_form.html (Swiss/Administrative — Archivo/Noto Sans
Thai/Source Serif 4/JetBrains Mono, Navy #1d3557) เพื่อความสม่ำเสมอของเอกสารทุกชนิด
ใน PR-Robot (Business Decision 2026-09-08) — Font Files ใช้ชุดเดียวกับที่ pr_pdf.py
ใช้อยู่แล้ว (ดู app/static/fonts/)
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.models import ApprovalRequest
from app.services.ar_numbering import format_ar_no
from app.services.user_lookup import resolve_user_names

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_MIN_DISPLAY_ROWS = 9


class _DisplayAmountItem:
    def __init__(self, label: str | None = None, amount: str | None = None) -> None:
        self.label = label
        self.amount = amount


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}"


def _fmt_date(value) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def render_ar_html(db: Session, ar: ApprovalRequest) -> str:
    """Render แค่ HTML String (แยกจากขั้น WeasyPrint แปลงเป็น PDF) — เปิดให้ Test
    ตรวจสอบ Autoescape ได้ตรงๆ โดยไม่ต้อง Parse PDF Bytes กลับมา (ดู
    tests/test_ar_pdf_security.py) — เหตุผลของ Autoescape เหมือน render_pr_html
    ทุกประการ (subject/description/suppliers ฯลฯ เป็นข้อความที่ผู้ใช้พิมพ์เองตรงๆ
    ถ้าไม่ Escape จะเปิดช่องให้ฝัง Tag แปลกปลอมเข้าไปใน HTML ก่อนส่งให้ WeasyPrint
    Render เป็น PDF ซึ่งอาจนำไปสู่ SSRF ผ่าน WeasyPrint url_fetcher เริ่มต้น)
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("ar_form.html")

    names = resolve_user_names(db, {ar.requested_by_id})

    class _ArView:
        pass

    ar_view = _ArView()
    ar_view.ar_no_display = format_ar_no(ar.ar_no)
    if ar.revision:
        ar_view.ar_no_display = f"{ar_view.ar_no_display} Rev.{ar.revision}"
    ar_view.application_date = _fmt_date(ar.application_date)
    ar_view.subject = ar.subject
    ar_view.budget_type = ar.budget_type.value if ar.budget_type else None
    ar_view.budget_no = ar.budget_no
    ar_view.budget_sub_category = ar.budget_sub_category
    ar_view.budget_name = ar.budget_name
    ar_view.budget_for_year = _fmt_money(ar.budget_for_year)
    ar_view.amount_used_before = _fmt_money(ar.amount_used_before)
    ar_view.this_application = _fmt_money(ar.this_application)
    ar_view.balance = _fmt_money(ar.balance)
    ar_view.description = ar.description
    ar_view.total = _fmt_money(ar.total)
    ar_view.vat_amount = _fmt_money(ar.vat_amount)
    ar_view.grand_total = _fmt_money(ar.grand_total)
    ar_view.suppliers = ar.suppliers
    ar_view.term_of_payment = ar.term_of_payment
    # แยก Schedule Start/Finish เป็น 2 คอลัมน์วันที่แล้ว (Feedback 2026-09-08) — รวมเป็น
    # ข้อความ Range เดียวให้ Template แสดงง่ายๆ เช่น "3/9/2026 - 15/9/2026" (ถ้ามีแค่
    # ด้านเดียวแสดงด้านนั้นด้านเดียว ไม่ใส่ขีดคั่นลอยๆ)
    start_str = _fmt_date(ar.schedule_start)
    finish_str = _fmt_date(ar.schedule_finish)
    if start_str and finish_str:
        ar_view.schedule_range = f"{start_str} - {finish_str}"
    else:
        ar_view.schedule_range = start_str or finish_str
    ar_view.requested_by_name = names.get(ar.requested_by_id)

    display_items = [
        _DisplayAmountItem(label=item.label, amount=_fmt_money(item.amount))
        for item in sorted(ar.amount_items, key=lambda i: i.item_no)
    ]
    # เก็บจำนวนรายการ "จริง" ไว้ก่อน Pad บรรทัดว่าง — ใช้ตัดสิน Tier (Fixed 1 หน้า vs
    # Overflow) แทนความยาวของ display_items หลัง Pad (ดูคำอธิบายยาวใน ar_form.html
    # ตรง {% set tier = ... %} — สรุปสั้นๆ: แถวว่างที่ Pad เพิ่มมีความสูงเกือบ 0 เพราะ
    # ไม่มีข้อความ (Div ว่างไม่สร้าง Line Box ใน WeasyPrint) ในขณะที่แถวจริงมีความสูง
    # เต็มเสมอ ถ้าใช้ความยาว List หลัง Pad (ซึ่ง Pad ขั้นต่ำ 9 เสมอ) มาตัดสิน Tier จะ
    # เข้าใจผิดว่ามีที่ว่างพอสำหรับ 12 แถวจริง ทั้งที่จริงพื้นที่ที่เหลือใน .items-wrap
    # (หลังย้าย Total/Vat/Grand Total ออกไปไว้ .bottom-block ที่ Fix ขนาดแล้ว) รองรับ
    # แถว "จริง" (มีข้อความ) ได้แค่ไม่กี่แถวก่อนโดน overflow:hidden ตัดทิ้งเงียบๆ
    # (ยืนยันด้วย WeasyPrint Render จริง + pdfplumber วัดตำแหน่งจริง 2026-09-08)
    real_item_count = len(ar.amount_items)
    while len(display_items) < _MIN_DISPLAY_ROWS:
        display_items.append(_DisplayAmountItem())

    return template.render(
        ar=ar_view,
        display_items=display_items,
        real_item_count=real_item_count,
        generated_at=_now_str(),
    )


def render_ar_pdf(db: Session, ar: ApprovalRequest) -> bytes:
    html_out = render_ar_html(db, ar)
    return HTML(string=html_out, base_url=str(_TEMPLATE_DIR)).write_pdf()


def _now_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
