"""Khatauni-specific extraction from persisted Tesseract words and boxes."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from digitization import bbox_for, build_lines, confidence_for, detect_table
from khatauni_hybrid import apply_hybrid_recognition
from khatauni_schema import HEADER_FIELDS, TABLE_COLUMNS
from khatauni_structured import annotate_structure, build_digital_khatauni


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = value.replace("।", " ").replace("|", " ")
    return re.sub(r"[^a-z0-9\u0900-\u097f]+", "", value)


def _token_ids(tokens: list[dict[str, Any]]) -> list[int]:
    return [int(token["index"]) for token in tokens if token.get("index") is not None]


def _candidate(label_tokens: list[dict[str, Any]], value_tokens: list[dict[str, Any]]) -> dict[str, Any]:
    value = " ".join(token["text"] for token in value_tokens).strip(" :-|।")
    confidence, source = confidence_for(value_tokens)
    return {
        "value": value,
        "confidence": confidence,
        "confidence_source": source,
        "bounding_box": bbox_for(value_tokens),
        "source_token_ids": _token_ids(value_tokens),
        "label_bounding_box": bbox_for(label_tokens),
    }


def _match_score(text: str, aliases: list[str]) -> float:
    compact = _norm(text)
    if not compact:
        return 0.0
    best = 0.0
    for alias in aliases:
        wanted = _norm(alias)
        if not wanted:
            continue
        if wanted in compact or compact in wanted:
            ratio = min(len(wanted), len(compact)) / max(len(wanted), len(compact))
            best = max(best, 0.82 + 0.18 * ratio)
        else:
            best = max(best, SequenceMatcher(None, compact, wanted).ratio())
    return best


def _split_line(tokens: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for index, token in enumerate(tokens):
        text = token.get("text", "")
        if ":" in text or "：" in text:
            prefix, suffix = re.split(r"[:：]", text, maxsplit=1)
            label_tokens = [dict(row) for row in tokens[:index]]
            value_tokens = [dict(row) for row in tokens[index + 1 :]]
            if prefix.strip():
                item = dict(token); item["text"] = prefix.strip(); label_tokens.append(item)
            if suffix.strip():
                item = dict(token); item["text"] = suffix.strip(); value_tokens.insert(0, item)
            return label_tokens, value_tokens
    return [], []


def _label_candidates(tokens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Match labels only; values are whatever Tesseract read to their right."""
    matches: dict[str, dict[str, Any]] = {}
    schema = [*HEADER_FIELDS, *TABLE_COLUMNS]
    for line in build_lines(tokens):
        ordered = sorted(line["tokens"], key=lambda row: (row.get("bbox") or {}).get("left", 0))
        left, right = _split_line(ordered)
        if not left or not right:
            # OCR sometimes drops the colon. Find the best leading token span,
            # while never fuzzy-matching the value portion itself.
            for stop in range(1, min(len(ordered), 6)):
                label_text = " ".join(row["text"] for row in ordered[:stop])
                ranked = sorted((( _match_score(label_text, field["aliases"]), field) for field in schema), key=lambda pair: pair[0], reverse=True)
                if ranked and ranked[0][0] >= 0.76 and stop < len(ordered):
                    left, right = ordered[:stop], ordered[stop:]
                    break
        if not left or not right:
            continue
        label_text = " ".join(row["text"] for row in left)
        ranked = sorted(((_match_score(label_text, field["aliases"]), field) for field in schema), key=lambda pair: pair[0], reverse=True)
        if not ranked or ranked[0][0] < 0.68:
            continue
        score, field = ranked[0]
        found = _candidate(left, right)
        found["label_score"] = score
        prior = matches.get(field["key"])
        if not prior or (found["confidence"] or -1) > (prior["confidence"] or -1):
            matches[field["key"]] = found
    return matches


def _inline_header_candidates(tokens: list[dict[str, Any]], height: int) -> dict[str, dict[str, Any]]:
    """Printed anchors can occur together on one line (Tehsil / District).

    Match labels only, and keep the intervening real token values. Requiring
    complete label aliases prevents a single OCR letter from matching a label.
    """
    result = {}
    aliases = {_norm(alias): field["key"] for field in HEADER_FIELDS for alias in field["aliases"]}
    for line in build_lines(tokens):
        ordered = sorted(line["tokens"], key=lambda t: t["bbox"]["left"])
        if not ordered or min(t["bbox"]["top"] for t in ordered) > height*.30:
            continue
        anchors, pos = [], 0
        while pos < len(ordered):
            matches = []
            for end in range(pos+1, min(len(ordered),pos+5)+1):
                key = aliases.get(_norm(" ".join(t["text"] for t in ordered[pos:end])))
                if key:
                    matches.append((end,key))
            if matches:
                end,key = max(matches)
                anchors.append((pos,end,key))
                pos = end
            else:
                pos += 1
        for index,(start,end,key) in enumerate(anchors):
            stop = anchors[index+1][0] if index+1 < len(anchors) else len(ordered)
            values = []
            for token in ordered[end:stop]:
                if values:
                    previous = values[-1]["bbox"]
                    gap = token["bbox"]["left"]-(previous["left"]+previous["width"])
                    if gap > max(50, 2.5*max(previous["height"],token["bbox"]["height"])):
                        break
                text = token["text"].strip(" ._:-|,;‘’\"'—")
                if re.search(r"[\w\u0900-\u097f]", text):
                    values.append({**token,"text":text})
            if not values:
                continue
            candidate = _candidate(ordered[start:end],values)
            candidate["label_score"] = 1.0
            candidate["source"] = "inline_printed_anchor"
            if key not in result or (candidate["confidence"] or 0) > (result[key]["confidence"] or 0):
                result[key] = candidate
    return result


