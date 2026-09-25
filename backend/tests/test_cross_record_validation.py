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
from services.cross_record_validation import normalize_value, validate_cross_record


class CrossRecordValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-cross-record-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'cross-record.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            self.officer = models.User(name="Officer", email="officer@example.test", role="officer")
            self.citizen = models.User(name="Citizen", email="citizen@example.test", role="user", phone_number="+919876543210", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            self.other = models.User(name="Other", email="other@example.test", role="user", phone_number="+919876543211", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            db.add_all([self.officer, self.citizen, self.other]); db.commit()
            self.officer_id, self.citizen_id, self.other_id = self.officer.id, self.citizen.id, self.other.id
        app = FastAPI(); app.include_router(officer.router, prefix="/api/officer")
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def login_as(self, user_id):
        with self.sessions() as db:
            _, token = new_session(db, db.get(models.User, user_id)); db.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def add_record(self, *, status="SUBMITTED", headers=None, parcels=None, verified=False, user_id=None, file_hash=None):
        headers, parcels = headers or {}, parcels or []
        with self.sessions() as db:
            document = models.Document(file_path="record.png", original_filename="record.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash=file_hash or f"hash-{datetime.datetime.utcnow().timestamp()}")
            submission = models.Submission(document=document, user_id=user_id or self.citizen_id, status=status)
            db.add(submission); db.flush()
            for index, (key, value) in enumerate(headers.items()):
                db.add(models.DynamicExtractedItem(document_id=document.id, item_type="key_value", display_order=index, ai_value=str(value), audit_metadata_json={"schema_key": key}))
            if parcels:
                table = models.DynamicExtractedTable(document_id=document.id, table_index=0, detected_headers=list(parcels[0]), column_count=len(parcels[0]))
                db.add(table); db.flush()
                for row_index, row in enumerate(parcels):
                    for column_index, (key, value) in enumerate(row.items()):
                        db.add(models.DynamicExtractedCell(table_id=table.id, document_id=document.id, row_index=row_index, column_index=column_index, ai_value=str(value), audit_metadata_json={"schema_key": key}))
            if verified:
                db.add(models.VerifiedRecord(record_id=f"LR-UP-LUC-{submission.id:06d}", submission_id=submission.id, owner_name="", father_guardian_name="", khasra_number="", khata_number="", area="", village="Rampur", tehsil="Sadar", district="Lucknow", state="UP", verification_status="VERIFIED", verified_by=self.officer_id))
            db.commit()
            return document.id, submission.id

    @staticmethod
    def identity(khata="42", holder="Ram", area="0.750"):
        return {"district": "Lucknow", "village_name": "Rampur", "khata_number": khata, "holder_name": holder}, [{"plot_number": "118", "holder_name": holder, "area": area}]

    def test_no_reference_and_insufficient_data(self):
        headers, parcels = self.identity(); document_id, _ = self.add_record(headers=headers, parcels=parcels)
        with self.sessions() as db:
            self.assertEqual(validate_cross_record(db, document_id)["status"], "NO_REFERENCE")
        missing_id, _ = self.add_record(headers={"district": "Lucknow"})
        with self.sessions() as db:
            self.assertEqual(validate_cross_record(db, missing_id)["status"], "INSUFFICIENT_DATA")

    def test_consistent_and_area_difference(self):
        headers, parcels = self.identity(); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        current_id, _ = self.add_record(headers=headers, parcels=parcels)
        changed_headers, changed_parcels = self.identity(area="0.650"); changed_id, _ = self.add_record(headers=changed_headers, parcels=changed_parcels)
        with self.sessions() as db:
            self.assertEqual(validate_cross_record(db, current_id)["status"], "CONSISTENT")
            changed = validate_cross_record(db, changed_id)
            self.assertEqual(changed["status"], "REVIEW_REQUIRED")
            self.assertEqual(changed["references"][0]["differences"][0]["field"], "area")

    def test_holder_difference_and_non_verified_records_are_ignored(self):
        headers, parcels = self.identity(holder="Ram"); self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        for status in ("SUBMITTED", "NEEDS_REVIEW", "REJECTED"):
            self.add_record(status=status, headers=headers, parcels=parcels, verified=False)
        current_headers, current_parcels = self.identity(holder="Shyam"); current_id, _ = self.add_record(headers=current_headers, parcels=current_parcels)
        with self.sessions() as db:
            result = validate_cross_record(db, current_id)
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertEqual(result["candidate_count"], 1)
            self.assertTrue(any(item["field"] == "holder_name" for item in result["references"][0]["differences"]))

    def test_current_document_is_excluded_and_final_value_wins(self):
        headers, parcels = self.identity(); document_id, submission_id = self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        with self.sessions() as db:
            item = db.query(models.DynamicExtractedItem).filter_by(document_id=document_id).first()
            item.ai_value, item.officer_value, item.final_value = "wrong", "also wrong", "Lucknow"
            db.commit()
            result = validate_cross_record(db, document_id)
            self.assertEqual(result["status"], "NO_REFERENCE")
            self.assertEqual(db.get(models.Submission, submission_id).status, "VERIFIED")

    def test_final_value_priority_and_devanagari_digits(self):
        headers, parcels = self.identity(khata="42"); reference_id, _ = self.add_record(status="VERIFIED", headers=headers, parcels=parcels, verified=True)
        current_headers, current_parcels = self.identity(khata="४२"); current_id, _ = self.add_record(headers=current_headers, parcels=current_parcels)
        with self.sessions() as db:
            current_khata = db.query(models.DynamicExtractedItem).filter_by(document_id=current_id).filter(models.DynamicExtractedItem.audit_metadata_json["schema_key"].as_string() == "khata_number").first()
            current_khata.ai_value, current_khata.officer_value, current_khata.final_value = "99", "98", "४२"
            db.commit()
            self.assertEqual(normalize_value("  ४२ /  "), "42/")
            self.assertEqual(validate_cross_record(db, current_id)["status"], "CONSISTENT")

    def test_endpoint_is_officer_only_audited_and_non_mutating(self):
        headers, parcels = self.identity(); document_id, submission_id = self.add_record(headers=headers, parcels=parcels)
        self.login_as(self.citizen_id)
        self.assertEqual(self.client.get(f"/api/officer/documents/{document_id}/cross-record-validation").status_code, 403)
        self.login_as(self.officer_id)
        response = self.client.get(f"/api/officer/documents/{document_id}/cross-record-validation")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "NO_REFERENCE")
        with self.sessions() as db:
            self.assertEqual(db.get(models.Submission, submission_id).status, "SUBMITTED")
            self.assertTrue(db.query(models.AuditLog).filter_by(document_id=document_id, action="CROSS_RECORD_VALIDATION_RUN").first())


if __name__ == "__main__":
    unittest.main()
