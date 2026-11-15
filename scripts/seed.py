"""Adds sample APPROVED campaigns so the homepage has something to show in the Stage 2 demo.

Run from the project folder:  python -m scripts.seed
Uses the same DATABASE_URL as the API. Safe to run twice: skips titles that already exist.
"""
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Campaign, CampaignStatus, CampaignType, ModerationLog

OWNER_ID = int(os.getenv("SEED_OWNER_ID", "1"))
ADMIN_ID = int(os.getenv("SEED_ADMIN_ID", "1"))
today = date.today()

SAMPLES = [
    dict(type=CampaignType.social_cause, title="Mindil Beach Clean-up", category="environment", location="Darwin",
         summary="Help clear plastic and rubbish from Mindil Beach before the wet season.",
         description="Meet at the Mindil Beach car park at 7am. Gloves, bags and water are provided. All ages welcome.",
         image_url="https://images.unsplash.com/photo-1618477461853-cf6ed80faba5", end=21),
    dict(type=CampaignType.social_cause, title="Winter Food Drive for Families", category="community", location="Palmerston",
         summary="Donate non-perishable food for local families who need support this season.",
         description="Drop donations at the community centre between 9am and 5pm on weekdays. Tinned food, rice and pasta are most needed.",
         image_url="https://images.unsplash.com/photo-1593113598332-cd288d649433", end=30),
    dict(type=CampaignType.social_cause, title="Mental Health Awareness Walk", category="health", location="Darwin Waterfront",
         summary="A 5 km walk to raise awareness and start conversations about mental health.",
         description="Join us for a relaxed walk along the waterfront. Local support services will have information stalls at the finish.",
         image_url="https://images.unsplash.com/photo-1476480862126-209bfaa8edc8", end=14),
    dict(type=CampaignType.social_cause, title="Tree Planting at Casuarina", category="environment", location="Casuarina",
         summary="Plant native trees to restore shade and habitat in the Casuarina reserve.",
         description="Tools and saplings are supplied. Wear closed shoes and a hat. Morning tea is provided for all volunteers.",
         image_url="https://images.unsplash.com/photo-1542601906990-b4d3fb778b09", end=None),
    dict(type=CampaignType.business_promotion, title="Volunteer Coffee Week", category="local business", location="Nightcliff",
         summary="Show your volunteer badge for discounted coffee all week.", business_name="Top End Coffee Co.",
         offer_text="20% off any coffee for registered volunteers",
         description="Top End Coffee Co. supports local volunteers. Show your PeopleforPeople profile at the counter to get the discount.",
         image_url="https://images.unsplash.com/photo-1509042239860-f550ce710b93", end=7),
    dict(type=CampaignType.business_promotion, title="Free Bike Tune-up for Volunteers", category="local business", location="Parap",
         summary="Free basic bike service for anyone volunteering with a listed campaign.", business_name="Parap Cycles",
         offer_text="Free basic tune-up (normally $45)",
         description="Book online and mention PeopleforPeople. Covers brakes, gears and tyre check. One per person.",
         image_url="https://images.unsplash.com/photo-1485965120184-e220f721d03e", end=28),
]


def main() -> None:
    Base.metadata.create_all(engine)
    added = 0
    with SessionLocal() as db:
        existing = set(db.scalars(select(Campaign.title)))
        for s in SAMPLES:
            if s["title"] in existing:
                continue
            end = s.pop("end")
            c = Campaign(
                **s, start_date=today - timedelta(days=1), end_date=today + timedelta(days=end) if end else None,
                status=CampaignStatus.APPROVED, created_by=OWNER_ID, reviewed_by=ADMIN_ID, reviewed_at=datetime.now(timezone.utc),
            )
            db.add(c)
            db.flush()
            db.add(ModerationLog(campaign_id=c.id, old_status=None, new_status=CampaignStatus.APPROVED, actor_id=ADMIN_ID, reason="Seeded demo data"))
            added += 1
        db.commit()
    print(f"Added {added} sample campaigns ({len(SAMPLES) - added} already existed).")


if __name__ == "__main__":
    main()
