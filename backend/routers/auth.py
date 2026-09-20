import base64
import datetime
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
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from security import SESSION_COOKIE_NAME, cookie_options, get_current_user, get_optional_current_user, new_session, revoke_session, require_citizen

router = APIRouter()

PASSWORD_ITERATIONS = 600_000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
INDIAN_PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")
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


def normalize_phone(phone_number: str) -> str:
    value = re.sub(r"[\s()-]", "", phone_number or "")
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        digits = value[1:]
        if not digits.startswith("91"):
            raise HTTPException(status_code=422, detail="Enter a valid Indian mobile number.")
        digits = digits[2:]
    else:
        digits = value[2:] if value.startswith("91") and len(value) == 12 else value
    if not INDIAN_PHONE_PATTERN.fullmatch(digits):
        raise HTTPException(status_code=422, detail="Enter a valid Indian mobile number.")
    return f"+91{digits}"


def _auth_secret() -> bytes:
    # This fallback is development-only and deliberately never exposes a code
    # outside the local development provider.
    return os.getenv("AUTH_CHALLENGE_SECRET", "development-only-change-before-production").encode("utf-8")


def _challenge_hash(subject: str, code: str) -> str:
    return hmac.new(_auth_secret(), f"{subject}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _development_delivery() -> bool:
    return os.getenv("OTP_PROVIDER", "development").strip().lower() == "development" and os.getenv("LANDSIGHT_ENV", "development").lower() != "production"


class OtpProvider:
    """Small delivery seam: providers receive a code but never persist it."""
    def send(self, destination: str, code: str, purpose: str) -> dict:
        raise NotImplementedError


class DevelopmentOtpProvider(OtpProvider):
    def send(self, destination: str, code: str, purpose: str) -> dict:
        return {"delivery": "development", "message": f"Development {purpose} code generated.", "development_code": code}


class ConfiguredProviderPlaceholder(OtpProvider):
    """Integration point for an approved SMS/email gateway; it never fakes delivery."""
    def send(self, destination: str, code: str, purpose: str) -> dict:
        raise HTTPException(status_code=503, detail=f"{purpose.capitalize()} delivery is not configured on this server.")


def _otp_provider() -> OtpProvider:
    return DevelopmentOtpProvider() if _development_delivery() else ConfiguredProviderPlaceholder()


def _set_session(response: Response, db: Session, user: models.User) -> None:
    _, token = new_session(db, user)
    response.set_cookie(SESSION_COOKIE_NAME, token, **cookie_options())


def _masked_phone(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    return f"+91******{phone_number[-4:]}"


def _profile_completed(user: models.User) -> bool:
    return bool(user.profile_completed_at and user.phone_verified_at and user.name and user.email and user.state and user.district)


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


@router.post("/phone/request-otp")
def request_phone_otp(payload: schemas.PhoneOtpRequest, db: Session = Depends(get_db)):
    phone_number = normalize_phone(payload.phone_number)
    now = datetime.datetime.utcnow()
    previous = db.query(models.PhoneOtpChallenge).filter(
        models.PhoneOtpChallenge.phone_number == phone_number,
        models.PhoneOtpChallenge.used_at.is_(None),
    ).order_by(models.PhoneOtpChallenge.created_at.desc()).first()
    if previous and (now - previous.created_at).total_seconds() < 60:
        raise HTTPException(status_code=429, detail="Please wait before requesting another code.")
    if previous:
        previous.used_at = now
    otp = _new_code()
    challenge = models.PhoneOtpChallenge(
        phone_number=phone_number, otp_hash=_challenge_hash(phone_number, otp),
        expires_at=now + datetime.timedelta(minutes=5), created_at=now,
    )
    db.add(challenge); db.commit()
    result = _otp_provider().send(phone_number, otp, "OTP")
    if "development_code" in result:
        result["development_otp"] = result.pop("development_code")
    result.update({"expires_in_seconds": 300, "resend_after_seconds": 60})
    return result


@router.post("/phone/verify-otp")
def verify_phone_otp(payload: schemas.PhoneOtpVerify, response: Response, current_user: models.User | None = Depends(get_optional_current_user), db: Session = Depends(get_db)):
    phone_number = normalize_phone(payload.phone_number)
    if not re.fullmatch(r"\d{6}", payload.otp or ""):
        raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
    now = datetime.datetime.utcnow()
    challenge = db.query(models.PhoneOtpChallenge).filter(
        models.PhoneOtpChallenge.phone_number == phone_number,
        models.PhoneOtpChallenge.used_at.is_(None),
    ).order_by(models.PhoneOtpChallenge.created_at.desc()).first()
    if not challenge or challenge.expires_at <= now or challenge.attempts >= 5:
        raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
    if not hmac.compare_digest(challenge.otp_hash, _challenge_hash(phone_number, payload.otp)):
        challenge.attempts += 1; db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
    challenge.used_at = now
    phone_user = db.query(models.User).filter(models.User.phone_number == phone_number).first()
    if current_user and current_user.role != "user":
        raise HTTPException(status_code=403, detail="Only citizen accounts can verify a phone number.")
    if current_user and phone_user and phone_user.id != current_user.id:
        raise HTTPException(status_code=409, detail="This phone number is already linked to another account.")
    user = current_user or phone_user
    if not user:
        user = models.User(role="user", phone_number=phone_number, phone_verified_at=now, name=None, email=None)
        db.add(user); db.flush()
    elif user.role != "user":
        raise HTTPException(status_code=409, detail="This phone number cannot be used for citizen access.")
    else:
        user.phone_number = phone_number
        user.phone_verified_at = now
    db.add(models.AuditLog(user_id=user.id, action="PHONE_VERIFIED"))
    _set_session(response, db, user)
    db.commit(); db.refresh(user)
    return {"message": "Phone verified.", "profile_completed": _profile_completed(user), "user": user_payload(user)}


@router.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id, "role": current_user.role, "name": current_user.name,
        "email": current_user.email, "phone_number": _masked_phone(current_user.phone_number),
        "phone_verified": bool(current_user.phone_verified_at), "email_verified": bool(current_user.email_verified_at),
        "profile_completed": _profile_completed(current_user), "state": current_user.state, "district": current_user.district,
        "pincode": current_user.pincode, "address": current_user.address,
        "aadhaar_provided": bool(current_user.aadhaar_provided),
        "aadhaar_masked": f"XXXX-XXXX-{current_user.aadhaar_last4}" if current_user.aadhaar_last4 else None,
        "aadhaar_status": current_user.aadhaar_status or "UNVERIFIED",
    }


@router.post("/logout")
def logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME), db: Session = Depends(get_db)):
    revoke_session(db, session_token)
    db.add(models.AuditLog(action="LOGOUT")); db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"message": "Signed out."}


