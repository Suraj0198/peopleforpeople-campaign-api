"""Tests follow section 8 of the KAN-23 spec, plus the joined-campaign fix from KAN-26."""
from datetime import timedelta

from conftest import ADMIN, OTHER, OWNER, TODAY, campaign_body


# ---------- public listing (KAN-31) ----------
def test_public_list_shows_only_approved_active(client, make_campaign):
    approved = make_campaign("APPROVED", title="Approved one")
    make_campaign("DRAFT", title="Draft one")
    make_campaign("PENDING", title="Pending one")
    make_campaign("REJECTED", title="Rejected one")
    make_campaign("ARCHIVED", title="Archived one")
    make_campaign("APPROVED", title="Future one", start_date=str(TODAY + timedelta(days=5)), end_date=None)

    res = client.get("/api/campaigns")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert [c["id"] for c in data["items"]] == [approved]
    assert {"description", "status", "created_by"}.isdisjoint(data["items"][0])  # cards stay small


def test_expired_campaign_hidden(client, make_campaign):
    cid = make_campaign("APPROVED", start_date=str(TODAY - timedelta(days=10)), end_date=str(TODAY - timedelta(days=1)))
    assert client.get("/api/campaigns").json()["total"] == 0
    assert client.get(f"/api/campaigns/{cid}").status_code == 404


def test_filters_search_and_pagination(client, make_campaign):
    for i in range(5):
        make_campaign("APPROVED", title=f"Tree planting {i}", category="environment")
    make_campaign(
        "APPROVED", type="business_promotion", title="Cafe discount week", business_name="Top End Cafe",
        offer_text="10% off for volunteers", category="local business",
    )

    page1 = client.get("/api/campaigns", params={"page_size": 2}).json()
    assert page1["total"] == 6 and len(page1["items"]) == 2 and page1["page"] == 1
    page3 = client.get("/api/campaigns", params={"page_size": 2, "page": 3}).json()
    assert len(page3["items"]) == 2

    promos = client.get("/api/campaigns", params={"type": "business_promotion"}).json()
    assert promos["total"] == 1 and promos["items"][0]["business_name"] == "Top End Cafe"

    assert client.get("/api/campaigns", params={"category": "ENVIRONMENT"}).json()["total"] == 5
    assert client.get("/api/campaigns", params={"search": "cafe"}).json()["total"] == 1
    assert client.get("/api/campaigns", params={"search": "100%"}).json()["total"] == 0  # % is not a wildcard


def test_page_size_capped(client):
    res = client.get("/api/campaigns", params={"page_size": 51})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ending_soon_sort(client, make_campaign):
    later = make_campaign("APPROVED", title="Later", end_date=str(TODAY + timedelta(days=20)))
    sooner = make_campaign("APPROVED", title="Sooner", end_date=str(TODAY + timedelta(days=2)))
    open_ended = make_campaign("APPROVED", title="Open", end_date=None)
    ids = [c["id"] for c in client.get("/api/campaigns", params={"sort": "ending_soon"}).json()["items"]]
    assert ids == [sooner, later, open_ended]


def test_featured_max_six(client, make_campaign):
    for i in range(8):
        make_campaign("APPROVED", title=f"Campaign number {i}")
    assert len(client.get("/api/campaigns/featured").json()) == 6


def test_pending_detail_visibility(client, make_campaign):
    cid = make_campaign("PENDING")
    assert client.get(f"/api/campaigns/{cid}").status_code == 404
    assert client.get(f"/api/campaigns/{cid}", headers=OTHER).status_code == 404
    assert client.get(f"/api/campaigns/{cid}", headers=OWNER).json()["status"] == "PENDING"
    assert client.get(f"/api/campaigns/{cid}", headers=ADMIN).status_code == 200


def test_unknown_campaign_404_format(client):
    res = client.get("/api/campaigns/12345")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "NOT_FOUND", "message": "Campaign not found."}}


# ---------- create / validation (KAN-40) ----------
def test_create_requires_login(client):
    res = client.post("/api/campaigns", json=campaign_body())
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_create_starts_as_draft(client):
    res = client.post("/api/campaigns", json=campaign_body(), headers=OWNER)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "DRAFT" and body["created_by"] == 1 and body["category"] == "environment"


def test_missing_title_400_with_field_error(client):
    body = campaign_body()
    del body["title"]
    res = client.post("/api/campaigns", json=body, headers=OWNER)
    assert res.status_code == 400
    assert any(d["field"] == "title" for d in res.json()["error"]["details"])


def test_promotion_needs_business_name(client):
    res = client.post("/api/campaigns", json=campaign_body(type="business_promotion"), headers=OWNER)
    assert res.status_code == 400
    assert "business_name" in res.text


def test_end_before_start_rejected(client):
    body = campaign_body(start_date=str(TODAY), end_date=str(TODAY - timedelta(days=1)))
    assert client.post("/api/campaigns", json=body, headers=OWNER).status_code == 400


def test_html_is_stripped(client):
    body = campaign_body(title="<script>alert(1)</script>Beach day", summary="<b>Clean</b> the beach with us today")
    res = client.post("/api/campaigns", json=body, headers=OWNER).json()
    assert res["title"] == "alert(1)Beach day"
    assert "<" not in res["summary"]


