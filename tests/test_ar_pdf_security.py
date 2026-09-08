"""Security Regression Test สำหรับ Approval Request — Pattern เดียวกับ
tests/test_pr_pdf_security.py ทุกประการ (พิสูจน์ว่า app/services/ar_pdf.py เปิด
Jinja2 Autoescape จริง ป้องกัน HTML/CSS Injection ผ่าน Subject/Description/Suppliers/
Term of Payment/Schedule/Budget Name/Amount Item Label ที่ผู้ใช้พิมพ์เองตรงๆ ก่อนส่งให้
WeasyPrint Render เป็น PDF — ความเสี่ยงเดียวกับ PR (SSRF ผ่าน WeasyPrint Default
url_fetcher ถ้าไม่ Escape)
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import ApprovalRequest, ARAmountItem, ARBudgetType, User
from app.services.ar_pdf import render_ar_html

_MALICIOUS_PAYLOAD = (
    '<link rel="attachment" href="http://169.254.169.254/latest/meta-data/">'
    "<script>alert(1)</script>"
)


def _make_ar(db_session: Session, requester: User) -> ApprovalRequest:
    ar = ApprovalRequest(
        ar_no=1,
        application_date=date(2026, 9, 8),
        subject=_MALICIOUS_PAYLOAD,
        budget_type=ARBudgetType.EXPENSES,
        budget_name=_MALICIOUS_PAYLOAD,
        description=_MALICIOUS_PAYLOAD,
        suppliers=_MALICIOUS_PAYLOAD,
        term_of_payment=_MALICIOUS_PAYLOAD,
        schedule=_MALICIOUS_PAYLOAD,
        requested_by_id=requester.id,
    )
    ar.amount_items.append(ARAmountItem(item_no=1, label=_MALICIOUS_PAYLOAD, amount=None))
    db_session.add(ar)
    db_session.commit()
    db_session.refresh(ar)
    return ar


def test_malicious_field_content_is_escaped_not_interpreted_as_html(
    db_session: Session, plain_user: User
):
    ar = _make_ar(db_session, plain_user)

    html_out = render_ar_html(db_session, ar)

    assert _MALICIOUS_PAYLOAD not in html_out
    assert "<script>" not in html_out
    assert '<link rel="attachment"' not in html_out

    assert "&lt;script&gt;" in html_out
    assert "&lt;link rel=" in html_out


def test_normal_thai_and_english_content_still_renders_correctly(
    db_session: Session, plain_user: User
):
    ar = ApprovalRequest(
        ar_no=2,
        application_date=date(2026, 9, 8),
        subject="ซ่อมรถยนต์ประจำแผนก",
        budget_type=ARBudgetType.ASSETS,
        budget_name="งบซ่อมบำรุงยานพาหนะ",
        description="รายละเอียดปกติ ไม่มีอะไรพิเศษ",
        suppliers="Vorachak Yont Co., Ltd.",
        term_of_payment="Credit 30 Days",
        schedule="3/9/2026",
        requested_by_id=plain_user.id,
    )
    ar.amount_items.append(ARAmountItem(item_no=1, label="ค่าตรวจเช็คระยะ", amount=None))
    db_session.add(ar)
    db_session.commit()
    db_session.refresh(ar)

    html_out = render_ar_html(db_session, ar)

    assert "ซ่อมรถยนต์ประจำแผนก" in html_out
    assert "งบซ่อมบำรุงยานพาหนะ" in html_out
    assert "ค่าตรวจเช็คระยะ" in html_out
