"""CSV renderer for the canonical verified-record export DTO."""

from __future__ import annotations

import csv
import io
import re
from typing import Any


_NUMERIC_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _safe_cell(value: Any) -> str:
    """Escape formula-like text for spreadsheet display without changing data."""

    text = _display(value)
    if not text or not isinstance(value, str):
        return text
    if text[0] in "=+@" or (text[0] == "-" and not _NUMERIC_TEXT.fullmatch(text)):
        return "'" + text
    return text


def _field_key(field: dict[str, Any], index: int) -> str:
    raw = field.get("normalized_label") or field.get("label") or field.get("field_id") or index
    key = re.sub(r"[^\w.-]+", "_", str(raw), flags=re.UNICODE).strip("._")
    return key or str(index)


def _table_key(table: dict[str, Any], index: int) -> str:
    raw = table.get("normalized_label") or table.get("label")
    key = re.sub(r"[^\w.-]+", "_", str(raw), flags=re.UNICODE).strip("._") if raw else ""
    return f"{index}_{key}" if key else str(index)


def canonical_export_rows(export: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """Flatten one canonical export deterministically into CSV columns/rows."""

    document = export.get("document") or {}
    verification = export.get("verification") or {}
    officer = verification.get("officer") or {}
    base: dict[str, Any] = {
        "record_id": export.get("record_id"),
        "status": export.get("status"),
        "document_id": document.get("id"),
        "submission_id": document.get("submission_id"),
        "document_type": document.get("document_type"),
        "original_filename": document.get("original_filename"),
        "uploaded_at": document.get("uploaded_at"),
        "verified_at": verification.get("verified_at"),
        "verified_by": officer.get("officer_id") or officer.get("name"),
    }
    for key, value in sorted((export.get("fields") or {}).items()):
        base[key] = value
    for index, field in enumerate(export.get("dynamic_fields") or []):
        base[f"field.{_field_key(field, index)}"] = field.get("value")

    tables = export.get("tables") or []
    table_columns: list[str] = []
    table_rows: list[dict[str, Any]] = []
    for table_index, table in enumerate(tables):
        table_key = _table_key(table, table_index)
        headers = table.get("headers") or []
        column_keys: dict[int, str] = {}
        for column_index, header in enumerate(headers):
            label = (header or {}).get("label")
            clean = re.sub(r"[^\w.-]+", "_", str(label), flags=re.UNICODE).strip("._") if label else ""
            column_keys[column_index] = clean or f"column_{column_index + 1}"
        rows = table.get("rows") or []
        for row in rows:
            flattened = dict(base)
            flattened["table_key"] = table_key
            flattened["table_index"] = table.get("table_index", table_index)
            flattened["table_row_index"] = row.get("row_index")
            for cell in row.get("cells") or []:
                column_index = cell.get("column_index")
                if column_index is None:
                    column_index = len(column_keys)
                    column_keys[column_index] = f"column_{column_index + 1}"
                column = f"table.{table_key}.{column_keys[column_index]}"
                flattened[column] = cell.get("value")
                if column not in table_columns:
                    table_columns.append(column)
            table_rows.append(flattened)

    if not table_rows:
        table_rows = [base]
    columns = list(base.keys())
    if tables:
        columns.extend(["table_key", "table_index", "table_row_index"])
    columns.extend(column for column in table_columns if column not in columns)
    return columns, table_rows


def render_verified_record_csv(export: dict[str, Any]) -> bytes:
    columns, rows = canonical_export_rows(export)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _safe_cell(row.get(column)) for column in columns})
    return stream.getvalue().encode("utf-8-sig")
