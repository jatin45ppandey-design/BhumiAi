"""Evaluate OCR candidates only against explicitly human-verified truth.

The manifest contains no document images or credentials. It records verified
field truth and the candidate outputs captured from extraction evidence.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any


ENGINES = ("tesseract", "local_htr", "hybrid")
CRITICAL_KEYS = {
    "khata_number", "gata_number", "khasra_number", "total_area",
    "holder_share", "share_area", "land_revenue",
}


def _normalized(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def _ratio(matches: int, total: int) -> float | None:
    return round(matches / total, 4) if total else None


def evaluate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    documents = [
        document for document in manifest.get("documents", [])
        if document.get("human_verified") is True
    ]
    fields = [
        field for document in documents for field in document.get("fields", [])
        if field.get("truth") not in (None, "")
    ]
    if not fields:
        return {
            "status": "NO_VERIFIED_GROUND_TRUTH",
            "verified_documents": len(documents),
            "verified_fields": 0,
            "metrics": None,
        }

    metrics = {}
    for engine in ENGINES:
        exact = critical_exact = holder_exact = numeric_exact = unresolved = 0
        critical_total = holder_total = numeric_total = character_errors = character_total = 0
        for field in fields:
            truth = _normalized(field["truth"])
            prediction = _normalized((field.get("predictions") or {}).get(engine))
            matched = prediction == truth
            exact += matched
            unresolved += not bool(prediction)
            character_errors += _edit_distance(prediction, truth)
            character_total += len(truth)
            key = field.get("key")
            kind = field.get("kind")
            if key in CRITICAL_KEYS:
                critical_total += 1
                critical_exact += matched
            if key == "holder_name" or kind == "holder":
                holder_total += 1
                holder_exact += matched
            if kind == "numeric" or key in CRITICAL_KEYS:
                numeric_total += 1
                numeric_exact += matched
        metrics[engine] = {
            "field_exact_match": _ratio(exact, len(fields)),
            "critical_field_exact_match": _ratio(critical_exact, critical_total),
            "holder_name_exact_match": _ratio(holder_exact, holder_total),
            "numeric_field_exact_match": _ratio(numeric_exact, numeric_total),
            "character_error_rate": round(character_errors / character_total, 4) if character_total else None,
            "unresolved_field_rate": _ratio(unresolved, len(fields)),
            "evaluated_fields": len(fields),
        }

    row_documents = [
        document for document in documents
        if document.get("truth_row_count") is not None
        and document.get("hybrid_row_count") is not None
    ]
    metrics["hybrid"]["table_row_count_exact_match"] = _ratio(
        sum(document["truth_row_count"] == document["hybrid_row_count"] for document in row_documents),
        len(row_documents),
    )
    metrics["hybrid"]["evaluated_row_documents"] = len(row_documents)
    return {
        "status": "READY",
        "verified_documents": len(documents),
        "verified_fields": len(fields),
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate verified Khatauni OCR truth")
    parser.add_argument(
        "manifest", nargs="?", default=str(Path(__file__).with_name("ground_truth.example.json")),
    )
    args = parser.parse_args()
    with Path(args.manifest).open(encoding="utf-8") as handle:
        result = evaluate_manifest(json.load(handle))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
