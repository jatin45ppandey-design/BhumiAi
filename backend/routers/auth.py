import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_db
import models, schemas

router = APIRouter()

PASSWORD_ITERATIONS = 600_000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
OFFICER_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{4,63}$")
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_STATE_TTL_SECONDS = 600
OAUTH_TICKET_TTL_SECONDS = 300
_oauth_tickets: dict[str, tuple[float, dict]] = {}

# Local development reads backend/.env; deployed environments provide the same
# values as environment variables. Existing environment values are preserved.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter a valid email address.")
    return normalized


def validate_password(password: str) -> str:
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be at least 8 characters.")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be 128 characters or fewer.")
    return password


def normalize_officer_id(officer_id: str) -> str:
    normalized = (officer_id or "").strip().upper()
    if not OFFICER_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid Government Officer ID.")
    return normalized


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def user_payload(user: models.User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role, "name": user.name}


def google_config() -> tuple[str, str, str, str, str]:
    """Read credentials only on the server; they are never sent to the browser."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    state_secret = os.getenv("GOOGLE_OAUTH_STATE_SECRET", "").strip()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback").strip()
    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
    if not client_id or not client_secret or len(state_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured yet. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_OAUTH_STATE_SECRET on the server.",
        )
    return client_id, client_secret, state_secret, redirect_uri, frontend_url


def sign_state(state_secret: str) -> str:
    payload = {"issued_at": int(time.time()), "nonce": secrets.token_urlsafe(24)}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(state_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_state(state: str, state_secret: str) -> None:
    try:
        encoded, signature = state.split(".", 1)
        expected = hmac.new(state_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        issued_at = payload.get("issued_at")
        now = time.time()
        if not isinstance(issued_at, int) or issued_at > now or now - issued_at > OAUTH_STATE_TTL_SECONDS:
            raise ValueError("expired")
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Google sign-in request expired. Please try again.")


def google_user_from_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    token_request = urlrequest.Request(
        GOOGLE_TOKEN_URL,
        data=urlparse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(token_request, timeout=10) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("missing access token")
        profile_request = urlrequest.Request(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urlrequest.urlopen(profile_request, timeout=10) as response:
            profile = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, urlerror.HTTPError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google could not verify this sign-in. Please try again.")

    if not profile.get("email_verified") or not profile.get("email") or not profile.get("sub"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Use a Google account with a verified email address.")
    return profile


def issue_oauth_ticket(user: models.User) -> str:
    now = time.time()
    for ticket, (expires_at, _) in list(_oauth_tickets.items()):
        if expires_at <= now:
            _oauth_tickets.pop(ticket, None)
    ticket = secrets.token_urlsafe(32)
    _oauth_tickets[ticket] = (now + OAUTH_TICKET_TTL_SECONDS, user_payload(user))
    return ticket


@router.get("/google/start")
def start_google_sign_in():
    client_id, _, state_secret, redirect_uri, _ = google_config()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": sign_state(state_secret),
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{urlparse.urlencode(params)}", status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
def google_callback(
    code: str | None = Query(default=None),
    state_value: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _, client_secret, state_secret, redirect_uri, frontend_url = google_config()
    if error or not code or not state_value:
        return RedirectResponse(f"{frontend_url}/login?google_error=cancelled", status_code=status.HTTP_302_FOUND)
    verify_state(state_value, state_secret)
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    profile = google_user_from_code(code, client_id, client_secret, redirect_uri)
    email = validate_email(profile["email"])
    google_subject = profile["sub"]
    user = db.query(models.User).filter(models.User.google_subject == google_subject).first()
    email_user = db.query(models.User).filter(func.lower(models.User.email) == email).first()

    if user and email_user and user.id != email_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This Google account is already linked to another user.")
    user = user or email_user
    if user and user.role != "user":
        return RedirectResponse(f"{frontend_url}/login?google_error=submitter_only", status_code=status.HTTP_302_FOUND)
    if not user:
        user = models.User(
            email=email,
            name=(profile.get("name") or email.split("@", 1)[0])[:120],
            role="user",
            google_subject=google_subject,
        )
        db.add(user)
    elif not user.google_subject:
        user.google_subject = google_subject
    elif user.google_subject != google_subject:
        return RedirectResponse(f"{frontend_url}/login?google_error=account_mismatch", status_code=status.HTTP_302_FOUND)
    db.commit()
    db.refresh(user)
    ticket = issue_oauth_ticket(user)
    return RedirectResponse(f"{frontend_url}/login?{urlparse.urlencode({'oauth_ticket': ticket})}", status_code=status.HTTP_302_FOUND)


@router.post("/google/exchange")
def exchange_google_ticket(payload: schemas.GoogleOAuthTicket):
    record = _oauth_tickets.pop(payload.ticket, None)
    if not record or record[0] <= time.time():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your Google sign-in session expired. Please sign in again.")
    return {"message": "Google sign-in successful", "user": record[1]}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(registration: schemas.UserRegistration, db: Session = Depends(get_db)):
    name = (registration.name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter your full name.")
    if len(name) > 120:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name must be 120 characters or fewer.")
    email = validate_email(registration.email)
    password = validate_password(registration.password)
    if db.query(models.User).filter(func.lower(models.User.email) == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    db_user = models.User(email=email, name=name, role="user", password_hash=hash_password(password))
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    db.refresh(db_user)
    return {"message": "Account created successfully. You can now sign in.", "user": user_payload(db_user)}

@router.post("/login")
def login(user: schemas.UserCreate, db: Session = Depends(get_db)):
    requested_role = (user.role or "").strip().lower()
    if requested_role == "user":
        email = validate_email(user.email or "")
        db_user = db.query(models.User).filter(func.lower(models.User.email) == email, models.User.role == "user").first()
        if not db_user or not user.password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
        if not db_user.password_hash:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account was created with Google. Please use Continue with Google.")
        if not verify_password(user.password, db_user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
        return {"message": "Login successful", "user": user_payload(db_user)}
    if requested_role != "officer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Choose a valid workspace.")

    officer_id = normalize_officer_id(user.officer_id or "")
    db_user = db.query(models.User).filter(models.User.officer_id == officer_id, models.User.role == "officer").first()
    if not db_user or not user.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Government Officer ID or password.")

    if db_user.password_hash:
        if not verify_password(user.password, db_user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Government Officer ID or password.")
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This Government Officer account is not provisioned correctly.")

    return {"message": "Login successful", "user": user_payload(db_user)}
