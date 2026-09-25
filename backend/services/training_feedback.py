"""Controlled capture and offline export of officer-verified OCR feedback."""

from __future__ import annotations

import datetime
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session

import models


FEEDBACK_STATUSES = {"PENDING", "VERIFIED_SAMPLE", "EXCLUDED"}


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _same_value(left: Any, right: Any) -> bool:
    return " ".join(_text(left).split()) == " ".join(_text(right).split())


def _schema_key(entity: Any) -> str | None:
    metadata = _metadata(getattr(entity, "audit_metadata_json", None))
    return str(metadata.get("schema_key") or getattr(entity, "normalized_label", "") or "").strip() or None


def _recognition_details(db: Session, entity: Any) -> tuple[str | None, str | None]:
    ocr_id = getattr(entity, "ocr_result_id", None)
    ocr = db.get(models.OCRResult, ocr_id) if ocr_id else None
    entity_metadata = _metadata(getattr(entity, "audit_metadata_json", None))
    evidence = entity_metadata.get("recognition_evidence") or {}
    selected = evidence.get("selected_engine") if isinstance(evidence, dict) else None
    metadata = _metadata(ocr.layout_metadata_json) if ocr else {}
    hybrid = metadata.get("hybrid_recognition") or {}
    engine = str(selected or ("hybrid" if hybrid else getattr(ocr, "engine", "") or "")).strip() or None
    model_version = hybrid.get("htr_model") if isinstance(hybrid, dict) else None
    return engine, str(model_version).strip() if model_version else None


def capture_correction_feedback(db: Session, entity: Any, entity_type: str, actor_id: int) -> tuple[models.AITrainingFeedback | None, str]:
    """Upsert one pending candidate for a meaningful officer correction.

    This intentionally never mutates OCR/entity evidence.  Reverting an edit
    excludes the pending candidate rather than treating an unchanged value as a
    training target.
    """

    original = getattr(entity, "ai_value", None)
    if not _text(original):
        original = getattr(entity, "raw_ocr_value", None)
    correction = getattr(entity, "final_value", None)
    if correction is None:
        correction = getattr(entity, "officer_value", None)
    existing = db.query(models.AITrainingFeedback).filter_by(
        document_id=entity.document_id, entity_type=entity_type, entity_id=entity.id,
    ).first()
    if not _text(original) or correction is None or _same_value(original, correction):
        if existing and existing.sample_status == "PENDING":
            existing.sample_status = "EXCLUDED"
            existing.exclusion_reason = "Correction reverted or no longer differs from recognition evidence."
            existing.image_trainable = False
            return existing, "excluded"
        return None, "unchanged"
    if existing and existing.sample_status != "PENDING":
        return existing, "terminal"
    engine, model_version = _recognition_details(db, entity)
    values = {
        "ocr_result_id": getattr(entity, "ocr_result_id", None),
        "schema_key": _schema_key(entity),
        "raw_ocr_value": getattr(entity, "raw_ocr_value", None),
        "ai_prediction": original,
        "officer_correction": str(correction),
        "ai_confidence": getattr(entity, "ai_confidence", None),
        "confidence_source": getattr(entity, "confidence_source", None),
        "bounding_box": getattr(entity, "bounding_box", None),
        "source_token_ids": getattr(entity, "source_token_ids", None) or [],
        "recognition_engine": engine,
        "model_version": model_version,
        "image_trainable": bool(getattr(entity, "bounding_box", None)),
        "exclusion_reason": None,
    }
    if existing:
        for name, value in values.items():
            setattr(existing, name, value)
        return existing, "updated"
    feedback = models.AITrainingFeedback(
        document_id=entity.document_id, entity_type=entity_type, entity_id=entity.id,
        sample_status="PENDING", **values,
    )
    db.add(feedback)
    db.flush()
    return feedback, "created"


def promote_document_feedback(db: Session, document_id: int, officer_id: int) -> int:
    rows = db.query(models.AITrainingFeedback).filter_by(document_id=document_id, sample_status="PENDING").all()
    now = datetime.datetime.utcnow()
    for row in rows:
        row.sample_status, row.verified_at, row.verified_by, row.exclusion_reason = "VERIFIED_SAMPLE", now, officer_id, None
    return len(rows)


def exclude_document_feedback(db: Session, document_id: int, reason: str) -> int:
    rows = db.query(models.AITrainingFeedback).filter_by(document_id=document_id, sample_status="PENDING").all()
    for row in rows:
        row.sample_status, row.exclusion_reason, row.image_trainable = "EXCLUDED", reason[:500], False
    return len(rows)


def feedback_summary(db: Session) -> dict[str, Any]:
    counts = Counter(row[0] for row in db.query(models.AITrainingFeedback.sample_status).all())
    schema_counts = dict(db.query(models.AITrainingFeedback.schema_key, func.count(models.AITrainingFeedback.id))
                         .group_by(models.AITrainingFeedback.schema_key).all())
    return {
        "pending": counts["PENDING"], "verified_samples": counts["VERIFIED_SAMPLE"], "excluded": counts["EXCLUDED"],
        "by_schema_key": {str(key or "unclassified"): value for key, value in schema_counts.items()},
    }


