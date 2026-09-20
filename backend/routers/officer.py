"""Officer workflow for real Tesseract-backed Khatauni digitization."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from typing import Any, Optional

import cv2
import numpy as np
import pytesseract
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from config import TESSERACT_CMD, TESSERACT_LANGUAGES
from database import get_db
from digitization import build_lines, confidence_for, load_tokens, normalized_label, tokens_from_tesseract
from khatauni_fast import prepare_page, recognize as recognize_fast_khatauni
from khatauni_extractor import KhatauniExtractor
from khatauni_schema import HEADER_FIELDS, TABLE_COLUMNS
from khatauni_structured import compact_recognition_evidence
import models
import schemas
from security import require_officer


router = APIRouter(dependencies=[Depends(require_officer)])
SUBMISSION_STATUSES = {"SUBMITTED", "PROCESSING", "NEEDS_REVIEW", "VERIFIED", "REJECTED"}
REJECTION_CATEGORIES = {
    "Poor Scan Quality", "Incomplete Document", "Incorrect Document",
    "Unreadable Information", "Duplicate Submission", "Information Mismatch", "Other",
}


def _source_digest(path: str) -> str:
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _load_document_image(path: str):
    """Load an image or render the first PDF page without changing source evidence."""
    if os.path.splitext(path)[1].lower() != ".pdf":
        return cv2.imread(path), None
    try:
        import fitz
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="PDF rendering support is unavailable") from exc
    pdf = fitz.open(path)
    try:
        if not pdf.page_count:
            raise HTTPException(status_code=400, detail="The uploaded PDF has no pages")
        pixmap = pdf.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        array = np.frombuffer(pixmap.tobytes("png"), dtype=np.uint8)
        return cv2.imdecode(array, cv2.IMREAD_COLOR), 1
    finally:
        pdf.close()


def _deskew(gray):
    inverse = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coordinates = np.column_stack(np.where(inverse > 0))
    if coordinates.size == 0:
        return gray, 0.0
    angle = cv2.minAreaRect(coordinates)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.15 or abs(angle) > 12:
        return gray, 0.0
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE), angle


def _assess_image_quality(source, gray) -> dict[str, Any]:
    height, width = gray.shape[:2]
    percentiles = [float(x) for x in np.percentile(gray, [5, 50, 95])]
    contrast_span = percentiles[2] - percentiles[0]
    dark_mask = gray < max(70, percentiles[1] - 35)
    horizontal = cv2.morphologyEx(dark_mask.astype("uint8") * 255, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, width // 20), 1)))
    vertical = cv2.morphologyEx(dark_mask.astype("uint8") * 255, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, height // 28))))
    channel_medians = np.median(source.reshape(-1, 3), axis=0)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    ink_density = float(np.mean(dark_mask))
    warnings = []
    if min(width, height) < 900:
        warnings.append("low_resolution")
    if blur < 80:
        warnings.append("possible_blur")
    if contrast_span < 80:
        warnings.append("low_contrast")
    if ink_density < 0.015:
        warnings.append("faint_or_sparse_ink")
    return {
        "width": int(width),
        "height": int(height),
        "paper_color_cast": round(float(np.max(channel_medians) - np.min(channel_medians)), 2),
        "gray_percentiles": percentiles,
        "contrast_span": round(float(contrast_span), 2),
        "laplacian_variance": round(blur, 2),
        "ink_density": round(ink_density, 4),
        "table_line_strength": round(float(np.mean((horizontal | vertical) > 0)), 4),
        "warnings": warnings,
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_safe(value: Any) -> Any:
    """Make audit snapshots safe for SQLite's strict JSON column serializer."""
    if value is None:
        return None
    return json.loads(_json(value))


def _changes(payload: Any) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)


def _document(db: Session, document_id: int) -> models.Document:
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _latest_ocr(db: Session, document_id: int) -> models.OCRResult | None:
    return db.query(models.OCRResult).filter(models.OCRResult.document_id == document_id).order_by(models.OCRResult.id.desc()).first()


def _officer(db: Session, officer_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == officer_id).first()
    if not user or user.role != "officer":
        raise HTTPException(status_code=403, detail="An officer account is required")
    return user


def _rejection_details(db: Session, submission: models.Submission) -> dict[str, Any] | None:
    event = db.query(models.AuditLog).filter(
        models.AuditLog.submission_id == submission.id,
        models.AuditLog.action == "REJECTED",
    ).order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc()).first()
    if not event:
        return None
    try:
        metadata = json.loads(event.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return {
        "reason_category": metadata.get("reason_category"),
        "officer_note": metadata.get("officer_note"),
        "actor_role": metadata.get("actor_role"),
        "rejected_at": event.timestamp,
        "rejected_by": event.user_id,
    }


def _submission_payload(db: Session, submission: models.Submission) -> dict[str, Any]:
    payload = schemas.Submission.model_validate(submission).model_dump()
    payload["rejection"] = _rejection_details(db, submission) if submission.status == "REJECTED" else None
    payload["verified_record_id"] = submission.verified_record.id if submission.verified_record else None
    return payload


def _submission_search_query(db: Session, *, status: str | None, search: str | None):
    if status:
        status = status.strip().upper()
        if status not in SUBMISSION_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported submission status")
    query = db.query(models.Submission).join(models.Document).join(models.User)
    if status:
        query = query.filter(models.Submission.status == status)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            cast(models.Submission.id, String).ilike(pattern),
            models.Submission.status.ilike(pattern),
            models.Document.original_filename.ilike(pattern),
            models.Document.document_type.ilike(pattern),
            models.Document.state.ilike(pattern), models.Document.district.ilike(pattern),
            models.Document.tehsil.ilike(pattern), models.Document.village.ilike(pattern),
            models.User.name.ilike(pattern), models.User.email.ilike(pattern),
        ))
    return query


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _value(row: Any) -> Optional[str]:
    # None means not supplied; an officer may intentionally correct to "".
    for name in ("final_value", "officer_value", "ai_value", "raw_ocr_value"):
        value = getattr(row, name, None)
        if value is not None:
            return value
    return None


def _headers(table: models.DynamicExtractedTable) -> list[Any]:
    if table.final_headers is not None:
        return _list(table.final_headers)
    if table.officer_headers is not None:
        return _list(table.officer_headers)
    return _list(table.detected_headers)


