import datetime
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import officer
from security import SESSION_COOKIE_NAME, new_session
from services.training_feedback import export_verified_feedback_dataset


class AITrainingFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-feedback-")
        self.root = Path(self.directory.name)
        self.image_path = self.root / "source.png"
        Image.new("L", (100, 60), color=255).save(self.image_path)
        self.engine = create_engine(f"sqlite:///{self.root / 'feedback.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            officer_user = models.User(name="Officer", email="officer@example.test", role="officer")
            citizen = models.User(name="Citizen", email="citizen@example.test", role="user", phone_number="+919876543210", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            db.add_all([officer_user, citizen]); db.commit()
            self.officer_id, self.citizen_id = officer_user.id, citizen.id
        app = FastAPI(); app.include_router(officer.router, prefix="/api/officer")
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.sequence = 0

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def login_as(self, user_id):
        with self.sessions() as db:
            _, token = new_session(db, db.get(models.User, user_id)); db.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def add_document(self, *, bbox=True):
        self.sequence += 1
        with self.sessions() as db:
            document = models.Document(file_path=str(self.image_path), original_filename="record.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash=f"feedback-{self.sequence}")
            submission = models.Submission(document=document, user_id=self.citizen_id, status="SUBMITTED")
            db.add(submission); db.flush()
            ocr = models.OCRResult(document_id=document.id, engine="tesseract", script="Devanagari", raw_text="118", processed_image_path=str(self.image_path), layout_metadata_json='{"hybrid_recognition":{"htr_model":"aayushpuri01/TrOCR-Devanagari"}}')
            db.add(ocr); db.flush()
            item = models.DynamicExtractedItem(document_id=document.id, ocr_result_id=ocr.id, item_type="key_value", original_label="Plot", normalized_label="plot_number", raw_ocr_value="118", ai_value="118", ai_confidence=58.0, confidence_source="recognition_evidence_v2", bounding_box={"left": 5, "top": 5, "width": 30, "height": 20} if bbox else None, source_token_ids=[1, 2], audit_metadata_json={"schema_key": "plot_number", "recognition_evidence": {"selected_engine": "local_htr"}})
            db.add(item); db.commit()
            return document.id, submission.id, item.id

    def edit(self, document_id, item_id, value):
        return self.client.patch(f"/api/officer/documents/{document_id}/dynamic-fields/{item_id}", json={"officer_value": value})

    def add_cell(self, document_id):
        with self.sessions() as db:
            ocr = db.query(models.OCRResult).filter_by(document_id=document_id).first()
            table = models.DynamicExtractedTable(document_id=document_id, ocr_result_id=ocr.id, table_index=0, detected_headers=["Plot"])
            db.add(table); db.flush()
            cell = models.DynamicExtractedCell(table_id=table.id, document_id=document_id, ocr_result_id=ocr.id, row_index=0, column_index=0, header_label="Plot", raw_ocr_value="118", ai_value="118", ai_confidence=55.0, confidence_source="recognition_evidence_v2", bounding_box={"left": 5, "top": 5, "width": 30, "height": 20}, audit_metadata_json={"schema_key": "plot_number"})
            db.add(cell); db.commit()
            return table.id, cell.id

    def feedback_rows(self, document_id):
        with self.sessions() as db:
            return db.query(models.AITrainingFeedback).filter_by(document_id=document_id).all()

    def test_unchanged_value_does_not_create_feedback(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.assertEqual(self.edit(document_id, item_id, "118").status_code, 200)
        self.assertEqual(self.feedback_rows(document_id), [])

    def test_correction_creates_pending_feedback_without_mutating_ocr_evidence(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.assertEqual(self.edit(document_id, item_id, "118/2").status_code, 200)
        rows = self.feedback_rows(document_id)
        self.assertEqual(len(rows), 1)
        sample = rows[0]
        self.assertEqual((sample.sample_status, sample.ai_prediction, sample.raw_ocr_value, sample.officer_correction), ("PENDING", "118", "118", "118/2"))
        self.assertEqual((sample.recognition_engine, sample.model_version, sample.source_token_ids), ("local_htr", "aayushpuri01/TrOCR-Devanagari", [1, 2]))
        with self.sessions() as db:
            item = db.get(models.DynamicExtractedItem, item_id)
            self.assertEqual((item.raw_ocr_value, item.ai_value), ("118", "118"))
            self.assertTrue(db.query(models.AuditLog).filter_by(document_id=document_id, action="AI_FEEDBACK_CAPTURED").first())

    def test_repeated_edit_updates_the_pending_candidate(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.edit(document_id, item_id, "118/2"); self.edit(document_id, item_id, "118-1")
        rows = self.feedback_rows(document_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].officer_correction, "118-1")

    def test_final_value_and_cell_correction_are_captured(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.assertEqual(self.client.patch(f"/api/officer/documents/{document_id}/dynamic-fields/{item_id}", json={"final_value": "118/2"}).status_code, 200)
        table_id, cell_id = self.add_cell(document_id)
        self.assertEqual(self.client.patch(f"/api/officer/documents/{document_id}/tables/{table_id}/cells/{cell_id}", json={"officer_value": "118-1"}).status_code, 200)
        rows = self.feedback_rows(document_id)
        self.assertEqual({(row.entity_type, row.officer_correction) for row in rows}, {("field", "118/2"), ("cell", "118-1")})

    def test_needs_review_keeps_feedback_pending_and_verify_promotes_it(self):
        document_id, submission_id, item_id = self.add_document(); self.login_as(self.officer_id)
        self.edit(document_id, item_id, "118/2")
        self.assertEqual(self.client.post(f"/api/officer/documents/{document_id}/mark-review").status_code, 200)
        self.assertEqual(self.feedback_rows(document_id)[0].sample_status, "PENDING")
        self.assertEqual(self.client.post(f"/api/officer/documents/{document_id}/approve").status_code, 200)
        rows = self.feedback_rows(document_id)
        self.assertEqual(rows[0].sample_status, "VERIFIED_SAMPLE")
        self.assertEqual(rows[0].verified_by, self.officer_id)
        self.assertIsNotNone(rows[0].verified_at)
        with self.sessions() as db:
            self.assertEqual(db.get(models.Submission, submission_id).status, "VERIFIED")
            self.assertTrue(db.query(models.AuditLog).filter_by(document_id=document_id, action="AI_FEEDBACK_VERIFIED").first())

    def test_rejection_excludes_pending_feedback(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.edit(document_id, item_id, "118/2")
        response = self.client.post(f"/api/officer/documents/{document_id}/reject", json={"reason_category": "Information Mismatch", "officer_note": "Officer review"})
        self.assertEqual(response.status_code, 200, response.text)
        sample = self.feedback_rows(document_id)[0]
        self.assertEqual(sample.sample_status, "EXCLUDED")
        self.assertIn("Information Mismatch", sample.exclusion_reason)

    def test_terminal_record_stays_immutable(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id)
        self.edit(document_id, item_id, "118/2")
        self.assertEqual(self.client.post(f"/api/officer/documents/{document_id}/approve").status_code, 200)
        self.assertEqual(self.edit(document_id, item_id, "118-1").status_code, 409)
        self.assertEqual(self.feedback_rows(document_id)[0].officer_correction, "118/2")

    def test_summary_is_officer_only_and_list_is_technical_only(self):
        document_id, _, item_id = self.add_document(); self.login_as(self.officer_id); self.edit(document_id, item_id, "118/2")
        self.login_as(self.citizen_id)
        self.assertEqual(self.client.get("/api/officer/ai-feedback/summary").status_code, 403)
        self.login_as(self.officer_id)
        summary = self.client.get("/api/officer/ai-feedback/summary").json()
        self.assertEqual((summary["pending"], summary["by_schema_key"]["plot_number"]), (1, 1))
        listed = self.client.get("/api/officer/ai-feedback", params={"status": "PENDING", "schema_key": "plot_number"}).json()
        self.assertEqual(len(listed), 1)
        self.assertNotIn("phone_number", str(listed))

    def test_export_excludes_pending_and_excluded_samples(self):
        pending_doc, _, pending_item = self.add_document(); excluded_doc, _, excluded_item = self.add_document()
        self.login_as(self.officer_id); self.edit(pending_doc, pending_item, "118/2"); self.edit(excluded_doc, excluded_item, "118/2")
        self.client.post(f"/api/officer/documents/{excluded_doc}/reject", json={"reason_category": "Information Mismatch", "officer_note": "Officer review"})
        with self.sessions() as db:
            result = export_verified_feedback_dataset(db, self.root / "exports"); db.commit()
        self.assertEqual((result["total_verified_samples"], result["image_trainable_samples"]), (0, 0))

    def test_verified_sample_exports_crop_and_missing_box_is_skipped_safely(self):
        crop_doc, _, crop_item = self.add_document(bbox=True); missing_doc, _, missing_item = self.add_document(bbox=False)
        self.login_as(self.officer_id)
        for document_id, item_id in ((crop_doc, crop_item), (missing_doc, missing_item)):
            self.edit(document_id, item_id, "118/2")
            self.assertEqual(self.client.post(f"/api/officer/documents/{document_id}/approve").status_code, 200)
        with self.sessions() as db:
            result = export_verified_feedback_dataset(db, self.root / "exports"); db.commit()
            self.assertEqual(result["total_verified_samples"], 2)
            self.assertEqual(result["image_trainable_samples"], 1)
            self.assertEqual(result["samples_missing_usable_crop"], 1)
            self.assertTrue((Path(result["export_directory"]) / "images" / "sample_000001.png").exists())
            self.assertTrue(db.query(models.AuditLog).filter_by(action="AI_FEEDBACK_DATASET_EXPORTED").first())


if __name__ == "__main__":
    unittest.main()
