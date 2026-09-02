"""Test Workflow อนุมัติ (Reviewed/Approved/Received) + ประวัติ/ค้นหา (Phase 6)"""
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
        "remark": "ทดสอบ Workflow",
    }
    body.update(overrides)
    return body


def _create_pr_as_plain(client: TestClient) -> dict:
    _login_as(client, "plain@example.com", "plainpass123")
    res = client.post("/prs", json=_sample_pr_body())
    assert res.status_code == 201
    return res.json()


def test_full_workflow_happy_path(client: TestClient, plain_user: User, admin_user: User):
    created = _create_pr_as_plain(client)
    assert created["status"] == "draft"
    assert created["requested_by_name"] == "Plain User"

    _login_as(client, "admin@example.com", "adminpass123")

    res = client.post(f"/prs/{created['id']}/review", json={"note": "ตรวจแล้วโอเค"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "reviewed"
    assert body["reviewed_by_name"] == "Admin"
    assert body["reviewed_at"] is not None

    res = client.post(f"/prs/{created['id']}/approve")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["approved_by_name"] == "Admin"

    res = client.post(f"/prs/{created['id']}/receive")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "received"
    assert body["received_by_name"] == "Admin"

    history = client.get(f"/prs/{created['id']}/history")
    assert history.status_code == 200
    actions = [h["action"] for h in history.json()]
    assert actions == ["pr.created", "pr.reviewed", "pr.approved", "pr.received"]
    assert history.json()[1]["detail"] == {"note": "ตรวจแล้วโอเค"}


def test_cannot_approve_before_review(client: TestClient, plain_user: User, admin_user: User):
    created = _create_pr_as_plain(client)
    _login_as(client, "admin@example.com", "adminpass123")
    res = client.post(f"/prs/{created['id']}/approve")
    assert res.status_code == 409


def test_cannot_receive_before_approve(client: TestClient, plain_user: User, admin_user: User):
    created = _create_pr_as_plain(client)
    _login_as(client, "admin@example.com", "adminpass123")
    client.post(f"/prs/{created['id']}/review")
    res = client.post(f"/prs/{created['id']}/receive")
    assert res.status_code == 409


def test_cannot_review_twice(client: TestClient, plain_user: User, admin_user: User):
    created = _create_pr_as_plain(client)
    _login_as(client, "admin@example.com", "adminpass123")
    client.post(f"/prs/{created['id']}/review")
    res = client.post(f"/prs/{created['id']}/review")
    assert res.status_code == 409


def test_plain_user_without_flags_cannot_review(client: TestClient, plain_user: User):
    created = _create_pr_as_plain(client)
    res = client.post(f"/prs/{created['id']}/review")
    assert res.status_code == 403


def test_plain_user_without_flags_cannot_approve(client: TestClient, plain_user: User):
    created = _create_pr_as_plain(client)
    res = client.post(f"/prs/{created['id']}/approve")
    assert res.status_code == 403


def test_plain_user_without_flags_cannot_receive(client: TestClient, plain_user: User):
    created = _create_pr_as_plain(client)
    res = client.post(f"/prs/{created['id']}/receive")
    assert res.status_code == 403


def test_reviewed_pr_can_no_longer_be_edited(
    client: TestClient, plain_user: User, admin_user: User
):
    created = _create_pr_as_plain(client)
    _login_as(client, "admin@example.com", "adminpass123")
    client.post(f"/prs/{created['id']}/review")

    res = client.patch(f"/prs/{created['id']}", json=_sample_pr_body())
    assert res.status_code == 409


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
