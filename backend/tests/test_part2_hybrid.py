from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageDraw

import khatauni_hybrid
from diagnostics.ground_truth_benchmark import evaluate_manifest
from khatauni_hybrid import _calculate_evidence_confidence, _ink_line_spans, _repair_template_columns, _select
from khatauni_schema import TABLE_COLUMNS
from khatauni_structured import _holder_relation_parts, annotate_structure, compact_recognition_evidence


def tesseract(
    text: str,
    confidence: float | None = 50,
    variants: list[str] | None = None,
    format_valid: bool | None = None,
):
    values = variants or [text]
    return {
        "text": text,
        "raw_text": text,
        "confidence": confidence,
        "format_valid": bool(text) if format_valid is None else format_valid,
        "pass_agreement": values.count(text) / len(values),
        "passes": [{"text": value} for value in values],
    }


def htr(text: str, score: float = 0.5, truncated: bool = False):
    return {"text": text, "model_score": score, "status": "ready", "truncated": truncated}


class CandidateSelectionTests(unittest.TestCase):
    def test_strong_tesseract_candidate_is_retained(self):
        result = _select(tesseract("123", 96), {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual(result["selected_engine"], "TESSERACT")
        self.assertEqual(result["selected_text"], "123")

    def test_weak_tesseract_with_valid_htr_selects_htr_without_fake_percentage(self):
        result = _select(tesseract("कमल", 25), htr("राम कुमार"), "handwritten")
        self.assertEqual(result["selected_engine"], "HTR")
        self.assertEqual(result["selected_text"], "राम कुमार")
        self.assertLess(result["confidence"], 60)
        self.assertNotEqual(result["confidence_breakdown"]["engine_base"], 50)

    def test_tesseract_htr_agreement_retains_local_consensus(self):
        result = _select(tesseract("राम कुमार", 50), htr("राम कुमार"), "handwritten")
        self.assertEqual(result["selected_engine"], "TESSERACT")
        self.assertEqual(result["supporting_engines"], ["HTR", "TESSERACT"])

    def test_tesseract_htr_disagreement_requires_review(self):
        result = _select(tesseract("राम", 30), htr("श्याम"), "handwritten")
        self.assertIn("engine_disagreement", result["warnings"])
        self.assertIn(result["confidence_level"], {"LOW", "UNAVAILABLE"})

    def test_repeated_tesseract_reads_outrank_one_disagreeing_htr_read(self):
        result = _select(
            tesseract("परसपुर", 33, ["परसपूर", "परसपुर"]),
            htr("ज़रु", .31),
            "handwritten",
        )
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("परसपुर", "TESSERACT"))
        self.assertIn("repeated-read support", result["selection_reason"])
        self.assertIn("engine_disagreement", result["warnings"])

    def test_numeric_disagreement_caps_tesseract_evidence(self):
        result = _select(tesseract("121", 96, ["121", "127"]), {"text": "", "status": "skipped"}, "numeric")
        self.assertIn("tesseract_digit_disagreement", result["warnings"])
        self.assertLessEqual(result["confidence"], 59)

    def test_unresolved_input_remains_unresolved(self):
        result = _select(tesseract("", 0), {"text": "", "status": "skipped"}, "handwritten")
        self.assertEqual(result["selected_text"], "")
        self.assertIsNone(result["selected_engine"])
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["confidence_level"], "UNAVAILABLE")

    def test_active_backend_has_no_bhashini_runtime_references(self):
        backend = Path(__file__).resolve().parents[1]
        active_files = list(backend.glob("*.py"))
        for directory in ("routers", "diagnostics"):
            active_files.extend((backend / directory).rglob("*.py"))
        matches = [path for path in active_files if "bhashini" in path.read_text(encoding="utf-8").lower()]
        self.assertEqual(matches, [])


