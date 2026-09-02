from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import User


def test_login_success_sets_cookie(client: TestClient, admin_user: User):
    res = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}
    )
    assert res.status_code == 200
    assert res.json()["email"] == "admin@example.com"
    assert "pr_robot_session" in res.cookies


def test_login_wrong_password_rejected(client: TestClient, admin_user: User):
    res = client.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_email_rejected(client: TestClient):
    res = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert res.status_code == 401


def test_me_requires_login(client: TestClient):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_returns_current_user_after_login(client: TestClient, plain_user: User):
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})
    res = client.get("/auth/me")
    assert res.status_code == 200
    assert res.json()["email"] == "plain@example.com"


def test_logout_clears_session(client: TestClient, plain_user: User):
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})
    client.post("/auth/logout")
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_plain_user_cannot_create_user(client: TestClient, plain_user: User):
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})
    res = client.post(
        "/users",
        json={"name": "New", "email": "new@example.com", "password": "newpass123"},
    )
    assert res.status_code == 403


def test_admin_can_create_user(client: TestClient, admin_user: User):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    res = client.post(
        "/users",
        json={
            "name": "Reviewer One",
            "email": "reviewer1@example.com",
            "password": "reviewer123",
            "can_review": True,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "reviewer1@example.com"
    assert body["can_review"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_admin_can_create_duplicate_email_rejected(client: TestClient, admin_user: User):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    res = client.post(
        "/users",
        json={"name": "Dup", "email": "admin@example.com", "password": "whatever123"},
    )
    assert res.status_code == 409


def test_admin_can_list_users(client: TestClient, admin_user: User, plain_user: User):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    res = client.get("/users")
    assert res.status_code == 200
    emails = {u["email"] for u in res.json()}
    assert {"admin@example.com", "plain@example.com"} <= emails