@router.put("/profile")
def update_profile(payload: schemas.ProfileUpdate, current_user: models.User = Depends(require_citizen), db: Session = Depends(get_db)):
    name = (payload.name or "").strip()
    state_value, district = (payload.state or "").strip(), (payload.district or "").strip()
    if not name or not state_value or not district:
        raise HTTPException(status_code=422, detail="Full name, state, and district are required.")
    email = validate_email(payload.email)
    existing = db.query(models.User).filter(func.lower(models.User.email) == email, models.User.id != current_user.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    if current_user.email != email:
        current_user.email_verified_at = None
    if payload.aadhaar_number:
        compact = re.sub(r"[\s-]", "", payload.aadhaar_number)
        if not re.fullmatch(r"\d{12}", compact):
            raise HTTPException(status_code=422, detail="Enter a valid 12-digit Aadhaar number.")
        current_user.aadhaar_last4, current_user.aadhaar_provided, current_user.aadhaar_status = compact[-4:], True, "UNVERIFIED"
    current_user.name, current_user.email = name[:120], email
    current_user.state, current_user.district = state_value[:120], district[:120]
    current_user.pincode, current_user.address = (payload.pincode or "").strip()[:20] or None, (payload.address or "").strip()[:500] or None
    current_user.profile_completed_at = datetime.datetime.utcnow()
    db.add(models.AuditLog(user_id=current_user.id, action="PROFILE_COMPLETED")); db.commit(); db.refresh(current_user)
    return me(current_user)


@router.post("/email/request-verification")
def request_email_verification(response: Response, current_user: models.User = Depends(require_citizen), db: Session = Depends(get_db)):
    if not current_user.email:
        raise HTTPException(status_code=422, detail="Complete your profile with an email address first.")
    now = datetime.datetime.utcnow()
    previous = db.query(models.EmailVerificationChallenge).filter(models.EmailVerificationChallenge.user_id == current_user.id,
        models.EmailVerificationChallenge.used_at.is_(None)).order_by(models.EmailVerificationChallenge.created_at.desc()).first()
    if previous and (now - previous.created_at).total_seconds() < 60:
        raise HTTPException(status_code=429, detail="Please wait before requesting another code.")
    if previous: previous.used_at = now
    code = _new_code(); db.add(models.EmailVerificationChallenge(user_id=current_user.id, email=current_user.email,
        code_hash=_challenge_hash(current_user.email, code), expires_at=now + datetime.timedelta(minutes=10), created_at=now)); db.commit()
    result = _otp_provider().send(current_user.email, code, "email verification")
    result["expires_in_seconds"] = 600
    return result


@router.post("/email/verify")
def verify_email(payload: schemas.EmailVerificationCode, current_user: models.User = Depends(require_citizen), db: Session = Depends(get_db)):
    now = datetime.datetime.utcnow()
    challenge = db.query(models.EmailVerificationChallenge).filter(models.EmailVerificationChallenge.user_id == current_user.id,
        models.EmailVerificationChallenge.used_at.is_(None)).order_by(models.EmailVerificationChallenge.created_at.desc()).first()
    if not challenge or challenge.expires_at <= now or challenge.attempts >= 5 or challenge.email != current_user.email or not re.fullmatch(r"\d{6}", payload.code or ""):
        raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
    if not hmac.compare_digest(challenge.code_hash, _challenge_hash(challenge.email, payload.code)):
        challenge.attempts += 1; db.commit(); raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
    challenge.used_at, current_user.email_verified_at = now, now
    db.add(models.AuditLog(user_id=current_user.id, action="EMAIL_VERIFIED")); db.commit()
    return {"message": "Email verified."}


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
    # A matching email alone is not sufficient proof to merge two accounts.
    # Existing accounts can link Google only through a future authenticated flow.
    if not user and email_user:
        return RedirectResponse(f"{frontend_url}/login?google_error=account_mismatch", status_code=status.HTTP_302_FOUND)
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
    elif user.google_subject != google_subject:
        return RedirectResponse(f"{frontend_url}/login?google_error=account_mismatch", status_code=status.HTTP_302_FOUND)
    user.email_verified_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(user)
    redirect = RedirectResponse(f"{frontend_url}/login?google_success=1", status_code=status.HTTP_302_FOUND)
    _set_session(redirect, db, user); db.commit()
    return redirect


@router.post("/google/exchange")
def exchange_google_ticket(payload: schemas.GoogleOAuthTicket, response: Response, db: Session = Depends(get_db)):
    record = _oauth_tickets.pop(payload.ticket, None)
    if not record or record[0] <= time.time():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your Google sign-in session expired. Please sign in again.")
    user = db.get(models.User, record[1]["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your Google sign-in session expired. Please sign in again.")
    _set_session(response, db, user); db.commit()
    return {"message": "Google sign-in successful", "user": user_payload(user)}


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
def login(user: schemas.UserCreate, response: Response, db: Session = Depends(get_db)):
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
        _set_session(response, db, db_user); db.commit()
        return {"message": "Login successful", "user": user_payload(db_user), "phone_verification_required": not bool(db_user.phone_verified_at)}
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

    _set_session(response, db, db_user); db.commit()
    return {"message": "Login successful", "user": user_payload(db_user)}
