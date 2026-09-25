from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from security import get_current_user, require_active_citizen, require_officer
import hashlib
import datetime
import os
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_UPLOAD_BYTES = max(1, int(os.getenv("MAX_UPLOAD_MB", "50"))) * 1024 * 1024

def generate_file_hash(file_path: str):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _latest_submission(db: Session, document_id: int):
    return db.query(models.Submission).filter(models.Submission.document_id == document_id).order_by(
        models.Submission.submitted_at.desc(), models.Submission.id.desc()
    ).first()


def _verified_record_for_document(db: Session, document: models.Document):
    record = db.query(models.VerifiedRecord).filter(
        models.VerifiedRecord.verification_status == "VERIFIED",
        models.VerifiedRecord.submission.has(models.Submission.document_id == document.id),
    ).order_by(models.VerifiedRecord.id.desc()).first()
    return record.submission if record else _latest_submission(db, document.id), record


def _exact_duplicate_match(db: Session, current: models.Document) -> models.Document | None:
    candidates = db.query(models.Document).filter(
        models.Document.file_hash == current.file_hash,
        models.Document.id < current.id,
    ).order_by(models.Document.id.asc()).all()
    for candidate in candidates:
        _, record = _verified_record_for_document(db, candidate)
        if record:
            return candidate
    return candidates[0] if candidates else None


def _duplicate_payload(db: Session, current: models.Document, matched: models.Document | None) -> dict:
    current_submission = _latest_submission(db, current.id)
    payload = {
        "duplicate": bool(matched), "match_type": "EXACT_FILE_HASH" if matched else "NONE",
        "current_submission_id": current_submission.id if current_submission else None,
        "current_status": current_submission.status if current_submission else None,
        "message": "Exact file match detected." if matched else "No exact duplicate detected.",
    }
    if not matched:
        return payload
    matched_submission, record = _verified_record_for_document(db, matched)
    payload.update({
        "matched_document_id": matched.id,
        "matched_submission_id": matched_submission.id if matched_submission else None,
        "matched_status": matched_submission.status if matched_submission else None,
        "verified_record_id": record.id if record else None,
        "verified_record_code": record.record_id if record else None,
        "verified_at": record.verified_at if record else None,
    })
    return payload

def _original_filename(filename: str | None) -> tuple[str, str]:
    safe_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    safe_name = "".join(character for character in safe_name if character.isprintable())
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a PDF, JPG, JPEG, or PNG document.")
    return safe_name[:255], extension


def _stored_file(stored_path: str | None) -> Path | None:
    if not stored_path:
        return None
    backend_root = Path(__file__).resolve().parent.parent
    upload_root = Path(UPLOAD_DIR)
    roots = {
        upload_root.resolve(),
        (backend_root / "uploads").resolve(),
        (backend_root / "storage").resolve(),
        (Path.cwd() / "uploads").resolve(),
        (Path.cwd() / "storage").resolve(),
    }
    raw_path = Path(stored_path)
    candidates = [raw_path] if raw_path.is_absolute() else [Path.cwd() / raw_path, backend_root / raw_path]
    for candidate in candidates:
        resolved = candidate.resolve()
        if any(resolved == root or root in resolved.parents for root in roots) and resolved.is_file():
            return resolved
    return None


def _may_view_document(db: Session, document_id: int, current_user: models.User) -> bool:
    if current_user.role == "officer":
        return True
    if current_user.role != "user":
        return False
    return db.query(models.Submission.id).filter(
        models.Submission.document_id == document_id,
        models.Submission.user_id == current_user.id,
    ).first() is not None


async def persist_upload(file, document_type, state, district, tehsil, village, db):
    original_filename, extension = _original_filename(file.filename)
    upload_directory = Path(UPLOAD_DIR)
    upload_directory.mkdir(parents=True, exist_ok=True)
    file_path = upload_directory / f"{uuid.uuid4().hex}{extension}"
    try:
        with file_path.open("xb") as buffer:
            size = 0
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="The uploaded document is too large.")
                buffer.write(chunk)
            if size == 0:
                raise HTTPException(status_code=422, detail="The uploaded document is empty.")
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    db_doc = models.Document(
        file_path=str(file_path), original_filename=original_filename, document_type=document_type,
        state=state, district=district, tehsil=tehsil, village=village,
        file_hash=generate_file_hash(str(file_path)), file_size=file_path.stat().st_size,
        uploaded_at=datetime.datetime.utcnow()
    )
    db.add(db_doc)
    return db_doc


