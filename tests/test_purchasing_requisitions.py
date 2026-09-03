"""Test บันทึก PR + Generate PDF (Phase 5)"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import PRStatus, PurchasingRequisition, SourceDocType, SourceDocument, User
from app.services.pr_pdf import render_pr_html


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
    pr.status = PRStatus.FINALIZED
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


def test_get_pr_pdf_auto_finalizes_on_first_download(
    client: TestClient, plain_user: User, db_session: Session
):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    pr = db_session.get(PurchasingRequisition, created["id"])
    assert pr.status == PRStatus.DRAFT

    res = client.get(f"/prs/{created['id']}/pdf")
    assert res.status_code == 200

    db_session.refresh(pr)
    assert pr.status == PRStatus.FINALIZED

    # ครั้งที่สองยังดาวน์โหลดได้ปกติ (ไม่ error แม้ Finalized แล้ว)
    res2 = client.get(f"/prs/{created['id']}/pdf")
    assert res2.status_code == 200


def test_finalized_pr_rejects_edit(client: TestClient, plain_user: User, db_session: Session):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{created['id']}/pdf")

    res = client.patch(f"/prs/{created['id']}", json=_sample_pr_body(remark="แก้ไม่ได้แล้ว"))
    assert res.status_code == 409


# ── Revise (Feedback จริงจากผู้ใช้ 2026-09-03): PR ที่ Finalized แล้วต้อง Revise
# ต่อได้เมื่อพบข้อผิดพลาดทีหลัง โดยไม่ไปรื้อของเดิมที่เซ็นกระดาษไปแล้ว — เลข PR ใช้เลข
# เดิม + Rev ต่อท้าย (อนุมัติจากผู้ใช้) ──────────────────────────────────────────────


def test_revise_draft_pr_rejected(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    res = client.post(f"/prs/{created['id']}/revise")
    assert res.status_code == 409


def test_revise_finalized_pr_creates_draft_copy(client: TestClient, plain_user: User):
    _login(client)
    original = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{original['id']}/pdf")

    res = client.post(f"/prs/{original['id']}/revise")
    assert res.status_code == 201
    revised = res.json()

    assert revised["id"] != original["id"]
    assert revised["pr_no"] == original["pr_no"]
    assert revised["revision"] == 1
    assert revised["revised_from_id"] == original["id"]
    assert revised["status"] == "draft"
    assert revised["requested_by_id"] == original["requested_by_id"]
    assert revised["section"] == original["section"]
    assert revised["items"][0]["description"] == original["items"][0]["description"]
    assert revised["budget_control"]["budget"] == original["budget_control"]["budget"]

    # ต้นฉบับต้องไม่ถูกแตะต้อง แต่รู้ตัวว่าถูก Revise ไปแล้วเป็นฉบับไหน
    orig_after = client.get(f"/prs/{original['id']}").json()
    assert orig_after["status"] == "finalized"
    assert orig_after["superseded_by_id"] == revised["id"]


def test_revise_can_be_edited_and_finalized_independently(
    client: TestClient, plain_user: User
):
    _login(client)
    original = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{original['id']}/pdf")
    revised = client.post(f"/prs/{original['id']}/revise").json()

    patch_res = client.patch(
        f"/prs/{revised['id']}", json=_sample_pr_body(remark="แก้ไขหลัง Revise")
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["remark"] == "แก้ไขหลัง Revise"


def test_revise_already_superseded_pr_rejected(client: TestClient, plain_user: User):
    _login(client)
    original = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{original['id']}/pdf")
    client.post(f"/prs/{original['id']}/revise")

    # Revise ซ้ำจากต้นฉบับเดิมอีกรอบ (ไม่ใช่จากฉบับ Rev.1 ล่าสุด) ต้องถูกปฏิเสธ
    res = client.post(f"/prs/{original['id']}/revise")
    assert res.status_code == 409


def test_revise_second_time_increments_revision(client: TestClient, plain_user: User):
    _login(client)
    original = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{original['id']}/pdf")
    rev1 = client.post(f"/prs/{original['id']}/revise").json()
    client.get(f"/prs/{rev1['id']}/pdf")

    res = client.post(f"/prs/{rev1['id']}/revise")
    assert res.status_code == 201
    rev2 = res.json()
    assert rev2["pr_no"] == original["pr_no"]
    assert rev2["revision"] == 2
    assert rev2["revised_from_id"] == rev1["id"]


def test_revise_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/prs/9999/revise")
    assert res.status_code == 404


def test_revise_requires_login(client: TestClient):
    res = client.post("/prs/1/revise")
    assert res.status_code == 401


def test_revised_pr_pdf_shows_rev_suffix(client: TestClient, plain_user: User, db_session: Session):
    _login(client)
    original = client.post("/prs", json=_sample_pr_body()).json()
    client.get(f"/prs/{original['id']}/pdf")
    revised = client.post(f"/prs/{original['id']}/revise").json()

    orig_pr = db_session.get(PurchasingRequisition, original["id"])
    revised_pr = db_session.get(PurchasingRequisition, revised["id"])

    orig_html = render_pr_html(db_session, orig_pr)
    revised_html = render_pr_html(db_session, revised_pr)

    assert "Rev." not in orig_html
    assert f"{original['pr_no']} Rev.1" in revised_html
