import datetime
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import officer
from security import SESSION_COOKIE_NAME, new_session
from services.structured_duplicate import check_structured_duplicate


class StructuredDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-structured-duplicate-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'structured.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            self.officer = models.User(name="Officer", email="officer@example.test", role="officer")
            self.citizen = models.User(name="Citizen", email="citizen@example.test", role="user", phone_number="+919876543210", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            db.add_all([self.officer, self.citizen]); db.commit()
            self.officer_id, self.citizen_id = self.officer.id, self.citizen.id
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

    @staticmethod
    def identity(khata="42", holder="Ram", area="0.750", plot="118"):
        return {"district": "Lucknow", "village_name": "Rampur", "khata_number": khata}, [{"plot_number": plot, "holder_name": holder, "guardian_name": "Mohan", "area": area}]

    def add_record(self, *, status="SUBMITTED", headers=None, parcels=None, verified=False):
        self.sequence += 1
        with self.sessions() as db:
            document = models.Document(file_path="record.png", original_filename="record.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash=f"structured-{self.sequence}")
            submission = models.Submission(document=document, user_id=self.citizen_id, status=status)
            db.add(submission); db.flush()
            for index, (key, value) in enumerate((headers or {}).items()):
                db.add(models.DynamicExtractedItem(document_id=document.id, item_type="key_value", display_order=index, ai_value=str(value), audit_metadata_json={"schema_key": key}))
            rows = parcels or []
            if rows:
                table = models.DynamicExtractedTable(document_id=document.id, table_index=0, detected_headers=list(rows[0]), column_count=len(rows[0]))
                db.add(table); db.flush()
                for row_index, row in enumerate(rows):
                    for column_index, (key, value) in enumerate(row.items()):
                        db.add(models.DynamicExtractedCell(table_id=table.id, document_id=document.id, row_index=row_index, column_index=column_index, ai_value=str(value), audit_metadata_json={"schema_key": key}))
            if verified:
                db.add(models.VerifiedRecord(record_id=f"LR-UP-LUC-{submission.id:06d}", submission_id=submission.id, owner_name="", father_guardian_name="", khasra_number="", khata_number="", area="", village="Rampur", tehsil="Sadar", district="Lucknow", state="UP", verification_status="VERIFIED", verified_by=self.officer_id))
            db.commit()
            return document.id, submission.id

    def result(self, document_id):
        with self.sessions() as db:
            return check_structured_duplicate(db, document_id)

    def test_no_verified_records_returns_no_match(self):
        headers, parcels = self.identity(); document_id, _ = self.add_record(headers=headers, parcels=parcels)
        self.assertEqual(self.result(document_id)["status"], "NO_MATCH")

    def test_matching_verified_record_is_possible_duplicate(self):
        headers, parcels = self.identity(); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        document_id, _ = self.add_record(headers=headers, parcels=parcels)
        result = self.result(document_id)
        self.assertEqual(result["status"], "POSSIBLE_DUPLICATE")
        self.assertEqual(result["matches"][0]["matched_plots"], ["118"])
        self.assertIn("holder_name", result["matches"][0]["matching_fields"])

    def test_area_or_holder_conflict_is_not_a_structured_duplicate(self):
        headers, parcels = self.identity(); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        changed_headers, changed_parcels = self.identity(area="0.650")
        changed_document, _ = self.add_record(headers=changed_headers, parcels=changed_parcels)
        other_headers, other_parcels = self.identity(holder="Shyam")
        other_document, _ = self.add_record(headers=other_headers, parcels=other_parcels)
        self.assertEqual(self.result(changed_document)["status"], "NO_MATCH")
        self.assertEqual(self.result(other_document)["status"], "NO_MATCH")

    def test_unrelated_verified_record_is_ignored(self):
        headers, parcels = self.identity(); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        unrelated_headers, unrelated_parcels = self.identity(khata="99", plot="999")
        document_id, _ = self.add_record(headers=unrelated_headers, parcels=unrelated_parcels)
        self.assertEqual(self.result(document_id)["status"], "NO_MATCH")

    def test_unverified_reference_statuses_are_ignored(self):
        headers, parcels = self.identity()
        for status in ("SUBMITTED", "PROCESSING", "NEEDS_REVIEW", "REJECTED"):
            self.add_record(status=status, headers=headers, parcels=parcels)
        document_id, _ = self.add_record(headers=headers, parcels=parcels)
        self.assertEqual(self.result(document_id)["status"], "NO_MATCH")

    def test_current_document_is_excluded(self):
        headers, parcels = self.identity(); document_id, _ = self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        self.assertEqual(self.result(document_id)["status"], "NO_MATCH")

    def test_final_value_and_devanagari_digits_normalize(self):
        headers, parcels = self.identity(khata="42", plot="118"); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        current_headers, current_parcels = self.identity(khata="४२", plot="११८")
        document_id, _ = self.add_record(headers=current_headers, parcels=current_parcels)
        with self.sessions() as db:
            plot_cell = db.query(models.DynamicExtractedCell).filter_by(document_id=document_id).first()
            plot_cell.ai_value = "bad"; plot_cell.final_value = "११८"; db.commit()
        self.assertEqual(self.result(document_id)["status"], "POSSIBLE_DUPLICATE")

    def test_fallback_plot_identity_requires_missing_khata_and_weak_name_is_not_enough(self):
        reference_headers, parcels = self.identity(khata="", holder="Ram Kumar"); self.add_record(status="VERIFIED", headers=reference_headers, parcels=parcels, verified=True)
        fallback_headers, fallback_parcels = self.identity(khata="", holder="Ram Kumar")
        fallback_document, _ = self.add_record(headers=fallback_headers, parcels=fallback_parcels)
        weak_headers, weak_parcels = self.identity(khata="", holder="RamKumar")
        weak_document, _ = self.add_record(headers=weak_headers, parcels=weak_parcels)
        self.assertEqual(self.result(fallback_document)["status"], "POSSIBLE_DUPLICATE")
        self.assertEqual(self.result(weak_document)["status"], "NO_MATCH")

    def test_endpoint_is_officer_only_audited_and_non_mutating(self):
        headers, parcels = self.identity(); document_id, submission_id = self.add_record(headers=headers, parcels=parcels)
        self.login_as(self.citizen_id)
        self.assertEqual(self.client.get(f"/api/officer/documents/{document_id}/structured-duplicate-check").status_code, 403)
        self.login_as(self.officer_id)
        response = self.client.get(f"/api/officer/documents/{document_id}/structured-duplicate-check")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "NO_MATCH")
        with self.sessions() as db:
            self.assertEqual(db.get(models.Submission, submission_id).status, "SUBMITTED")
            self.assertTrue(db.query(models.AuditLog).filter_by(document_id=document_id, action="STRUCTURED_DUPLICATE_CHECKED").first())


if __name__ == "__main__":
    unittest.main()
