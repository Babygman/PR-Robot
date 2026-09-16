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

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.models import BudgetMaster, PRStatus, PurchasingRequisition
from app.services import pr_budget_workflow
from app.services.user_lookup import resolve_user_names

# 4 ชื่อ Rank ที่ตรงกับตาราง "Authority" ในฟอร์มจริง (pr_form.html) — Pattern เดียวกับ
# _AUTHORITY_RANKS ของ ar_pdf.py ทุกประการ (ยืนยันกับผู้ใช้แล้ว 2026-09-15 ให้ PR ใช้
# รายชื่อตำแหน่งตายตัวชุดเดียวกับ AR) — Level ที่ตั้งชื่อไม่ตรงจะไม่ถูก Auto-fill ลงตาราง
# Authority (ไม่ Error/ไม่ Crash แค่ไม่มีลายเซ็นแสดงในช่องนั้น)
_AUTHORITY_RANKS = ["President / Director", "General Manager", "Senior Manager", "Manager"]

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
    names = resolve_user_names(db, {pr.requested_by_id})
    return {"requested_by_name": names.get(pr.requested_by_id)}


def render_pr_html(
    db: Session, pr: PurchasingRequisition, *, signature_log: list[dict] | None = None
) -> str:
    """Render แค่ HTML String (แยกจากขั้น WeasyPrint แปลงเป็น PDF) — เปิดให้ Test
    ตรวจสอบ Autoescape ได้ตรงๆ โดยไม่ต้อง Parse PDF Bytes กลับมา (ดู
    tests/test_pr_pdf_security.py)

    signature_log (Phase C, 2026-09-16, Design §3.2.3): รายการ Signature Log ที่จะฝังลง
    ท้ายเอกสาร (Name/Position/Date-time/IP) — ส่งมาเฉพาะตอน Seal ครั้งเดียวตอน Finalize
    จริงเท่านั้น (ดู app/services/pdf_sealing.py::seal_pr) การเรียกแบบปกติ (พิมพ์/
    ดาวน์โหลดระหว่างขั้นตอน) ไม่ส่งพารามิเตอร์นี้ — None แปลว่าไม่แสดง Section นี้เลย
    """
    # Security Review (Phase 8, 2026-09-02): Autoescape ต้องเปิดเสมอ — description/
    # reason/remark/section/division ฯลฯ อาจมาจาก Gemini AI สกัดข้อมูลจากเอกสารที่
    # อัปโหลด (ควบคุมโดยผู้ไม่หวังดีได้) หรือผู้ใช้พิมพ์เองตรงๆ ก็ได้ ถ้าไม่ Escape
    # HTML จะเปิดช่องให้ฝัง Tag แปลกปลอมเข้าไปใน HTML ก่อนส่งให้ WeasyPrint Render
    # เป็น PDF ซึ่งอาจนำไปสู่ SSRF ผ่าน WeasyPrint url_fetcher เริ่มต้น (เช่น
    # <link rel="attachment" href="http://169.254.169.254/..."> หรือ Layout เพี้ยน)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("pr_form.html")

    names = _resolve_names(db, pr)

    class _PrView:
        pass

    pr_view = _PrView()
    pr_view.section = pr.section
    pr_view.division = pr.division
    # Revise (2026-09-03): PR ที่ Revise มาจากฉบับ Finalized เดิม ใช้เลข PR เดิม + Rev
    # ต่อท้าย (เช่น "3 Rev.1") — revision=0 คือต้นฉบับ แสดงเลขเปล่าๆ เหมือนเดิม
    pr_view.pr_no = f"{pr.pr_no} Rev.{pr.revision}" if pr.revision else str(pr.pr_no)
    pr_view.doc_date = _fmt_date(pr.doc_date)
    pr_view.remark = pr.remark
    pr_view.requested_by_name = names["requested_by_name"]

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

    # Phase 11 (2026-09-15): budget/used_before_amount/balance ไม่ Denormalize เก็บใน
    # pr_budget_control แล้ว — อ่านสดจาก budget_master ผ่าน budget_master_id แทน (Resolve
    # จริงตอนกด "ส่งขออนุมัติ" — ดู pr_budget_workflow.start_budget_workflow — ว่างเปล่า
    # เฉพาะ PR ที่ยังไม่เคยกดส่งขออนุมัติเลยเท่านั้น)
    budget_view = _BudgetView()
    bc = pr.budget_control
    budget_view.budget_no = bc.budget_no if bc and bc.budget_no else ""
    budget_view.account_code = bc.account_code if bc and bc.account_code else ""
    budget_view.this_application = _fmt_money(bc.this_application) if bc else ""
    master = db.get(BudgetMaster, bc.budget_master_id) if bc and bc.budget_master_id else None
    if master is not None:
        budget_view.budget = _fmt_money(master.budgeted_amount)
        budget_view.used_before_amount = _fmt_money(master.used_amount)
        budget_view.balance = _fmt_money(master.budgeted_amount - master.used_amount)
    else:
        budget_view.budget = ""
        budget_view.used_before_amount = ""
        budget_view.balance = ""

    # PR Approval Level (Phase 11 Phase 4, 2026-09-15): Auto-fill ตาราง Authority จาก
    # Workflow อนุมัติดิจิทัลจริง (เดิม Hardcode ว่างเปล่าไว้เซ็นสดตาม Scope Revision
    # Phase 9) — Pattern เดียวกับ ar_pdf.py ทุกประการ แต่ไม่มี fa_signature (PR ไม่มี FA
    # Acknowledge) และ Step ของ build_approval_progress ไม่มี step_type (ทุกแถวเป็น
    # Level เสมอ) — เติมทีละแถวทันทีที่ Level นั้นอนุมัติผ่านจริง ไม่ต้องรอครบทุก Level
    authority_signatures: dict[str, dict[str, str]] = {}
    if pr.status == PRStatus.FINALIZED:
        for step in pr_budget_workflow.build_approval_progress(db, pr):
            if step["status"] != "approved":
                continue
            if step["level_name"] not in _AUTHORITY_RANKS:
                continue
            authority_signatures[step["level_name"]] = {
                "name": step["acted_by_name"] or "",
                "date": _fmt_date(step["acted_at"]),
                "comment": step["reason"] or "",
            }

    return template.render(
        pr=pr_view,
        display_items=display_items,
        budget=budget_view,
        authority_signatures=authority_signatures,
        signature_log=signature_log,
        generated_at=_now_str(),
    )


def render_pr_pdf(
    db: Session, pr: PurchasingRequisition, *, signature_log: list[dict] | None = None
) -> bytes:
    html_out = render_pr_html(db, pr, signature_log=signature_log)
    return HTML(string=html_out, base_url=str(_TEMPLATE_DIR)).write_pdf()


def _now_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