def _item_json(item: models.DynamicExtractedItem) -> dict[str, Any]:
    return {
        "id": item.id, "field_id": item.id, "document_id": item.document_id, "ocr_result_id": item.ocr_result_id,
        "item_type": item.item_type, "display_order": item.display_order, "original_label": item.original_label,
        "normalized_label": item.normalized_label, "raw_ocr_value": item.raw_ocr_value, "ai_value": item.ai_value,
        "ai_confidence": item.ai_confidence, "confidence_source": item.confidence_source, "row_index": item.row_index,
        "column_index": item.column_index, "bounding_box": item.bounding_box, "source_token_ids": item.source_token_ids or [],
        "officer_value": item.officer_value, "final_value": item.final_value, "display_value": _value(item),
        "edited": bool(item.edited_by or item.edited_at), "edited_by": item.edited_by, "edited_at": item.edited_at,
        "audit_metadata": item.audit_metadata_json or {},
    }


def _cell_json(cell: models.DynamicExtractedCell) -> dict[str, Any]:
    return {
        "id": cell.id, "cell_id": cell.id, "table_id": cell.table_id, "document_id": cell.document_id,
        "ocr_result_id": cell.ocr_result_id, "row_index": cell.row_index, "column_index": cell.column_index,
        "header_label": cell.header_label, "raw_ocr_value": cell.raw_ocr_value, "ai_value": cell.ai_value,
        "ai_confidence": cell.ai_confidence, "confidence_source": cell.confidence_source, "bounding_box": cell.bounding_box,
        "source_token_ids": cell.source_token_ids or [], "officer_value": cell.officer_value, "final_value": cell.final_value,
        "display_value": _value(cell), "edited": bool(cell.edited_by or cell.edited_at), "edited_by": cell.edited_by,
        "edited_at": cell.edited_at, "audit_metadata": cell.audit_metadata_json or {},
    }


def _table_json(table: models.DynamicExtractedTable, cells: list[models.DynamicExtractedCell]) -> dict[str, Any]:
    detected = _list(table.detected_headers)
    effective = _headers(table)
    maximum = max([cell.column_index for cell in cells], default=-1) + 1
    column_count = max(table.column_count or 0, len(detected), len(effective), maximum)
    header_rows = []
    for index in range(column_count):
        label = effective[index] if index < len(effective) else None
        header_rows.append({"column_index": index, "label": label if isinstance(label, str) and label.strip() else f"Unknown Column {index + 1}", "detected": index < len(detected)})
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in sorted(cells, key=lambda entry: (entry.row_index, entry.column_index, entry.id)):
        grouped[cell.row_index].append(_cell_json(cell))
    return {
        "id": table.id, "table_id": table.id, "document_id": table.document_id, "ocr_result_id": table.ocr_result_id,
        "table_index": table.table_index, "original_label": table.original_label, "normalized_label": table.normalized_label,
        "detected_headers": detected, "officer_headers": _list(table.officer_headers), "final_headers": _list(table.final_headers),
        "headers": header_rows, "row_count": len(grouped), "column_count": column_count, "bounding_box": table.bounding_box,
        "ai_confidence": table.ai_confidence, "confidence_source": table.confidence_source,
        "edited": bool(table.edited_by or table.edited_at), "edited_by": table.edited_by, "edited_at": table.edited_at,
        "cells": [_cell_json(cell) for cell in cells],
        "rows": [{"row_index": key, "cells": value} for key, value in sorted(grouped.items())],
    }


def _summary(items: list[models.DynamicExtractedItem], tables: list[dict[str, Any]]) -> dict[str, int]:
    cells = [cell for table in tables for cell in table["cells"]]
    detected_items = [item for item in items if (item.raw_ocr_value or item.ai_value or "").strip()]
    populated_cells = [cell for cell in cells if (cell.get("raw_ocr_value") or cell.get("ai_value") or "").strip()]
    values = [item.ai_confidence for item in detected_items] + [cell["ai_confidence"] for cell in populated_cells]
    rows = {(table["table_id"], row["row_index"]) for table in tables for row in table["rows"]}
    return {
        "fields_detected": len(detected_items), "header_fields_detected": len(detected_items),
        "header_fields_total": len(items), "tables_detected": len(tables), "rows_digitized": len(rows),
        "columns_detected": sum(table["column_count"] for table in tables),
        "ocr_cells_populated": len(populated_cells),
        "high_confidence_items": sum(value is not None and value >= 90 for value in values),
        "medium_confidence_items": sum(value is not None and 70 <= value < 90 for value in values),
        "low_confidence_items": sum(value is not None and value < 70 for value in values),
        "unavailable_confidence_items": sum(value is None for value in values),
    }


def _digitization(db: Session, document_id: int) -> dict[str, Any]:
    ocr = _latest_ocr(db, document_id)
    fields = db.query(models.DynamicExtractedItem).filter(
        models.DynamicExtractedItem.document_id == document_id, models.DynamicExtractedItem.is_deleted.is_(False)
    )
    tables_query = db.query(models.DynamicExtractedTable).filter(
        models.DynamicExtractedTable.document_id == document_id, models.DynamicExtractedTable.is_deleted.is_(False)
    )
    if ocr:
        fields = fields.filter(or_(models.DynamicExtractedItem.ocr_result_id == ocr.id, models.DynamicExtractedItem.ocr_result_id.is_(None)))
        tables_query = tables_query.filter(or_(models.DynamicExtractedTable.ocr_result_id == ocr.id, models.DynamicExtractedTable.ocr_result_id.is_(None)))
    field_rows = fields.order_by(models.DynamicExtractedItem.display_order, models.DynamicExtractedItem.id).all()
    table_payloads = []
    for table in tables_query.order_by(models.DynamicExtractedTable.table_index, models.DynamicExtractedTable.id).all():
        cells = db.query(models.DynamicExtractedCell).filter(
            models.DynamicExtractedCell.table_id == table.id, models.DynamicExtractedCell.is_deleted.is_(False)
        ).order_by(models.DynamicExtractedCell.row_index, models.DynamicExtractedCell.column_index, models.DynamicExtractedCell.id).all()
        table_payloads.append(_table_json(table, cells))
    metadata = {}
    if ocr and ocr.layout_metadata_json:
        try:
            metadata = json.loads(ocr.layout_metadata_json)
        except json.JSONDecodeError:
            pass
    return {"document_id": document_id, "ocr_result_id": ocr.id if ocr else None, "items": [_item_json(item) for item in field_rows], "tables": table_payloads, "summary": _summary(field_rows, table_payloads), "layout_metadata": metadata, "digital_khatauni": metadata.get("digital_khatauni")}


