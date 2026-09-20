"""Verified-record search and read views.

The original demo stored a small, fixed summary on ``VerifiedRecord``. That
summary is retained for backwards compatibility, but a newly digitized record
can also contain document-specific fields and tables. This router discovers
those additive models at runtime, so legacy databases keep serving records
while a migrated database exposes the richer structure.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, inspect as sa_inspect, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
import models


router = APIRouter()


_RECORD_COLUMNS = (
    "id",
    "record_id",
    "submission_id",
    "owner_name",
    "father_guardian_name",
    "khasra_number",
    "khata_number",
    "area",
    "village",
    "tehsil",
    "district",
    "state",
    "verification_status",
    "verified_by",
    "verified_at",
)


def _model_if_ready(db: Session, model_name: str):
    """Return an additive model only after its physical table exists."""

    model = getattr(models, model_name, None)
    table = getattr(model, "__table__", None) if model is not None else None
    if table is None:
        return None
    try:
        return model if sa_inspect(db.get_bind()).has_table(table.name) else None
    except SQLAlchemyError:
        return None


def _without_deleted(query, model):
    """Respect optional soft deletion without requiring it on legacy tables."""

    is_deleted = getattr(model, "is_deleted", None)
    if is_deleted is not None:
        return query.filter(or_(is_deleted.is_(None), is_deleted.is_(False)))
    return query


def _json_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _list_value(value: Any) -> list[Any]:
    value = _json_value(value, [])
    return value if isinstance(value, list) else []


def _display_value(item: Any, include_raw: bool = False) -> Optional[str]:
    """Use an officer/final correction when present, otherwise real OCR text."""

    names = ["final_value", "officer_value", "ai_value"]
    if include_raw:
        names.append("raw_ocr_value")
    for name in names:
        value = getattr(item, name, None)
        if value not in (None, ""):
            return value
    return None


def _item_payload(item: Any, *, cell: bool = False) -> dict[str, Any]:
    payload = {
        "id": getattr(item, "id", None),
        "field_id": getattr(item, "field_id", getattr(item, "id", None)) if not cell else None,
        "cell_id": getattr(item, "cell_id", getattr(item, "id", None)) if cell else None,
        "original_label": getattr(item, "original_label", None),
        "normalized_label": getattr(item, "normalized_label", None),
        "header_label": getattr(item, "header_label", None),
        "item_type": getattr(item, "item_type", None),
        "row_index": getattr(item, "row_index", None),
        "column_index": getattr(item, "column_index", None),
        "raw_ocr_value": getattr(item, "raw_ocr_value", None),
        "ai_value": getattr(item, "ai_value", None),
        "ai_confidence": getattr(item, "ai_confidence", None),
        "confidence_source": getattr(item, "confidence_source", None),
        "officer_value": getattr(item, "officer_value", None),
        "final_value": getattr(item, "final_value", None),
        "display_value": _display_value(item, include_raw=cell),
        "bounding_box": _json_value(getattr(item, "bounding_box", None)),
        "source_token_ids": _list_value(getattr(item, "source_token_ids", None)),
        "edited": bool(getattr(item, "edited", False)),
        "edited_by": getattr(item, "edited_by", None),
        "edited_at": getattr(item, "edited_at", None),
    }
    # Do not make an absent label look semantic. The frontend can explicitly
    # render "Unknown Column N" for an unreadable table header.
    if not cell:
        payload.pop("header_label", None)
        payload.pop("cell_id", None)
    return payload


def _header_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("label", "header_label", "value", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _serialize_table(table: Any, cells: list[Any]) -> dict[str, Any]:
    detected_headers = _list_value(getattr(table, "detected_headers", None))
    officer_headers = _list_value(getattr(table, "officer_headers", None))
    final_headers = _list_value(getattr(table, "final_headers", None))
    header_by_column = {
        index: _header_text(header)
        for index, header in enumerate(detected_headers)
        if _header_text(header)
    }
    # Preserve the source headers while letting an officer's saved correction
    # become the header displayed on the permanent, verified representation.
    for corrections in (officer_headers, final_headers):
        for index, header in enumerate(corrections):
            label = _header_text(header)
            if label:
                header_by_column[index] = label
    for cell in cells:
        column_index = getattr(cell, "column_index", None)
        header_label = getattr(cell, "header_label", None)
        if column_index is not None and header_label and str(header_label).strip():
            header_by_column.setdefault(column_index, str(header_label).strip())

    observed_columns = [
        getattr(cell, "column_index", None)
        for cell in cells
        if isinstance(getattr(cell, "column_index", None), int)
    ]
    stated_column_count = getattr(table, "column_count", None) or 0
    column_count = max(
        len(detected_headers),
        stated_column_count,
        (max(observed_columns) + 1) if observed_columns else 0,
    )
    headers = [
        {
            "column_index": index,
            "label": header_by_column.get(index) or f"Unknown Column {index + 1}",
            "detected": bool(header_by_column.get(index)),
        }
        for index in range(column_count)
    ]

    rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in sorted(
        cells,
        key=lambda row: (
            getattr(row, "row_index", -1) if getattr(row, "row_index", None) is not None else -1,
            getattr(row, "column_index", -1) if getattr(row, "column_index", None) is not None else -1,
            getattr(row, "id", 0) or 0,
        ),
    ):
        row_index = getattr(cell, "row_index", None)
        if row_index is None:
            # The detector knew this cell exists but not its row. Keep it
            # visible without inventing a position.
            row_index = -1
        rows[row_index].append(_item_payload(cell, cell=True))

    return {
        "id": getattr(table, "id", None),
        "table_id": getattr(table, "table_id", getattr(table, "id", None)),
        "table_index": getattr(table, "table_index", None),
        "original_label": getattr(table, "original_label", None),
        "normalized_label": getattr(table, "normalized_label", None),
        "detected_headers": detected_headers,
        "officer_headers": officer_headers,
        "final_headers": final_headers,
        "headers": headers,
        "row_count": getattr(table, "row_count", None),
        "column_count": getattr(table, "column_count", None),
        "bounding_box": _json_value(getattr(table, "bounding_box", None)),
        "ai_confidence": getattr(table, "ai_confidence", None),
        "confidence_source": getattr(table, "confidence_source", None),
        "edited": bool(getattr(table, "edited", False)),
        "edited_by": getattr(table, "edited_by", None),
        "edited_at": getattr(table, "edited_at", None),
        "cells": [_item_payload(cell, cell=True) for cell in cells],
        "rows": [
            {"row_index": row_index, "cells": row_cells}
            for row_index, row_cells in sorted(rows.items(), key=lambda pair: pair[0])
        ],
    }


def _latest_ocr_result_id(db: Session, document_id: int) -> Optional[int]:
    """Resolve the OCR generation that should define the current record view."""

    try:
        return (
            db.query(models.OCRResult.id)
            .filter(models.OCRResult.document_id == document_id)
            .order_by(models.OCRResult.id.desc())
            .limit(1)
            .scalar()
        )
    except SQLAlchemyError:
        return None


def _for_current_ocr_or_manual(query, model, ocr_result_id: Optional[int]):
    """Keep the newest OCR generation plus officer/manual (NULL) additions."""

    source_ocr = getattr(model, "ocr_result_id", None)
    if source_ocr is None:
        return query
    if ocr_result_id is None:
        return query.filter(source_ocr.is_(None))
    return query.filter(or_(source_ocr == ocr_result_id, source_ocr.is_(None)))


def _dynamic_digitization(
    db: Session,
    document_id: Optional[int],
    ocr_result_id: Optional[int] = None,
) -> dict[str, Any]:
    """Load current OCR content and manual additions linked to a document.

    Re-running OCR creates a new extraction generation. Showing all generations
    in a permanent record would duplicate stale fields and tables, so this view
    is scoped to the latest OCR result and rows explicitly created without an
    OCR result (manual officer digitization).
    """

    empty = {
        "available": False,
        "ocr_result_id": None,
        "fields": [],
        "tables": [],
        "summary": {
            "fields_detected": 0,
            "tables_detected": 0,
            "rows_digitized": 0,
            "columns_detected": 0,
            "cells_digitized": 0,
        },
    }
    if document_id is None:
        return empty

    latest_ocr_id = ocr_result_id if ocr_result_id is not None else _latest_ocr_result_id(db, document_id)

    item_model = _model_if_ready(db, "DynamicExtractedItem")
    table_model = _model_if_ready(db, "DynamicExtractedTable")
    cell_model = _model_if_ready(db, "DynamicExtractedCell")
    if not any((item_model, table_model, cell_model)):
        return empty

    fields: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    try:
        if item_model is not None:
            items_query = _without_deleted(db.query(item_model), item_model).filter(
                item_model.document_id == document_id
            )
            items_query = _for_current_ocr_or_manual(items_query, item_model, latest_ocr_id)
            for item in items_query.order_by(item_model.display_order, item_model.id).all():
                fields.append(_item_payload(item))

        if table_model is not None:
            tables_query = _without_deleted(db.query(table_model), table_model).filter(
                table_model.document_id == document_id
            )
            tables_query = _for_current_ocr_or_manual(tables_query, table_model, latest_ocr_id)
            for table in tables_query.order_by(table_model.table_index, table_model.id).all():
                table_cells: list[Any] = []
                if cell_model is not None:
                    cells_query = _without_deleted(db.query(cell_model), cell_model).filter(
                        cell_model.table_id == table.id
                    )
                    cells_query = _for_current_ocr_or_manual(cells_query, cell_model, latest_ocr_id)
                    table_cells = cells_query.order_by(
                        cell_model.row_index, cell_model.column_index, cell_model.id
                    ).all()
                tables.append(_serialize_table(table, table_cells))
    except SQLAlchemyError:
        # New ORM code can be deployed before a local migration completes. Do
        # not turn a pre-existing verified record into a server error then.
        return empty

    observed_rows = {
        (table["id"], row["row_index"])
        for table in tables
        for row in table["rows"]
        if row["row_index"] is not None and row["row_index"] >= 0
    }
    observed_columns = sum(len(table["headers"]) for table in tables)
    cell_count = sum(len(table["cells"]) for table in tables)
    detected_fields = [field for field in fields if str(field.get("raw_ocr_value") or field.get("ai_value") or "").strip()]
    ocr_cells = [cell for table in tables for cell in table["cells"] if str(cell.get("raw_ocr_value") or cell.get("ai_value") or "").strip()]
    return {
        "available": True,
        "ocr_result_id": latest_ocr_id,
        "fields": fields,
        "tables": tables,
        "summary": {
            "fields_detected": len(detected_fields),
            "header_fields_detected": len(detected_fields),
            "header_fields_total": len(fields),
            "tables_detected": len(tables),
            "rows_digitized": len(observed_rows),
            "columns_detected": observed_columns,
            "cells_digitized": cell_count,
            "ocr_cells_populated": len(ocr_cells),
        },
    }


def _matching_document_ids(db: Session, search: str) -> set[int]:
    """Find documents whose actual dynamic labels, values, or cells match."""

    pattern = f"%{search}%"
    matches: set[int] = set()

    def collect(model_name: str, attributes: tuple[str, ...]):
        model = _model_if_ready(db, model_name)
        if model is None:
            return
        conditions = []
        for name in attributes:
            column = getattr(model, name, None)
            if column is not None:
                conditions.append(cast(column, String).ilike(pattern))
        if not conditions:
            return
        try:
            query = _without_deleted(db.query(model.document_id), model)
            rows = query.filter(or_(*conditions)).distinct().all()
            matches.update(document_id for (document_id,) in rows if document_id is not None)
        except SQLAlchemyError:
            return

    collect(
        "DynamicExtractedItem",
        (
            "original_label",
            "normalized_label",
            "raw_ocr_value",
            "ai_value",
            "officer_value",
            "final_value",
        ),
    )
    collect(
        "DynamicExtractedTable",
        (
            "original_label",
            "normalized_label",
            "detected_headers",
            "officer_headers",
            "final_headers",
        ),
    )
    collect(
        "DynamicExtractedCell",
        (
            "header_label",
            "raw_ocr_value",
            "ai_value",
            "officer_value",
            "final_value",
        ),
    )
    collect(
        "DynamicDigitizationAudit",
        ("action", "entity_type", "before_json", "after_json", "metadata_json"),
    )

    # Existing fixed extractions remain searchable while older permanent
    # records are kept intact.
    try:
        legacy_conditions = [
            cast(models.ExtractedField.field_name, String).ilike(pattern),
            cast(models.ExtractedField.ai_value, String).ilike(pattern),
            cast(models.ExtractedField.officer_value, String).ilike(pattern),
            cast(models.ExtractedField.final_value, String).ilike(pattern),
        ]
        rows = (
            db.query(models.OCRResult.document_id)
            .join(models.ExtractedField)
            .filter(or_(*legacy_conditions))
            .distinct()
            .all()
        )
        matches.update(document_id for (document_id,) in rows if document_id is not None)
    except SQLAlchemyError:
        pass
    try:
        rows = (
            db.query(models.AuditLog.document_id)
            .filter(
                or_(
                    cast(models.AuditLog.action, String).ilike(pattern),
                    cast(models.AuditLog.metadata_json, String).ilike(pattern),
                )
            )
            .distinct()
            .all()
        )
        matches.update(document_id for (document_id,) in rows if document_id is not None)
    except SQLAlchemyError:
        pass
    return matches


def _digitization_audit(db: Session, document_id: Optional[int]) -> list[dict[str, Any]]:
    """Return append-only dynamic corrections for the permanent record view."""

    if document_id is None:
        return []
    audit_model = _model_if_ready(db, "DynamicDigitizationAudit")
    if audit_model is None:
        return []
    try:
        audits = (
            db.query(audit_model)
            .filter(audit_model.document_id == document_id)
            .order_by(audit_model.created_at.desc(), audit_model.id.desc())
            .all()
        )
    except SQLAlchemyError:
        return []
    return [
        {
            "id": getattr(audit, "id", None),
            "audit_id": getattr(audit, "audit_id", getattr(audit, "id", None)),
            "timestamp": getattr(audit, "created_at", None),
            "action": getattr(audit, "action", None),
            "entity_type": getattr(audit, "entity_type", None),
            "entity_id": getattr(audit, "entity_id", None),
            "item_id": getattr(audit, "item_id", None),
            "table_id": getattr(audit, "table_id", None),
            "cell_id": getattr(audit, "cell_id", None),
            "actor_id": getattr(audit, "actor_id", None),
            "before": _json_value(getattr(audit, "before_json", None)),
            "after": _json_value(getattr(audit, "after_json", None)),
            "metadata": _json_value(getattr(audit, "metadata_json", None)),
        }
        for audit in audits
    ]


def _record_payload(record: Any, digitization: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload = {column: getattr(record, column, None) for column in _RECORD_COLUMNS}
    submission = getattr(record, "submission", None)
    document = getattr(submission, "document", None) if submission is not None else None
    payload["document_name"] = getattr(document, "original_filename", None)
    payload["document_type"] = getattr(document, "document_type", None)
    if digitization is not None:
        payload["digitization_summary"] = digitization["summary"]
    return payload


@router.get("/")
def get_verified_records(
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Search permanent records across metadata and document-specific content."""

    query = db.query(models.VerifiedRecord)
    term = (search or "").strip()
    if term:
        pattern = f"%{term}%"
        document_matches = _matching_document_ids(db, term)
        metadata_match = models.VerifiedRecord.submission.has(
            models.Submission.document.has(
                or_(
                    models.Document.original_filename.ilike(pattern),
                    models.Document.document_type.ilike(pattern),
                    models.Document.state.ilike(pattern),
                    models.Document.district.ilike(pattern),
                    models.Document.tehsil.ilike(pattern),
                    models.Document.village.ilike(pattern),
                )
            )
        )
        conditions = [
            cast(models.VerifiedRecord.id, String).ilike(pattern),
            models.VerifiedRecord.record_id.ilike(pattern),
            models.VerifiedRecord.owner_name.ilike(pattern),
            models.VerifiedRecord.father_guardian_name.ilike(pattern),
            models.VerifiedRecord.khasra_number.ilike(pattern),
            models.VerifiedRecord.khata_number.ilike(pattern),
            models.VerifiedRecord.area.ilike(pattern),
            models.VerifiedRecord.village.ilike(pattern),
            models.VerifiedRecord.tehsil.ilike(pattern),
            models.VerifiedRecord.district.ilike(pattern),
            models.VerifiedRecord.state.ilike(pattern),
            metadata_match,
        ]
        if document_matches:
            conditions.append(
                models.VerifiedRecord.submission.has(
                    models.Submission.document_id.in_(document_matches)
                )
            )
        query = query.filter(or_(*conditions))

    records = query.order_by(models.VerifiedRecord.verified_at.desc(), models.VerifiedRecord.id.desc()).all()
    return [
        _record_payload(
            record,
            _dynamic_digitization(
                db,
                getattr(getattr(record, "submission", None), "document_id", None),
            ),
        )
        for record in records
    ]


