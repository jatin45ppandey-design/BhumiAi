import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from security import require_active_citizen
from services.export_service import build_verified_record_export
from services.export_service import export_filename
from services.export_csv import render_verified_record_csv
from services.export_pdf import PdfFontUnavailableError, render_verified_record_pdf
from fastapi import Response

router = APIRouter()
SUBMISSION_STATUSES = {"SUBMITTED", "PROCESSING", "NEEDS_REVIEW", "VERIFIED", "REJECTED"}


def _rejection_details(db: Session, submission: models.Submission):
    event = db.query(models.AuditLog).filter(
        models.AuditLog.submission_id == submission.id,
        models.AuditLog.action == "REJECTED",
    ).order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc()).first()
    if not event:
        return None
    import json
    try:
        metadata = json.loads(event.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return {
        "reason_category": metadata.get("reason_category"), "officer_note": metadata.get("officer_note"),
        "actor_role": metadata.get("actor_role"), "rejected_at": event.timestamp, "rejected_by": event.user_id,
    }


def _submission_payload(db: Session, submission: models.Submission):
    payload = schemas.Submission.model_validate(submission).model_dump()
    payload["rejection"] = _rejection_details(db, submission) if submission.status == "REJECTED" else None
    payload["verified_record_id"] = submission.verified_record.id if submission.verified_record else None
    return payload


@router.get("/notifications", response_model=list[schemas.UserNotification])
def get_notifications(current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    return db.query(models.UserNotification).filter(models.UserNotification.user_id == current_user.id).order_by(
        models.UserNotification.created_at.desc(), models.UserNotification.id.desc()
    ).all()


@router.patch("/notifications/{notification_id}/read", response_model=schemas.UserNotification)
def mark_notification_read(notification_id: int, current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    notification = db.query(models.UserNotification).filter(
        models.UserNotification.id == notification_id, models.UserNotification.user_id == current_user.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit(); db.refresh(notification)
    return notification

@router.get("/dashboard")
def get_user_dashboard(current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    user_id = current_user.id
    counts = dict(
        db.query(models.Submission.status, func.count(models.Submission.id))
        .filter(
            models.Submission.user_id == user_id,
            models.Submission.status != "UPLOADED",
        )
        .group_by(models.Submission.status)
        .all()
    )
    
    return {
        "total_submitted": sum(counts.values()),
        "pending_review": counts.get("SUBMITTED", 0),
        "processing": counts.get("PROCESSING", 0),
        "verified": counts.get("VERIFIED", 0),
        "needs_review": counts.get("NEEDS_REVIEW", 0),
        "rejected": counts.get("REJECTED", 0),
    }

@router.get("/submissions", response_model=list[schemas.Submission])
def get_my_submissions(status: str | None = None, search: str | None = None, current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    """Return only the requested citizen's submissions, including their own rejection metadata."""
    if status:
        status = status.strip().upper()
        if status not in SUBMISSION_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported submission status")
    query = db.query(models.Submission).join(models.Document).filter(
        models.Submission.user_id == current_user.id,
        models.Submission.status != "UPLOADED",
    )
    if status:
        query = query.filter(models.Submission.status == status)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            cast(models.Submission.id, String).ilike(pattern), models.Submission.status.ilike(pattern),
            models.Document.original_filename.ilike(pattern), models.Document.document_type.ilike(pattern),
            models.Document.state.ilike(pattern), models.Document.district.ilike(pattern),
            models.Document.tehsil.ilike(pattern), models.Document.village.ilike(pattern),
        ))
    rows = query.order_by(models.Submission.submitted_at.desc(), models.Submission.id.desc()).all()
    return [_submission_payload(db, row) for row in rows]


@router.get("/records/{id}/export/json")
def export_my_verified_record_json(
    id: int,
    current_user: models.User = Depends(require_active_citizen),
    db: Session = Depends(get_db),
):
    """Export only a verified record belonging to the authenticated citizen."""

    record = db.query(models.VerifiedRecord).filter(models.VerifiedRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    submission = record.submission
    if not submission or submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You may export only your own verified records.")
    if str(record.verification_status or "").upper() != "VERIFIED":
        raise HTTPException(status_code=409, detail="Only verified records can be exported.")
    payload = build_verified_record_export(db, record)
    db.add(models.AuditLog(
        user_id=current_user.id,
        submission_id=record.submission_id,
        record_id=record.id,
        action="RECORD_EXPORTED",
        metadata_json=json.dumps({"format": "JSON"}),
    ))
    db.commit()
    return payload


def _owned_verified_record(id: int, current_user: models.User, db: Session):
    record = db.query(models.VerifiedRecord).filter(models.VerifiedRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if not record.submission or record.submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You may export only your own verified records.")
    if str(record.verification_status or "").upper() != "VERIFIED":
        raise HTTPException(status_code=409, detail="Only verified records can be exported.")
    return record


@router.get("/records/{id}/export/csv")
def export_my_verified_record_csv(id: int, current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    record = _owned_verified_record(id, current_user, db)
    content = render_verified_record_csv(build_verified_record_export(db, record))
    db.add(models.AuditLog(user_id=current_user.id, submission_id=record.submission_id, record_id=record.id,
                           action="RECORD_EXPORTED", metadata_json=json.dumps({"format": "CSV"})))
    db.commit()
    return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{export_filename(record.record_id, "csv")}"'})


@router.get("/records/{id}/export/pdf")
def export_my_verified_record_pdf(id: int, current_user: models.User = Depends(require_active_citizen), db: Session = Depends(get_db)):
    record = _owned_verified_record(id, current_user, db)
    try:
        content = render_verified_record_pdf(build_verified_record_export(db, record))
    except PdfFontUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.add(models.AuditLog(user_id=current_user.id, submission_id=record.submission_id, record_id=record.id,
                           action="RECORD_EXPORTED", metadata_json=json.dumps({"format": "PDF"})))
    db.commit()
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{export_filename(record.record_id, "pdf")}"'})