def _mapped_geometry_table(tokens: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    """Map coordinate-clustered source columns into the configured schema."""
    lines = build_lines(tokens)
    detected, _ = detect_table(lines, width, height)
    if not detected:
        return []
    mapping: dict[int, int] = {}
    for source_index, header in enumerate(detected.get("detected_headers") or []):
        ranked = sorted(((_match_score(header, column["aliases"]), target_index) for target_index, column in enumerate(TABLE_COLUMNS)), reverse=True)
        if ranked and ranked[0][0] >= 0.55:
            mapping[source_index] = ranked[0][1]
    rows = []
    for source_row in detected.get("rows") or []:
        cells = []
        for cell in source_row.get("cells") or []:
            target_index = mapping.get(cell.get("column_index"))
            value = (cell.get("raw_ocr_value") or "").strip()
            if target_index is None or not value:
                continue
            cells.append({
                "column_index": target_index,
                "raw_ocr_value": value,
                "ai_value": value,
                "ai_confidence": cell.get("ai_confidence"),
                "confidence_source": cell.get("confidence_source") or "unavailable",
                "bounding_box": cell.get("bounding_box"),
                "source_token_ids": cell.get("source_token_ids") or [],
            })
        if cells:
            rows.append({"cells": cells, "source": "tesseract_coordinate_clustering"})
    return rows


@dataclass
class KhatauniExtractor:
    raw_ocr: str
    normalized_ocr: str
    tokens: list[dict[str, Any]]
    image_width: int
    image_height: int
    image_path: str | None = None

    def extract(self) -> dict[str, Any]:
        candidates = _label_candidates(self.tokens)
        candidates.update(_inline_header_candidates(self.tokens, self.image_height))
        header_fields = []
        for field in HEADER_FIELDS:
            match = candidates.get(field["key"], {})
            header_fields.append({
                "key": field["key"],
                "label": field["label"],
                "ocr_value": match.get("value", ""),
                "ocr_confidence": match.get("confidence"),
                "confidence_source": match.get("confidence_source", "unavailable"),
                "bounding_box": match.get("bounding_box"),
                "source_token_ids": match.get("source_token_ids", []),
                "audit_metadata": match,
            })

        rows = _mapped_geometry_table(self.tokens, self.image_width, self.image_height)
        if not rows:
            labelled_cells = []
            for column_index, column in enumerate(TABLE_COLUMNS):
                match = candidates.get(column["key"])
                if not match or not match.get("value"):
                    continue
                labelled_cells.append({
                    "column_index": column_index,
                    "raw_ocr_value": match["value"],
                    "ai_value": match["value"],
                    "ai_confidence": match.get("confidence"),
                    "confidence_source": match.get("confidence_source", "unavailable"),
                    "bounding_box": match.get("bounding_box"),
                    "source_token_ids": match.get("source_token_ids", []),
                })
            if labelled_cells:
                rows = [{"cells": labelled_cells, "source": "tesseract_label_mapping"}]

        populated = [field for field in header_fields if field["ocr_value"]]
        populated_cells = [cell for row in rows for cell in row["cells"] if cell.get("ocr_value", cell.get("raw_ocr_value"))]
        confidences = [entry.get("ocr_confidence", entry.get("ai_confidence")) for entry in [*populated, *populated_cells]]
        structure = {
            "document_type": "khatauni",
            "header_fields": header_fields,
            "table_headers": [column["label"] for column in TABLE_COLUMNS],
            "rows": rows,
            "extraction_summary": {
                "header_fields_detected": len(populated),
                "header_fields_total": len(HEADER_FIELDS),
                "table_rows_detected": len(rows),
                "ocr_cells_populated": len(populated_cells),
                "high_confidence_values": sum(value is not None and value >= 90 for value in confidences),
                "medium_confidence_values": sum(value is not None and 70 <= value < 90 for value in confidences),
                "low_confidence_values": sum(value is not None and value < 70 for value in confidences),
                "unavailable_values": sum(value is None for value in confidences),
            },
        }
        structure = apply_hybrid_recognition(structure, self.image_path)
        structure = annotate_structure(structure)
        structure["digital_khatauni"] = build_digital_khatauni(structure)
        return structure
