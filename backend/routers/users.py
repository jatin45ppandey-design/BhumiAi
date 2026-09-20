from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas

router = APIRouter()

@router.get("/dashboard")
def get_user_dashboard(user_id: int, db: Session = Depends(get_db)):
    # Get user specific stats
    total = db.query(models.Submission).filter(models.Submission.user_id == user_id).count()
    pending = db.query(models.Submission).filter(
        models.Submission.user_id == user_id, 
        models.Submission.status.in_(["SUBMITTED", "PROCESSING"])
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
        "verified": verified,
        "needs_review": needs_review,
        "rejected": rejected
    }

@router.get("/submissions", response_model=list[schemas.Submission])
def get_my_submissions(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Submission).filter(models.Submission.user_id == user_id).all()
