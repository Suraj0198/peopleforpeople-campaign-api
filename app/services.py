"""Business rules: who can see a campaign, allowed status changes, and the moderation log."""
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .errors import ApiError, not_found
from .models import Campaign, CampaignJoin, CampaignStatus, ModerationLog, utcnow
from .schemas import CampaignCard, CampaignDetail

S = CampaignStatus

# (from, to) -> who may make the change
TRANSITIONS: dict[tuple[CampaignStatus, CampaignStatus], str] = {
    (S.DRAFT, S.PENDING): "owner",
    (S.REJECTED, S.PENDING): "owner",
    (S.PENDING, S.APPROVED): "admin",
    (S.PENDING, S.REJECTED): "admin",
    (S.APPROVED, S.ARCHIVED): "owner_or_admin",
}
EDITABLE = {S.DRAFT, S.REJECTED}


def public_filter(stmt: Select, today: date | None = None) -> Select:
    """Shown publicly only when APPROVED and today is between start_date and end_date."""
    today = today or date.today()
    return stmt.where(
        Campaign.status == S.APPROVED,
        Campaign.start_date <= today,
        or_(Campaign.end_date.is_(None), Campaign.end_date >= today),
    )


def is_public(c: Campaign, today: date | None = None) -> bool:
    today = today or date.today()
    return c.status == S.APPROVED and c.start_date <= today and (c.end_date is None or c.end_date >= today)


def is_owner(c: Campaign, user: CurrentUser | None) -> bool:
    return user is not None and c.created_by == user.id


def can_view(c: Campaign, user: CurrentUser | None) -> bool:
    return is_public(c) or is_owner(c, user) or (user is not None and user.is_admin)


def get_campaign(db: Session, campaign_id: int) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise not_found()
    return c


def get_visible(db: Session, campaign_id: int, user: CurrentUser | None) -> Campaign:
    c = get_campaign(db, campaign_id)
    if not can_view(c, user):
        raise not_found()  # don't reveal that hidden campaigns exist
    return c


def get_owned(db: Session, campaign_id: int, user: CurrentUser) -> Campaign:
    c = get_visible(db, campaign_id, user)
    if not is_owner(c, user):
        raise ApiError(403, "FORBIDDEN", "Only the person who created this campaign can do this.")
    return c


def change_status(db: Session, c: Campaign, new: CampaignStatus, actor: CurrentUser, reason: str | None = None) -> None:
    if (c.status, new) not in TRANSITIONS:
        raise ApiError(
            409,
            "INVALID_STATUS_TRANSITION",
            f"This campaign is {c.status.value} and cannot be changed to {new.value}.",
        )
    old = c.status
    c.status = new
    if new == S.PENDING:  # resubmitted: clear the previous review
        c.rejection_reason, c.reviewed_by, c.reviewed_at = None, None, None
    if new in (S.APPROVED, S.REJECTED):
        c.reviewed_by, c.reviewed_at = actor.id, utcnow()
        c.rejection_reason = reason if new == S.REJECTED else None
    log_change(db, c, old, new, actor, reason)


def log_change(db: Session, c: Campaign, old, new, actor: CurrentUser, reason: str | None = None) -> None:
    db.add(ModerationLog(campaign_id=c.id, old_status=old, new_status=new, actor_id=actor.id, reason=reason))


def paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list[Campaign], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def join_info(db: Session, ids: list[int], user: CurrentUser | None) -> tuple[dict[int, int], set[int]]:
    if not ids:
        return {}, set()
    counts = dict(
        db.execute(
            select(CampaignJoin.campaign_id, func.count()).where(CampaignJoin.campaign_id.in_(ids)).group_by(CampaignJoin.campaign_id)
        ).all()
    )
    joined: set[int] = set()
    if user is not None:
        joined = set(
            db.scalars(select(CampaignJoin.campaign_id).where(CampaignJoin.campaign_id.in_(ids), CampaignJoin.user_id == user.id))
        )
    return counts, joined


def to_cards(db: Session, campaigns: list[Campaign], user: CurrentUser | None) -> list[CampaignCard]:
    counts, joined = join_info(db, [c.id for c in campaigns], user)
    return [
        CampaignCard.model_validate(c).model_copy(update={"participants": counts.get(c.id, 0), "joined": c.id in joined})
        for c in campaigns
    ]


def to_details(db: Session, campaigns: list[Campaign], user: CurrentUser | None) -> list[CampaignDetail]:
    counts, joined = join_info(db, [c.id for c in campaigns], user)
    return [
        CampaignDetail.model_validate(c).model_copy(update={"participants": counts.get(c.id, 0), "joined": c.id in joined})
        for c in campaigns
    ]
