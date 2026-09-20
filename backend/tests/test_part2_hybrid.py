from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import bhashini_ocr
import khatauni_hybrid
from diagnostics.ground_truth_benchmark import evaluate_manifest
from khatauni_hybrid import _ink_line_spans, _repair_template_columns, _select
from khatauni_schema import TABLE_COLUMNS
from khatauni_structured import _holder_relation_parts, annotate_structure, compact_recognition_evidence


def tesseract(text: str, confidence: float = 50, variants: list[str] | None = None):
    values = variants or [text]
    return {
        "text": text,
        "raw_text": text,
        "confidence": confidence,
        "format_valid": bool(text),
        "pass_agreement": values.count(text) / len(values),
        "passes": [{"text": value} for value in values],
    }


def htr(text: str, score: float = 0.5):
    return {"text": text, "model_score": score, "status": "ready", "truncated": False}


def bhashini(text: str):
    return {"text": text, "raw_text": text, "confidence": None, "status": "ready"}


class CandidateSelectionTests(unittest.TestCase):
    def test_tesseract_bhashini_agreement_outvotes_htr(self):
        result = _select(tesseract("123", 62), htr("128"), bhashini("123"), "numeric")
        self.assertEqual(result["selected_engine"], "TESSERACT")
        self.assertEqual(result["selected_text"], "123")
        self.assertEqual(result["supporting_engines"], ["BHASHINI", "TESSERACT"])

    def test_handwriting_consensus_can_select_htr_without_fake_percentage(self):
        result = _select(tesseract("कमल", 25), htr("राम कुमार"), bhashini("राम कुमार"), "handwritten")
        self.assertEqual(result["selected_engine"], "HTR")
        self.assertEqual(result["selected_text"], "राम कुमार")
        self.assertIsNone(result["confidence"])

    def test_all_engines_disagree_requires_review(self):
        result = _select(tesseract("राम", 30), htr("श्याम"), bhashini("मोहन"), "handwritten")
        self.assertIn("engine_disagreement", result["warnings"])
        self.assertIn(result["confidence_level"], {"LOW", "UNAVAILABLE"})

    def test_numeric_disagreement_caps_tesseract_evidence(self):
        result = _select(tesseract("121", 96, ["121", "127"]), {"text": "", "status": "skipped"}, bhashini("127"), "numeric")
        self.assertIn("tesseract_digit_disagreement", result["warnings"])
        self.assertLessEqual(result["confidence"], 59)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        bhashini_ocr._circuit_open_until = 0

    def test_response_parser_rejects_missing_output(self):
        result = bhashini_ocr._parse_response({"unexpected": []}, "model")
        self.assertEqual(result["status"], "malformed_response")
        self.assertFalse(result["text"])

    def test_wall_clock_timeout_falls_back(self):
        image = Image.new("L", (20, 20), "white")

        def slow_request(*args, **kwargs):
            time.sleep(0.2)

        with patch.object(bhashini_ocr, "BHASHINI_UDYAT_KEY", "configured"), \
                patch.object(bhashini_ocr, "BHASHINI_INFERENCE_KEY", "configured"), \
                patch.object(bhashini_ocr, "BHASHINI_TIMEOUT_SECONDS", 0.03), \
                patch.object(bhashini_ocr.urllib.request, "urlopen", slow_request):
            started = time.monotonic()
            result = bhashini_ocr.recognize_crop(image, handwritten=True)
            elapsed = time.monotonic() - started
        self.assertEqual(result["reason"], "network_or_timeout")
        self.assertLess(elapsed, 0.15)


