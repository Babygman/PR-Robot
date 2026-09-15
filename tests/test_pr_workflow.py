"""Test สถานะ PR (Draft/Finalized) + ประวัติ/ค้นหา (Phase 6, ปรับปรุงตาม Scope
Revision Phase 9, 2026-09-03)

Scope Revision Phase 9: เหลือแค่ 2 สถานะ: draft (แก้ไขได้) และ finalized (ล็อกแล้ว)

PR Approval Level (Phase 11, 2026-09-15): จุด Finalize ย้ายจาก "พิมพ์/ดาวน์โหลด PDF
ครั้งแรก" ไปเป็น POST /prs/{id}/submit-for-approval แทนแล้ว (พิมพ์ดูกี่ครั้งก็ได้ไม่มีผล
ข้างเคียงอีกต่อไป — ดู test_purchasing_requisitions.py::test_get_pr_pdf_does_not_finalize)
ไฟล์นี้ใช้ budget_control=None (ไม่มี Budget Control เลย) จึง Finalize ทันทีตอน Submit
ไม่มี Workflow อนุมัติเข้ามาเกี่ยวข้อง (ดู tests/test_pr_approval_workflow.py สำหรับ Case
ที่มี Budget Control)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import User


def _login_as(client: TestClient, email: str, password: str) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200


def _sample_pr_body(**overrides) -> dict:
    body = {
        "section": "Production",
        "division": "Warehouse",
        "doc_date": "2026-09-02",
        "items": [
            {
                "account_code": "5100-01",
                "description": "กระดาษ A4 80 แกรม",
                "quantity": "10 รีม",
                "required_date": "2026-09-10",
                "reason": "เติมสต๊อก",
                "ref_po": None,
            }
        ],
        "budget_control": None,
        "remark": "ทดสอบ",
    }
    body.update(overrides)
    return body


def _create_pr_as_plain(client: TestClient) -> dict:
    _login_as(client, "plain@example.com", "plainpass123")
    res = client.post("/prs", json=_sample_pr_body())
    assert res.status_code == 201
    return res.json()


def test_pr_created_as_draft_with_only_requested_by(client: TestClient, plain_user: User):
    created = _create_pr_as_plain(client)
    assert created["status"] == "draft"
    assert created["requested_by_name"] == "Plain User"
    # ไม่มี Field ของ Workflow เดิมอีกแล้ว
    assert "reviewed_by_id" not in created
    assert "approved_by_id" not in created
    assert "received_by_id" not in created


def test_pr_history_records_creation_and_finalize(client: TestClient, plain_user: User):
    created = _create_pr_as_plain(client)
    client.post(f"/prs/{created['id']}/submit-for-approval")

    history = client.get(f"/prs/{created['id']}/history")
    assert history.status_code == 200
    actions = [h["action"] for h in history.json()]
    assert actions == ["pr.created", "pr.submitted_for_approval", "pr.finalized"]


def test_list_prs_search_by_q(client: TestClient, plain_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    client.post("/prs", json=_sample_pr_body(section="Accounting", division="Finance"))
    client.post("/prs", json=_sample_pr_body(section="Production", division="Warehouse"))

    res = client.get("/prs", params={"q": "Accounting"})
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["section"] == "Accounting"


def test_list_prs_filter_by_pr_no(client: TestClient, plain_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    created = client.post("/prs", json=_sample_pr_body()).json()

    res = client.get("/prs", params={"pr_no": created["pr_no"]})
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["id"] == created["id"]


def test_list_prs_filter_by_status(client: TestClient, plain_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    draft = client.post("/prs", json=_sample_pr_body()).json()
    finalized = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{finalized['id']}/submit-for-approval")

    res = client.get("/prs", params={"status_filter": "finalized"})
    assert res.status_code == 200
    results = res.json()
    ids = {r["id"] for r in results}
    assert finalized["id"] in ids
    assert draft["id"] not in ids


def test_list_prs_filter_requested_by_me(client: TestClient, plain_user: User, admin_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    client.post("/prs", json=_sample_pr_body())

    _login_as(client, "admin@example.com", "adminpass123")
    client.post("/prs", json=_sample_pr_body())

    res = client.get("/prs", params={"requested_by_me": True})
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["requested_by_id"] == admin_user.id


def test_list_prs_date_range_filter(client: TestClient, plain_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    client.post("/prs", json=_sample_pr_body(doc_date="2026-01-01"))
    client.post("/prs", json=_sample_pr_body(doc_date="2026-09-02"))

    res = client.get("/prs", params={"doc_date_from": "2026-06-01"})
    assert res.status_code == 200
    results = res.json()
    assert all(r["doc_date"] >= "2026-06-01" for r in results)
    assert len(results) == 1


def test_history_not_found_for_missing_pr(client: TestClient, plain_user: User):
    _login_as(client, "plain@example.com", "plainpass123")
    res = client.get("/prs/9999/history")
    assert res.status_code == 404
