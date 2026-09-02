"""Security Regression Test (Phase 8) — พิสูจน์ว่า HTML/CSS Injection ผ่านช่องทาง
Description/Reason/Section/Division/Remark ของ PR ไม่สามารถฝัง Tag ดิบเข้าไปใน
HTML ก่อนส่งให้ WeasyPrint Render เป็น PDF ได้อีกต่อไป

พบระหว่าง Security Review Phase 8 (2026-09-02): app/services/pr_pdf.py เดิมสร้าง
Jinja2 Environment โดยไม่เปิด autoescape — Field พวกนี้มาจาก Gemini AI สกัดข้อมูล
จากเอกสารที่อัปโหลด (ควบคุมโดยผู้ไม่หวังดีได้) หรือผู้ใช้พิมพ์ตรงๆ ก็ได้ ถ้าไม่ Escape
จะเปิดช่องให้ฝัง Tag เช่น <link rel="attachment" href="http://169.254.169.254/...">
ซึ่งรวมกับช่องโหว่ SSRF ที่รู้จักแล้วใน WeasyPrint default url_fetcher (PYSEC-2026-2034,
พบจาก pip-audit) จะทำให้ PDF Generation กลายเป็นช่องทาง SSRF ไปยัง Internal
Network/Cloud Metadata ได้จริง — แก้แล้วด้วย autoescape=select_autoescape(["html"])
ใน render_pr_html()
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import PRItem, PurchasingRequisition, User
from app.services.pr_pdf import render_pr_html

_MALICIOUS_PAYLOAD = (
    '<link rel="attachment" href="http://169.254.169.254/latest/meta-data/">'
    "<script>alert(1)</script>"
)


def _make_pr(db_session: Session, requester: User) -> PurchasingRequisition:
    pr = PurchasingRequisition(
        pr_no=1,
        section=_MALICIOUS_PAYLOAD,
        division="แผนกทดสอบ",
        doc_date=date(2026, 9, 2),
        remark=_MALICIOUS_PAYLOAD,
        requested_by_id=requester.id,
    )
    pr.items.append(
        PRItem(
            item_no=1,
            account_code="TEST-01",
            description=_MALICIOUS_PAYLOAD,
            quantity="1",
            reason=_MALICIOUS_PAYLOAD,
        )
    )
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


def test_malicious_field_content_is_escaped_not_interpreted_as_html(
    db_session: Session, plain_user: User
):
    pr = _make_pr(db_session, plain_user)

    html_out = render_pr_html(db_session, pr)

    # Payload ดิบต้องไม่ปรากฏใน Output เลย (ถ้าปรากฏ = ยังไม่ Escape = ช่องโหว่กลับมา)
    assert _MALICIOUS_PAYLOAD not in html_out
    assert "<script>" not in html_out
    assert '<link rel="attachment"' not in html_out

    # ต้องเห็นเป็นข้อความที่ Escape แล้วแทน (พิสูจน์ว่า Autoescape ทำงานจริง ไม่ใช่แค่
    # หายไปเฉยๆ)
    assert "&lt;script&gt;" in html_out
    assert "&lt;link rel=" in html_out


def test_normal_thai_and_english_content_still_renders_correctly(
    db_session: Session, plain_user: User
):
    pr = PurchasingRequisition(
        pr_no=2,
        section="จัดซื้อ",
        division="Warehouse",
        doc_date=date(2026, 9, 2),
        remark="หมายเหตุปกติ ไม่มีอะไรพิเศษ",
        requested_by_id=plain_user.id,
    )
    pr.items.append(
        PRItem(
            item_no=1,
            account_code="5100-01",
            description="กระดาษ A4 80 แกรม",
            quantity="10 รีม",
            reason="เติมสต๊อก",
        )
    )
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)

    html_out = render_pr_html(db_session, pr)

    # Escape ปกติของ Jinja2 ไม่ควรทำลายข้อความภาษาไทย/อังกฤษปกติที่ไม่มีอักขระพิเศษ HTML
    assert "จัดซื้อ" in html_out
    assert "กระดาษ A4 80 แกรม" in html_out
    assert "เติมสต๊อก" in html_out
