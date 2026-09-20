from __future__ import annotations

import tempfile
import unittest
import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import documents, officer, users
from security import SESSION_COOKIE_NAME, new_session


class DuplicateResolutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-duplicate-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'duplicates.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine); self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            officer_user = models.User(name="Officer", email="officer@example.test", role="officer")
            owner = models.User(name="Original Owner", email="owner@example.test", role="user", phone_number="+919876543210", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            uploader = models.User(name="New Uploader", email="new@example.test", role="user", phone_number="+919876543211", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            unrelated = models.User(name="Unrelated", email="unrelated@example.test", role="user", phone_number="+919876543212", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            db.add_all([officer_user, owner, uploader, unrelated]); db.flush()
            existing_doc = models.Document(file_path="existing.pdf", original_filename="original-khatauni.pdf", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="exact-hash")
            existing = models.Submission(document=existing_doc, user=owner, status="VERIFIED")
            current_doc = models.Document(file_path="current.pdf", original_filename="resubmitted-khatauni.pdf", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="exact-hash")
            current = models.Submission(document=current_doc, user=uploader, status="SUBMITTED")
            unique_doc = models.Document(file_path="unique.pdf", original_filename="unique.pdf", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="unique-hash")
            db.add_all([existing, current, unique_doc]); db.flush()
            record = models.VerifiedRecord(record_id="LR-UP-LUC-000014", submission_id=existing.id, owner_name="", father_guardian_name="", khasra_number="", khata_number="", area="", village="Rampur", tehsil="Sadar", district="Lucknow", state="UP", verification_status="VERIFIED", verified_by=officer_user.id)
            db.add(record); db.commit()
            self.officer_id, self.owner_id, self.uploader_id, self.unrelated_id = officer_user.id, owner.id, uploader.id, unrelated.id
            self.current_doc_id, self.current_submission_id, self.unique_doc_id = current_doc.id, current.id, unique_doc.id
            self.existing_doc_id, self.existing_submission_id, self.record_id = existing_doc.id, existing.id, record.id
        app = FastAPI(); app.include_router(documents.router, prefix="/api/documents"); app.include_router(officer.router, prefix="/api/officer"); app.include_router(users.router, prefix="/api/user")
        def database():
            with self.sessions() as db: yield db
        app.dependency_overrides[get_db] = database; self.client = TestClient(app)

    def login_as(self, user_id):
        with self.sessions() as db:
            _, token = new_session(db, db.get(models.User, user_id)); db.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def test_unique_file_reports_none_without_processing(self):
        self.login_as(self.officer_id)
        with patch.object(officer, "recognize_fast_khatauni", side_effect=AssertionError("duplicate check must not OCR")), \
                patch.object(officer, "_load_document_image", side_effect=AssertionError("duplicate check must not load image")):
            response = self.client.post(f"/api/documents/{self.unique_doc_id}/duplicate-check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_type"], "NONE")
        self.assertFalse(response.json()["duplicate"])

    def test_exact_match_returns_verified_reference_and_never_auto_rejects(self):
        self.login_as(self.officer_id)
        response = self.client.post(f"/api/documents/{self.current_doc_id}/duplicate-check")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["duplicate"])
        self.assertEqual(payload["match_type"], "EXACT_FILE_HASH")
        self.assertEqual(payload["matched_document_id"], self.existing_doc_id)
        self.assertEqual(payload["matched_submission_id"], self.existing_submission_id)
        self.assertEqual(payload["matched_status"], "VERIFIED")
        self.assertEqual(payload["current_status"], "SUBMITTED")
        self.assertEqual(payload["verified_record_id"], self.record_id)
        self.assertEqual(payload["verified_record_code"], "LR-UP-LUC-000014")
        self.assertEqual(payload["related_submissions"], [
            {"document_id": self.existing_doc_id, "submission_id": self.existing_submission_id, "status": "VERIFIED"},
            {"document_id": self.current_doc_id, "submission_id": self.current_submission_id, "status": "SUBMITTED"},
        ])
        self.login_as(self.owner_id)
        self.assertTrue(self.client.get("/api/user/notifications").json() == [])
        self.login_as(self.officer_id)
        rows = self.client.get("/api/officer/submissions", params={"status": "SUBMITTED"}).json()
        self.assertIn(self.current_submission_id, [row["id"] for row in rows])
        with self.sessions() as db:
            self.assertTrue(db.query(models.AuditLog).filter_by(action="DUPLICATE_CHECKED", document_id=self.current_doc_id).first())

    def test_rejected_match_includes_its_existing_rejection_reason(self):
        self.login_as(self.officer_id)
        with self.sessions() as db:
            source_doc = models.Document(file_path="prior.pdf", original_filename="prior.pdf", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="rejected-hash")
            source = models.Submission(document=source_doc, user_id=self.owner_id, status="REJECTED")
            current_doc = models.Document(file_path="retry.pdf", original_filename="retry.pdf", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash="rejected-hash")
            current = models.Submission(document=current_doc, user_id=self.uploader_id, status="SUBMITTED")
            db.add_all([source, current]); db.flush()
            db.add(models.AuditLog(document_id=source_doc.id, submission_id=source.id, user_id=self.officer_id,
                action="REJECTED", metadata_json='{"reason_category":"Poor Scan Quality","officer_note":"Please upload a clearer scan."}'))
            db.commit(); current_doc_id = current_doc.id
        response = self.client.post(f"/api/documents/{current_doc_id}/duplicate-check")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["matched_status"], "REJECTED")
        self.assertEqual(payload["previous_rejection"]["reason_category"], "Poor Scan Quality")
        self.assertEqual(payload["previous_rejection"]["officer_note"], "Please upload a clearer scan.")

    def test_continue_override_preserves_both_submissions(self):
        self.login_as(self.officer_id)
        self.client.post(f"/api/documents/{self.current_doc_id}/duplicate-check")
        response = self.client.post(f"/api/documents/{self.current_doc_id}/duplicate-continue", params={"matched_document_id": self.existing_doc_id})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(models.Submission, self.current_submission_id).status, "SUBMITTED")
            self.assertEqual(db.get(models.Submission, self.existing_submission_id).status, "VERIFIED")
            self.assertTrue(db.query(models.AuditLog).filter_by(action="DUPLICATE_OVERRIDE_CONTINUE", document_id=self.current_doc_id).first())

    def test_duplicate_rejection_notifies_owner_without_exposing_uploader(self):
        self.login_as(self.officer_id)
        self.client.post(f"/api/documents/{self.current_doc_id}/duplicate-check")
        rejected = self.client.post(f"/api/officer/documents/{self.current_doc_id}/reject", json={"reason_category": "Duplicate Submission", "officer_note": "This submission exactly matches existing verified record LR-UP-LUC-000014."})
        self.assertEqual(rejected.status_code, 200)
        self.login_as(self.uploader_id)
        uploader_rows = self.client.get("/api/user/submissions", params={"status": "REJECTED"}).json()
        self.assertEqual(uploader_rows[0]["rejection"]["reason_category"], "Duplicate Submission")
        self.assertNotIn("Original Owner", str(uploader_rows))
        self.login_as(self.owner_id)
        notices = self.client.get("/api/user/notifications").json()
        self.assertEqual(len(notices), 1)
        self.assertIn("LR-UP-LUC-000014", notices[0]["message"])
        self.assertNotIn("New Uploader", notices[0]["message"])
        self.login_as(self.unrelated_id)
        self.assertEqual(self.client.get("/api/user/notifications").json(), [])


if __name__ == "__main__":
    unittest.main()
