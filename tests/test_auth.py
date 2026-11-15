"""Checks the login-cookie integration with the auth service (AUTH_MODE=db and remote)."""
import hashlib

import httpx
import pytest
from sqlalchemy import text

from app import auth
from app.config import load_settings
from app.db import engine
from conftest import campaign_body


@pytest.fixture()
def auth_tables(client):
    """Same shape as the auth service's schema.sql (users + sessions)."""
    with engine.begin() as conn:
        conn.execute(text("create table users (id integer primary key, email text, password_hash text, role text)"))
        conn.execute(text("create table sessions (token_hash text primary key, user_id integer, expires_at timestamp)"))
        conn.execute(text("insert into users values (7, 'urja@example.com', 'x', 'user'), (8, 'boss@example.com', 'x', 'admin')"))
        for sid, user_id, expires in [("good-token", 7, "2999-01-01 00:00:00"), ("admin-token", 8, "2999-01-01 00:00:00"), ("old-token", 7, "2000-01-01 00:00:00")]:
            conn.execute(text("insert into sessions values (:h, :u, :e)"), {"h": hashlib.sha256(sid.encode()).hexdigest(), "u": user_id, "e": expires})
    yield
    with engine.begin() as conn:
        conn.execute(text("drop table sessions"))
        conn.execute(text("drop table users"))


@pytest.fixture()
def mode(monkeypatch):
    def _set(name):
        settings = load_settings().__class__(**{**load_settings().__dict__, "auth_mode": name})
        monkeypatch.setattr(auth, "get_settings", lambda: settings)
    return _set


def test_db_mode_uses_sid_cookie(client, auth_tables, mode):
    mode("db")
    res = client.post("/api/campaigns", json=campaign_body(), cookies={"sid": "good-token"})
    assert res.status_code == 201 and res.json()["created_by"] == 7

    assert client.post("/api/campaigns", json=campaign_body(), cookies={"sid": "old-token"}).status_code == 401  # expired
    assert client.post("/api/campaigns", json=campaign_body(), cookies={"sid": "made-up"}).status_code == 401
    assert client.post("/api/campaigns", json=campaign_body(), headers={"X-Dev-User": "1:admin"}).status_code == 401  # dev header ignored
    assert client.get("/api/admin/campaigns", cookies={"sid": "admin-token"}).status_code == 200
    assert client.get("/api/admin/campaigns", cookies={"sid": "good-token"}).status_code == 403


def test_remote_mode_calls_auth_me(client, mode, monkeypatch):
    mode("remote")
    calls = []

    def fake_get(url, cookies, timeout):
        calls.append((url, cookies))
        if cookies.get("sid") == "good-token":
            return httpx.Response(200, json={"id": 5, "email": "a@b.com", "role": "user"})
        return httpx.Response(401, json={"error": "Not authenticated"})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    assert client.post("/api/campaigns", json=campaign_body(), cookies={"sid": "good-token"}).json()["created_by"] == 5
    assert client.post("/api/campaigns", json=campaign_body(), cookies={"sid": "bad"}).status_code == 401
    assert calls[0][0].endswith("/auth/me")


def test_dev_mode_blocked_in_production(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        load_settings()