def _audit(db: Session, *, document_id: int, action: str, entity_type: str, actor_id: int | None = None,
           ocr_result_id: int | None = None, entity_id: int | None = None, item_id: int | None = None,
           table_id: int | None = None, cell_id: int | None = None, before: Any = None, after: Any = None,
           metadata: dict[str, Any] | None = None) -> None:
    """Append provenance plus the app's existing audit-log event."""
    db.add(models.DynamicDigitizationAudit(document_id=document_id, ocr_result_id=ocr_result_id, item_id=item_id,
           table_id=table_id, cell_id=cell_id, actor_id=actor_id, action=action, entity_type=entity_type,
           entity_id=entity_id, before_json=_json_safe(before), after_json=_json_safe(after), metadata_json=_json_safe(metadata)))
    db.add(models.AuditLog(document_id=document_id, user_id=actor_id, action=action,
           metadata_json=_json({"entity_type": entity_type, "entity_id": entity_id, **(metadata or {})})))


def _refresh_count(db: Session, table: models.DynamicExtractedTable) -> None:
    cells = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.table_id == table.id,
        models.DynamicExtractedCell.is_deleted.is_(False)).all()
    table.row_count = len({cell.row_index for cell in cells})
    table.column_count = max(len(_headers(table)), max([cell.column_index for cell in cells], default=-1) + 1)


def _table(db: Session, document_id: int, table_id: int) -> models.DynamicExtractedTable:
    table = db.query(models.DynamicExtractedTable).filter(models.DynamicExtractedTable.id == table_id,
        models.DynamicExtractedTable.document_id == document_id, models.DynamicExtractedTable.is_deleted.is_(False)).first()
    if not table:
        raise HTTPException(status_code=404, detail="Dynamic table not found")
    return table


@router.get("/dashboard")
def get_officer_dashboard(db: Session = Depends(get_db)):
    total = db.query(models.Submission).count()
    low_docs: set[int] = set()
    for model in (models.ExtractedField, models.DynamicExtractedItem, models.DynamicExtractedCell):
        try:
            if model is models.ExtractedField:
                rows = db.query(models.OCRResult.document_id).join(model).filter(model.ai_confidence.isnot(None), model.ai_confidence < 60).distinct().all()
            else:
                rows = db.query(model.document_id).filter(model.is_deleted.is_(False), model.ai_confidence.isnot(None), model.ai_confidence < 60).distinct().all()
            low_docs.update(row[0] for row in rows)
        except Exception:
            pass
    return {
        "total_received": total,
        "pending": db.query(models.Submission).filter(models.Submission.status == "SUBMITTED").count(),
        "processing": db.query(models.Submission).filter(models.Submission.status == "PROCESSING").count(),
        "digitized": db.query(models.OCRResult).count(), "verified": db.query(models.VerifiedRecord).count(),
        "needs_review": db.query(models.Submission).filter(models.Submission.status == "NEEDS_REVIEW").count(),
        "rejected": db.query(models.Submission).filter(models.Submission.status == "REJECTED").count(),
        "low_confidence": db.query(models.Submission).filter(models.Submission.document_id.in_(low_docs)).count() if low_docs else 0,
    }


@router.get("/submissions", response_model=list[schemas.Submission])
def get_all_submissions(status: str | None = None, search: str | None = None, db: Session = Depends(get_db)):
    rows = _submission_search_query(db, status=status, search=search).order_by(
        models.Submission.submitted_at.desc(), models.Submission.id.desc()
    ).all()
    return [_submission_payload(db, row) for row in rows]


