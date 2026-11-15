"""Admin moderation: queue, approve, reject (KAN-40) and history (KAN-49)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, require_admin
from ..db import get_db
from ..models import Campaign, CampaignStatus, CampaignType, ModerationLog
from ..schemas import CampaignDetail, HistoryEntry, Page, RejectIn
from .. import services as svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/campaigns", response_model=Page[CampaignDetail], summary="Moderation queue (default: PENDING)")
def admin_queue(
    status: CampaignStatus = CampaignStatus.PENDING,
    type: CampaignType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    stmt = select(Campaign).where(Campaign.status == status)
    if type:
        stmt = stmt.where(Campaign.type == type)
    stmt = stmt.order_by(Campaign.updated_at.asc(), Campaign.id.asc())  # oldest first
    rows, total = svc.paginate(db, stmt, page, page_size)
    return Page(items=svc.to_details(db, rows, admin), page=page, page_size=page_size, total=total)


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignDetail, summary="Approve (PENDING to APPROVED)")
def approve(campaign_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    c = svc.get_campaign(db, campaign_id)
    svc.change_status(db, c, CampaignStatus.APPROVED, admin)
    db.commit()
    return svc.to_details(db, [c], admin)[0]


@router.post("/campaigns/{campaign_id}/reject", response_model=CampaignDetail, summary="Reject with a reason (PENDING to REJECTED)")
def reject(campaign_id: int, body: RejectIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    c = svc.get_campaign(db, campaign_id)
    svc.change_status(db, c, CampaignStatus.REJECTED, admin, reason=body.reason)
    db.commit()
    return svc.to_details(db, [c], admin)[0]


@router.get("/campaigns/{campaign_id}/history", response_model=list[HistoryEntry], summary="Moderation log for one campaign")
def history(campaign_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    svc.get_campaign(db, campaign_id)
    stmt = select(ModerationLog).where(ModerationLog.campaign_id == campaign_id).order_by(ModerationLog.id)
    return list(db.scalars(stmt))
