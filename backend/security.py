"""Opaque cookie-session authentication shared by all protected routers."""
from __future__ import annotations

import datetime
import hashlib
import os
import secrets

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models

SESSION_COOKIE_NAME = "bhumi_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "7"))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session(db: Session, user: models.User) -> tuple[models.UserSession, str]:
    token = secrets.token_urlsafe(48)
    now = datetime.datetime.utcnow()
    session = models.UserSession(
        user_id=user.id, token_hash=_token_hash(token), created_at=now,
        expires_at=now + datetime.timedelta(days=SESSION_DAYS), last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return session, token


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> models.User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required.")
    now = datetime.datetime.utcnow()
    session = db.query(models.UserSession).filter(
        models.UserSession.token_hash == _token_hash(session_token),
        models.UserSession.revoked_at.is_(None),
        models.UserSession.expires_at > now,
    ).first()
    if not session or not session.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please sign in again.")
    # Avoid a database write on every authenticated API call while retaining a
    # useful recent-activity timestamp for session operations.
    if not session.last_seen_at or now - session.last_seen_at >= datetime.timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return session.user


def get_optional_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> models.User | None:
    if not session_token:
        return None
    now = datetime.datetime.utcnow()
    session = db.query(models.UserSession).filter(
        models.UserSession.token_hash == _token_hash(session_token),
        models.UserSession.revoked_at.is_(None), models.UserSession.expires_at > now,
    ).first()
    return session.user if session else None


def require_citizen(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Citizen access is required.")
    return current_user


def require_officer(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "officer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Officer access is required.")
    return current_user


def require_active_citizen(current_user: models.User = Depends(require_citizen)) -> models.User:
    """Citizen workspace access requires the phone-primary identity and profile."""
    if not (current_user.phone_verified_at and current_user.profile_completed_at and current_user.email and current_user.name and current_user.state and current_user.district):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Complete phone verification and your profile to access the citizen workspace.")
    return current_user


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.query(models.UserSession).filter(
        models.UserSession.token_hash == _token_hash(token), models.UserSession.revoked_at.is_(None)
    ).first()
    if session:
        session.revoked_at = datetime.datetime.utcnow()


def cookie_options() -> dict:
    production = os.getenv("LANDSIGHT_ENV", "development").lower() == "production"
    return {"httponly": True, "samesite": "lax", "secure": production, "max_age": SESSION_DAYS * 86400, "path": "/"}
