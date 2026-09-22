"""Human-readable PDF renderer for the canonical verified-record DTO."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import fitz


_MARGINS = 36
_INK = (0.10, 0.14, 0.20)
_MUTED = (0.35, 0.40, 0.46)
_ACCENT = (0.62, 0.30, 0.08)
_PALE = (0.98, 0.94, 0.88)
_FONT_PATH_ENV = "BHUMIAI_PDF_FONT_PATH"
_DEVANAGARI_SAMPLE = "कृषि भूमि"


class PdfFontUnavailableError(RuntimeError):
    """Raised when PDF export cannot render Devanagari safely."""


def _supports_devanagari(path: Path) -> bool:
    try:
        font = fitz.Font(fontfile=str(path))
        return all(font.has_glyph(ord(character)) for character in _DEVANAGARI_SAMPLE if not character.isspace())
    except (RuntimeError, ValueError):
        return False


def _font_path() -> str:
    configured = os.environ.get(_FONT_PATH_ENV, "").strip()
    candidates = [Path(configured).expanduser()] if configured else [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "mangal.ttf",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "Nirmala.ttc",
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf"),
        Path("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file() and _supports_devanagari(candidate):
            return str(candidate)
    if configured:
        raise PdfFontUnavailableError(
            f"Configured {_FONT_PATH_ENV} does not point to a usable Devanagari font."
        )
    raise PdfFontUnavailableError(
        "No installed Devanagari-capable font is available for PDF export. "
        f"Install one or configure {_FONT_PATH_ENV}."
    )


def _text(value: Any) -> str:
    return "—" if value is None or value == "" else str(value)


def _has_value(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _human_label(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title() or "Verified field"


def _human_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return _text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%d %b %Y, %H:%M")


_PREFERRED_DETAIL_FIELDS = (
    (("district",), "district", "District"),
    (("tehsil",), "tehsil", "Tehsil"),
    (("revenue_village",), None, "Revenue Village"),
    (("village_name", "village"), "village", "Village Name"),
    (("village_code",), None, "Village Code"),
    (("pargana",), None, "Pargana"),
    (("crop_year", "fasli_year", "fasli", "record_year"), None, "Fasli Year"),
    (("khata_number",), "khata_number", "Khata Number"),
    (("holder_name", "khatedar_name", "owner_name"), "owner_name", "Khatedar Name"),
    (("guardian_name", "father_husband_name", "father_guardian_name"), "father_guardian_name", "Father / Husband Name"),
    (("patwari_circle", "patwari_halka"), None, "Patwari Halka"),
    (("patwari_name",), None, "Patwari Name"),
    (("lekhpal_name",), None, "Lekhpal Name"),
    (("issue_date",), None, "Issue Date"),
)

_FIXED_FIELD_LABELS = {
    "owner_name": "Owner Name",
    "father_guardian_name": "Father / Guardian Name",
    "khasra_number": "Khasra Number",
    "khata_number": "Khata Number",
    "area": "Area",
    "village": "Village",
    "tehsil": "Tehsil",
    "district": "District",
    "state": "State",
}


def _presentation_rows(export: dict[str, Any]) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
    """Select non-empty canonical fields for the human-readable PDF only."""

    dynamic = []
    for index, field in enumerate(export.get("dynamic_fields") or []):
        value = field.get("value")
        if not _has_value(value):
            continue
        key = _normalise_key(field.get("normalized_label") or field.get("label"))
        dynamic.append((index, key, str(field.get("label") or _human_label(key)), value))

    fixed = export.get("fields") or {}
    details: list[tuple[str, Any]] = []
    used_dynamic: set[int] = set()
    represented_fixed: set[str] = set()
    for dynamic_keys, fixed_key, fallback_label in _PREFERRED_DETAIL_FIELDS:
        match = next((item for item in dynamic if item[0] not in used_dynamic and item[1] in dynamic_keys), None)
        if match:
            used_dynamic.add(match[0])
            details.append((match[2], match[3]))
            if fixed_key:
                represented_fixed.add(fixed_key)
        elif fixed_key and _has_value(fixed.get(fixed_key)):
            details.append((_FIXED_FIELD_LABELS.get(fixed_key, fallback_label), fixed[fixed_key]))
            represented_fixed.add(fixed_key)

    additional = [(label, value) for index, _key, label, value in dynamic if index not in used_dynamic]
    for key, value in fixed.items():
        if _has_value(value) and key not in represented_fixed:
            additional.append((_FIXED_FIELD_LABELS.get(key, _human_label(key)), value))
    return details, additional


def _wrap(value: Any, width: float, size: float, font: fitz.Font) -> list[str]:
    text = _text(value)
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split(" ") or [""]
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if font.text_length(candidate, fontsize=size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = ""
            for character in word:
                candidate = current + character
                if font.text_length(candidate, fontsize=size) > width and current:
                    lines.append(current)
                    current = character
                else:
                    current = candidate
        lines.append(current)
    return lines or [""]


class _PdfWriter:
    def __init__(self, landscape: bool):
        self.landscape = landscape
        self.width = 842 if landscape else 595
        self.height = 595 if landscape else 842
        self.font_path = _font_path()
        self.font = fitz.Font(fontfile=self.font_path)
        self.document = fitz.open()
        self.page = self.document.new_page(width=self.width, height=self.height)
        self.y = _MARGINS

    def new_page(self) -> None:
        self.page = self.document.new_page(width=self.width, height=self.height)
        self.y = _MARGINS

    def ensure(self, height: float) -> None:
        if self.y + height > self.height - _MARGINS - 24:
            self.new_page()

    def write(self, value: Any, size: float = 10, color=_INK, bold: bool = False, gap: float = 4) -> None:
        lines = _wrap(value, self.width - 2 * _MARGINS, size, self.font)
        line_height = size * 1.35
        self.ensure(line_height * len(lines) + gap)
        for line in lines:
            self.page.insert_text((_MARGINS, self.y + size), line, fontname="bhumi", fontfile=self.font_path, fontsize=size, color=color)
            self.y += line_height
        self.y += gap

    def heading(self, value: str) -> None:
        self.ensure(30)
        self.page.draw_rect((_MARGINS, self.y - 3, self.width - _MARGINS, self.y + 20), color=None, fill=_PALE)
        self.page.insert_text((_MARGINS + 8, self.y + 13), value, fontname="bhumi", fontfile=self.font_path, fontsize=12, color=_ACCENT)
        self.y += 30

    def key_values(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.write(f"{key}: {_text(value)}", size=9, gap=3)

    def label_values(self, rows: list[tuple[str, Any]]) -> None:
        """Render compact label/value rows without database-style table chrome."""

        usable = self.width - 2 * _MARGINS
        label_width = usable * 0.42
        value_width = usable - label_width - 14
        for label, value in rows:
            label_lines = _wrap(label, label_width, 8.5, self.font)
            value_lines = _wrap(value, value_width, 9, self.font)
            line_count = max(len(label_lines), len(value_lines))
            height = line_count * 12 + 10
            self.ensure(height)
            for index, line in enumerate(label_lines):
                self.page.insert_text((_MARGINS, self.y + 10 + index * 12), line,
                                      fontname="bhumi", fontfile=self.font_path, fontsize=8.5, color=_MUTED)
            for index, line in enumerate(value_lines):
                self.page.insert_text((_MARGINS + label_width + 14, self.y + 10 + index * 12), line,
                                      fontname="bhumi", fontfile=self.font_path, fontsize=9, color=_INK)
            self.page.draw_line((_MARGINS, self.y + height - 3), (self.width - _MARGINS, self.y + height - 3),
                                color=(0.88, 0.89, 0.90), width=0.4)
            self.y += height
        self.y += 8

    def table(self, headers: list[str], rows: list[list[Any]]) -> None:
        if not headers:
            if rows:
                self.write("; ".join(_text(value) for row in rows for value in row), size=9)
            else:
                self.write("—", size=9)
            return
        usable = self.width - 2 * _MARGINS
        widths = [usable / len(headers)] * len(headers)
        header_wrapped = [_wrap(value, widths[index] - 8, 8, self.font) for index, value in enumerate(headers)]
        header_height = max(len(lines) for lines in header_wrapped) * 11 + 12

        def draw_row(row: list[Any], row_index: int, wrapped: list[list[str]], height: float) -> None:
            height = max(len(lines) for lines in wrapped) * 11 + 12
            if row_index == 0:
                self.page.draw_rect((_MARGINS, self.y, self.width - _MARGINS, self.y + height), color=None, fill=_PALE)
            x = _MARGINS
            for index, lines in enumerate(wrapped):
                self.page.draw_rect((x, self.y, x + widths[index], self.y + height), color=(0.80, 0.82, 0.84), fill=None, width=0.5)
                cell_size = 8.5 if row_index else 8
                for line_index, line in enumerate(lines):
                    self.page.insert_text((x + 4, self.y + 4 + cell_size * (line_index + 1)), line,
                                          fontname="bhumi", fontfile=self.font_path, fontsize=cell_size, color=_INK)
                x += widths[index]
            self.y += height

        for row_index, row in enumerate(rows):
            wrapped = [_wrap(value, widths[index] - 8, 8.5, self.font) for index, value in enumerate(row)]
            height = max(len(lines) for lines in wrapped) * 11 + 12
            if row_index == 0:
                self.ensure(header_height + height + 2)
                draw_row(headers, 0, header_wrapped, header_height)
            elif self.y + height > self.height - _MARGINS - 24:
                self.new_page()
                draw_row(headers, 0, header_wrapped, header_height)
            draw_row(row, 1, wrapped, height)
        if not rows:
            self.ensure(header_height + 2)
            draw_row(headers, 0, header_wrapped, header_height)
        self.y += 10

    def finish(self) -> bytes:
        for page in self.document:
            page.insert_text((self.width - 110, self.height - 18), "Generated by BhumiAI", fontname="bhumi", fontfile=self.font_path, fontsize=7, color=_MUTED)
        data = self.document.tobytes()
        self.document.close()
        return data


def render_verified_record_pdf(export: dict[str, Any]) -> bytes:
    tables = export.get("tables") or []
    widest = max((len(table.get("headers") or []) for table in tables), default=0)
    writer = _PdfWriter(landscape=widest > 5)
    document = export.get("document") or {}
    verification = export.get("verification") or {}
    officer = verification.get("officer") or {}
    detail_rows, additional_rows = _presentation_rows(export)
    writer.write("BhumiAI", size=22, color=_ACCENT, gap=2)
    writer.write("Verified Digital Land Record", size=15, gap=14)
    writer.heading("Record Information")
    record_rows = [
        ("Record ID", export.get("record_id")),
        ("Document Type", document.get("document_type")),
        ("Status", export.get("status")),
        ("Verified At", _human_timestamp(verification.get("verified_at"))),
        ("Verified By", officer.get("name") or officer.get("officer_id")),
        ("Source Document", document.get("original_filename")),
    ]
    writer.label_values([(label, value) for label, value in record_rows if _has_value(value)])
    if detail_rows:
        writer.heading("Land Record Details")
        writer.label_values(detail_rows)
    for table_index, table in enumerate(tables):
        writer.heading(table.get("label") or ("Main Khatauni Table" if table_index == 0 else f"Structured Table {table.get('table_index', table_index) + 1}"))
        headers = table.get("headers") or []
        header_names = [_text(header.get("label")) for header in headers]
        rows = []
        for row in table.get("rows") or []:
            by_column = {cell.get("column_index"): cell.get("value") for cell in row.get("cells") or []}
            rows.append([by_column.get(index) for index in range(len(headers))])
        writer.table(header_names, rows)
    if additional_rows:
        writer.heading("Additional Verified Information")
        writer.label_values(additional_rows)
    writer.heading("Verification Information")
    verification_rows = [
        ("Verified Status", verification.get("status")),
        ("Verified At", _human_timestamp(verification.get("verified_at"))),
        ("Verifying Officer", officer.get("name") or officer.get("officer_id")),
    ]
    writer.label_values([(label, value) for label, value in verification_rows if _has_value(value)])
    return writer.finish()
