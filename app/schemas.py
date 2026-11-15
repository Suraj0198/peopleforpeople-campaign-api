"""Request and response bodies (validated with Pydantic)."""
import re
from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import CampaignStatus, CampaignType

TAG_RE = re.compile(r"<[^>]*>")


def clean_text(value):
    """Trim and strip HTML tags so nothing a user types can run as script on the site (stored XSS)."""
    if value is None or not isinstance(value, str):
        return value
    value = TAG_RE.sub("", value).strip()
    return value or None


# ---------- requests ----------
class CampaignIn(BaseModel):
    """Body for POST /api/campaigns and PUT /api/campaigns/{id}."""

    model_config = ConfigDict(extra="forbid")

    type: CampaignType
    title: str = Field(min_length=3, max_length=120)
    summary: str = Field(min_length=10, max_length=280)
    description: str = Field(min_length=20, max_length=5000)
    category: str = Field(min_length=2, max_length=50)
    image_url: AnyHttpUrl | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    business_name: str | None = Field(default=None, max_length=120)
    offer_text: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date | None = None

    @field_validator("title", "summary", "description", "category", "location", "business_name", "offer_text", mode="before")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)

    @field_validator("category")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @model_validator(mode="after")
    def _rules(self):
        if self.type == CampaignType.business_promotion and not self.business_name:
            raise ValueError("business_name is required for a business_promotion campaign")
        if self.type == CampaignType.social_cause:
            self.business_name = None
            self.offer_text = None
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self

    def to_columns(self) -> dict:
        data = self.model_dump()
        data["image_url"] = str(self.image_url) if self.image_url else None
        return data


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)


# ---------- responses ----------
class CampaignCard(BaseModel):
    """Short form used by the homepage and listing cards."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: CampaignType
    title: str
    summary: str
    category: str
    image_url: str | None
    location: str | None
    business_name: str | None
    offer_text: str | None
    start_date: date
    end_date: date | None
    participants: int = 0
    joined: bool = False


class CampaignDetail(CampaignCard):
    """Full campaign, used by the details page, 'my campaigns' and the admin queue."""

    description: str
    status: CampaignStatus
    rejection_reason: str | None
    created_by: int
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class JoinResult(BaseModel):
    campaign_id: int
    joined: bool
    participants: int


class HistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_status: CampaignStatus | None
    new_status: CampaignStatus
    actor_id: int
    reason: str | None
    created_at: datetime
