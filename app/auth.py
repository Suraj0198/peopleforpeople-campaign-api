"""Works out who is calling, using the login session from Aftab's auth service (KAN-22/30/39).

The auth service sets an HttpOnly cookie called `sid` on login and stores sha256(sid) in its
`sessions` table. Because both services use the same Neon database, this API can check the
cookie directly (AUTH_MODE=db). AUTH_MODE=remote asks the auth service's /auth/me instead.
"""
import hashlib
from dataclasses import dataclass

import httpx
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str = "user"
    email: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


SESSION_QUERY = text(
    """
    select u.id, u.email, u.role
      from sessions s join users u on u.id = s.user_id
     where s.token_hash = :token_hash and s.expires_at > CURRENT_TIMESTAMP
    """
)


def _from_db(db: Session, sid: str) -> CurrentUser | None:
    token_hash = hashlib.sha256(sid.encode()).hexdigest()  # same as the auth service
    row = db.execute(SESSION_QUERY, {"token_hash": token_hash}).first()
    return CurrentUser(id=row.id, email=row.email, role=row.role) if row else None


def _from_remote(base_url: str, cookie_name: str, sid: str) -> CurrentUser | None:
    try:
        res = httpx.get(f"{base_url}/auth/me", cookies={cookie_name: sid}, timeout=15)
    except httpx.HTTPError as exc:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Login service is not reachable. Please try again.") from exc
    if res.status_code == 401:
        return None
    if res.status_code != 200:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Login service returned an unexpected response.")
    data = res.json()
    return CurrentUser(id=int(data["id"]), email=data.get("email"), role=data.get("role", "user"))


def _from_dev_header(request: Request) -> CurrentUser | None:
    raw = request.headers.get("X-Dev-User")  # e.g. "1:user" or "99:admin"
    if not raw:
        return None
    try:
        user_id, _, role = raw.partition(":")
        return CurrentUser(id=int(user_id), role=role or "user")
    except ValueError as exc:
        raise ApiError(400, "BAD_DEV_USER", "X-Dev-User must look like '1:user' or '99:admin'.") from exc


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser | None:
    settings = get_settings()
    if settings.auth_mode == "dev":
        return _from_dev_header(request)
    sid = request.cookies.get(settings.session_cookie)
    if not sid:
        return None
    if settings.auth_mode == "db":
        return _from_db(db, sid)
    return _from_remote(settings.auth_base_url, settings.session_cookie, sid)


def get_current_user(user: CurrentUser | None = Depends(get_optional_user)) -> CurrentUser:
    if user is None:
        raise ApiError(401, "NOT_AUTHENTICATED", "Please log in first.")
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise ApiError(403, "FORBIDDEN", "Only administrators can do this.")
    return user