class TableAndStructureTests(unittest.TestCase):
    def test_repairs_one_missing_template_column(self):
        positions = [0, 10, 20, 30, 40, 60, 70, 80, 90, 100, 110]
        self.assertEqual(_repair_template_columns(positions), list(range(0, 111, 10)))

    def test_detects_two_clear_ink_lines(self):
        image = Image.new("L", (160, 70), "white")
        draw = ImageDraw.Draw(image)
        for y in (12, 45):
            for x in range(8, 140, 18):
                draw.rectangle((x, y, x + 10, y + 8), fill="black")
        self.assertEqual(len(_ink_line_spans(image)), 2)

    def test_explicit_relation_marker_is_source_derived(self):
        self.assertEqual(_holder_relation_parts("राम पुत्र श्याम"), ("राम", "पुत्र", "श्याम"))
        self.assertIsNone(_holder_relation_parts("राम श्याम"))

    def test_recognition_warning_reaches_validation_status(self):
        structure = {"header_fields": [{
            "key": "khata_number", "ocr_value": "12", "ocr_confidence": 95,
            "audit_metadata": {"warnings": ["engine_disagreement"]},
        }], "rows": []}
        annotate_structure(structure)
        self.assertIn("engine_disagreement", structure["header_fields"][0]["validation"]["warnings"])
        self.assertEqual(structure["header_fields"][0]["status"], "LOW")

    def test_compact_evidence_excludes_engine_internals(self):
        compact = compact_recognition_evidence({
            "selected_engine": "TESSERACT",
            "warnings": [],
            "tesseract": {"passes": [{"tokens": ["verbose"]}]},
            "request_headers": {"Authorization": "must-not-persist"},
            "candidates": {"tesseract": {"raw_text": "12", "confidence": 80}},
        })
        self.assertEqual(compact["selected_engine"], "TESSERACT")
        self.assertNotIn("tesseract", compact)
        self.assertNotIn("request_headers", compact)

    def test_two_holder_lines_become_two_source_linked_rows(self):
        image = Image.new("RGB", (240, 40), "white")
        xs = list(range(0, 240, 20))

        def selected(candidate, *args):
            return {
                "selected_text": candidate.get("text", ""),
                "selected_engine": "TESSERACT",
                "supporting_engines": [],
                "confidence": candidate.get("confidence"),
                "confidence_level": "LOW",
                "warnings": [],
                "selection_reason": "test candidate",
                "confidence_method": "test",
            }

        holder_results = [
            {**selected({"text": "holder_line_a", "confidence": None}), "selected_text": "holder_line_a"},
            {**selected({"text": "holder_line_b", "confidence": None}), "selected_text": "holder_line_b"},
        ]
        with patch.object(khatauni_hybrid, "_table_grid", return_value=((0, 0), xs, [0, 30], image)), \
                patch.object(khatauni_hybrid, "_tesseract_candidate", return_value=tesseract("1", 80)), \
                patch.object(khatauni_hybrid, "_maybe_htr", return_value={"text": "", "status": "skipped"}), \
                patch.object(khatauni_hybrid, "_maybe_bhashini", return_value={"text": "", "status": "skipped"}), \
                patch.object(khatauni_hybrid, "_select", side_effect=selected), \
                patch.object(khatauni_hybrid, "_ink_line_spans", return_value=[(0, 10), (14, 24)]), \
                patch.object(khatauni_hybrid, "_recognize_crop", side_effect=holder_results):
            rows = khatauni_hybrid.recognize_table_rows("ignored.png")

        holder_column = next(index for index, column in enumerate(TABLE_COLUMNS) if column["key"] == "holder_name")
        plot_column = next(index for index, column in enumerate(TABLE_COLUMNS) if column["key"] == "plot_number")
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["cells"][holder_column]["raw_ocr_value"] for row in rows], ["holder_line_a", "holder_line_b"])
        self.assertEqual([row["cells"][plot_column]["raw_ocr_value"] for row in rows], ["1", "1"])
        self.assertEqual({row["source_physical_row_index"] for row in rows}, {0})


class BenchmarkTests(unittest.TestCase):
    def test_empty_manifest_makes_no_accuracy_claim(self):
        result = evaluate_manifest({"documents": []})
        self.assertEqual(result["status"], "NO_VERIFIED_GROUND_TRUTH")
        self.assertIsNone(result["metrics"])

    def test_only_verified_truth_is_counted(self):
        manifest = {"documents": [
            {"human_verified": False, "fields": [{"key": "khata_number", "truth": "1", "predictions": {"hybrid": "1"}}]},
            {"human_verified": True, "truth_row_count": 2, "hybrid_row_count": 2, "fields": [
                {"key": "khata_number", "kind": "numeric", "truth": "12", "predictions": {"tesseract": "12", "hybrid": "12"}},
            ]},
        ]}
        result = evaluate_manifest(manifest)
        self.assertEqual(result["verified_fields"], 1)
        self.assertEqual(result["metrics"]["hybrid"]["field_exact_match"], 1.0)
        self.assertEqual(result["metrics"]["bhashini"]["unresolved_field_rate"], 1.0)
        self.assertEqual(result["metrics"]["hybrid"]["table_row_count_exact_match"], 1.0)


if __name__ == "__main__":
    unittest.main()