@router.get("/submissions/{id}", response_model=schemas.Submission)
def get_submission(id: int, db: Session = Depends(get_db)):
    submission = db.query(models.Submission).filter(models.Submission.id == id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status == "SUBMITTED":
        submission.status = "PROCESSING"
        db.commit()
        db.refresh(submission)
    return _submission_payload(db, submission)


@router.post("/documents/{id}/preprocess")
def preprocess_document(id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    doc = _document(db, id)
    image, pdf_page = _load_document_image(doc.file_path)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not read image file")
    prepared = prepare_page(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
    if prepared is not None:
        processed_path = f"{os.path.splitext(doc.file_path)[0]}_processed.png"
        if not cv2.imwrite(processed_path, prepared["gray"]):
            raise HTTPException(status_code=500, detail="Could not save preprocessed image")
        doc.processed_file_path = processed_path
        details = {"processed_file_path": processed_path, "orientation_correction_degrees": 0,
            "deskew_degrees": 0.0, "pdf_page": pdf_page,
            "operations": ["grayscale", "document_boundary", "perspective_and_skew_normalization", "resize"],
            "quality": _assess_image_quality(image, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)),
            "fast_layout": {k: prepared[k] for k in ("xs", "ys", "transform")},
            "source_sha256": _source_digest(doc.file_path),
            "processed_sha256": _source_digest(processed_path)}
        details["fast_layout"]["preprocessing_seconds"] = time.perf_counter() - started
        db.add(models.AuditLog(document_id=id, action="PREPROCESS_COMPLETED", metadata_json=_json(details)))
        db.commit()
        return {"message": "Document preprocessed", **{k:v for k,v in details.items() if k not in {"fast_layout", "source_sha256", "processed_sha256"}}}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray, deskew_angle = _deskew(gray)
    quality = _assess_image_quality(image, gray)
    paper_color_cast = quality["paper_color_cast"]
    if paper_color_cast > 20:
        # Colored or textured paper keeps grayscale strokes; bounded CLAHE can
        # lift faint ink without thresholding away handwriting.
        denoised = cv2.fastNlMeansDenoising(gray, h=7)
        result = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(denoised)
        operations = ["grayscale", "deskew", "denoise_light", "CLAHE_light", "preserve_grayscale_strokes"]
    else:
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
        result = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 35, 13)
        operations = ["grayscale", "deskew", "denoise", "CLAHE", "adaptive_threshold"]

    correction = 0
    try:
        if not os.path.isfile(TESSERACT_CMD):
            raise pytesseract.TesseractNotFoundError(TESSERACT_CMD)
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        osd = pytesseract.image_to_osd(Image.fromarray(result), config="--psm 0")
        match = re.search(r"Rotate:\s*(\d+)", osd)
        correction = int(match.group(1)) if match else 0
        if correction == 90:
            result = cv2.rotate(result, cv2.ROTATE_90_CLOCKWISE)
        elif correction == 180:
            result = cv2.rotate(result, cv2.ROTATE_180)
        elif correction == 270:
            result = cv2.rotate(result, cv2.ROTATE_90_COUNTERCLOCKWISE)
        print(f"OPENCV ORIENTATION CORRECTION document_id={id} rotate={correction}", flush=True)
    except Exception as exc:
        print(f"OPENCV ORIENTATION DETECTION UNAVAILABLE document_id={id} reason={type(exc).__name__}", flush=True)
        correction = 0
    base, extension = os.path.splitext(doc.file_path)
    # Lossless enhancement protects tiny dots; original upload is untouched.
    extension = ".png"
    processed_path = f"{base}_processed{extension}"
    if not cv2.imwrite(processed_path, result):
        raise HTTPException(status_code=500, detail="Could not save preprocessed image")
    doc.processed_file_path = processed_path
    db.add(models.AuditLog(document_id=id, action="PREPROCESS_COMPLETED", metadata_json=_json({"processed_file_path": processed_path,
        "orientation_correction_degrees": correction, "deskew_degrees": deskew_angle, "pdf_page": pdf_page,
        "operations": operations, "quality": quality})))
    db.commit()
    return {"message": "Document preprocessed", "processed_file_path": processed_path,
        "orientation_correction_degrees": correction, "deskew_degrees": deskew_angle, "pdf_page": pdf_page,
        "operations": operations, "quality": quality}


@router.post("/documents/{id}/ocr")
def run_ocr(id: int, processed_path: str | None = None, db: Session = Depends(get_db)):
    doc = _document(db, id)
    image_path = processed_path or doc.file_path
    print("TESSERACT OCR STARTED", flush=True)
    print(f"document_id={id}", flush=True)
    print(f"image={image_path}", flush=True)
    print(f"language={TESSERACT_LANGUAGES}", flush=True)
    raw_text, tokens, confidence = "", [], None
    metadata: dict[str, Any] = {"source_image_path": image_path, "psm": 6}
    engine = "OCR_FAILED"
    _audit(db, document_id=id, action="OCR_STARTED", entity_type="document", entity_id=id,
        metadata={"image_path": image_path, "languages": TESSERACT_LANGUAGES})
    try:
        if not os.path.isfile(TESSERACT_CMD):
            raise pytesseract.TesseractNotFoundError(TESSERACT_CMD)
        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        with Image.open(image_path) as source:
            image = source.copy()
        prepared = None
        source_digest = _source_digest(doc.file_path)
        preprocessing = db.query(models.AuditLog).filter_by(document_id=id, action="PREPROCESS_COMPLETED").order_by(models.AuditLog.id.desc()).first()
        if preprocessing:
            details = json.loads(preprocessing.metadata_json or "{}")
            if (details.get("fast_layout") and details.get("processed_file_path") == image_path
                    and details.get("source_sha256") == source_digest
                    and details.get("processed_sha256") == _source_digest(image_path)):
                gray = np.asarray(image.convert("L"))
                prepared = {**details["fast_layout"], "gray": gray,
                    "binary": cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]}
        try:
            fast = recognize_fast_khatauni(image, prepared)
        except Exception as exc:
            # A specialised recognizer failure must not disable generic OCR.
            fast = None
            metadata["fast_path_fallback"] = type(exc).__name__
        if fast:
            tokens, raw_text = fast["tokens"], fast["raw_text"]
            metadata.update({"fast_structure": fast["structure"], "source_sha256": source_digest,
                "image_width": fast["image_width"], "image_height": fast["image_height"],
                "psm": 7, "token_bbox_source": "field_crop_mapped_to_source_image"})
        else:
            data = pytesseract.image_to_data(image, lang=TESSERACT_LANGUAGES, config="--psm 6", output_type=pytesseract.Output.DICT)
            tokens = tokens_from_tesseract(data)
            # Reuse the same engine output, preserving recognised line order.
            raw_text = "\n".join(line["text"] for line in build_lines(tokens))
            metadata.update({"image_width": image.width, "image_height": image.height, "token_bbox_source": "pytesseract.image_to_data"})
        confidence, _ = confidence_for(tokens)
        engine = f"Tesseract OCR {str(pytesseract.get_tesseract_version()).split()[0]}"
        print("TESSERACT OCR COMPLETED", flush=True)
        print(f"characters={len(raw_text)}", flush=True)
        print(f"tokens={len(tokens)}", flush=True)
        print(f"mean_confidence={confidence if confidence is not None else 'unavailable'}", flush=True)
        try:
            print(f"TESSERACT OCR OUTPUT PREVIEW\n{raw_text[:300]}", flush=True)
        except UnicodeEncodeError:
            print(raw_text[:300].encode("unicode_escape").decode("ascii"), flush=True)
    except pytesseract.TesseractNotFoundError:
        engine = "OCR_FAILED: Tesseract executable unavailable"
        print("TESSERACT OCR FAILED: executable unavailable", flush=True)
    except Exception as exc:
        engine = f"OCR_FAILED: {type(exc).__name__}"
        metadata["error"] = f"{type(exc).__name__}: {exc}"
        print(f"TESSERACT OCR FAILED: {type(exc).__name__}: {exc}", flush=True)

    legacy = [{"text": token["text"], "confidence": token.get("confidence")} for token in tokens]
    ocr = models.OCRResult(document_id=id, engine=engine, script="Devanagari/English", raw_text=raw_text,
        processed_image_path=image_path, languages=TESSERACT_LANGUAGES, overall_confidence=confidence,
        token_count=len(tokens), token_confidence_json=_json(legacy), token_layout_json=_json(tokens),
        layout_metadata_json=_json(metadata))
    db.add(ocr)
    db.flush()
    _audit(db, document_id=id, ocr_result_id=ocr.id, action="OCR_COMPLETED" if raw_text else "OCR_FAILED",
        entity_type="ocr_result", entity_id=ocr.id, metadata={"engine": engine, "languages": TESSERACT_LANGUAGES,
        "character_count": len(raw_text), "token_count": len(tokens), "overall_confidence": confidence, "image_path": image_path})
    db.commit()
    return {"message": "Tesseract OCR completed successfully." if raw_text else "OCR produced no text; officer may digitize manually.",
        "status": "COMPLETED" if raw_text else "OCR_FAILED", "ocr_id": ocr.id, "raw_text": raw_text, "engine": engine,
        "languages": TESSERACT_LANGUAGES, "overall_confidence": confidence, "token_count": len(tokens),
        "character_count": len(raw_text), "processed_image_path": image_path, "tokens": tokens}