class EvidenceConfidenceTests(unittest.TestCase):
    def _score(self, selected_text, selected_engine, tess, local_htr, kind, agreements=None, supporting=None, warnings=None):
        return _calculate_evidence_confidence(
            selected_text,
            selected_engine,
            tess,
            local_htr,
            kind,
            agreements or {},
            supporting or [],
            warnings or [],
        )

    def test_strong_tesseract_only_numeric_score(self):
        result = _select(tesseract("125", 82), {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("125", "TESSERACT"))
        self.assertEqual(result["confidence"], 72.5)
        self.assertEqual(result["confidence_level"], "MEDIUM")
        self.assertEqual(result["confidence_breakdown"]["stability_bonus"], 0)
        self.assertEqual(result["confidence_breakdown"]["validation_bonus"], 4)
        self.assertEqual(result["confidence_breakdown"]["signals"]["total_passes"], 1)

    def test_normalized_multi_pass_stability_meaningfully_increases_evidence(self):
        result = _select(tesseract("125", 82, ["125", "125"]), {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual(result["confidence"], 86.5)
        self.assertEqual(result["confidence_level"], "HIGH")
        self.assertEqual(result["confidence_breakdown"]["signals"]["stable_passes"], 2)
        self.assertEqual(result["confidence_breakdown"]["stability_bonus"], 14)

    def test_empty_passes_are_omitted_and_normalized_text_is_compared(self):
        tess = tesseract("उन्नाव", 62, ["उन्\u200dनाव", "", "उन्नाव"])
        score, _, breakdown = self._score(
            "उन्नाव", "TESSERACT", tess, {"text": "", "status": "skipped"}, "handwritten",
        )
        self.assertEqual(breakdown["signals"]["total_passes"], 2)
        self.assertEqual(breakdown["signals"]["stable_passes"], 2)
        self.assertGreaterEqual(score, 80)

    def test_invalid_optional_passes_do_not_contradict_one_valid_read(self):
        tess = tesseract("2024-25", 95)
        tess["passes"] = [
            {"text": "9", "format_valid": False},
            {"text": "", "format_valid": False},
            {"text": "2024-25", "format_valid": True},
        ]
        result = _select(tess, {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual(result["selected_text"], "2024-25")
        self.assertNotIn("tesseract_digit_disagreement", result["warnings"])
        self.assertEqual(result["confidence_breakdown"]["signals"]["total_passes"], 1)
        self.assertEqual(result["confidence_breakdown"]["signals"]["ignored_empty_or_invalid_passes"], 2)

    def test_matching_tesseract_and_htr_agreement_bonus(self):
        result = _select(tesseract("राम कुमार", 74, ["राम कुमार", "राम कुमार"]), htr("राम कुमार", .83), "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("राम कुमार", "TESSERACT"))
        self.assertEqual(result["confidence"], 98)
        self.assertEqual(result["confidence_breakdown"]["agreement_bonus"], 14)
        self.assertEqual(result["confidence_breakdown"]["raw_htr_model_score"], .83)
        self.assertFalse(result["confidence_breakdown"]["signals"]["htr_model_evidence"]["calibrated_probability"])

    def test_approximate_independent_agreement_gets_single_bonus(self):
        score, _, breakdown = self._score(
            "राम कुमार", "TESSERACT", tesseract("राम कुमार", 70), htr("राम कुमारी"),
            "handwritten", {"tesseract_htr": .85}, [], [],
        )
        self.assertEqual(score, 73.5)
        self.assertEqual(breakdown["agreement_bonus"], 4)

    def test_clear_engine_disagreement_penalty_and_cap(self):
        result = _select(tesseract("राम कुमार", 80), htr("सीता देवी"), "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("राम कुमार", "TESSERACT"))
        self.assertEqual(result["confidence"], 58)
        self.assertIn({"reason": "engine_disagreement", "value": -12}, result["confidence_breakdown"]["penalties"])
        self.assertIn({"reason": "engine_disagreement", "max_score": 58}, result["confidence_breakdown"]["applied_caps"])

    def test_numeric_pass_disagreement_penalty_and_cap(self):
        result = _select(tesseract("125", 80, ["125", "128"]), {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("125", "TESSERACT"))
        self.assertEqual(result["confidence"], 55)
        self.assertIn({"reason": "tesseract_digit_disagreement", "max_score": 55}, result["confidence_breakdown"]["applied_caps"])

    def test_invalid_numeric_candidate_is_capped_without_rewriting_value(self):
        result = _select(tesseract("12x", 80, format_valid=False), {"text": "", "status": "skipped"}, "numeric")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("12x", "TESSERACT"))
        self.assertEqual(result["confidence"], 45)
        self.assertEqual(result["confidence_breakdown"]["validation_bonus"], 0)

    def test_valid_htr_only_devanagari_uses_conservative_base(self):
        result = _select(tesseract("", None), htr("राम कुमार", .83), "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("राम कुमार", "HTR"))
        self.assertEqual(result["confidence"], 72)
        self.assertEqual(result["confidence_breakdown"]["engine_base"], 68)
        self.assertEqual(result["confidence_breakdown"]["raw_htr_model_score"], .83)

    def test_htr_internal_read_stability_can_reach_high_evidence(self):
        local_htr = {
            **htr("राम कुमार", .83),
            "line_candidate": {"text": "राम कुमार"},
            "word_candidates": [{"text": "राम"}, {"text": "कुमार"}],
        }
        result = _select(tesseract("", None), local_htr, "handwritten")
        self.assertEqual(result["confidence"], 86)
        self.assertEqual(result["confidence_level"], "HIGH")
        self.assertEqual(result["confidence_breakdown"]["signals"]["stable_passes"], 2)

    def test_htr_selection_with_tesseract_agreement_preserves_selection(self):
        result = _select(tesseract("राम कुमार", 25), htr("राम कुमार", .83), "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("राम कुमार", "HTR"))
        self.assertEqual(result["confidence"], 86)
        self.assertEqual(result["confidence_level"], "HIGH")

    def test_mixed_script_safety_cap(self):
        result = _select(tesseract("Ram", 80), htr("राम कुमार", .83), "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("राम कुमार", "HTR"))
        self.assertEqual(result["confidence"], 45)
        self.assertIn({"reason": "mixed_script_review", "max_score": 45}, result["confidence_breakdown"]["applied_caps"])

    def test_truncated_htr_safety_cap(self):
        score, _, breakdown = self._score(
            "राम कुमार", "HTR", tesseract("", None), htr("राम कुमार", .83, truncated=True), "handwritten",
        )
        self.assertEqual(score, 45)
        self.assertIn({"reason": "truncated_htr", "max_score": 45}, breakdown["applied_caps"])

    def test_no_usable_candidate_has_no_score(self):
        result = _select(tesseract("", None), {"text": "", "status": "skipped"}, "handwritten")
        self.assertEqual((result["selected_text"], result["selected_engine"]), ("", None))
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["confidence_breakdown"]["final_score"], None)


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

    def test_recognition_warning_remains_separate_from_validation_status(self):
        structure = {"header_fields": [{
            "key": "khata_number", "ocr_value": "12", "ocr_confidence": 95,
            "audit_metadata": {"warnings": ["engine_disagreement"]},
        }], "rows": []}
        annotate_structure(structure)
        validation = structure["header_fields"][0]["validation"]
        self.assertEqual(validation["warnings"], [])
        self.assertIn("engine_disagreement", validation["recognition_warnings"])
        self.assertEqual(validation["review_status"], "NEEDS_REVIEW")
        self.assertEqual(structure["header_fields"][0]["status"], "PASS")

    def test_compact_evidence_excludes_engine_internals(self):
        compact = compact_recognition_evidence({
            "selected_engine": "TESSERACT",
            "warnings": [],
            "tesseract": {"passes": [{"tokens": ["verbose"]}]},
            "request_headers": {"Authorization": "must-not-persist"},
            "candidates": {"tesseract": {"raw_text": "12", "confidence": 80, "passes": [
                {"variant": "gray", "raw_text": "12", "normalized_text": "12", "confidence": 80, "tokens": ["verbose"]},
            ]}},
            "confidence_breakdown": {"final_score": 72, "signals": {"stable_passes": 1}},
        })
        self.assertEqual(compact["selected_engine"], "TESSERACT")
        self.assertNotIn("tesseract", compact)
        self.assertNotIn("request_headers", compact)
        self.assertNotIn("tokens", compact["candidates"]["tesseract"]["passes"][0])
        self.assertEqual(compact["confidence_breakdown"]["final_score"], 72)

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
        self.assertEqual(result["metrics"]["local_htr"]["unresolved_field_rate"], 1.0)
        self.assertEqual(result["metrics"]["hybrid"]["table_row_count_exact_match"], 1.0)


if __name__ == "__main__":
    unittest.main()
