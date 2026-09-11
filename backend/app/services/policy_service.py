from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PolicySettings


def get_policy(db: Session) -> PolicySettings:
    """Returns the live risk engine policy, seeding it from the static
    defaults in app.core.config on first read."""
    policy = db.query(PolicySettings).filter(PolicySettings.id == 1).first()
    if policy is None:
        policy = PolicySettings(
            id=1,
            weight_mrz=settings.WEIGHT_MRZ,
            weight_tamper=settings.WEIGHT_TAMPER,
            weight_face=settings.WEIGHT_FACE,
            weight_consistency=settings.WEIGHT_CONSISTENCY,
            weight_watchlist=settings.WEIGHT_WATCHLIST,
            threshold_low=settings.THRESHOLD_LOW,
            threshold_medium=settings.THRESHOLD_MEDIUM,
            threshold_high=settings.THRESHOLD_HIGH,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def update_policy(db: Session, **fields) -> PolicySettings:
    policy = get_policy(db)
    for key, value in fields.items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    return policy
