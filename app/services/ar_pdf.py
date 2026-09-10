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

from app.models import ApprovalRequest, ARStatus
from app.services import budget_workflow
from app.services.ar_numbering import format_ar_no
from app.services.user_lookup import resolve_user_names

# 4 ชื่อ Rank ที่ตรงกับตาราง "Authority" ในฟอร์มจริง (ar_form.html) — ตัวอย่าง Flow
# จริงที่แนบมา (2026-09-09) ยืนยันว่าใช้ 4 ชื่อนี้เป๊ะ ระบบ Match BudgetApprovalLevel.
# level_name กับชื่อในลิสต์นี้แบบ Exact String — Level ที่ตั้งชื่อไม่ตรงจะไม่ถูก
# Auto-fill ลงตาราง Authority (ไม่ Error/ไม่ Crash แค่ไม่มีลายเซ็นแสดงในช่องนั้น)
_AUTHORITY_RANKS = ["President / Director", "General Manager", "Senior Manager", "Manager"]

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

    # Budget Control (2026-09-09, Design v4.1 §6.1): Auto-fill ตาราง Authority + ช่อง
    # F&A จาก Workflow อนุมัติจริงในระบบ (เดิม Hardcode ว่างเปล่าไว้เซ็นสด) — เติมทีละ
    # แถวทันทีที่ Level นั้น/FA Acknowledge ผ่านจริง (ไม่ต้องรอครบ) PDF Regenerate ใหม่
    # ทุกครั้งที่เปิด/พิมพ์อยู่แล้ว จึงไม่กระทบกลไก Finalize/Lock เดิมเลย
    authority_signatures: dict[str, dict[str, str]] = {}
    fa_signature: dict[str, str] | None = None
    if ar.status == ARStatus.FINALIZED:
        for step in budget_workflow.build_approval_progress(db, ar):
            if step["status"] != "approved":
                continue
            # Correction 2026-09-10 (Phase A): เติม Comment ที่ผู้อนุมัติกรอกตอนกด
            # "อนุมัติ" (ไม่บังคับ) ลงช่อง Comments ในตาราง Authority ของ PDF ด้วย —
            # ใช้คอลัมน์ reason เดิม (เดิมใช้เก็บเหตุผลปฏิเสธเท่านั้น ตอนนี้ใช้ร่วมกับ
            # Comment ตอนอนุมัติด้วย ดู budget_workflow.approve_level/fa_acknowledge)
            signed = {
                "name": step["acted_by_name"] or "",
                "date": _fmt_date(step["acted_at"]),
                "comment": step["reason"] or "",
            }
            if step["step_type"].value == "level" and step["level_name"] in _AUTHORITY_RANKS:
                authority_signatures[step["level_name"]] = signed
            elif step["step_type"].value == "fa_acknowledge":
                fa_signature = signed

    return template.render(
        ar=ar_view,
        display_items=display_items,
        real_item_count=real_item_count,
        authority_signatures=authority_signatures,
        fa_signature=fa_signature,
        generated_at=_now_str(),
    )


def render_ar_pdf(db: Session, ar: ApprovalRequest) -> bytes:
    html_out = render_ar_html(db, ar)
    return HTML(string=html_out, base_url=str(_TEMPLATE_DIR)).write_pdf()


def _now_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