def _commit_uploaded_document(
    db: Session,
    document: models.Document,
    *,
    user_id: int,
    status: str,
    actor_role: str,
) -> models.Submission:
    """Persist the document, owner submission, and provenance as one DB unit."""
    submission = models.Submission(document=document, user_id=user_id, status=status)
    try:
        db.add(submission)
        db.flush()
        db.add(models.AuditLog(
            user_id=user_id,
            document_id=document.id,
            submission_id=submission.id,
            action="DOCUMENT_UPLOADED",
            metadata_json=json.dumps({"actor_role": actor_role}),
        ))
        db.commit()
    except Exception:
        db.rollback()
        Path(document.file_path).unlink(missing_ok=True)
        raise
    db.refresh(document)
    db.refresh(submission)
    return submission


@router.get("/{id}/content")
def get_document_content(
    id: int,
    variant: str = "original",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(models.Document).filter(models.Document.id == id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _may_view_document(db, document.id, current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    if variant not in {"original", "processed"}:
        raise HTTPException(status_code=422, detail="Unsupported document variant.")
    stored_path = document.file_path if variant == "original" else document.processed_file_path
    source = _stored_file(stored_path)
    if not source:
        raise HTTPException(status_code=404, detail="Document file not found")
    display_name = document.original_filename if variant == "original" else f"{Path(document.original_filename).stem}-enhanced{source.suffix}"
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    return FileResponse(
        source,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(display_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    state: str = Form(...),
    district: str = Form(...),
    tehsil: str = Form(...),
    village: str = Form(...),
    current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)
):
    db_doc = await persist_upload(file, document_type, state, district, tehsil, village, db)
    submission = _commit_uploaded_document(
        db, db_doc, user_id=current_user.id, status="UPLOADED", actor_role="CITIZEN"
    )
    return {
        "message": "Document uploaded successfully",
        "document_id": db_doc.id,
        "submission_id": submission.id,
        "status": submission.status,
    }

@router.post("/officer-upload")
async def officer_upload_document(
    file: UploadFile = File(...), document_type: str = Form(...), state: str = Form(...),
    district: str = Form(...), tehsil: str = Form(...), village: str = Form(...),
    current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)
):
    doc = await persist_upload(file, document_type, state, district, tehsil, village, db)
    submission = _commit_uploaded_document(
        db, doc, user_id=current_officer.id, status="PROCESSING", actor_role="OFFICER"
    )
    return {"message":"Officer document uploaded and added to processing queue", "document_id":doc.id, "submission_id":submission.id, "status":submission.status, "review_url":f"/officer/review/{doc.id}"}

@router.post("/{id}/duplicate-check")
def duplicate_check(id: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    duplicate = _exact_duplicate_match(db, doc)
    doc.duplicate_checked_at = datetime.datetime.utcnow()
    doc.duplicate_of_id = duplicate.id if duplicate else None
    latest_submission = _latest_submission(db, id)
    payload = _duplicate_payload(db, doc, duplicate)
    db.add(models.AuditLog(document_id=id, submission_id=latest_submission.id if latest_submission else None,
        user_id=current_officer.id, action="DUPLICATE_CHECKED", metadata_json=json.dumps({
            "duplicate": payload["duplicate"], "match_type": payload["match_type"],
            "matched_document_id": payload.get("matched_document_id"), "matched_submission_id": payload.get("matched_submission_id"),
            "verified_record_id": payload.get("verified_record_id"),
        })))
    db.commit()
    return payload


@router.post("/{id}/duplicate-continue")
def continue_after_duplicate(id: int, matched_document_id: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    current = db.query(models.Document).filter(models.Document.id == id).first()
    matched = db.query(models.Document).filter(models.Document.id == matched_document_id).first()
    if not current or not matched:
        raise HTTPException(status_code=404, detail="Document not found")
    if current.file_hash != matched.file_hash or matched.id >= current.id:
        raise HTTPException(status_code=422, detail="Continue Review requires a previous exact document match")
    current_submission = _latest_submission(db, id)
    if not current_submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_submission.status not in {"SUBMITTED", "PROCESSING", "NEEDS_REVIEW"}:
        raise HTTPException(status_code=409, detail="Only an active submission can continue duplicate review.")
    db.add(models.AuditLog(user_id=current_officer.id, document_id=id, submission_id=current_submission.id,
        action="DUPLICATE_OVERRIDE_CONTINUE", metadata_json=json.dumps({"matched_document_id": matched.id, "match_type": "EXACT_FILE_HASH"})))
    db.commit()
    return {"message": "Duplicate review acknowledged; the current submission remains unchanged."}

@router.post("/{id}/submit")
def submit_document(id: int, current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    submission = _latest_submission(db, id)
    if not submission or submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You may submit only a document you uploaded.")
    if submission.status != "UPLOADED":
        raise HTTPException(status_code=409, detail="This document has already been submitted.")

    submission.status = "SUBMITTED"
    submission.submitted_at = datetime.datetime.utcnow()
    
    # Audit log
    audit = models.AuditLog(
        user_id=current_user.id,
        document_id=id,
        submission_id=submission.id,
        action="SUBMITTED_TO_OFFICER"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(submission)
    return {"message": "Submitted to officer", "submission_id": submission.id}