@router.post("/documents/{id}/extract")
def extract_fields(id: int, ocr_id: int | None = None, db: Session = Depends(get_db)):
    doc = _document(db, id)
    ocr = db.query(models.OCRResult).filter(models.OCRResult.id == ocr_id, models.OCRResult.document_id == id).first() if ocr_id else _latest_ocr(db, id)
    if not ocr:
        raise HTTPException(status_code=404, detail="OCR result not found for this document")
    tokens = load_tokens(ocr.token_layout_json)
    try:
        metadata = json.loads(ocr.layout_metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    width, height = int(metadata.get("image_width") or 0), int(metadata.get("image_height") or 0)
    if width <= 0 or height <= 0:
        try:
            with Image.open(ocr.processed_image_path) as image:
                width, height = image.size
        except Exception:
            boxes = [token.get("bbox") or {} for token in tokens]
            width = max([int(box.get("left", 0)) + int(box.get("width", 0)) for box in boxes], default=1)
            height = max([int(box.get("top", 0)) + int(box.get("height", 0)) for box in boxes], default=1)
    extractor = KhatauniExtractor(
        raw_ocr=ocr.raw_text or "",
        normalized_ocr=re.sub(r"\s+", " ", ocr.raw_text or "").strip(),
        tokens=tokens,
        image_width=width,
        image_height=height,
        image_path=doc.file_path,
    )
    structure = metadata.get("fast_structure")
    if structure and metadata.get("source_sha256") != _source_digest(doc.file_path):
        raise HTTPException(status_code=409, detail="Source image changed. Please run recognition again before extraction.")
    if structure and metadata.get("auto_fields_created") and db.query(models.DynamicExtractedItem.id).filter_by(document_id=id, ocr_result_id=ocr.id).first():
        return {"message": "Previously extracted values loaded.", **_digitization(db, id)}
    if not structure:
        structure = extractor.extract()

    # Repeat extraction only replaces untouched candidates from this OCR run.
    old_items = db.query(models.DynamicExtractedItem).filter(models.DynamicExtractedItem.document_id == id,
        models.DynamicExtractedItem.ocr_result_id == ocr.id, models.DynamicExtractedItem.created_by.is_(None),
        models.DynamicExtractedItem.edited_by.is_(None), models.DynamicExtractedItem.is_deleted.is_(False)).all()
    for item in old_items:
        item.is_deleted, item.deleted_at = True, datetime.datetime.utcnow()
    old_tables = db.query(models.DynamicExtractedTable).filter(models.DynamicExtractedTable.document_id == id,
        models.DynamicExtractedTable.ocr_result_id == ocr.id, models.DynamicExtractedTable.created_by.is_(None),
        models.DynamicExtractedTable.edited_by.is_(None), models.DynamicExtractedTable.is_deleted.is_(False)).all()
    for table in old_tables:
        table.is_deleted, table.deleted_at = True, datetime.datetime.utcnow()
        for cell in table.cells:
            if not cell.edited_by:
                cell.is_deleted, cell.deleted_at = True, datetime.datetime.utcnow()

    item_count = detected_item_count = table_count = cell_count = populated_cell_count = 0
    for order, source in enumerate(structure["header_fields"]):
        value = source.get("ocr_value") or ""
        db.add(models.DynamicExtractedItem(document_id=id, ocr_result_id=ocr.id, item_type="key_value", display_order=order,
            original_label=source.get("label"), normalized_label=source.get("key"), raw_ocr_value=value,
            ai_value=value, final_value=None, ai_confidence=source.get("ocr_confidence"),
            confidence_source=source.get("confidence_source"), row_index=None, column_index=None,
            bounding_box=source.get("bounding_box"), source_token_ids=source.get("source_token_ids") or [],
            audit_metadata_json={"source": "khatauni_label_mapping", "schema_key": source.get("key"),
                "status": source.get("status"), "validation": source.get("validation"),
                "recognition_evidence": compact_recognition_evidence(source.get("audit_metadata"))}))
        item_count += 1
        detected_item_count += bool(value)
    headers = structure["table_headers"]
    table = models.DynamicExtractedTable(document_id=id, ocr_result_id=ocr.id, table_index=0,
        original_label="मुख्य खतौनी तालिका", normalized_label="khatauni_main_table",
        detected_headers=headers, row_count=len(structure["rows"]), column_count=len(headers),
        ai_confidence=None, confidence_source="tesseract_token_mean", source_token_ids=[],
        audit_metadata_json={"source": "khatauni_schema", "headings_only": True})
    db.add(table); db.flush(); table_count = 1
    for row_index, source_row in enumerate(structure["rows"]):
        by_column = {cell["column_index"]: cell for cell in source_row.get("cells", [])}
        for column_index, header in enumerate(headers):
            source_cell = by_column.get(column_index, {})
            value = source_cell.get("raw_ocr_value") or ""
            db.add(models.DynamicExtractedCell(table_id=table.id, document_id=id, ocr_result_id=ocr.id,
                row_index=row_index, column_index=column_index, header_label=header,
                raw_ocr_value=value, ai_value=value, final_value=None,
                ai_confidence=source_cell.get("ai_confidence"), confidence_source=source_cell.get("confidence_source") or "unavailable",
                bounding_box=source_cell.get("bounding_box"), source_token_ids=source_cell.get("source_token_ids") or [],
                audit_metadata_json={"source": source_row.get("source", "khatauni_extractor"), "schema_key": TABLE_COLUMNS[column_index]["key"],
                    "status": source_cell.get("status"), "validation": source_cell.get("validation"),
                    "recognition_evidence": compact_recognition_evidence(source_cell.get("audit_metadata")),
                    "source_physical_row_index": source_row.get("source_physical_row_index"),
                    "source_line_index": source_row.get("source_line_index"),
                    "source_line_count": source_row.get("source_line_count")}))
            cell_count += 1
            populated_cell_count += bool(value)
    extraction_summary = structure["extraction_summary"]
    metadata.update({"detected_document_type": "khatauni", "layout_detector": "khatauni_label_token_and_roi_geometry",
        "khatauni_extraction_summary": extraction_summary, "hybrid_recognition": structure.get("hybrid_metadata", {}),
        "digital_khatauni": structure.get("digital_khatauni"),
        "schema_header_count": len(HEADER_FIELDS),
        "schema_column_count": len(TABLE_COLUMNS), "auto_fields_created": item_count,
        "auto_tables_created": table_count, "auto_cells_created": cell_count})
    ocr.layout_metadata_json = _json(metadata)
    _audit(db, document_id=id, ocr_result_id=ocr.id, action="KHATAUNI_EXTRACTION_COMPLETED", entity_type="ocr_result", entity_id=ocr.id,
        metadata=extraction_summary)
    db.commit()
    message = "Khatauni values extracted with persisted OCR tokens and bounded hybrid recognition."
    if not detected_item_count and not populated_cell_count:
        message = "No readable Khatauni values were detected. Officer verification is required."
    return {"message": message, **_digitization(db, id)}


@router.get("/documents/{id}/digitization")
def get_digitization(id: int, db: Session = Depends(get_db)):
    _document(db, id)
    return _digitization(db, id)


@router.get("/documents/{id}/fields", response_model=list[schemas.ExtractedField])
def get_extracted_fields(id: int, db: Session = Depends(get_db)):
    ocr = _latest_ocr(db, id)
    return ocr.extracted_fields if ocr else []


@router.get("/documents/{id}/ocr/latest")
def get_latest_ocr(id: int, db: Session = Depends(get_db)):
    ocr = _latest_ocr(db, id)
    if not ocr:
        raise HTTPException(status_code=404, detail="No OCR result exists for this document.")
    try:
        metadata = json.loads(ocr.layout_metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {"ocr_id": ocr.id, "raw_text": ocr.raw_text, "engine": ocr.engine,
        "languages": ocr.languages or TESSERACT_LANGUAGES, "overall_confidence": ocr.overall_confidence,
        "token_count": ocr.token_count, "character_count": len(ocr.raw_text or ""),
        "status": "COMPLETED" if (ocr.raw_text or "").strip() else "OCR_FAILED", "processed_image_path": ocr.processed_image_path,
        "layout_metadata": metadata, "tokens": load_tokens(ocr.token_layout_json)}


# Compatibility for pre-dynamic demo records only.
@router.patch("/documents/{id}/fields/{field_id}")
def edit_field(id: int, field_id: int, update: schemas.ExtractedFieldUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _officer(db, officer_id)
    field = db.query(models.ExtractedField).filter(models.ExtractedField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    before = field.final_value if field.final_value is not None else field.ai_value
    field.officer_value, field.final_value, field.edited = update.officer_value, update.officer_value, True
    db.add(models.AuditLog(document_id=id, user_id=officer_id, action="Legacy field edited",
        metadata_json=_json({"field": field.field_name, "before": before, "after": update.officer_value})))
    db.commit()
    return {"message": "Field updated"}


@router.post("/documents/{id}/dynamic-fields")
def add_dynamic_field(id: int, payload: schemas.DynamicExtractedItemUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id)
    label = (payload.original_label or "").strip() or None
    value = payload.officer_value if payload.officer_value is not None else payload.final_value
    item = models.DynamicExtractedItem(document_id=id, ocr_result_id=None, item_type=payload.item_type or "key_value",
        display_order=payload.display_order, original_label=label, normalized_label=payload.normalized_label or (normalized_label(label) if label else None),
        raw_ocr_value=payload.raw_ocr_value, ai_value=payload.ai_value, ai_confidence=payload.ai_confidence,
        confidence_source=payload.confidence_source or "officer_manual", row_index=payload.row_index, column_index=payload.column_index,
        bounding_box=payload.bounding_box, source_token_ids=payload.source_token_ids or [], officer_value=value, final_value=value,
        created_by=officer_id, edited_by=officer_id, edited_at=datetime.datetime.utcnow(), audit_metadata_json={"source": "officer_manual"})
    db.add(item); db.flush()
    _audit(db, document_id=id, action="Dynamic field added", entity_type="field", entity_id=item.id, item_id=item.id,
        actor_id=officer_id, after=_item_json(item))
    db.commit()
    return {"message": "Field added", "field": _item_json(item)}


@router.patch("/documents/{id}/dynamic-fields/{field_id}")
def edit_dynamic_field(id: int, field_id: int, payload: schemas.DynamicExtractedItemUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id)
    item = db.query(models.DynamicExtractedItem).filter(models.DynamicExtractedItem.id == field_id,
        models.DynamicExtractedItem.document_id == id, models.DynamicExtractedItem.is_deleted.is_(False)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dynamic field not found")
    before, changed = _item_json(item), _changes(payload)
    for name in ("item_type", "display_order", "original_label", "raw_ocr_value", "ai_value", "ai_confidence", "confidence_source", "row_index", "column_index", "bounding_box", "source_token_ids"):
        if name in changed:
            setattr(item, name, changed[name])
    if "normalized_label" in changed:
        item.normalized_label = changed["normalized_label"]
    elif "original_label" in changed:
        item.normalized_label = normalized_label(item.original_label or "")
    if "officer_value" in changed:
        item.officer_value = changed["officer_value"]; item.final_value = changed["officer_value"]
    elif "final_value" in changed:
        item.final_value = changed["final_value"]
    item.edited_by, item.edited_at = officer_id, datetime.datetime.utcnow()
    _audit(db, document_id=id, ocr_result_id=item.ocr_result_id, action="FIELD_EDITED", entity_type="field",
        entity_id=item.id, item_id=item.id, actor_id=officer_id, before=before, after=_item_json(item))
    db.commit()
    return {"message": "Field updated", "field": _item_json(item)}


@router.delete("/documents/{id}/dynamic-fields/{field_id}")
def delete_dynamic_field(id: int, field_id: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id)
    item = db.query(models.DynamicExtractedItem).filter(models.DynamicExtractedItem.id == field_id,
        models.DynamicExtractedItem.document_id == id, models.DynamicExtractedItem.is_deleted.is_(False)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dynamic field not found")
    before = _item_json(item)
    item.is_deleted, item.deleted_by, item.deleted_at = True, officer_id, datetime.datetime.utcnow()
    _audit(db, document_id=id, ocr_result_id=item.ocr_result_id, action="Dynamic field deleted", entity_type="field",
        entity_id=item.id, item_id=item.id, actor_id=officer_id, before=before)
    db.commit()
    return {"message": "Field removed"}


@router.post("/documents/{id}/tables")
def add_dynamic_table(id: int, payload: schemas.DynamicExtractedTableUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id)
    headers = payload.detected_headers if payload.detected_headers is not None else []
    next_index = db.query(models.DynamicExtractedTable).filter(models.DynamicExtractedTable.document_id == id).count()
    table = models.DynamicExtractedTable(document_id=id, ocr_result_id=None,
        table_index=payload.table_index if payload.table_index is not None else next_index, original_label=payload.original_label,
        normalized_label=payload.normalized_label or (normalized_label(payload.original_label) if payload.original_label else None),
        detected_headers=headers, officer_headers=headers, final_headers=headers, row_count=0, column_count=len(headers),
        bounding_box=payload.bounding_box, ai_confidence=payload.ai_confidence, confidence_source=payload.confidence_source or "officer_manual",
        source_token_ids=payload.source_token_ids or [], created_by=officer_id, edited_by=officer_id,
        edited_at=datetime.datetime.utcnow(), audit_metadata_json={"source": "officer_manual"})
    db.add(table); db.flush()
    _audit(db, document_id=id, action="Dynamic table added", entity_type="table", entity_id=table.id, table_id=table.id,
        actor_id=officer_id, after={"headers": headers})
    db.commit()
    return {"message": "Table added", "table": _table_json(table, [])}


@router.patch("/documents/{id}/tables/{table_id}")
def edit_dynamic_table(id: int, table_id: int, payload: schemas.DynamicExtractedTableUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id); table = _table(db, id, table_id)
    cells = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.table_id == table.id,
        models.DynamicExtractedCell.is_deleted.is_(False)).all()
    before, changed, old_headers = _table_json(table, cells), _changes(payload), _headers(table)
    for name in ("table_index", "original_label", "normalized_label", "bounding_box", "ai_confidence", "confidence_source", "source_token_ids"):
        if name in changed:
            setattr(table, name, changed[name])
    # UI uses officer_headers so OCR headers remain preserved. A legacy client
    # sending detected_headers is also treated as a correction, never a rewrite.
    requested = changed.get("final_headers", changed.get("officer_headers", changed.get("detected_headers")))
    if requested is not None:
        revised = list(requested)
        table.officer_headers, table.final_headers = revised, revised
        # Keep cells aligned when a correction adds/removes document columns.
        new_count = len(revised)
        if new_count < len(old_headers):
            for cell in cells:
                if cell.column_index >= new_count:
                    cell.is_deleted, cell.deleted_by, cell.deleted_at = True, officer_id, datetime.datetime.utcnow()
        elif new_count > len(old_headers):
            rows = sorted({cell.row_index for cell in cells})
            for row_index in rows:
                for column_index in range(len(old_headers), new_count):
                    db.add(models.DynamicExtractedCell(table_id=table.id, document_id=id, ocr_result_id=table.ocr_result_id,
                        row_index=row_index, column_index=column_index, header_label=revised[column_index], officer_value="", final_value="",
                        confidence_source="officer_manual", created_by=officer_id, edited_by=officer_id, edited_at=datetime.datetime.utcnow(),
                        audit_metadata_json={"source": "officer_manual"}))
        for cell in cells:
            if cell.column_index < new_count:
                cell.header_label = revised[cell.column_index] if isinstance(revised[cell.column_index], str) else None
    table.edited_by, table.edited_at = officer_id, datetime.datetime.utcnow()
    _refresh_count(db, table)
    refreshed = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.table_id == table.id,
        models.DynamicExtractedCell.is_deleted.is_(False)).all()
    _audit(db, document_id=id, ocr_result_id=table.ocr_result_id, action="Table headers edited", entity_type="table",
        entity_id=table.id, table_id=table.id, actor_id=officer_id, before=before, after=_table_json(table, refreshed))
    db.commit()
    return {"message": "Table updated", "table": _table_json(table, refreshed)}


@router.post("/documents/{id}/tables/{table_id}/rows")
def add_dynamic_row(id: int, table_id: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id); table = _table(db, id, table_id)
    cells = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.table_id == table.id,
        models.DynamicExtractedCell.is_deleted.is_(False)).all()
    row_index, headers = max([cell.row_index for cell in cells], default=-1) + 1, _headers(table)
    count = max(table.column_count or 0, len(headers))
    created = []
    for column_index in range(count):
        header = headers[column_index] if column_index < len(headers) else f"Unknown Column {column_index + 1}"
        cell = models.DynamicExtractedCell(table_id=table.id, document_id=id, ocr_result_id=table.ocr_result_id,
            row_index=row_index, column_index=column_index, header_label=header, officer_value="", final_value="",
            confidence_source="officer_manual", created_by=officer_id, edited_by=officer_id, edited_at=datetime.datetime.utcnow(),
            audit_metadata_json={"source": "officer_manual"})
        db.add(cell); created.append(cell)
    db.flush(); _refresh_count(db, table)
    _audit(db, document_id=id, ocr_result_id=table.ocr_result_id, action="ROW_ADDED_MANUALLY", entity_type="table_row",
        entity_id=table.id, table_id=table.id, actor_id=officer_id, after={"row_index": row_index, "cell_count": len(created)})
    db.commit()
    return {"message": "Row added", "row_index": row_index, "cells": [_cell_json(cell) for cell in created]}


@router.delete("/documents/{id}/tables/{table_id}/rows/{row_index}")
def delete_dynamic_row(id: int, table_id: int, row_index: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id); table = _table(db, id, table_id)
    cells = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.table_id == table.id,
        models.DynamicExtractedCell.row_index == row_index, models.DynamicExtractedCell.is_deleted.is_(False)).all()
    if not cells:
        raise HTTPException(status_code=404, detail="Table row not found")
    for cell in cells:
        cell.is_deleted, cell.deleted_by, cell.deleted_at = True, officer_id, datetime.datetime.utcnow()
    _refresh_count(db, table)
    _audit(db, document_id=id, ocr_result_id=table.ocr_result_id, action="ROW_REMOVED", entity_type="table_row",
        entity_id=table.id, table_id=table.id, actor_id=officer_id, before={"row_index": row_index, "cell_count": len(cells)})
    db.commit()
    return {"message": "Row removed"}


@router.patch("/documents/{id}/tables/{table_id}/cells/{cell_id}")
def edit_dynamic_cell(id: int, table_id: int, cell_id: int, payload: schemas.DynamicExtractedCellUpdate, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id); _table(db, id, table_id)
    cell = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.id == cell_id,
        models.DynamicExtractedCell.table_id == table_id, models.DynamicExtractedCell.document_id == id,
        models.DynamicExtractedCell.is_deleted.is_(False)).first()
    if not cell:
        raise HTTPException(status_code=404, detail="Dynamic cell not found")
    before, changed = _cell_json(cell), _changes(payload)
    for name in ("row_index", "column_index", "header_label", "raw_ocr_value", "ai_value", "ai_confidence", "confidence_source", "bounding_box", "source_token_ids"):
        if name in changed:
            setattr(cell, name, changed[name])
    if "officer_value" in changed:
        cell.officer_value, cell.final_value = changed["officer_value"], changed["officer_value"]
    elif "final_value" in changed:
        cell.final_value = changed["final_value"]
    cell.edited_by, cell.edited_at = officer_id, datetime.datetime.utcnow()
    _audit(db, document_id=id, ocr_result_id=cell.ocr_result_id, action="FIELD_EDITED", entity_type="cell", entity_id=cell.id,
        table_id=table_id, cell_id=cell.id, actor_id=officer_id, before=before, after=_cell_json(cell))
    db.commit()
    return {"message": "Cell updated", "cell": _cell_json(cell)}


@router.delete("/documents/{id}/tables/{table_id}/cells/{cell_id}")
def delete_dynamic_cell(id: int, table_id: int, cell_id: int, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    _document(db, id); _officer(db, officer_id); table = _table(db, id, table_id)
    cell = db.query(models.DynamicExtractedCell).filter(models.DynamicExtractedCell.id == cell_id,
        models.DynamicExtractedCell.table_id == table_id, models.DynamicExtractedCell.document_id == id,
        models.DynamicExtractedCell.is_deleted.is_(False)).first()
    if not cell:
        raise HTTPException(status_code=404, detail="Dynamic cell not found")
    before = _cell_json(cell)
    cell.is_deleted, cell.deleted_by, cell.deleted_at = True, officer_id, datetime.datetime.utcnow()
    _refresh_count(db, table)
    _audit(db, document_id=id, ocr_result_id=cell.ocr_result_id, action="Table cell removed", entity_type="cell", entity_id=cell.id,
        table_id=table_id, cell_id=cell.id, actor_id=officer_id, before=before)
    db.commit()
    return {"message": "Cell removed"}


@router.post("/documents/{id}/{action}")
def verify_document(id: int, action: str, rejection: schemas.RejectionDecision | None = None, current_officer: models.User = Depends(require_officer), db: Session = Depends(get_db)):
    officer_id = current_officer.id
    if action not in {"approve", "reject", "mark-review"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    _officer(db, officer_id)
    submission = db.query(models.Submission).filter(models.Submission.document_id == id).order_by(models.Submission.id.desc()).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    doc = _document(db, id)
    if action == "reject":
        category = (rejection.reason_category if rejection else "").strip()
        note = (rejection.officer_note if rejection and rejection.officer_note else "").strip()
        if category not in REJECTION_CATEGORIES:
            raise HTTPException(status_code=422, detail="Choose a rejection reason category")
        if category == "Other" and not note:
            raise HTTPException(status_code=422, detail="Add an officer note when using Other")
    submission.status = {"approve": "VERIFIED", "reject": "REJECTED", "mark-review": "NEEDS_REVIEW"}[action]
    if action == "approve":
        ocr = _latest_ocr(db, id)
        dynamic_count = db.query(models.DynamicExtractedItem).filter(models.DynamicExtractedItem.document_id == id,
            models.DynamicExtractedItem.is_deleted.is_(False)).count() + db.query(models.DynamicExtractedTable).filter(
            models.DynamicExtractedTable.document_id == id, models.DynamicExtractedTable.is_deleted.is_(False)).count()
        if not ocr and not dynamic_count:
            raise HTTPException(status_code=400, detail="OCR or manual digitization is required before approval")
        # Fixed columns are only a legacy compatibility shell. Arbitrary OCR
        # labels stay exclusively in the dynamic tables/items rather than being
        # guessed into Owner/Khasra/etc.
        legacy = {field.field_name: (field.final_value if field.final_value is not None else field.ai_value)
                  for field in (ocr.extracted_fields if ocr else [])}
        record = db.query(models.VerifiedRecord).filter(models.VerifiedRecord.submission_id == submission.id).first()
        if not record:
            record = models.VerifiedRecord(record_id=f"LR-{(doc.state or 'NA')[:2].upper()}-{(doc.district or 'NA')[:3].upper()}-{submission.id:06d}",
                submission_id=submission.id, owner_name=legacy.get("owner_name", ""), father_guardian_name=legacy.get("father_guardian_name", ""),
                khasra_number=legacy.get("khasra_number", ""), khata_number=legacy.get("khata_number", ""), area=legacy.get("area", ""),
                village=legacy.get("village", ""), tehsil=legacy.get("tehsil", ""), district=legacy.get("district", ""),
                state=legacy.get("state", ""), verification_status="VERIFIED", verified_by=officer_id)
            db.add(record); db.flush()
        else:
            record.verification_status, record.verified_by = "VERIFIED", officer_id
        _audit(db, document_id=id, ocr_result_id=ocr.id if ocr else None, action="VERIFIED", entity_type="verified_record",
            entity_id=record.id, actor_id=officer_id, metadata={"record_id": record.record_id, "dynamic_structure": _digitization(db, id)["summary"]})
    else:
        metadata = None
        if action == "reject":
            metadata = {"reason_category": category, "officer_note": note or None, "actor_role": "OFFICER"}
            # Exact duplicate resolution remains an officer decision. Only a
            # confirmed Duplicate Submission rejection can notify the owner of
            # a different, already verified source record.
            if category == "Duplicate Submission" and doc.duplicate_of_id:
                matched_submission = db.query(models.Submission).filter(
                    models.Submission.document_id == doc.duplicate_of_id
                ).order_by(models.Submission.submitted_at.desc(), models.Submission.id.desc()).first()
                matched_record = None
                if matched_submission:
                    matched_record = db.query(models.VerifiedRecord).filter(
                        models.VerifiedRecord.submission_id == matched_submission.id
                    ).first()
                if matched_record and matched_submission and matched_submission.user_id != submission.user_id:
                    exists = db.query(models.UserNotification).filter(
                        models.UserNotification.user_id == matched_submission.user_id,
                        models.UserNotification.type == "EXACT_DUPLICATE_NOTICE",
                        models.UserNotification.document_id == doc.duplicate_of_id,
                        models.UserNotification.record_id == matched_record.id,
                    ).first()
                    if not exists:
                        db.add(models.UserNotification(
                            user_id=matched_submission.user_id, type="EXACT_DUPLICATE_NOTICE", title="Record Notice",
                            message=f"A new submission exactly matched one of your verified land-record documents. Record: {matched_record.record_id}. The new submission was reviewed by an officer. No changes have been made to your verified record.",
                            document_id=doc.duplicate_of_id, record_id=matched_record.id,
                        ))
        db.add(models.AuditLog(document_id=id, user_id=officer_id, submission_id=submission.id,
            action="NEEDS_REVIEW" if action == "mark-review" else "REJECTED", metadata_json=_json(metadata) if metadata else None))
    db.commit()
    return {"message": f"Document {action}d successfully"}


@router.get("/audit")
def get_audit_logs(db: Session = Depends(get_db)):
    return db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).all()
