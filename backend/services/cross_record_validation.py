"""Deterministic, advisory comparison against BhumiAI's verified-record repository."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models


IDENTITY_KEYS = ("district", "village_name", "revenue_village", "khata_number")
HEADER_COMPARE_KEYS = (
    "district", "tehsil", "revenue_village", "village_name", "village_code",
    "khata_number", "crop_year", "holder_name", "guardian_name",
)
PARCEL_COMPARE_KEYS = (
    "holder_name", "guardian_name", "residence", "share", "area", "land_type",
    "revenue", "land_category",
)
NAME_KEYS = {"holder_name", "guardian_name"}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def normalize_value(value: Any) -> str:
    """Normalize only presentation differences; identifiers still compare exactly."""

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(DEVANAGARI_DIGITS)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*([,;/|:])\s*", r"\1", text)
    return text.casefold()


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


def reviewed_value(entry: Any) -> str:
    """Return the reviewed value without substituting document/upload metadata."""

    for name in ("final_value", "officer_value", "ai_value", "raw_ocr_value"):
        value = getattr(entry, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _schema_key(entry: Any) -> str:
    return str(_metadata(getattr(entry, "audit_metadata_json", None)).get("schema_key") or "").strip()


def _latest_ocr_id(db: Session, document_id: int) -> int | None:
    result = db.query(models.OCRResult.id).filter(
        models.OCRResult.document_id == document_id
    ).order_by(models.OCRResult.id.desc()).first()
    return result[0] if result else None


def build_snapshot(db: Session, document_id: int) -> dict[str, Any]:
    """Build the canonical reviewed header and parcel structure for one document."""

    ocr_id = _latest_ocr_id(db, document_id)
    item_query = db.query(models.DynamicExtractedItem).filter(
        models.DynamicExtractedItem.document_id == document_id,
        models.DynamicExtractedItem.is_deleted.is_(False),
    )
    table_query = db.query(models.DynamicExtractedTable.id).filter(
        models.DynamicExtractedTable.document_id == document_id,
        models.DynamicExtractedTable.is_deleted.is_(False),
    )
    if ocr_id is not None:
        item_query = item_query.filter(or_(models.DynamicExtractedItem.ocr_result_id == ocr_id, models.DynamicExtractedItem.ocr_result_id.is_(None)))
        table_query = table_query.filter(or_(models.DynamicExtractedTable.ocr_result_id == ocr_id, models.DynamicExtractedTable.ocr_result_id.is_(None)))
    headers: dict[str, str] = {}
    for item in item_query.order_by(models.DynamicExtractedItem.display_order, models.DynamicExtractedItem.id).all():
        key, value = _schema_key(item), reviewed_value(item)
        if key and value and key not in headers:
            headers[key] = value
    table_ids = [row[0] for row in table_query.all()]
    rows: dict[tuple[int, int], dict[str, str]] = defaultdict(dict)
    if table_ids:
        cells = db.query(models.DynamicExtractedCell).filter(
            models.DynamicExtractedCell.table_id.in_(table_ids),
            models.DynamicExtractedCell.is_deleted.is_(False),
        ).order_by(models.DynamicExtractedCell.table_id, models.DynamicExtractedCell.row_index, models.DynamicExtractedCell.column_index).all()
        for cell in cells:
            key, value = _schema_key(cell), reviewed_value(cell)
            if key and value:
                rows[(cell.table_id, cell.row_index)].setdefault(key, value)
    return {"document_id": document_id, "headers": headers, "parcels": list(rows.values())}


def _village(snapshot: dict[str, Any]) -> str:
    headers = snapshot["headers"]
    return normalize_value(headers.get("village_name") or headers.get("revenue_village"))


def _identity(snapshot: dict[str, Any]) -> dict[str, str]:
    headers = snapshot["headers"]
    return {
        "district": normalize_value(headers.get("district")),
        "village": _village(snapshot),
        "khata_number": normalize_value(headers.get("khata_number")),
    }


def _plot_numbers(snapshot: dict[str, Any]) -> set[str]:
    return {normalize_value(row.get("plot_number")) for row in snapshot["parcels"] if normalize_value(row.get("plot_number"))}


def _candidate_match(current: dict[str, Any], reference: dict[str, Any]) -> list[str]:
    current_identity, reference_identity = _identity(current), _identity(reference)
    if not current_identity["district"] or not current_identity["village"]:
        return []
    if current_identity["district"] != reference_identity["district"] or current_identity["village"] != reference_identity["village"]:
        return []
    if current_identity["khata_number"]:
        return ["district", "village", "khata_number"] if current_identity["khata_number"] == reference_identity["khata_number"] else []
    if _plot_numbers(current).intersection(_plot_numbers(reference)):
        return ["district", "village", "plot_number"]
    return []


def _difference(scope: str, field: str, current_value: str, reference_value: str, plot_number: str | None = None) -> dict[str, Any]:
    result = {
        "scope": scope,
        "field": field,
        "current_value": current_value,
        "reference_value": reference_value,
        "type": "VALUE_DIFFERENCE",
        "severity": "REVIEW",
    }
    if plot_number:
        result["plot_number"] = plot_number
    return result


def _compare(current: dict[str, Any], reference: dict[str, Any]) -> tuple[int, list[dict[str, Any]], int]:
    consistent, variations, differences = 0, 0, []
    for key in HEADER_COMPARE_KEYS:
        current_value, reference_value = current["headers"].get(key, ""), reference["headers"].get(key, "")
        if not current_value or not reference_value:
            continue
        if normalize_value(current_value) == normalize_value(reference_value):
            consistent += 1
        else:
            differences.append(_difference("header", key, current_value, reference_value))
    reference_rows = {normalize_value(row.get("plot_number")): row for row in reference["parcels"] if normalize_value(row.get("plot_number"))}
    for current_row in current["parcels"]:
        plot = normalize_value(current_row.get("plot_number"))
        reference_row = reference_rows.get(plot)
        if not plot or not reference_row:
            continue
        for key in PARCEL_COMPARE_KEYS:
            current_value, reference_value = current_row.get(key, ""), reference_row.get(key, "")
            if not current_value or not reference_value:
                continue
            if normalize_value(current_value) == normalize_value(reference_value):
                consistent += 1
            else:
                differences.append(_difference("parcel", key, current_value, reference_value, current_row.get("plot_number")))
    return consistent, differences, variations


def validate_cross_record(db: Session, document_id: int) -> dict[str, Any]:
    current = build_snapshot(db, document_id)
    identity = _identity(current)
    if not identity["district"] or not identity["village"] or (not identity["khata_number"] and not _plot_numbers(current)):
        return {"status": "INSUFFICIENT_DATA", "message": "Reviewed district, village, and khata number or plot number are required for cross-record validation.", "current_document_id": document_id, "candidate_count": 0, "references": [], "summary": {"references_checked": 0, "consistent_fields": 0, "differences": 0, "text_variations": 0}}
    verified_records = db.query(models.VerifiedRecord).join(models.Submission).filter(
        models.VerifiedRecord.verification_status == "VERIFIED",
        models.Submission.status == "VERIFIED",
        models.Submission.document_id != document_id,
    ).order_by(models.VerifiedRecord.verified_at.desc(), models.VerifiedRecord.id.desc()).all()
    references, total_consistent, total_differences, total_variations = [], 0, 0, 0
    for record in verified_records:
        reference_document_id = record.submission.document_id if record.submission else None
        if reference_document_id is None:
            continue
        reference = build_snapshot(db, reference_document_id)
        matched_on = _candidate_match(current, reference)
        if not matched_on:
            continue
        consistent, differences, variations = _compare(current, reference)
        references.append({"record_id": record.record_id, "record_db_id": record.id, "document_id": reference_document_id, "matched_on": matched_on, "consistent_count": consistent, "difference_count": len(differences), "differences": differences})
        total_consistent += consistent
        total_differences += len(differences)
        total_variations += variations
    if not references:
        status, message = "NO_REFERENCE", "No matching verified BhumiAI record was found for comparison."
    elif total_differences:
        status, message = "REVIEW_REQUIRED", "Differences were found against an existing verified record. Officer review is required."
    else:
        status, message = "CONSISTENT", "Reviewed values are consistent with the selected verified record reference."
    return {"status": status, "message": message, "current_document_id": document_id, "candidate_count": len(references), "references": references, "summary": {"references_checked": len(references), "consistent_fields": total_consistent, "differences": total_differences, "text_variations": total_variations}}