def feedback_list(db: Session, *, status: str | None = None, schema_key: str | None = None) -> list[dict[str, Any]]:
    query = db.query(models.AITrainingFeedback)
    if status:
        query = query.filter(models.AITrainingFeedback.sample_status == status)
    if schema_key:
        query = query.filter(models.AITrainingFeedback.schema_key == schema_key)
    rows = query.order_by(models.AITrainingFeedback.updated_at.desc(), models.AITrainingFeedback.id.desc()).all()
    return [{
        "id": row.id, "document_id": row.document_id, "ocr_result_id": row.ocr_result_id,
        "entity_type": row.entity_type, "entity_id": row.entity_id, "schema_key": row.schema_key,
        "ai_prediction": row.ai_prediction, "officer_correction": row.officer_correction,
        "ai_confidence": row.ai_confidence, "confidence_source": row.confidence_source,
        "recognition_engine": row.recognition_engine, "model_version": row.model_version,
        "image_trainable": row.image_trainable, "sample_status": row.sample_status,
        "verified_at": row.verified_at, "exclusion_reason": row.exclusion_reason,
    } for row in rows]


def _crop_box(bounding_box: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(bounding_box, dict):
        return None
    try:
        left, top = float(bounding_box["left"]), float(bounding_box["top"])
        right = float(bounding_box.get("right", left + float(bounding_box["width"])))
        bottom = float(bounding_box.get("bottom", top + float(bounding_box["height"])))
    except (KeyError, TypeError, ValueError):
        return None
    left, top = max(0, math.floor(left)), max(0, math.floor(top))
    right, bottom = min(width, math.ceil(right)), min(height, math.ceil(bottom))
    return (left, top, right, bottom) if right > left and bottom > top else None


def export_feedback_crop(feedback: models.AITrainingFeedback, output_path: Path) -> tuple[bool, str | None]:
    """Copy a clamped evidence crop without ever modifying the source image."""

    source = feedback.ocr_result.processed_image_path if feedback.ocr_result else None
    if not source or not Path(source).is_file():
        feedback.image_trainable = False
        return False, "processed_source_unavailable"
    try:
        with Image.open(source) as image:
            box = _crop_box(feedback.bounding_box, *image.size)
            if not box:
                feedback.image_trainable = False
                return False, "bounding_box_unavailable"
            image.crop(box).save(output_path, format="PNG")
        feedback.image_trainable = True
        return True, None
    except Exception:
        feedback.image_trainable = False
        return False, "crop_unavailable"


def export_verified_feedback_dataset(db: Session, export_root: str | Path) -> dict[str, Any]:
    """Create a local, image-only dataset from already verified feedback samples."""

    root = Path(export_root)
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output = root / f"bhumiai_feedback_{stamp}"
    suffix = 1
    while output.exists():
        suffix += 1
        output = root / f"bhumiai_feedback_{stamp}_{suffix}"
    images = output / "images"
    images.mkdir(parents=True, exist_ok=False)
    samples = db.query(models.AITrainingFeedback).filter_by(sample_status="VERIFIED_SAMPLE").order_by(models.AITrainingFeedback.id).all()
    skipped: list[dict[str, Any]] = []
    schema_counts = Counter(row.schema_key or "unclassified" for row in samples)
    exported = 0
    with (output / "dataset.jsonl").open("w", encoding="utf-8") as dataset:
        for feedback in samples:
            filename = f"sample_{feedback.id:06d}.png"
            created, reason = export_feedback_crop(feedback, images / filename)
            if not created:
                skipped.append({"id": feedback.id, "reason": reason})
                continue
            dataset.write(json.dumps({
                "id": feedback.id, "image": f"images/{filename}", "text": feedback.officer_correction,
                "prediction": feedback.ai_prediction, "schema_key": feedback.schema_key,
                "confidence": feedback.ai_confidence, "recognition_engine": feedback.recognition_engine,
                "model_version": feedback.model_version,
            }, ensure_ascii=False) + "\n")
            exported += 1
    manifest = {
        "schema": "bhumiai_feedback_dataset_v1", "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_verified_samples": len(samples), "image_trainable_samples": exported,
        "samples_missing_usable_crop": len(skipped), "samples_by_schema_key": dict(sorted(schema_counts.items())),
        "skipped_samples": skipped,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    db.add(models.AuditLog(action="AI_FEEDBACK_DATASET_EXPORTED", metadata_json=json.dumps({
        "total_verified_samples": len(samples), "image_trainable_samples": exported,
        "samples_missing_usable_crop": len(skipped), "export_directory": output.name,
    }, ensure_ascii=False)))
    return {"export_directory": str(output), **manifest}
