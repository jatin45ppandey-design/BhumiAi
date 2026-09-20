from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import hashlib
import datetime
import os
import shutil
import json

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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


def _rejection_details(db: Session, submission: models.Submission | None):
    if not submission or submission.status != "REJECTED":
        return None
    event = db.query(models.AuditLog).filter(models.AuditLog.submission_id == submission.id,
        models.AuditLog.action == "REJECTED").order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc()).first()
    if not event:
        return None
    try:
        metadata = json.loads(event.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return {"reason_category": metadata.get("reason_category"), "officer_note": metadata.get("officer_note")}


def _duplicate_payload(db: Session, current: models.Document, matched: models.Document | None, include_details: bool = False) -> dict:
    current_submission = _latest_submission(db, current.id)
    payload = {
        "duplicate": bool(matched), "match_type": "EXACT_FILE_HASH" if matched else "NONE",
        "current_submission_id": current_submission.id if current_submission else None,
        "current_status": current_submission.status if current_submission else None,
        "message": "Exact file match detected." if matched else "No exact duplicate detected.",
    }
    # The citizen upload flow also uses this endpoint for a lightweight check.
    # Match details are reserved for the officer workflow; without a server-side
    # identity system this follows the application's existing role-query pattern.
    if not matched or not include_details:
        return payload
    matched_submission = _latest_submission(db, matched.id)
    record = None
    if matched_submission:
        record = db.query(models.VerifiedRecord).filter(
            models.VerifiedRecord.submission_id == matched_submission.id
        ).first()
    verified_metadata = {
        key: value for key, value in {
            "owner_name": record.owner_name if record else None,
            "father_guardian_name": record.father_guardian_name if record else None,
            "khasra_number": record.khasra_number if record else None,
            "khata_number": record.khata_number if record else None,
            "area": record.area if record else None,
            "village": record.village if record else None,
            "tehsil": record.tehsil if record else None,
            "district": record.district if record else None,
            "state": record.state if record else None,
        }.items() if value not in (None, "")
    }
    related_documents = db.query(models.Document).filter(
        models.Document.file_hash == current.file_hash
    ).order_by(models.Document.id.asc()).all()
    related_submissions = []
    for related_document in related_documents:
        related_submission = _latest_submission(db, related_document.id)
        if related_submission:
            related_submissions.append({
                "document_id": related_document.id,
                "submission_id": related_submission.id,
                "status": related_submission.status,
            })
    payload.update({
        "matched_document_id": matched.id,
        "matched_submission_id": matched_submission.id if matched_submission else None,
        "matched_status": matched_submission.status if matched_submission else None,
        "verified_record_id": record.id if record else None,
        "verified_record_code": record.record_id if record else None,
        "verified_at": record.verified_at if record else None,
        "verified_metadata": verified_metadata,
        "matched_document": {"filename": matched.original_filename, "document_type": matched.document_type,
            "village": matched.village, "district": matched.district, "state": matched.state, "tehsil": matched.tehsil},
        "current_citizen": {"name": current_submission.user.name} if current_submission and current_submission.user else None,
        "related_submissions": related_submissions,
        "previous_rejection": _rejection_details(db, matched_submission),
    })
    return payload

async def persist_upload(file, document_type, state, district, tehsil, village, db):
    safe_name = os.path.basename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    db_doc = models.Document(
        file_path=file_path, original_filename=safe_name, document_type=document_type,
        state=state, district=district, tehsil=tehsil, village=village,
        file_hash=generate_file_hash(file_path), file_size=os.path.getsize(file_path),
        uploaded_at=datetime.datetime.utcnow()
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    state: str = Form(...),
    district: str = Form(...),
    tehsil: str = Form(...),
    village: str = Form(...),
    db: Session = Depends(get_db)
):
    db_doc = await persist_upload(file, document_type, state, district, tehsil, village, db)
    db.add(models.AuditLog(document_id=db_doc.id, action="DOCUMENT_UPLOADED", metadata_json='{"actor_role":"CITIZEN"}'))
    db.commit()
    return {"message": "Document uploaded successfully", "document_id": db_doc.id}

@router.post("/officer-upload")
async def officer_upload_document(
    file: UploadFile = File(...), document_type: str = Form(...), state: str = Form(...),
    district: str = Form(...), tehsil: str = Form(...), village: str = Form(...),
    officer_id: int = Form(...), db: Session = Depends(get_db)
):
    officer = db.query(models.User).filter(models.User.id == officer_id, models.User.role == "officer").first()
    if not officer:
        raise HTTPException(status_code=403, detail="Officer identity is required for officer upload.")
    doc = await persist_upload(file, document_type, state, district, tehsil, village, db)
    submission = models.Submission(document_id=doc.id, user_id=officer.id, status="PROCESSING")
    db.add(submission)
    db.flush()
    db.add(models.AuditLog(user_id=officer.id, document_id=doc.id, submission_id=submission.id, action="DOCUMENT_UPLOADED", metadata_json='{"actor_role":"OFFICER"}'))
    db.commit(); db.refresh(submission)
    return {"message":"Officer document uploaded and added to processing queue", "document_id":doc.id, "submission_id":submission.id, "status":submission.status, "review_url":f"/officer/review/{doc.id}"}

@router.post("/{id}/duplicate-check")
def duplicate_check(id: int, officer_id: int | None = None, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    duplicate = db.query(models.Document).filter(
        models.Document.file_hash == doc.file_hash,
        models.Document.id != id
    ).order_by(models.Document.id.asc()).first()
    doc.duplicate_checked_at = datetime.datetime.utcnow()
    doc.duplicate_of_id = duplicate.id if duplicate else None
    latest_submission = _latest_submission(db, id)
    if officer_id is not None:
        officer = db.query(models.User).filter(models.User.id == officer_id, models.User.role == "officer").first()
        if not officer:
            raise HTTPException(status_code=403, detail="Officer identity is required for duplicate resolution.")
    payload = _duplicate_payload(db, doc, duplicate, include_details=officer_id is not None)
    db.add(models.AuditLog(document_id=id, submission_id=latest_submission.id if latest_submission else None,
        user_id=officer_id, action="DUPLICATE_CHECKED", metadata_json=json.dumps({
            "duplicate": payload["duplicate"], "match_type": payload["match_type"],
            "matched_document_id": payload.get("matched_document_id"), "matched_submission_id": payload.get("matched_submission_id"),
            "verified_record_id": payload.get("verified_record_id"),
        })))
    db.commit()
    return payload


@router.post("/{id}/duplicate-continue")
def continue_after_duplicate(id: int, officer_id: int, matched_document_id: int, db: Session = Depends(get_db)):
    current = db.query(models.Document).filter(models.Document.id == id).first()
    matched = db.query(models.Document).filter(models.Document.id == matched_document_id).first()
    officer = db.query(models.User).filter(models.User.id == officer_id, models.User.role == "officer").first()
    if not current or not matched:
        raise HTTPException(status_code=404, detail="Document not found")
    if not officer:
        raise HTTPException(status_code=403, detail="Officer identity is required for duplicate resolution.")
    current_submission = _latest_submission(db, id)
    db.add(models.AuditLog(user_id=officer_id, document_id=id, submission_id=current_submission.id if current_submission else None,
        action="DUPLICATE_OVERRIDE_CONTINUE", metadata_json=json.dumps({"matched_document_id": matched.id, "match_type": "EXACT_FILE_HASH"})))
    db.commit()
    return {"message": "Duplicate review acknowledged; the current submission remains unchanged."}

@router.post("/{id}/submit")
def submit_document(id: int, user_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    submission = models.Submission(document_id=id, user_id=user_id, status="SUBMITTED")
    db.add(submission)
    
    # Audit log
    audit = models.AuditLog(
        user_id=user_id,
        document_id=id,
        submission_id=submission.id,
        action="SUBMITTED_TO_OFFICER"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(submission)
    return {"message": "Submitted to officer", "submission_id": submission.id}


@router.post("/development/reset-land-records")
def reset_land_records(confirm: bool = False, db: Session = Depends(get_db)):
    """Clear operational land-record data in development while keeping users."""
    if os.environ.get("LANDSIGHT_ENV", "development").lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if not confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to clear land-record data")

    documents = db.query(models.Document).all()
    file_paths = {
        path
        for document in documents
        for path in (document.file_path, getattr(document, "processed_file_path", None))
        if path
    }
    counts = {
        "documents": len(documents),
        "submissions": db.query(models.Submission).count(),
        "verified_records": db.query(models.VerifiedRecord).count(),
        "ocr_results": db.query(models.OCRResult).count(),
    }
    for model in (
        models.DynamicDigitizationAudit, models.AuditLog, models.DynamicExtractedCell,
        models.DynamicExtractedTable, models.DynamicExtractedItem, models.ExtractedField,
        models.OCRResult, models.UserNotification, models.VerifiedRecord, models.Submission, models.Document,
    ):
        db.query(model).delete(synchronize_session=False)
    db.commit()

    upload_root = os.path.abspath(UPLOAD_DIR)
    file_paths.update(
        os.path.join(upload_root, name)
        for name in os.listdir(upload_root)
        if os.path.isfile(os.path.join(upload_root, name))
    )
    removed_files = 0
    for path in file_paths:
        absolute = os.path.abspath(path)
        if os.path.commonpath([upload_root, absolute]) == upload_root and os.path.isfile(absolute):
            os.remove(absolute)
            removed_files += 1
    return {"message": "Development land-record data cleared; users preserved.", "removed": counts, "removed_files": removed_files}