def test_unknown_fields_rejected(client):
    body = campaign_body(status="APPROVED")  # can't self-approve by sending a status
    assert client.post("/api/campaigns", json=body, headers=OWNER).status_code == 400


# ---------- moderation flow ----------
def test_submit_then_second_submit_conflicts(client, make_campaign):
    cid = make_campaign("DRAFT")
    assert client.post(f"/api/campaigns/{cid}/submit", headers=OWNER).json()["status"] == "PENDING"
    res = client.post(f"/api/campaigns/{cid}/submit", headers=OWNER)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_only_owner_can_submit_or_edit(client, make_campaign):
    cid = make_campaign("DRAFT")
    assert client.post(f"/api/campaigns/{cid}/submit", headers=OTHER).status_code == 404  # hidden from others
    assert client.post(f"/api/campaigns/{cid}/submit", headers=ADMIN).status_code == 403
    assert client.put(f"/api/campaigns/{cid}", json=campaign_body(), headers=ADMIN).status_code == 403


def test_non_admin_cannot_moderate(client, make_campaign):
    cid = make_campaign("PENDING")
    assert client.post(f"/api/admin/campaigns/{cid}/approve", headers=OWNER).status_code == 403
    assert client.post(f"/api/admin/campaigns/{cid}/reject", json={"reason": "Not good enough here"}, headers=OWNER).status_code == 403
    assert client.get("/api/admin/campaigns", headers=OWNER).status_code == 403


def test_admin_queue(client, make_campaign):
    pending = make_campaign("PENDING")
    make_campaign("DRAFT")
    data = client.get("/api/admin/campaigns", headers=ADMIN).json()
    assert data["total"] == 1 and data["items"][0]["id"] == pending


def test_reject_needs_reason(client, make_campaign):
    cid = make_campaign("PENDING")
    assert client.post(f"/api/admin/campaigns/{cid}/reject", json={}, headers=ADMIN).status_code == 400
    assert client.post(f"/api/admin/campaigns/{cid}/reject", json={"reason": "too short"}, headers=ADMIN).status_code == 400


def test_approve_twice_conflicts(client, make_campaign):
    cid = make_campaign("APPROVED")
    assert client.post(f"/api/admin/campaigns/{cid}/approve", headers=ADMIN).status_code == 409


def test_rejected_edit_resubmit_and_history(client, make_campaign):
    cid = make_campaign("REJECTED")
    mine = client.get("/api/me/campaigns", headers=OWNER).json()["items"][0]
    assert mine["status"] == "REJECTED" and mine["rejection_reason"] == "Please add a contact email."

    edited = client.put(f"/api/campaigns/{cid}", json=campaign_body(description="Contact us at beach@example.com to volunteer."), headers=OWNER)
    assert edited.status_code == 200
    resubmitted = client.post(f"/api/campaigns/{cid}/submit", headers=OWNER).json()
    assert resubmitted["status"] == "PENDING" and resubmitted["rejection_reason"] is None

    steps = [(h["old_status"], h["new_status"]) for h in client.get(f"/api/admin/campaigns/{cid}/history", headers=ADMIN).json()]
    assert steps == [(None, "DRAFT"), ("DRAFT", "PENDING"), ("PENDING", "REJECTED"), ("REJECTED", "PENDING")]


def test_approved_cannot_be_edited(client, make_campaign):
    cid = make_campaign("APPROVED")
    res = client.put(f"/api/campaigns/{cid}", json=campaign_body(), headers=OWNER)
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_EDITABLE"


def test_archive(client, make_campaign):
    cid = make_campaign("APPROVED")
    assert client.post(f"/api/campaigns/{cid}/archive", headers=OTHER).status_code == 403
    assert client.post(f"/api/campaigns/{cid}/archive", headers=OWNER).json()["status"] == "ARCHIVED"
    assert client.get("/api/campaigns").json()["total"] == 0


def test_rejection_reason_hidden_from_public(client, make_campaign):
    cid = make_campaign("APPROVED")
    assert client.get(f"/api/campaigns/{cid}").json()["rejection_reason"] is None


# ---------- joins (KAN-26 issue 2) ----------
def test_join_persists_and_counts(client, make_campaign):
    cid = make_campaign("APPROVED")
    assert client.post(f"/api/campaigns/{cid}/join").status_code == 401
    assert client.post(f"/api/campaigns/{cid}/join", headers=OTHER).json() == {"campaign_id": cid, "joined": True, "participants": 1}
    assert client.post(f"/api/campaigns/{cid}/join", headers=OTHER).json()["participants"] == 1  # joining twice is harmless
    client.post(f"/api/campaigns/{cid}/join", headers=ADMIN)

    # a fresh request (as after logging out and in again) still shows joined
    card = client.get("/api/campaigns", headers=OTHER).json()["items"][0]
    assert card["joined"] is True and card["participants"] == 2
    assert client.get("/api/campaigns").json()["items"][0]["joined"] is False
    assert [c["id"] for c in client.get("/api/me/joined", headers=OTHER).json()] == [cid]

    assert client.delete(f"/api/campaigns/{cid}/join", headers=OTHER).json() == {"campaign_id": cid, "joined": False, "participants": 1}


def test_cannot_join_hidden_campaign(client, make_campaign):
    cid = make_campaign("PENDING")
    assert client.post(f"/api/campaigns/{cid}/join", headers=OTHER).status_code == 404


def test_health(client):
    assert client.get("/health").json()["ok"] is True
