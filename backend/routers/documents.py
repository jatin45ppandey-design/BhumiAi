from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import hashlib
import datetime
import os
import shutil

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def generate_file_hash(file_path: str):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

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
def duplicate_check(id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    duplicate = db.query(models.Document).filter(
        models.Document.file_hash == doc.file_hash,
        models.Document.id != id
    ).first()
    doc.duplicate_checked_at = datetime.datetime.utcnow()
    doc.duplicate_of_id = duplicate.id if duplicate else None
    latest_submission = db.query(models.Submission).filter(models.Submission.document_id == id).order_by(models.Submission.id.desc()).first()
    db.add(models.AuditLog(document_id=id, submission_id=latest_submission.id if latest_submission else None,
        action="DUPLICATE_CHECKED", metadata_json=(f'{{"duplicate":true,"duplicate_id":{duplicate.id}}}' if duplicate else '{"duplicate":false}')))
    db.commit()
    
    if duplicate:
        return {"duplicate": True, "duplicate_id": duplicate.id, "message": "Possible duplicate submission detected."}
    return {"duplicate": False, "message": "No exact duplicate detected."}

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
        models.OCRResult, models.VerifiedRecord, models.Submission, models.Document,
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
