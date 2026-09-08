"""Smoke tests สำหรับ Page Routes (Phase 7) — ยืนยันว่าแต่ละหน้าคืน 200 + HTML
ที่มีเนื้อหาคาดหวัง (ไม่ทดสอบ JS ฝั่ง Client ที่นี่ — ส่วนนั้นทดสอบด้วย Browser E2E)
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_page_login(client: TestClient) -> None:
    resp = client.get("/app/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "login" in resp.text.lower()


def test_page_dashboard(client: TestClient) -> None:
    resp = client.get("/app/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "pr-table-body" in resp.text


def test_page_pr_new(client: TestClient) -> None:
    resp = client.get("/app/prs/new")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PR_ID = null" in resp.text


def test_page_pr_edit(client: TestClient) -> None:
    resp = client.get("/app/prs/42/edit")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PR_ID = 42" in resp.text


def test_page_pr_detail(client: TestClient) -> None:
    resp = client.get("/app/prs/42")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PR_ID = 42" in resp.text


def test_page_ar_list(client: TestClient) -> None:
    resp = client.get("/app/ars")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ar-table-body" in resp.text


def test_page_ar_new(client: TestClient) -> None:
    resp = client.get("/app/ars/new")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "AR_ID = null" in resp.text


def test_page_ar_edit(client: TestClient) -> None:
    resp = client.get("/app/ars/42/edit")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "AR_ID = 42" in resp.text


def test_page_ar_detail(client: TestClient) -> None:
    resp = client.get("/app/ars/42")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "AR_ID = 42" in resp.text


def test_page_upload(client: TestClient) -> None:
    resp = client.get("/app/documents/upload")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "doc-file" in resp.text


def test_root_redirects_to_app(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/app/"


def test_static_assets_served(client: TestClient) -> None:
    css = client.get("/static/style.css")
    assert css.status_code == 200
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "apiFetch" in js.text