@router.get("/{id}")
def get_verified_record_detail(id: int, db: Session = Depends(get_db)):
    record = db.query(models.VerifiedRecord).filter(models.VerifiedRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    submission = getattr(record, "submission", None)
    document = getattr(submission, "document", None) if submission is not None else None
    document_id = getattr(document, "id", None)
    ocr = None
    if document_id is not None:
        ocr = (
            db.query(models.OCRResult)
            .filter(models.OCRResult.document_id == document_id)
            .order_by(models.OCRResult.id.desc())
            .first()
        )
    legacy_fields = getattr(ocr, "extracted_fields", []) if ocr is not None else []
    audit_logs = []
    if document_id is not None:
        audit_logs = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.document_id == document_id)
            .order_by(models.AuditLog.timestamp.desc())
            .all()
        )

    digitization = _dynamic_digitization(db, document_id, getattr(ocr, "id", None))
    return {
        "record": _record_payload(record),
        "document": {
            "id": document_id,
            "original": getattr(document, "file_path", None),
            "enhanced": getattr(ocr, "processed_image_path", None) if ocr else None,
            "original_filename": getattr(document, "original_filename", None),
            "document_type": getattr(document, "document_type", None),
            "state": getattr(document, "state", None),
            "district": getattr(document, "district", None),
            "tehsil": getattr(document, "tehsil", None),
            "village": getattr(document, "village", None),
        },
        "ocr": {
            "raw_text": getattr(ocr, "raw_text", None) if ocr else None,
            "engine": getattr(ocr, "engine", None) if ocr else None,
            "script": getattr(ocr, "script", None) if ocr else None,
            "languages": getattr(ocr, "languages", None) if ocr else None,
            "overall_confidence": getattr(ocr, "overall_confidence", None) if ocr else None,
            "fields": [
                {
                    "id": field.id,
                    "name": field.field_name,
                    "ai_value": field.ai_value,
                    "ai_confidence": field.ai_confidence,
                    "confidence_source": getattr(field, "confidence_source", None),
                    "officer_value": field.officer_value,
                    "final_value": getattr(field, "final_value", None),
                    "edited": field.edited,
                }
                for field in legacy_fields
            ],
        },
        "digitized": digitization,
        "digitization_audit": _digitization_audit(db, document_id),
        "audit_trail": [
            {
                "timestamp": audit.timestamp,
                "action": audit.action,
                "metadata": audit.metadata_json,
                "user_id": audit.user_id,
            }
            for audit in audit_logs
        ],
    }
