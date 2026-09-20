from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text

from database import engine, Base
import models
from routers import auth, users, documents, officer, records

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# Preserve the real Hindi OCR preview in Windows terminal/log output. Without
# this, a cp1252 console can raise UnicodeEncodeError while reporting success.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except (AttributeError, OSError):
    pass

# Create tables
Base.metadata.create_all(bind=engine)

# Additive SQLite migrations. Existing local demo records are retained and the
# new dynamic tables are created by metadata.create_all above. The ALTERs below
# only extend pre-existing tables created before dynamic digitization support.
def apply_local_migrations():
    additions = {
        "users": {"password_hash": "TEXT", "google_subject": "TEXT", "officer_id": "TEXT"},
        "ocr_results": {
            "languages":"TEXT",
            "overall_confidence":"REAL",
            "token_count":"INTEGER",
            "token_confidence_json":"TEXT",
            # Complete pytesseract image_to_data records (text, confidence, and
            # bounding boxes) are persisted separately from the legacy summary.
            "token_layout_json":"TEXT",
            "layout_metadata_json":"TEXT",
        },
        "extracted_fields": {"confidence_source":"TEXT", "final_value":"TEXT"},
        "documents": {
            "file_size": "INTEGER",
            "uploaded_at": "DATETIME",
            "processed_file_path": "TEXT",
            "duplicate_checked_at": "DATETIME",
            "duplicate_of_id": "INTEGER",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            present = {row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))}
            for name, declaration in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_subject_unique "
            "ON users(google_subject) WHERE google_subject IS NOT NULL"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_officer_id_unique "
            "ON users(officer_id) WHERE officer_id IS NOT NULL"
        ))
        # Explicit indexes keep dynamic document views and later generic search
        # inexpensive without modifying or rebuilding the legacy tables.
        indexes = (
            ("ix_dynamic_extracted_items_document_id", "dynamic_extracted_items", "document_id"),
            ("ix_dynamic_extracted_items_normalized_label", "dynamic_extracted_items", "normalized_label"),
            ("ix_dynamic_extracted_tables_document_id", "dynamic_extracted_tables", "document_id"),
            ("ix_dynamic_extracted_cells_document_id", "dynamic_extracted_cells", "document_id"),
            ("ix_dynamic_extracted_cells_table_id", "dynamic_extracted_cells", "table_id"),
            ("ix_dynamic_digitization_audits_document_id", "dynamic_digitization_audits", "document_id"),
        )
        for index_name, table, column in indexes:
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))
apply_local_migrations()

# Provision one authority-issued developer officer when these values are set
# server-side. No public route can create an officer account.
from database import SessionLocal
def provision_government_officer():
    officer_id = os.getenv("GOVERNMENT_OFFICER_ID", "").strip().upper()
    officer_email = os.getenv("GOVERNMENT_OFFICER_EMAIL", "").strip().lower()
    officer_name = os.getenv("GOVERNMENT_OFFICER_NAME", "Government Verification Officer").strip()
    officer_password = os.getenv("GOVERNMENT_OFFICER_PASSWORD", "")
    if not any((officer_id, officer_email, officer_password)):
        return
    if not all((officer_id, officer_email, officer_password)):
        raise RuntimeError("Set GOVERNMENT_OFFICER_ID, GOVERNMENT_OFFICER_EMAIL, and GOVERNMENT_OFFICER_PASSWORD together.")
    officer_id = auth.normalize_officer_id(officer_id)
    officer_email = auth.validate_email(officer_email)
    officer_password = auth.validate_password(officer_password)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.officer_id == officer_id).first()
        email_user = db.query(models.User).filter_by(email=officer_email).first()
        if user and email_user and user.id != email_user.id:
            raise RuntimeError("Government Officer ID and email belong to different accounts.")
        user = user or email_user
        if user and user.role != "officer":
            raise RuntimeError("Government officer email is already assigned to a Record Submitter account.")
        if not user:
            user = models.User(email=officer_email, name=officer_name, role="officer")
            db.add(user)
        user.officer_id = officer_id
        user.name = officer_name[:120] or "Government Verification Officer"
        user.role = "officer"
        if not user.password_hash or not auth.verify_password(officer_password, user.password_hash):
            user.password_hash = auth.hash_password(officer_password)
        db.commit()
    finally:
        db.close()
provision_government_officer()

app = FastAPI(title="Land Record Intelligence System API")

default_cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "http://10.128.94.242:3000"]
configured_cors_origins = [origin.strip().rstrip("/") for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
allowed_cors_origins = list(dict.fromkeys([*default_cors_origins, *configured_cors_origins]))

app.add_middleware(
    CORSMiddleware,
    # The local Next dev server may be opened through its LAN address while
    # still talking to this loopback API. Keep credentials scoped to known
    # local development origins instead of permitting arbitrary websites.
    allow_origins=allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("storage", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/user", tags=["users"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(officer.router, prefix="/api/officer", tags=["officer"])
app.include_router(officer.router, prefix="/api", tags=["officer_alias"])
app.include_router(records.router, prefix="/api/verified-records", tags=["records"])

@app.get("/")
def root():
    return {"message": "Welcome to SIH Land Record API"}

@app.get("/health")
def health():
    return {"status": "ok"}
