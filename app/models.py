"""Database tables: campaigns, moderation log, and campaign joins."""
import enum
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignType(str, enum.Enum):
    social_cause = "social_cause"
    business_promotion = "business_promotion"


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


def _enum(e: type[enum.Enum], length: int) -> Enum:
    # stored as VARCHAR + CHECK constraint, so it works the same on SQLite and Postgres
    return Enum(e, native_enum=False, create_constraint=True, length=length, values_callable=lambda members: [m.value for m in members])


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[CampaignType] = mapped_column(_enum(CampaignType, 30))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(280))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), index=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(120))
    business_name: Mapped[str | None] = mapped_column(String(120))
    offer_text: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CampaignStatus] = mapped_column(_enum(CampaignStatus, 20), default=CampaignStatus.DRAFT)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(Integer, index=True)  # users.id from the auth service
    reviewed_by: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_campaigns_public", "status", "start_date", "end_date"),)


class ModerationLog(Base):
    """One row per status change, so admins can see who did what and why."""

    __tablename__ = "campaign_moderation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[CampaignStatus | None] = mapped_column(_enum(CampaignStatus, 20))
    new_status: Mapped[CampaignStatus] = mapped_column(_enum(CampaignStatus, 20))
    actor_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CampaignJoin(Base):
    """A user joining a campaign. Stored server-side so 'joined' survives logout/login (KAN-26 issue 2)."""

    __tablename__ = "campaign_joins"

    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
