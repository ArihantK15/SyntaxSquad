from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings
from app.core.database import get_db


def require_officer_auth(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """
    Minimal API-key gate for the most sensitive, irreversible actions (case
    deletion, biometric purge) -- see the OFFICER_API_KEY setting for the
    scope and limits of what this actually protects against. Any request
    missing the header, or presenting the wrong value, is rejected before
    the route body ever runs.
    """
    if not x_api_key or x_api_key != settings.OFFICER_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key for this action.")


# Re-export get_db
__all__ = ["get_db", "require_officer_auth"]
