"""Part 1 structured Khatauni validation and response helpers.

This module never invents land-record values. It only wraps OCR/HTR or officer
values with conservative validation, status, and evidence metadata.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from khatauni_schema import TABLE_COLUMNS


DEVANAGARI_DIGITS = str.maketrans("\u0966\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u096e\u096f", "0123456789")

KHATAUNI_DETAIL_KEYS = {
    "district": "district",
    "tehsil": "tehsil",
    "village_name": "village",
    "revenue_village": "village",
    "village_code": "village_code",
    "crop_year": "fasli_year",
    "khata_number": "khata_number",
    "land_category": "category",
    "category": "category",
    "part_number": "part_number",
}

LAND_DETAIL_KEYS = {
    "plot_number": "gata_number",
    "khasra_number": "khasra_number",
    "holder_name": "holder_name",
    "guardian_name": "relation_name",
    "share": "holder_share",
    "area": "total_area",
    "revenue": "land_revenue",
    "order_remarks": "mutation_details",
}

KHATAUNI_DETAIL_ORDER = [
    "district",
    "tehsil",
    "village",
    "village_code",
    "fasli_year",
    "record_year",
    "khata_number",
    "category",
    "part_number",
]

LAND_DETAIL_ORDER = [
    "gata_number",
    "khasra_number",
    "holder_name",
    "relation_type",
    "relation_name",
    "total_area",
    "holder_share",
    "share_area",
    "land_revenue",
    "mutation_details",
    "order_details",
    "order_date",
]

NUMERIC_KEYS = {
    "khata_number",
    "gata_number",
    "khasra_number",
    "village_code",
    "fasli_year",
    "record_year",
    "total_area",
    "share_area",
    "land_revenue",
}

TEXT_KEYS = {"district", "tehsil", "village", "holder_name", "relation_name", "category"}
SHARE_KEYS = {"holder_share"}
REVIEW_RECOGNITION_WARNINGS = {
    "engine_disagreement", "tesseract_digit_disagreement", "recognition_pass_disagreement",
}
RELATION_MARKERS = (
    "\u092a\u0941\u0924\u094d\u0930\u0940",  # daughter
    "\u092a\u0941\u0924\u094d\u0930",        # son
    "\u092a\u0924\u094d\u0928\u0940",       # wife
    "\u092a\u093f\u0924\u093e",             # father
    "\u092a\u0924\u093f",                    # husband
)


def _canonical_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").translate(DEVANAGARI_DIGITS).strip()


def _value_of(entry: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = entry.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def _status(confidence: float | None, warnings: list[str], value: str | None) -> str:
    """Return deterministic format validation, independent of recognition evidence."""

    if not value:
        return "UNRESOLVED"
    if warnings:
        return "NEEDS_REVIEW"
    return "PASS"


def _evidence_level(confidence: float | None) -> str:
    if confidence is None:
        return "UNAVAILABLE"
    if confidence >= 85:
        return "HIGH"
    if confidence >= 65:
        return "MEDIUM"
    return "LOW"


def validate_candidate(canonical_key: str, value: str | None, confidence: float | None) -> dict[str, Any]:
    """Flag suspicious OCR candidates without replacing their values."""

    raw_value = value if value not in ("", None) else None
    normalized = _canonical_text(raw_value or "") if raw_value else None
    warnings: list[str] = []

    if raw_value is None:
        warnings.append("unresolved")
    elif canonical_key in NUMERIC_KEYS:
        if not re.fullmatch(r"[0-9]+(?:[./ -][0-9]+)*", normalized or ""):
            warnings.append("numeric_pattern_mismatch")
    elif canonical_key in SHARE_KEYS:
        if not re.fullmatch(r"[0-9]+(?:/[0-9]+)?|[0-9]+(?:\.[0-9]+)?|[\u0900-\u097f ]+", normalized or ""):
            warnings.append("share_pattern_mismatch")
    elif canonical_key in TEXT_KEYS:
        letters = re.findall(r"[A-Za-z\u0900-\u097f]", raw_value, flags=re.UNICODE)
        if not letters:
            warnings.append("text_pattern_mismatch")
        latin = re.findall(r"[A-Za-z]", raw_value)
        devanagari = re.findall(r"[\u0900-\u097f]", raw_value)
        if latin and devanagari and canonical_key in {"holder_name", "relation_name", "village", "tehsil", "district"}:
            warnings.append("mixed_script_review")

    return {
        "raw_value": raw_value,
        "normalized_value": normalized,
        "status": _status(confidence, warnings, raw_value),
        "warnings": warnings,
        "confidence": confidence,
        "recognition_evidence_score": confidence,
        "recognition_evidence_level": _evidence_level(confidence),
        "confidence_type": "recognition_evidence_score",
    }


def _add_recognition_warnings(
    validation: dict[str, Any], metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    recognition_warnings: list[str] = []
    for warning in (metadata or {}).get("warnings") or []:
        if warning in REVIEW_RECOGNITION_WARNINGS and warning not in recognition_warnings:
            recognition_warnings.append(warning)
    validation["recognition_warnings"] = recognition_warnings
    validation["review_status"] = "NEEDS_REVIEW" if recognition_warnings else "CLEAR"
    if isinstance(metadata, dict) and metadata.get("confidence_method"):
        validation["confidence_type"] = metadata["confidence_method"]
    return validation


def compact_recognition_evidence(metadata: Any) -> dict[str, Any] | None:
    """Keep review-grade provenance while excluding verbose engine internals."""

    if not isinstance(metadata, dict):
        return None
    keys = (
        "source", "recognizer", "schema_key", "canonical_key", "selected_engine",
        "supporting_engines", "selection_reason", "warnings", "agreements",
        "confidence_method", "layout_certainty", "roi", "source_physical_row_index",
        "source_line_index", "source_line_count",
    )
    compact = {key: metadata[key] for key in keys if metadata.get(key) is not None}
    candidate_keys = (
        "raw_text", "normalized_text", "confidence", "confidence_type", "status",
        "reason", "model_id", "truncated",
    )
    candidates = {}
    for engine, candidate in (metadata.get("candidates") or {}).items():
        if isinstance(candidate, dict):
            compact_candidate = {
                key: candidate.get(key) for key in candidate_keys if candidate.get(key) is not None
            }
            passes = candidate.get("passes")
            if isinstance(passes, list):
                safe_passes = []
                for pass_candidate in passes:
                    if not isinstance(pass_candidate, dict):
                        continue
                    safe_passes.append({
                        key: pass_candidate.get(key)
                        for key in ("variant", "raw_text", "normalized_text", "confidence", "format_valid")
                        if pass_candidate.get(key) is not None
                    })
                if safe_passes:
                    compact_candidate["passes"] = safe_passes
            candidates[engine] = compact_candidate
    if candidates:
        compact["candidates"] = candidates
    if isinstance(metadata.get("confidence_breakdown"), dict):
        compact["confidence_breakdown"] = metadata["confidence_breakdown"]
    validation = metadata.get("validation")
    if isinstance(validation, dict):
        compact["validation"] = validation
    return compact or None


def _evidence(entry: dict[str, Any], value_names: tuple[str, ...], canonical_key: str) -> dict[str, Any]:
    value = _value_of(entry, value_names)
    confidence = entry.get("ocr_confidence", entry.get("ai_confidence"))
    metadata = entry.get("audit_metadata") if isinstance(entry.get("audit_metadata"), dict) else {}
    validation = _add_recognition_warnings(
        validate_candidate(canonical_key, value, confidence), metadata,
    )
    return {
        **validation,
        "source_bbox": entry.get("bounding_box"),
        "source_token_ids": entry.get("source_token_ids") or [],
        "confidence_source": entry.get("confidence_source") or "unavailable",
        "recognition_evidence": compact_recognition_evidence(metadata),
    }


def _holder_relation_parts(value: str | None) -> tuple[str, str, str] | None:
    """Split one holder line only around one explicit, whitespace-bound marker."""

    normalized = re.sub(r"\s+", " ", _canonical_text(value or "")).strip()
    if not normalized:
        return None
    marker_pattern = "|".join(re.escape(marker) for marker in RELATION_MARKERS)
    matches = list(re.finditer(rf"\s+({marker_pattern})\s+", normalized))
    if len(matches) != 1:
        return None
    match = matches[0]
    holder, relation_name = normalized[:match.start()].strip(), normalized[match.end():].strip()
    if not holder or not relation_name:
        return None
    return holder, match.group(1), relation_name


def _derived_relation_evidence(
    source: dict[str, Any], value: str, canonical_key: str, source_raw_value: str,
) -> dict[str, Any]:
    payload = _evidence(source, ("raw_ocr_value", "ai_value"), canonical_key)
    confidence = payload.get("confidence")
    recognition = source.get("audit_metadata") if isinstance(source.get("audit_metadata"), dict) else {}
    validation = _add_recognition_warnings(
        validate_candidate(canonical_key, value, confidence), recognition,
    )
    return {
        **payload,
        **validation,
        "source_raw_value": source_raw_value,
        "derivation": "single_explicit_relation_marker",
    }


def annotate_structure(structure: dict[str, Any]) -> dict[str, Any]:
    """Add validation/status metadata to existing extractor fields and cells."""

    for field in structure.get("header_fields", []):
        canonical = KHATAUNI_DETAIL_KEYS.get(field.get("key"), field.get("key"))
        metadata = field.get("audit_metadata") if isinstance(field.get("audit_metadata"), dict) else {}
        validation = _add_recognition_warnings(
            validate_candidate(canonical, field.get("ocr_value"), field.get("ocr_confidence")),
            metadata,
        )
        field["validation"] = validation
        field["status"] = validation["status"]
        field["audit_metadata"] = {**metadata, "validation": validation, "canonical_key": canonical}

    for row in structure.get("rows", []):
        for cell in row.get("cells", []):
            try:
                schema_key = TABLE_COLUMNS[int(cell.get("column_index", -1))]["key"]
            except (IndexError, TypeError, ValueError):
                schema_key = None
            canonical = LAND_DETAIL_KEYS.get(schema_key or "", schema_key or "unknown")
            metadata = cell.get("audit_metadata") if isinstance(cell.get("audit_metadata"), dict) else {}
            validation = _add_recognition_warnings(
                validate_candidate(canonical, cell.get("raw_ocr_value") or cell.get("ai_value"), cell.get("ai_confidence")),
                metadata,
            )
            cell["validation"] = validation
            cell["status"] = validation["status"]
            cell["audit_metadata"] = {**metadata, "validation": validation, "canonical_key": canonical}
    return structure


def build_digital_khatauni(structure: dict[str, Any]) -> dict[str, Any]:
    """Build the Part 1 A/B structured view from existing OCR structure."""

    fields_by_key = {field.get("key"): field for field in structure.get("header_fields", [])}
    khatauni_details = {}
    for canonical in KHATAUNI_DETAIL_ORDER:
        source = next((field for key, field in fields_by_key.items() if KHATAUNI_DETAIL_KEYS.get(key) == canonical), None)
        khatauni_details[canonical] = _evidence(source, ("ocr_value",), canonical) if source else {
            **validate_candidate(canonical, None, None),
            "source_bbox": None,
            "source_token_ids": [],
            "confidence_source": "unavailable",
            "recognition_evidence": None,
        }

    land_details = []
    for row_index, row in enumerate(structure.get("rows", [])):
        holder_source = None
        row_payload = {
            key: {
                **validate_candidate(key, None, None),
                "source_bbox": None,
                "source_token_ids": [],
                "confidence_source": "unavailable",
                "recognition_evidence": None,
            }
            for key in LAND_DETAIL_ORDER
        }
        for cell in row.get("cells", []):
            try:
                schema_key = TABLE_COLUMNS[int(cell.get("column_index", -1))]["key"]
            except (IndexError, TypeError, ValueError):
                continue
            canonical = LAND_DETAIL_KEYS.get(schema_key)
            if not canonical:
                continue
            row_payload[canonical] = _evidence(cell, ("raw_ocr_value", "ai_value"), canonical)
            if canonical == "holder_name":
                holder_source = cell
        holder_value = row_payload["holder_name"].get("raw_value")
        relation = _holder_relation_parts(holder_value)
        if relation and holder_source:
            holder_name, relation_type, relation_name = relation
            row_payload["holder_name"] = _derived_relation_evidence(
                holder_source, holder_name, "holder_name", holder_value,
            )
            row_payload["relation_type"] = _derived_relation_evidence(
                holder_source, relation_type, "relation_type", holder_value,
            )
            row_payload["relation_name"] = _derived_relation_evidence(
                holder_source, relation_name, "relation_name", holder_value,
            )
        if any(value.get("raw_value") is not None for value in row_payload.values()):
            row_payload["_row_index"] = row_index
            row_payload["_source"] = row.get("source")
            row_payload["_source_physical_row_index"] = row.get("source_physical_row_index")
            row_payload["_source_line_index"] = row.get("source_line_index")
            land_details.append(row_payload)

    return {
        "schema_version": "digital_khatauni_part1_v1",
        "recognition_version": "recognition_evidence_v2",
        "khatauni_details": khatauni_details,
        "land_details": land_details,
        "schema_notes": [
            "Values are source-derived OCR/HTR candidates or officer corrections only.",
            "Relation fields are split only from one explicit marker in a recognized holder line.",
            "Status flags review need; it is not legal verification.",
        ],
    }


def empty_schema_shape() -> dict[str, Any]:
    return {
        "khatauni_details": {key: None for key in KHATAUNI_DETAIL_ORDER},
        "land_details": [{key: None for key in LAND_DETAIL_ORDER}],
    }
