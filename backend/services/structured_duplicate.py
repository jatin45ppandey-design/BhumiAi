"""Conservative structured duplicate detection for reviewed Khatauni records."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

import models
from services.cross_record_validation import _candidate_match, _identity, _plot_numbers, build_snapshot, normalize_value


CRITICAL_FIELDS = ("holder_name", "guardian_name", "share", "area")
OPTIONAL_FIELDS = ("land_type", "revenue", "land_category")
COMPARISON_FIELDS = CRITICAL_FIELDS + OPTIONAL_FIELDS


def _rows_by_plot(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        normalize_value(row.get("plot_number")): row
        for row in snapshot["parcels"]
        if normalize_value(row.get("plot_number"))
    }


def check_structured_duplicate(db: Session, document_id: int) -> dict[str, Any]:
    """Surface possible matches only when identity, plots, and shared values agree."""

    current = build_snapshot(db, document_id)
    identity = _identity(current)
    if not identity["district"] or not identity["village"] or (not identity["khata_number"] and not _plot_numbers(current)):
        return {
            "status": "INSUFFICIENT_DATA", "message": "Reviewed district, village, and khata number or plot number are required for structured duplicate detection.",
            "document_id": document_id, "matches": [], "summary": {"candidate_count": 0, "possible_duplicates": 0},
        }

    verified_records = db.query(models.VerifiedRecord).join(models.Submission).filter(
        models.VerifiedRecord.verification_status == "VERIFIED",
        models.Submission.status == "VERIFIED",
        models.Submission.document_id != document_id,
    ).order_by(models.VerifiedRecord.verified_at.desc(), models.VerifiedRecord.id.desc()).all()
    current_rows = _rows_by_plot(current)
    matches: list[dict[str, Any]] = []
    candidate_count = 0
    for record in verified_records:
        reference_document_id = record.submission.document_id if record.submission else None
        if reference_document_id is None:
            continue
        reference = build_snapshot(db, reference_document_id)
        matched_identity = _candidate_match(current, reference)
        if not matched_identity:
            continue
        candidate_count += 1
        reference_rows = _rows_by_plot(reference)
        matched_plots = sorted(set(current_rows).intersection(reference_rows))
        if not matched_plots:
            continue
        matching_fields: set[str] = set()
        material_differences: list[dict[str, str]] = []
        for plot in matched_plots:
            for field in COMPARISON_FIELDS:
                current_value = current_rows[plot].get(field, "")
                reference_value = reference_rows[plot].get(field, "")
                if not current_value or not reference_value:
                    continue
                if normalize_value(current_value) == normalize_value(reference_value):
                    matching_fields.add(field)
                elif field in CRITICAL_FIELDS:
                    material_differences.append({"plot_number": current_rows[plot].get("plot_number", plot), "field": field, "current_value": current_value, "reference_value": reference_value})
        # A shared critical field is required; names are exact-normalized only and
        # never establish identity by themselves.
        if material_differences or not (matching_fields.intersection(CRITICAL_FIELDS)):
            continue
        matches.append({
            "record_id": record.record_id, "record_db_id": record.id, "document_id": reference_document_id,
            "matched_identity": matched_identity, "matched_plots": matched_plots,
            "matching_fields": sorted(matching_fields), "material_differences": [],
        })
    status = "POSSIBLE_DUPLICATE" if matches else "NO_MATCH"
    return {
        "status": status,
        "message": "A structurally similar verified record was found. Officer review is required." if matches else "No probable structured duplicate was found among verified BhumiAI records.",
        "document_id": document_id, "matches": matches,
        "summary": {"candidate_count": candidate_count, "possible_duplicates": len(matches)},
    }
