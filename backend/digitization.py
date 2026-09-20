"""Layout-aware, document-native OCR structure helpers.

This module deliberately does not know land-record field names.  It works only
with OCR words, their Tesseract geometry and separators that are actually
present in a document.  A human officer can correct any weak layout result.
"""

from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if confidence >= 0 else None


def tokens_from_tesseract(data: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Convert ``image_to_data`` output into JSON-safe word tokens with boxes."""
    tokens: list[dict[str, Any]] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = (raw_text or "").strip()
        if not text:
            continue
        left = _as_int(data.get("left", [0])[index])
        top = _as_int(data.get("top", [0])[index])
        width = _as_int(data.get("width", [0])[index])
        height = _as_int(data.get("height", [0])[index])
        tokens.append(
            {
                "index": index,
                "text": text,
                "confidence": _as_confidence(data.get("conf", [None])[index]),
                "bbox": {"left": left, "top": top, "width": width, "height": height},
                "page_num": _as_int(data.get("page_num", [0])[index]),
                "block_num": _as_int(data.get("block_num", [0])[index]),
                "par_num": _as_int(data.get("par_num", [0])[index]),
                "line_num": _as_int(data.get("line_num", [0])[index]),
                "word_num": _as_int(data.get("word_num", [0])[index]),
            }
        )
    return tokens


def load_tokens(raw_json: str | None) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        return []
    return [token for token in parsed if isinstance(token, dict) and token.get("text")]


def bbox_for(tokens: list[dict[str, Any]]) -> dict[str, int] | None:
    boxes = [token.get("bbox") for token in tokens if isinstance(token.get("bbox"), dict)]
    if not boxes:
        return None
    left = min(_as_int(box.get("left")) for box in boxes)
    top = min(_as_int(box.get("top")) for box in boxes)
    right = max(_as_int(box.get("left")) + _as_int(box.get("width")) for box in boxes)
    bottom = max(_as_int(box.get("top")) + _as_int(box.get("height")) for box in boxes)
    return {"left": left, "top": top, "width": max(right - left, 0), "height": max(bottom - top, 0)}


def confidence_for(tokens: list[dict[str, Any]]) -> tuple[float | None, str]:
    values = [token.get("confidence") for token in tokens]
    values = [float(value) for value in values if isinstance(value, (int, float)) and value >= 0]
    if not values:
        return None, "unavailable"
    return sum(values) / len(values), "tesseract_token_mean"


def _sort_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        tokens,
        key=lambda token: (
            _as_int((token.get("bbox") or {}).get("top")),
            _as_int((token.get("bbox") or {}).get("left")),
        ),
    )


def build_lines(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group Tesseract words into its own recognised visual lines."""
    groups: dict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for token in tokens:
        key = (
            _as_int(token.get("page_num")),
            _as_int(token.get("block_num")),
            _as_int(token.get("par_num")),
            _as_int(token.get("line_num")),
        )
        groups[key].append(token)

    lines: list[dict[str, Any]] = []
    for key, line_tokens in groups.items():
        ordered = _sort_tokens(line_tokens)
        box = bbox_for(ordered)
        if not box:
            continue
        lines.append(
            {
                "key": key,
                "tokens": ordered,
                "text": " ".join(token["text"] for token in ordered),
                "bbox": box,
            }
        )
    return sorted(lines, key=lambda line: (line["bbox"]["top"], line["bbox"]["left"]))


def normalized_label(label: str) -> str | None:
    normalized = re.sub(r"\s+", " ", label.strip()).lower()
    normalized = re.sub(r"^[\W_]+|[\W_]+$", "", normalized, flags=re.UNICODE)
    return normalized or None


def _clean_segment(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for token in tokens:
        text = token["text"].strip(" \t:：|¦")
        if text:
            copied = dict(token)
            copied["text"] = text
            result.append(copied)
    return result


def detect_key_value_items(lines: list[dict[str, Any]], excluded_keys: set[tuple[int, int, int, int]] | None = None) -> list[dict[str, Any]]:
    """Find label/value pairs from actual separators without a label dictionary."""
    excluded_keys = excluded_keys or set()
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for line in lines:
        if line["key"] in excluded_keys:
            continue
        line_tokens = line["tokens"]
        colon_indexes = [index for index, token in enumerate(line_tokens) if ":" in token["text"] or "：" in token["text"]]
        if not colon_indexes:
            continue
        boundary = 0
        for colon_position, colon_index in enumerate(colon_indexes):
            next_colon = colon_indexes[colon_position + 1] if colon_position + 1 < len(colon_indexes) else len(line_tokens)
            label_tokens = _clean_segment(line_tokens[boundary : colon_index + 1])
            value_tokens = _clean_segment(line_tokens[colon_index + 1 : next_colon])
            boundary = colon_index + 1
            # A colon attached to a word is the strongest document-native
            # signal of a local label (for example ``तहसील:``).  Do not carry
            # unrelated OCR text from the beginning of a crowded header line
            # into that label.  When a separator was read as its own token,
            # retain only the immediately preceding short phrase instead.
            colon_text = line_tokens[colon_index].get("text", "")
            attached = colon_text.strip(" \t:：|¦")
            if attached and (":" in colon_text or "：" in colon_text):
                attached_tokens = _clean_segment([line_tokens[colon_index]])
                label_tokens = attached_tokens or label_tokens[-3:]
            else:
                label_tokens = label_tokens[-3:]
            if not label_tokens or not value_tokens:
                continue
            label = " ".join(token["text"] for token in label_tokens).strip()
            value = " ".join(token["text"] for token in value_tokens).strip()
            if len(label) < 2 or len(value) < 1:
                continue
            key = (label, value)
            if key in seen:
                continue
            seen.add(key)
            confidence, source = confidence_for(label_tokens + value_tokens)
            found.append(
                {
                    "original_label": label,
                    "normalized_label": normalized_label(label),
                    "ai_value": value,
                    "ai_confidence": confidence,
                    "confidence_source": source,
                    "bounding_box": bbox_for(label_tokens + value_tokens),
                    "row_index": None,
                    "column_index": None,
                }
            )
    return found


def _meaningful(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [token for token in tokens if re.search(r"[\w\u0900-\u097F]", token.get("text", ""), re.UNICODE)]


def _column_edges(header_tokens: list[dict[str, Any]], page_width: int) -> list[int]:
    """Prefer OCR-recognised table separators; otherwise use wide geometry gaps."""
    separators = sorted(
        _as_int((token.get("bbox") or {}).get("left"))
        for token in header_tokens
        if token.get("text", "").strip() in {"|", "¦"}
    )
    distinct: list[int] = []
    for position in separators:
        if not distinct or position - distinct[-1] >= max(45, page_width // 25):
            distinct.append(position)
    if len(distinct) >= 2:
        return [0, *distinct, page_width]

    words = sorted(
        _meaningful(header_tokens),
        key=lambda token: _as_int((token.get("bbox") or {}).get("left")),
    )
    if not words:
        return []
    # A table header often contains a long wrapped label per column.  Grouping
    # by word *centres* with a large page-wide threshold merges neighboring
    # narrow columns.  Use genuine whitespace between word boxes instead.  The
    # value scales with the page but is deliberately modest so a source table
    # can retain its own column count without knowing its schema in advance.
    threshold = max(26, page_width // 55)
    clusters: list[list[dict[str, Any]]] = [[words[0]]]
    for word in words[1:]:
        prior = clusters[-1][-1]
        prior_box = prior.get("bbox") or {}
        word_box = word.get("bbox") or {}
        prior_right = _as_int(prior_box.get("left")) + _as_int(prior_box.get("width"))
        gap = _as_int(word_box.get("left")) - prior_right
        if gap >= threshold:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    if len(clusters) < 2:
        return []
    edges = [0]
    for left_cluster, right_cluster in zip(clusters, clusters[1:]):
        left_box = left_cluster[-1].get("bbox") or {}
        right_box = right_cluster[0].get("bbox") or {}
        prior_right = _as_int(left_box.get("left")) + _as_int(left_box.get("width"))
        next_left = _as_int(right_box.get("left"))
        edges.append((prior_right + next_left) // 2)
    edges.append(page_width)
    return edges


def _tokens_in_column(tokens: list[dict[str, Any]], left: int, right: int) -> list[dict[str, Any]]:
    return [
        token
        for token in tokens
        if left <= _as_int((token.get("bbox") or {}).get("left")) + _as_int((token.get("bbox") or {}).get("width")) // 2 < right
    ]


def _row_groups(lines: list[dict[str, Any]], start_y: int, image_height: int) -> list[list[dict[str, Any]]]:
    candidates = [line for line in lines if line["bbox"]["top"] >= start_y and line["bbox"]["top"] < image_height]
    groups: list[list[dict[str, Any]]] = []
    tolerance = max(55, image_height // 24)
    for line in candidates:
        if not groups or line["bbox"]["top"] - groups[-1][-1]["bbox"]["top"] > tolerance:
            groups.append([line])
        else:
            groups[-1].append(line)
    # Ignore page-edge artefacts and keep only groups that contain a real word.
    return [group for group in groups if _meaningful([token for line in group for token in line["tokens"]])]


def detect_table(lines: list[dict[str, Any]], image_width: int, image_height: int) -> tuple[dict[str, Any] | None, set[tuple[int, int, int, int]]]:
    """Reconstruct one best-effort table from genuine OCR geometry.

    The method intentionally returns unknown headers where geometry exists but
    text is weak. It never substitutes a land-record schema.
    """
    candidates: list[tuple[float, dict[str, Any]]] = []
    for line in lines:
        box = line["bbox"]
        if box["top"] < image_height * 0.14 or box["top"] > image_height * 0.72:
            continue
        words = _meaningful(line["tokens"])
        width_score = box["width"] / max(image_width, 1)
        separators = sum(token["text"].strip() in {"|", "¦"} for token in line["tokens"])
        if len(words) < 4 or width_score < 0.55:
            continue
        score = min(len(words), 18) + width_score * 7 + separators * 3
        candidates.append((score, line))
    if not candidates:
        return None, set()

    # The first strong, wide row is usually a table section/header. Prefer an
    # earlier equally-strong candidate so document totals do not win.
    candidates.sort(key=lambda pair: (-pair[0], pair[1]["bbox"]["top"]))
    score, anchor = candidates[0]
    comparable = [pair for pair in candidates if pair[0] >= score * 0.84]
    # Decorative numbering/header fragments can be a very wide but sparse
    # line just above the real column-label line.  Prefer the densest genuine
    # candidate in the first half of the page, then retain the earliest one as
    # a tie-breaker.  This is purely geometry/OCR-density based.
    upper_candidates = [pair for pair in comparable if pair[1]["bbox"]["top"] <= image_height * 0.48] or comparable
    near_best = [pair for pair in upper_candidates if pair[0] >= score * 0.88] or upper_candidates
    anchor = min(near_best, key=lambda pair: pair[1]["bbox"]["top"])[1]
    header_top = anchor["bbox"]["top"]
    # Header words commonly wrap over several nearby OCR lines.  Follow the
    # observed line spacing until a real vertical break rather than assuming a
    # fixed page-height band that can swallow the first data row.
    continuation_gap = max(32, image_height // 35)
    max_header_depth = max(80, image_height // 12)
    header_lines = []
    last_bottom = header_top
    for line in (line for line in lines if line["bbox"]["top"] >= header_top):
        top = line["bbox"]["top"]
        if top - header_top > max_header_depth or (header_lines and top - last_bottom > continuation_gap):
            break
        header_lines.append(line)
        last_bottom = max(last_bottom, top + line["bbox"]["height"])
    header_bottom = last_bottom
    header_tokens = [token for line in header_lines for token in line["tokens"]]
    # The anchor is the most horizontal header line; it provides the cleanest
    # geometry for column cuts.  Wrapped continuation lines supply any words
    # missed on that line after those cuts are established.
    edges = _column_edges(anchor["tokens"], image_width)
    if len(edges) < 3:
        edges = _column_edges(header_tokens, image_width)
    if len(edges) < 3:
        return None, {line["key"] for line in header_lines}

    # Use the anchor line as the primary source for column labels. It is the
    # safest way to preserve the actual text nearest the table section title.
    headers: list[str] = []
    for column_index, (left, right) in enumerate(zip(edges, edges[1:])):
        segment = _meaningful(_tokens_in_column(anchor["tokens"], left, right))
        if not segment:
            segment = _meaningful(_tokens_in_column(header_tokens, left, right))
        label = " ".join(token["text"] for token in _sort_tokens(segment)).strip()
        headers.append(label[:180] if len(label) >= 2 else f"Unknown Column {column_index + 1}")

    # Tesseract line boxes can overlap the next visual row when a wrapped
    # header contains a tall glyph.  The capped header depth is a safer lower
    # edge than a single oversized OCR bounding box.
    row_start = min(header_bottom, header_top + max_header_depth) + max(8, image_height // 160)
    # A later, wide OCR line with enough words to be another header is a
    # document-layout boundary.  It prevents a second table's content from
    # being appended to the first table without relying on any field names.
    later_headers = [line["bbox"]["top"] for _, line in candidates if line["bbox"]["top"] > row_start + max(70, image_height // 18)]
    row_end = min(later_headers) if later_headers else image_height
    row_groups = _row_groups(lines, row_start, row_end)
    rows: list[dict[str, Any]] = []
    for row_index, group in enumerate(row_groups):
        row_tokens = [token for line in group for token in line["tokens"]]
        if not _meaningful(row_tokens):
            continue
        cells: list[dict[str, Any]] = []
        for column_index, (left, right) in enumerate(zip(edges, edges[1:])):
            cell_tokens = _meaningful(_tokens_in_column(row_tokens, left, right))
            value = " ".join(token["text"] for token in _sort_tokens(cell_tokens)).strip()
            confidence, source = confidence_for(cell_tokens)
            cells.append(
                {
                    "row_index": len(rows),
                    "column_index": column_index,
                    "header_label": headers[column_index],
                    "raw_ocr_value": value,
                    "ai_value": value,
                    "ai_confidence": confidence,
                    "confidence_source": source,
                    "bounding_box": bbox_for(cell_tokens),
                }
            )
        if any(cell["ai_value"] for cell in cells):
            rows.append({"row_index": len(rows), "cells": cells})

    if not rows:
        return None, {line["key"] for line in header_lines}
    return (
        {
            "original_label": None,
            "detected_headers": headers,
            "bounding_box": bbox_for(header_tokens),
            "rows": rows,
        },
        {line["key"] for line in header_lines},
    )


def detect_document_structure(tokens: list[dict[str, Any]], image_width: int, image_height: int) -> dict[str, Any]:
    """Return dynamic fields/tables derived only from OCR words and geometry."""
    lines = build_lines(tokens)
    table, table_line_keys = detect_table(lines, image_width, image_height)
    items = detect_key_value_items(lines, table_line_keys)
    return {"items": items, "tables": [table] if table else [], "lines": lines}
