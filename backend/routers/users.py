from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session
from database import get_db
import models, schemas

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
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.UserNotification).filter(models.UserNotification.user_id == user_id).order_by(
        models.UserNotification.created_at.desc(), models.UserNotification.id.desc()
    ).all()


@router.patch("/notifications/{notification_id}/read", response_model=schemas.UserNotification)
def mark_notification_read(notification_id: int, user_id: int, db: Session = Depends(get_db)):
    notification = db.query(models.UserNotification).filter(
        models.UserNotification.id == notification_id, models.UserNotification.user_id == user_id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit(); db.refresh(notification)
    return notification

@router.get("/dashboard")
def get_user_dashboard(user_id: int, db: Session = Depends(get_db)):
    # Get user specific stats
    total = db.query(models.Submission).filter(models.Submission.user_id == user_id).count()
    pending = db.query(models.Submission).filter(
        models.Submission.user_id == user_id,
        models.Submission.status == "SUBMITTED"
    ).count()
    processing = db.query(models.Submission).filter(
        models.Submission.user_id == user_id,
        models.Submission.status == "PROCESSING"
    ).count()
    verified = db.query(models.Submission).filter(
        models.Submission.user_id == user_id, 
        models.Submission.status == "VERIFIED"
    ).count()
    needs_review = db.query(models.Submission).filter(
        models.Submission.user_id == user_id, 
        models.Submission.status == "NEEDS_REVIEW"
    ).count()
    rejected = db.query(models.Submission).filter(
        models.Submission.user_id == user_id, 
        models.Submission.status == "REJECTED"
    ).count()
    
    return {
        "total_submitted": total,
        "pending_review": pending,
        "processing": processing,
        "verified": verified,
        "needs_review": needs_review,
        "rejected": rejected
    }

@router.get("/submissions", response_model=list[schemas.Submission])
def get_my_submissions(user_id: int, status: str | None = None, search: str | None = None, db: Session = Depends(get_db)):
    """Return only the requested citizen's submissions, including their own rejection metadata."""
    if status:
        status = status.strip().upper()
        if status not in SUBMISSION_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported submission status")
    query = db.query(models.Submission).join(models.Document).filter(models.Submission.user_id == user_id)
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
