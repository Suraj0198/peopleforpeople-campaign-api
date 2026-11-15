import os
from datetime import date, timedelta

# must be set before the app is imported
os.environ.update({"DATABASE_URL": "sqlite://", "AUTH_MODE": "dev", "APP_ENV": "test", "AUTO_CREATE_TABLES": "false"})

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

TODAY = date.today()
OWNER = {"X-Dev-User": "1:user"}
OTHER = {"X-Dev-User": "2:user"}
ADMIN = {"X-Dev-User": "99:admin"}


def campaign_body(**overrides):
    body = {
        "type": "social_cause",
        "title": "Darwin Beach Clean-up",
        "summary": "Join us to clean Mindil Beach this month",
        "description": "Bring gloves and water. Bags and snacks are provided for all volunteers.",
        "category": "Environment",
        "image_url": "https://example.com/beach.jpg",
        "location": "Darwin",
        "start_date": str(TODAY - timedelta(days=1)),
        "end_date": str(TODAY + timedelta(days=10)),
    }
    body.update(overrides)
    return body


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_campaign(client):
    """Create a campaign as OWNER and move it to the requested status."""

    def _make(status="APPROVED", headers=OWNER, **overrides):
        res = client.post("/api/campaigns", json=campaign_body(**overrides), headers=headers)
        assert res.status_code == 201, res.text
        cid = res.json()["id"]
        if status in ("PENDING", "APPROVED", "REJECTED", "ARCHIVED"):
            assert client.post(f"/api/campaigns/{cid}/submit", headers=headers).status_code == 200
        if status in ("APPROVED", "ARCHIVED"):
            assert client.post(f"/api/admin/campaigns/{cid}/approve", headers=ADMIN).status_code == 200
        if status == "REJECTED":
            r = client.post(f"/api/admin/campaigns/{cid}/reject", json={"reason": "Please add a contact email."}, headers=ADMIN)
            assert r.status_code == 200
        if status == "ARCHIVED":
            assert client.post(f"/api/campaigns/{cid}/archive", headers=headers).status_code == 200
        return cid

    return _make
