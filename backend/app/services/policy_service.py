from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PolicySettings


class PolicyValidationError(ValueError):
    """Raised when a policy update would leave weights/thresholds inconsistent."""


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
    """
    Applies the given fields and enforces the weights-sum-to-100% /
    ascending-thresholds invariants unconditionally, on the resulting state
    rather than just the incoming fields -- so a hypothetical future partial
    update (e.g. only threshold_low) can't leave thresholds out of order
    just because the caller didn't also resend the other two. The API route
    already checks a full payload before calling this, but that's the only
    call site today; this is the one place the invariant actually has to
    hold no matter what calls it.
    """
    policy = get_policy(db)
    for key, value in fields.items():
        setattr(policy, key, value)

    total_weight = (
        policy.weight_mrz + policy.weight_tamper + policy.weight_face
        + policy.weight_consistency + policy.weight_watchlist
    )
    if abs(total_weight - 1.0) > 0.01:
        db.rollback()
        raise PolicyValidationError(
            f"Factor weights must sum to 100% (got {round(total_weight * 100, 1)}%)."
        )

    if not (0 <= policy.threshold_low < policy.threshold_medium < policy.threshold_high <= 100):
        db.rollback()
        raise PolicyValidationError(
            "Risk tier cutoffs must be strictly ascending and within 0-100."
        )

    db.commit()
    db.refresh(policy)
    return policy
