"""Public listing (KAN-31), owner create/edit/submit (KAN-40), archive and joins (KAN-49)."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user, get_optional_user
from ..db import get_db
from ..errors import ApiError
from ..models import Campaign, CampaignJoin, CampaignStatus, CampaignType
from ..schemas import CampaignCard, CampaignDetail, CampaignIn, JoinResult, Page
from .. import services as svc

router = APIRouter(prefix="/api", tags=["campaigns"])
FEATURED_LIMIT = 6


# ---------------- KAN-31: public listing and details ----------------
@router.get("/campaigns", response_model=Page[CampaignCard], summary="List approved, active campaigns")
def list_campaigns(
    type: CampaignType | None = None,
    category: str | None = Query(None, max_length=50),
    search: str | None = Query(None, max_length=100, description="Matches title or summary"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    sort: Literal["newest", "ending_soon"] = "newest",
    db: Session = Depends(get_db),
    user: CurrentUser | None = Depends(get_optional_user),
):
    stmt = svc.public_filter(select(Campaign))
    if type:
        stmt = stmt.where(Campaign.type == type)
    if category:
        stmt = stmt.where(func.lower(Campaign.category) == category.strip().lower())
    if search and search.strip():
        q = search.strip()
        stmt = stmt.where(Campaign.title.icontains(q, autoescape=True) | Campaign.summary.icontains(q, autoescape=True))
    if sort == "ending_soon":
        stmt = stmt.order_by(Campaign.end_date.asc().nulls_last(), Campaign.id.desc())
    else:
        stmt = stmt.order_by(Campaign.created_at.desc(), Campaign.id.desc())
    rows, total = svc.paginate(db, stmt, page, page_size)
    return Page(items=svc.to_cards(db, rows, user), page=page, page_size=page_size, total=total)


@router.get("/campaigns/featured", response_model=list[CampaignCard], summary="Up to 6 campaigns for the homepage")
def featured_campaigns(db: Session = Depends(get_db), user: CurrentUser | None = Depends(get_optional_user)):
    stmt = svc.public_filter(select(Campaign)).order_by(Campaign.reviewed_at.desc(), Campaign.id.desc()).limit(FEATURED_LIMIT)
    return svc.to_cards(db, list(db.scalars(stmt)), user)


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail, summary="Campaign details")
def campaign_detail(campaign_id: int, db: Session = Depends(get_db), user: CurrentUser | None = Depends(get_optional_user)):
    c = svc.get_visible(db, campaign_id, user)
    detail = svc.to_details(db, [c], user)[0]
    if not (svc.is_owner(c, user) or (user and user.is_admin)):
        detail = detail.model_copy(update={"rejection_reason": None})
    return detail


# ---------------- KAN-40: create, edit, submit ----------------
@router.post("/campaigns", response_model=CampaignDetail, status_code=201, summary="Create a campaign (starts as DRAFT)")
def create_campaign(body: CampaignIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    c = Campaign(**body.to_columns(), status=CampaignStatus.DRAFT, created_by=user.id)
    db.add(c)
    db.flush()
    svc.log_change(db, c, None, CampaignStatus.DRAFT, user)
    db.commit()
    return svc.to_details(db, [c], user)[0]


@router.put("/campaigns/{campaign_id}", response_model=CampaignDetail, summary="Edit a DRAFT or REJECTED campaign")
def update_campaign(campaign_id: int, body: CampaignIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    c = svc.get_owned(db, campaign_id, user)
    if c.status not in svc.EDITABLE:
        raise ApiError(409, "NOT_EDITABLE", f"This campaign is {c.status.value} and cannot be edited.")
    for key, value in body.to_columns().items():
        setattr(c, key, value)
    db.commit()
    return svc.to_details(db, [c], user)[0]


@router.post("/campaigns/{campaign_id}/submit", response_model=CampaignDetail, summary="Send for admin review (to PENDING)")
def submit_campaign(campaign_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    c = svc.get_owned(db, campaign_id, user)
    svc.change_status(db, c, CampaignStatus.PENDING, user)
    db.commit()
    return svc.to_details(db, [c], user)[0]


@router.get("/me/campaigns", response_model=Page[CampaignDetail], summary="My campaigns, all statuses")
def my_campaigns(
    status: CampaignStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(Campaign).where(Campaign.created_by == user.id)
    if status:
        stmt = stmt.where(Campaign.status == status)
    rows, total = svc.paginate(db, stmt.order_by(Campaign.updated_at.desc(), Campaign.id.desc()), page, page_size)
    return Page(items=svc.to_details(db, rows, user), page=page, page_size=page_size, total=total)


# ---------------- KAN-49: archive ----------------
@router.post("/campaigns/{campaign_id}/archive", response_model=CampaignDetail, summary="Archive an APPROVED campaign")
def archive_campaign(campaign_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    c = svc.get_visible(db, campaign_id, user)
    if not (svc.is_owner(c, user) or user.is_admin):
        raise ApiError(403, "FORBIDDEN", "Only the owner or an administrator can archive this campaign.")
    svc.change_status(db, c, CampaignStatus.ARCHIVED, user)
    db.commit()
    return svc.to_details(db, [c], user)[0]


# ---------------- joins (fixes KAN-26 issue 2: 'joined' lost after logout) ----------------
def _participants(db: Session, campaign_id: int) -> int:
    return db.scalar(select(func.count()).where(CampaignJoin.campaign_id == campaign_id)) or 0


@router.post("/campaigns/{campaign_id}/join", response_model=JoinResult, summary="Join a campaign")
def join_campaign(campaign_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    c = svc.get_campaign(db, campaign_id)
    if not svc.is_public(c):
        raise ApiError(404, "NOT_FOUND", "Campaign not found or not open for joining.")
    if db.get(CampaignJoin, (campaign_id, user.id)) is None:
        db.add(CampaignJoin(campaign_id=campaign_id, user_id=user.id))
        db.commit()
    return JoinResult(campaign_id=campaign_id, joined=True, participants=_participants(db, campaign_id))


@router.delete("/campaigns/{campaign_id}/join", response_model=JoinResult, summary="Leave a campaign")
def leave_campaign(campaign_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    svc.get_campaign(db, campaign_id)
    db.execute(delete(CampaignJoin).where(CampaignJoin.campaign_id == campaign_id, CampaignJoin.user_id == user.id))
    db.commit()
    return JoinResult(campaign_id=campaign_id, joined=False, participants=_participants(db, campaign_id))


@router.get("/me/joined", response_model=list[CampaignCard], summary="Campaigns I have joined")
def my_joined(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    stmt = (
        select(Campaign)
        .join(CampaignJoin, CampaignJoin.campaign_id == Campaign.id)
        .where(CampaignJoin.user_id == user.id)
        .order_by(CampaignJoin.created_at.desc())
    )
    return svc.to_cards(db, list(db.scalars(stmt)), user)
