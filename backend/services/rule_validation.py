"""Conservative, explainable checks for the current reviewed Khatauni record."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from services.cross_record_validation import build_snapshot, normalize_value


SIGNIFICANT_PARCEL_KEYS = (
    "holder_name", "guardian_name", "share", "area", "land_type", "revenue", "land_category",
)
IDENTIFIER_PATTERN = re.compile(r"^\d+(?:[./-]\d+)*$")
AREA_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")


def _result(rule_id: str, name: str, status: str, *, scope: str = "record", **details: Any) -> dict[str, Any]:
    return {"rule_id": rule_id, "name": name, "status": status, "scope": scope, **details}


def _meaningful(row: dict[str, str]) -> bool:
    return any(normalize_value(row.get(key)) for key in SIGNIFICANT_PARCEL_KEYS)


def _identifier(value: str) -> str:
    return re.sub(r"\s+", "", normalize_value(value))


def _identifier_is_valid(value: str) -> bool:
    return bool(IDENTIFIER_PATTERN.fullmatch(_identifier(value)))


def validate_rule_based(db: Session, document_id: int) -> dict[str, Any]:
    """Evaluate deterministic advisory rules without changing any record state."""

    snapshot = build_snapshot(db, document_id)
    headers = snapshot["headers"]
    meaningful_rows = [row for row in snapshot["parcels"] if _meaningful(row)]
    results: list[dict[str, Any]] = []

    district = headers.get("district", "")
    village = headers.get("village_name") or headers.get("revenue_village") or ""
    missing_location = []
    if not normalize_value(district):
        missing_location.append("district")
    if not normalize_value(village):
        missing_location.append("village_name or revenue_village")
    results.append(_result(
        "RV-01", "LOCATION_IDENTIFIERS", "REVIEW" if missing_location else "PASS",
        field="location", value={"district": district, "village": village},
        message=(f"Location context is missing: {', '.join(missing_location)}." if missing_location else "District and village context are present."),
    ))

    khata = headers.get("khata_number", "")
    results.append(_result(
        "RV-02", "KHATA_NUMBER_REQUIRED", "REVIEW" if not normalize_value(khata) else "PASS",
        field="khata_number", value=khata,
        message="Khata number is required for officer review." if not normalize_value(khata) else "Khata number is present.",
    ))

    missing_plot_rows = [
        (index, row) for index, row in enumerate(meaningful_rows)
        if not normalize_value(row.get("plot_number"))
    ]
    if missing_plot_rows:
        for row_index, row in missing_plot_rows:
            results.append(_result(
                "RV-03", "PLOT_NUMBER_REQUIRED", "REVIEW", scope="parcel", row_index=row_index,
                field="plot_number", value=row.get("plot_number", ""),
                message="A populated parcel row should include a plot number.",
            ))
    else:
        results.append(_result(
            "RV-03", "PLOT_NUMBER_REQUIRED", "PASS" if meaningful_rows else "NOT_APPLICABLE", scope="parcel",
            message="Meaningful parcel rows include plot numbers." if meaningful_rows else "No populated parcel rows to check.",
        ))

    areas = [(index, row) for index, row in enumerate(meaningful_rows) if normalize_value(row.get("area"))]
    if not areas:
        results.append(_result("RV-04", "AREA_VALIDITY", "NOT_APPLICABLE", scope="parcel", field="area", message="No populated area values to check."))
    else:
        for row_index, row in areas:
            value = row.get("area", "")
            normalized = normalize_value(value)
            valid = bool(AREA_PATTERN.fullmatch(normalized)) and float(normalized) > 0
            results.append(_result(
                "RV-04", "AREA_VALIDITY", "PASS" if valid else "REVIEW", scope="parcel", row_index=row_index,
                plot_number=row.get("plot_number", ""), field="area", value=value,
                message="Area is a positive numeric value." if valid else "Area should be a positive numeric value.",
            ))

    plots = [(_identifier(row.get("plot_number", "")), index, row) for index, row in enumerate(meaningful_rows) if _identifier(row.get("plot_number", ""))]
    repeated = {plot for plot, count in Counter(plot for plot, _, _ in plots).items() if count > 1}
    if repeated:
        for plot in sorted(repeated):
            results.append(_result(
                "RV-05", "DUPLICATE_PLOT_WITHIN_CURRENT_RECORD", "REVIEW", scope="parcel", plot_number=plot,
                message="The same plot number appears in more than one populated parcel row; officer review is required.",
            ))
    else:
        results.append(_result(
            "RV-05", "DUPLICATE_PLOT_WITHIN_CURRENT_RECORD", "PASS" if plots else "NOT_APPLICABLE", scope="parcel",
            message="No repeated populated plot numbers were found." if plots else "No populated plot numbers to compare.",
        ))

    identifiers = [("khata_number", None, khata)] if normalize_value(khata) else []
    identifiers.extend(("plot_number", index, row.get("plot_number", "")) for index, row in enumerate(meaningful_rows) if normalize_value(row.get("plot_number")))
    if not identifiers:
        results.append(_result("RV-06", "NUMERIC_IDENTIFIER_FORMAT", "NOT_APPLICABLE", message="No populated numeric-like identifiers to check."))
    else:
        for field, row_index, value in identifiers:
            valid = _identifier_is_valid(value)
            results.append(_result(
                "RV-06", "NUMERIC_IDENTIFIER_FORMAT", "PASS" if valid else "REVIEW",
                scope="parcel" if field == "plot_number" else "record", row_index=row_index,
                field=field, value=value,
                message="Numeric-like identifier format is acceptable." if valid else "Identifier contains unsupported characters; review the OCR value.",
            ))

    counts = Counter(result["status"] for result in results)
    has_data = bool(headers or meaningful_rows)
    status = "INSUFFICIENT_DATA" if not has_data else "REVIEW_REQUIRED" if counts["REVIEW"] else "PASS"
    message = (
        "No reviewed structured values are available for rule validation." if status == "INSUFFICIENT_DATA"
        else "One or more deterministic validation rules require officer review." if status == "REVIEW_REQUIRED"
        else "Reviewed values passed the available deterministic validation rules."
    )
    return {
        "status": status, "message": message, "document_id": document_id,
        "summary": {"passed": counts["PASS"], "review": counts["REVIEW"], "not_applicable": counts["NOT_APPLICABLE"]},
        "rules": results,
    }
