"""Test บันทึก PR + Generate PDF (Phase 5)"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import PRStatus, PurchasingRequisition, SourceDocType, SourceDocument, User


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


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
        "budget_control": {
            "account_code_1": "5100",
            "account_code_2": None,
            "budget": "150000.00",
            "used_before_amount": "42300.00",
            "this_application": "1500.00",
            "balance": "106200.00",
        },
        "remark": "ต้องการด่วน",
    }
    body.update(overrides)
    return body


def test_create_pr_requires_login(client: TestClient):
    res = client.post("/prs", json=_sample_pr_body())
    assert res.status_code == 401


def test_create_pr_success(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/prs", json=_sample_pr_body())
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "draft"
    assert body["requested_by_id"] == plain_user.id
    assert body["reviewed_by_id"] is None
    assert len(body["items"]) == 1
    assert body["items"][0]["item_no"] == 1
    assert body["budget_control"]["budget"] == "150000.00"
    assert isinstance(body["pr_no"], int)


def test_create_pr_allocates_sequential_numbers(client: TestClient, plain_user: User):
    _login(client)
    res1 = client.post("/prs", json=_sample_pr_body())
    res2 = client.post("/prs", json=_sample_pr_body())
    assert res2.json()["pr_no"] == res1.json()["pr_no"] + 1


def test_create_pr_rejects_missing_source_document(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/prs", json=_sample_pr_body(source_document_ids=[9999]))
    assert res.status_code == 400


def test_create_pr_links_source_document(
    client: TestClient, plain_user: User, db_session: Session
):
    doc = SourceDocument(
        file_path="storage/uploads/dummy.pdf",
        doc_type=SourceDocType.QUOTATION,
        uploaded_by_id=plain_user.id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    _login(client)
    res = client.post("/prs", json=_sample_pr_body(source_document_ids=[doc.id]))
    assert res.status_code == 201

    db_session.refresh(doc)
    assert doc.pr_id == res.json()["id"]


def test_get_pr_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.get("/prs/9999")
    assert res.status_code == 404


def test_list_prs_returns_created(client: TestClient, plain_user: User):
    _login(client)
    client.post("/prs", json=_sample_pr_body())
    res = client.get("/prs")
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_update_draft_pr_success(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    updated_body = _sample_pr_body(remark="แก้ไขแล้ว")
    updated_body["items"].append(
        {
            "account_code": "5100-02",
            "description": "ปากกา",
            "quantity": "5 โหล",
            "required_date": None,
            "reason": None,
            "ref_po": None,
        }
    )
    res = client.patch(f"/prs/{created['id']}", json=updated_body)
    assert res.status_code == 200
    body = res.json()
    assert body["remark"] == "แก้ไขแล้ว"
    assert len(body["items"]) == 2
    assert [i["item_no"] for i in body["items"]] == [1, 2]


def test_update_draft_pr_can_remove_budget_control(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    assert created["budget_control"] is not None

    updated_body = _sample_pr_body(budget_control=None)
    res = client.patch(f"/prs/{created['id']}", json=updated_body)
    assert res.status_code == 200
    assert res.json()["budget_control"] is None


def test_update_draft_pr_can_add_budget_control(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body(budget_control=None)).json()
    assert created["budget_control"] is None

    res = client.patch(f"/prs/{created['id']}", json=_sample_pr_body())
    assert res.status_code == 200
    assert res.json()["budget_control"]["budget"] == "150000.00"


def test_update_non_draft_pr_rejected(
    client: TestClient, plain_user: User, db_session: Session
):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    pr = db_session.get(PurchasingRequisition, created["id"])
    pr.status = PRStatus.REVIEWED
    db_session.commit()

    res = client.patch(f"/prs/{created['id']}", json=_sample_pr_body())
    assert res.status_code == 409


def test_get_pr_pdf_returns_valid_pdf(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    res = client.get(f"/prs/{created['id']}/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"
    assert len(res.content) > 1000
