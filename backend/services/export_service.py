"""Canonical, database-only exports for verified records.

The builder deliberately reads persisted values only. It does not import or
invoke preprocessing, OCR, HTR, extraction, or confidence code.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models


EXPORT_SCHEMA = "bhumiai_verified_record_v1"
EXPORT_VERSION = 1


def export_filename(record_id: Any, extension: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(record_id or "record")).strip("._") or "record"
    return f"BhumiAI_Khatauni_{safe}.{extension}"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return value


def _timestamp(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _persisted_value(item: Any) -> Any:
    """Select the authoritative persisted value, never raw OCR text."""

    for name in ("final_value", "officer_value", "ai_value"):
        value = getattr(item, name, None)
        if value not in (None, ""):
            return value
    return None


def _header_label(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("label", "header_label", "value", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _headers(table: Any) -> list[dict[str, Any]]:
    source: list[Any] = []
    for name in ("final_headers", "officer_headers", "detected_headers"):
        candidate = getattr(table, name, None)
        if isinstance(candidate, list) and candidate:
            source = candidate
            break
    count = max(len(source), int(getattr(table, "column_count", None) or 0))
    return [{"column_index": index, "label": _header_label(source[index]) if index < len(source) else None}
            for index in range(count)]


def _legacy_fields(db: Session, ocr_result_id: int | None) -> list[dict[str, Any]]:
    if ocr_result_id is None:
        return []
    try:
        rows = db.query(models.ExtractedField).filter(
            models.ExtractedField.ocr_result_id == ocr_result_id
        ).order_by(models.ExtractedField.id).all()
    except SQLAlchemyError:
        return []
    return [
        {
            "field_id": row.id,
            "field_name": row.field_name,
            "value": _persisted_value(row),
            "confidence": row.ai_confidence,
            "confidence_source": row.confidence_source,
        }
        for row in rows
    ]


def _dynamic_data(db: Session, document_id: int | None, ocr_result_id: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if document_id is None:
        return [], []
    try:
        current_item_source = (models.DynamicExtractedItem.ocr_result_id == ocr_result_id) if ocr_result_id is not None else models.DynamicExtractedItem.ocr_result_id.is_(None)
        items = db.query(models.DynamicExtractedItem).filter(
            models.DynamicExtractedItem.document_id == document_id,
            models.DynamicExtractedItem.is_deleted.is_(False),
            or_(current_item_source, models.DynamicExtractedItem.ocr_result_id.is_(None)),
        ).order_by(models.DynamicExtractedItem.display_order, models.DynamicExtractedItem.id).all()
        current_table_source = (models.DynamicExtractedTable.ocr_result_id == ocr_result_id) if ocr_result_id is not None else models.DynamicExtractedTable.ocr_result_id.is_(None)
        tables = db.query(models.DynamicExtractedTable).filter(
            models.DynamicExtractedTable.document_id == document_id,
            models.DynamicExtractedTable.is_deleted.is_(False),
            or_(current_table_source, models.DynamicExtractedTable.ocr_result_id.is_(None)),
        ).order_by(models.DynamicExtractedTable.table_index, models.DynamicExtractedTable.id).all()
    except SQLAlchemyError:
        return [], []

    fields = [
        {
            "field_id": item.id,
            "label": item.original_label,
            "normalized_label": item.normalized_label,
            "item_type": item.item_type,
            "display_order": item.display_order,
            "value": _persisted_value(item),
            "confidence": item.ai_confidence,
            "confidence_source": item.confidence_source,
        }
        for item in items
    ]
    exported_tables: list[dict[str, Any]] = []
    for table in tables:
        try:
            current_cell_source = (models.DynamicExtractedCell.ocr_result_id == ocr_result_id) if ocr_result_id is not None else models.DynamicExtractedCell.ocr_result_id.is_(None)
            cells = db.query(models.DynamicExtractedCell).filter(
                models.DynamicExtractedCell.table_id == table.id,
                models.DynamicExtractedCell.document_id == document_id,
                models.DynamicExtractedCell.is_deleted.is_(False),
                or_(current_cell_source, models.DynamicExtractedCell.ocr_result_id.is_(None)),
            ).order_by(models.DynamicExtractedCell.row_index, models.DynamicExtractedCell.column_index,
                       models.DynamicExtractedCell.id).all()
        except SQLAlchemyError:
            cells = []
        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in cells:
            rows.setdefault(cell.row_index, []).append({
                "cell_id": cell.id,
                "column_index": cell.column_index,
                "header_label": cell.header_label,
                "value": _persisted_value(cell),
                "confidence": cell.ai_confidence,
                "confidence_source": cell.confidence_source,
            })
        exported_tables.append({
            "table_id": table.id,
            "table_index": table.table_index,
            "label": table.original_label,
            "normalized_label": table.normalized_label,
            "headers": _headers(table),
            "rows": [{"row_index": index, "cells": values} for index, values in sorted(rows.items())],
        })
    return fields, exported_tables


def build_verified_record_export(db: Session, record: models.VerifiedRecord) -> dict[str, Any]:
    """Build the stable export DTO from one already-verified database record."""

    submission = record.submission
    document = submission.document if submission else None
    document_id = document.id if document else None
    latest_ocr_id = None
    if document_id is not None:
        latest_ocr = db.query(models.OCRResult).filter(
            models.OCRResult.document_id == document_id
        ).order_by(models.OCRResult.id.desc()).first()
        latest_ocr_id = latest_ocr.id if latest_ocr else None

    fixed_fields = {
        name: getattr(record, name, None)
        for name in ("owner_name", "father_guardian_name", "khasra_number", "khata_number",
                     "area", "village", "tehsil", "district", "state")
    }
    dynamic_fields, tables = _dynamic_data(db, document_id, latest_ocr_id)
    officer = record.officer
    verified_at: datetime | None = record.verified_at
    return {
        "export_schema": EXPORT_SCHEMA,
        "export_version": EXPORT_VERSION,
        "record_id": record.record_id,
        "status": record.verification_status,
        "document": {
            "id": document_id,
            "submission_id": submission.id if submission else None,
            "document_type": document.document_type if document else None,
            "original_filename": document.original_filename if document else None,
            "uploaded_at": _timestamp(document.uploaded_at) if document else None,
            "state": document.state if document else None,
            "district": document.district if document else None,
            "tehsil": document.tehsil if document else None,
            "village": document.village if document else None,
        },
        "fields": fixed_fields,
        "legacy_extracted_fields": _legacy_fields(db, latest_ocr_id),
        "dynamic_fields": dynamic_fields,
        "tables": tables,
        "verification": {
            "status": record.verification_status,
            "verified_at": _timestamp(verified_at),
            "officer": {
                "name": officer.name if officer else None,
                "officer_id": officer.officer_id if officer else None,
            },
        },
    }
