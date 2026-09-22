from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import fitz

from database import Base, get_db
import models
from routers import officer, records, users
from security import SESSION_COOKIE_NAME, new_session
from services.export_service import build_verified_record_export, export_filename
from services import export_csv, export_pdf


class VerifiedExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-export-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'export.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        now = datetime.datetime.utcnow()
        with self.sessions() as db:
            self.officer = models.User(name="Export Officer", email="officer@example.test", role="officer", officer_id="GOV-EXPORT-1")
            self.citizen = models.User(name="Export Citizen", email="citizen@example.test", role="user", phone_number="+919876543210", phone_verified_at=now, state="UP", district="Lucknow", profile_completed_at=now)
            self.other = models.User(name="Other Citizen", email="other@example.test", role="user", phone_number="+919876543211", phone_verified_at=now, state="UP", district="Lucknow", profile_completed_at=now)
            db.add_all([self.officer, self.citizen, self.other]); db.flush()
            document = models.Document(file_path="/safe/verified.png", original_filename="verified.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="export-hash")
            submission = models.Submission(document=document, user=self.citizen, status="VERIFIED")
            db.add(submission); db.flush()
            record = models.VerifiedRecord(record_id="LR-EXPORT-0001", submission_id=submission.id, owner_name="Final Owner", father_guardian_name="Guardian", khasra_number="K-1", khata_number="KH-2", area="1.5", village="Rampur", tehsil="Sadar", district="Lucknow", state="UP", verification_status="VERIFIED", verified_by=self.officer.id, verified_at=now)
            db.add(record); db.flush()
            ocr = models.OCRResult(document_id=document.id, engine="Tesseract", script="Devanagari", raw_text="RAW OCR MUST NOT WIN", processed_image_path="/safe/processed.png")
            db.add(ocr); db.flush()
            db.add(models.ExtractedField(ocr_result_id=ocr.id, field_name="owner_name", ai_value="OCR Owner", officer_value="Corrected Owner", final_value="Final Owner", ai_confidence=42))
            item = models.DynamicExtractedItem(document_id=document.id, ocr_result_id=ocr.id, original_label="गाटा संख्या", normalized_label="gata_number", item_type="key_value", ai_value="OCR remark", officer_value="स्वीकृत टिप्पणी")
            table = models.DynamicExtractedTable(document_id=document.id, ocr_result_id=ocr.id, table_index=0, detected_headers=["Parcel"], column_count=1)
            db.add_all([item, table]); db.flush()
            db.add(models.DynamicExtractedCell(table_id=table.id, document_id=document.id, ocr_result_id=ocr.id, row_index=0, column_index=0, header_label="Parcel", ai_value="OCR parcel", final_value="Approved parcel"))
            pending_document = models.Document(file_path="/safe/pending.png", original_filename="pending.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="pending-hash")
            pending_submission = models.Submission(document=pending_document, user=self.citizen, status="PROCESSING")
            db.add(pending_submission); db.flush()
            pending_record = models.VerifiedRecord(record_id="LR-EXPORT-PENDING", submission_id=pending_submission.id, owner_name="Pending", father_guardian_name=None, khasra_number="1", khata_number="2", area="1", village="Rampur", tehsil="Sadar", district="Lucknow", state="UP", verification_status="PROCESSING", verified_by=self.officer.id)
            db.add(pending_record); db.commit()
            self.officer_id, self.citizen_id, self.other_id = self.officer.id, self.citizen.id, self.other.id
            self.record_id, self.pending_record_id = record.id, pending_record.id
        app = FastAPI()
        app.include_router(users.router, prefix="/api/user")
        app.include_router(records.router, prefix="/api/verified-records")
        app.include_router(officer.router, prefix="/api/officer")
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def login_as(self, user_id):
        with self.sessions() as db:
            _, token = new_session(db, db.get(models.User, user_id)); db.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def test_builder_uses_final_values_and_preserves_dynamic_tables(self):
        with self.sessions() as db:
            export = build_verified_record_export(db, db.get(models.VerifiedRecord, self.record_id))
        self.assertEqual(export["export_schema"], "bhumiai_verified_record_v1")
        self.assertEqual(export["fields"]["owner_name"], "Final Owner")
        self.assertEqual(export["legacy_extracted_fields"][0]["value"], "Final Owner")
        self.assertEqual(export["dynamic_fields"][0]["value"], "स्वीकृत टिप्पणी")
        self.assertEqual(export["tables"][0]["rows"][0]["cells"][0]["value"], "Approved parcel")
        self.assertNotIn("RAW OCR MUST NOT WIN", json.dumps(export))

    def test_officer_can_export_and_audit_is_recorded_without_ocr(self):
        self.login_as(self.officer_id)
        with patch("routers.officer.recognize_fast_khatauni", side_effect=AssertionError("export must not run OCR")), patch("routers.officer._load_document_image", side_effect=AssertionError("export must not load image")):
            response = self.client.get(f"/api/verified-records/{self.record_id}/export/json")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["record_id"], "LR-EXPORT-0001")
        self.assertEqual(response.json()["status"], "VERIFIED")
        with self.sessions() as db:
            self.assertTrue(db.query(models.AuditLog).filter_by(action="RECORD_EXPORTED").first())

    def test_citizen_owns_export_and_cannot_export_other_record(self):
        self.login_as(self.citizen_id)
        own = self.client.get(f"/api/user/records/{self.record_id}/export/json")
        self.assertEqual(own.status_code, 200)
        self.login_as(self.other_id)
        denied = self.client.get(f"/api/user/records/{self.record_id}/export/json")
        self.assertEqual(denied.status_code, 403)

    def test_unauthenticated_and_non_verified_exports_are_denied(self):
        self.assertEqual(self.client.get(f"/api/verified-records/{self.record_id}/export/json").status_code, 401)
        self.login_as(self.officer_id)
        response = self.client.get(f"/api/verified-records/{self.pending_record_id}/export/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/verified-records/99999/export/json").status_code, 404)

    def test_csv_uses_canonical_dto_hindi_and_formula_safe_values(self):
        with self.sessions() as db:
            export = build_verified_record_export(db, db.get(models.VerifiedRecord, self.record_id))
            export["dynamic_fields"].append({"field_id": 999, "label": "Formula", "normalized_label": "formula", "value": "=danger"})
        content = export_csv.render_verified_record_csv(export)
        text = content.decode("utf-8-sig")
        self.assertIn("स्वीकृत टिप्पणी", text.replace("\xa0", " "))
        self.assertIn("' =danger".replace("' ", "'"), text)
        self.assertTrue(text.splitlines()[0].startswith("record_id,"))
        self.assertNotIn("/", export_filename("../unsafe/id", "csv"))

    def test_csv_and_pdf_endpoints_are_verified_only_and_audited(self):
        self.login_as(self.officer_id)
        with patch("routers.records.build_verified_record_export", wraps=build_verified_record_export) as builder, \
             patch("routers.officer.recognize_fast_khatauni", side_effect=AssertionError("export must not run OCR")):
            csv_response = self.client.get(f"/api/verified-records/{self.record_id}/export/csv")
            pdf_response = self.client.get(f"/api/verified-records/{self.record_id}/export/pdf")
        self.assertEqual(csv_response.status_code, 200, csv_response.text)
        self.assertTrue(csv_response.headers["content-type"].startswith("text/csv"))
        self.assertIn("attachment", csv_response.headers["content-disposition"])
        self.assertTrue(csv_response.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(pdf_response.status_code, 200, pdf_response.text)
        self.assertEqual(pdf_response.headers["content-type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF-"))
        self.assertGreater(len(builder.call_args_list), 0)
        pdf = fitz.open(stream=pdf_response.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in pdf).replace("\xa0", " ")
        pdf.close()
        self.assertIn("Verified Digital Land Record", text.replace("\xa0", " "))
        self.assertIn("स्वीकृत टिप्पणी", text.replace("\xa0", " "))
        with self.sessions() as db:
            formats = [json.loads(row.metadata_json)["format"] for row in db.query(models.AuditLog).filter_by(action="RECORD_EXPORTED").all()]
        self.assertIn("CSV", formats); self.assertIn("PDF", formats)

    def test_citizen_csv_pdf_ownership_and_missing_table_rows(self):
        self.login_as(self.citizen_id)
        csv_response = self.client.get(f"/api/user/records/{self.record_id}/export/csv")
        pdf_response = self.client.get(f"/api/user/records/{self.record_id}/export/pdf")
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f"/api/user/records/{self.record_id}/export/csv").status_code, 403)
        self.assertEqual(self.client.get(f"/api/user/records/{self.record_id}/export/pdf").status_code, 403)
        columns, rows = export_csv.canonical_export_rows({"record_id": "NO-TABLE", "status": "VERIFIED", "fields": {"village": None}, "tables": []})
        self.assertEqual(len(rows), 1); self.assertIn("village", columns)

    def test_pdf_renders_real_devanagari_value(self):
        with self.sessions() as db:
            export = build_verified_record_export(db, db.get(models.VerifiedRecord, self.record_id))
        export["dynamic_fields"] = [{"label": "\u0917\u093e\u091f\u093e \u0938\u0902\u0916\u094d\u092f\u093e", "value": "\u0938\u094d\u0935\u0940\u0915\u0943\u0924 \u091f\u093f\u092a\u094d\u092a\u0923\u0940"}]
        pdf = fitz.open(stream=export_pdf.render_verified_record_pdf(export), filetype="pdf")
        text = "\n".join(page.get_text() for page in pdf).replace("\xa0", " ")
        pdf.close()
        self.assertIn("\u0938\u094d\u0935\u0940\u0915\u0943\u0924 \u091f\u093f\u092a\u094d\u092a\u0923\u0940", text)

    def test_json_csv_and_pdf_share_final_values_and_table_headers(self):
        self.login_as(self.officer_id)
        json_response = self.client.get(f"/api/verified-records/{self.record_id}/export/json")
        csv_response = self.client.get(f"/api/verified-records/{self.record_id}/export/csv")
        pdf_response = self.client.get(f"/api/verified-records/{self.record_id}/export/pdf")
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        payload = json_response.json()
        csv_text = csv_response.content.decode("utf-8-sig")
        pdf = fitz.open(stream=pdf_response.content, filetype="pdf")
        pdf_text = "\n".join(page.get_text() for page in pdf).replace("\xa0", " ")
        pdf.close()
        self.assertEqual(payload["fields"]["owner_name"], "Final Owner")
        self.assertEqual(payload["tables"][0]["rows"][0]["cells"][0]["value"], "Approved parcel")
        for value in ("Final Owner", "Approved parcel"):
            self.assertIn(value, csv_text)
            self.assertIn(value, pdf_text)
        self.assertIn("Parcel", pdf_text)
        self.assertIn("Field", pdf_text)
        self.assertNotIn("OCR Owner", csv_text)
        self.assertNotIn("OCR Owner", pdf_text)

    def test_pdf_wide_multi_page_table_repeats_headers(self):
        headers = [{"label": f"Column {index}"} for index in range(6)]
        rows = [
            {"cells": [{"column_index": index, "value": f"Long final value {row} " * 3} for index in range(6)]}
            for row in range(24)
        ]
        export = {"record_id": "WIDE", "status": "VERIFIED", "document": {}, "fields": {}, "dynamic_fields": [],
                  "tables": [{"label": "Khatauni Table", "headers": headers, "rows": rows}], "verification": {}}
        pdf = fitz.open(stream=export_pdf.render_verified_record_pdf(export), filetype="pdf")
        text = "\n".join(page.get_text() for page in pdf).replace("\xa0", " ")
        self.assertGreater(pdf.page_count, 1)
        self.assertGreater(pdf[0].rect.width, pdf[0].rect.height)
        self.assertGreaterEqual(text.count("Column 0"), 2)
        pdf.close()

    def test_unavailable_configured_pdf_font_fails_cleanly_without_audit(self):
        with self.sessions() as db:
            export = build_verified_record_export(db, db.get(models.VerifiedRecord, self.record_id))
        missing_font = str(Path(self.directory.name) / "missing-deva-font.ttf")
        with patch.dict(export_pdf.os.environ, {"BHUMIAI_PDF_FONT_PATH": missing_font}):
            with self.assertRaisesRegex(export_pdf.PdfFontUnavailableError, "BHUMIAI_PDF_FONT_PATH"):
                export_pdf.render_verified_record_pdf(export)
        self.login_as(self.officer_id)
        with patch("routers.records.render_verified_record_pdf", side_effect=export_pdf.PdfFontUnavailableError("No usable font")):
            response = self.client.get(f"/api/verified-records/{self.record_id}/export/pdf")
        self.assertEqual(response.status_code, 503)
        with self.sessions() as db:
            self.assertFalse(db.query(models.AuditLog).filter_by(action="RECORD_EXPORTED").first())

    def test_successful_exports_record_minimal_audit_metadata(self):
        self.login_as(self.officer_id)
        for format in ("json", "csv", "pdf"):
            response = self.client.get(f"/api/verified-records/{self.record_id}/export/{format}")
            self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            rows = db.query(models.AuditLog).filter_by(action="RECORD_EXPORTED").order_by(models.AuditLog.id).all()
        self.assertEqual({json.loads(row.metadata_json)["format"] for row in rows}, {"JSON", "CSV", "PDF"})
        for row in rows:
            self.assertEqual(row.user_id, self.officer_id)
            self.assertEqual(row.record_id, self.record_id)
            self.assertIsNotNone(row.submission_id)
            self.assertIsNotNone(row.timestamp)
            self.assertEqual(set(json.loads(row.metadata_json)), {"format"})

    def test_non_verified_status_blocks_every_export_format(self):
        self.login_as(self.officer_id)
        for format in ("json", "csv", "pdf"):
            response = self.client.get(f"/api/verified-records/{self.pending_record_id}/export/{format}")
            self.assertEqual(response.status_code, 409)
        with self.sessions() as db:
            record = db.get(models.VerifiedRecord, self.pending_record_id)
            record.verification_status = "REJECTED"
            db.commit()
        for format in ("json", "csv", "pdf"):
            response = self.client.get(f"/api/verified-records/{self.pending_record_id}/export/{format}")
            self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
