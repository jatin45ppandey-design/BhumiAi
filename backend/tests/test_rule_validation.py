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
from services.rule_validation import validate_rule_based


class RuleValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-rule-validation-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'rules.db'}", connect_args={"check_same_thread": False})
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

    def add_record(self, headers=None, parcels=None):
        self.sequence += 1
        with self.sessions() as db:
            document = models.Document(file_path="record.png", original_filename="record.png", document_type="Khatauni", state="UP", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash=f"rule-{self.sequence}")
            submission = models.Submission(document=document, user_id=self.citizen_id, status="SUBMITTED")
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
            db.commit()
            return document.id, submission.id

    @staticmethod
    def valid_headers(khata="42"):
        return {"district": "Lucknow", "village_name": "Rampur", "khata_number": khata}

    @staticmethod
    def valid_row(plot="118", area="0.750"):
        return {"plot_number": plot, "holder_name": "Ram", "area": area}

    def result(self, document_id):
        with self.sessions() as db:
            return validate_rule_based(db, document_id)

    def test_valid_reviewed_record_passes(self):
        document_id, _ = self.add_record(self.valid_headers(), [self.valid_row()])
        self.assertEqual(self.result(document_id)["status"], "PASS")

    def test_missing_location_and_khata_require_review(self):
        missing_location, _ = self.add_record({"khata_number": "42"}, [self.valid_row()])
        missing_khata, _ = self.add_record({"district": "Lucknow", "village_name": "Rampur"}, [self.valid_row()])
        self.assertEqual(self.result(missing_location)["status"], "REVIEW_REQUIRED")
        self.assertEqual(self.result(missing_khata)["status"], "REVIEW_REQUIRED")

    def test_meaningful_row_without_plot_requires_review_but_empty_row_is_ignored(self):
        missing_plot, _ = self.add_record(self.valid_headers(), [{"holder_name": "Ram", "area": "1"}])
        empty_row, _ = self.add_record(self.valid_headers(), [{}])
        self.assertEqual(self.result(missing_plot)["status"], "REVIEW_REQUIRED")
        self.assertEqual(self.result(empty_row)["status"], "PASS")

    def test_invalid_area_values_require_review(self):
        for area in ("-0.5", "0", "abc"):
            with self.subTest(area=area):
                document_id, _ = self.add_record(self.valid_headers(), [self.valid_row(area=area)])
                result = self.result(document_id)
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertTrue(any(rule["rule_id"] == "RV-04" and rule["status"] == "REVIEW" for rule in result["rules"]))

    def test_positive_ascii_and_devanagari_areas_pass(self):
        for area in ("1", "0.750", "१२.५०"):
            with self.subTest(area=area):
                document_id, _ = self.add_record(self.valid_headers(), [self.valid_row(area=area)])
                self.assertEqual(self.result(document_id)["status"], "PASS")

    def test_repeated_plot_requires_review(self):
        document_id, _ = self.add_record(self.valid_headers(), [self.valid_row(), self.valid_row(area="1.5")])
        result = self.result(document_id)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(any(rule["rule_id"] == "RV-05" and rule["status"] == "REVIEW" for rule in result["rules"]))

    def test_supported_and_malformed_numeric_identifier_formats(self):
        for plot in ("118/2", "118-1", "118.2"):
            with self.subTest(plot=plot):
                document_id, _ = self.add_record(self.valid_headers(), [self.valid_row(plot=plot)])
                self.assertEqual(self.result(document_id)["status"], "PASS")
        malformed, _ = self.add_record(self.valid_headers("forty-two"), [self.valid_row(plot="118A")])
        result = self.result(malformed)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertGreaterEqual(sum(rule["rule_id"] == "RV-06" and rule["status"] == "REVIEW" for rule in result["rules"]), 2)

    def test_final_value_overrides_ai_value(self):
        document_id, _ = self.add_record(self.valid_headers(), [self.valid_row(plot="bad")])
        with self.sessions() as db:
            cell = db.query(models.DynamicExtractedCell).filter_by(document_id=document_id).first()
            cell.final_value = "118/2"; db.commit()
        self.assertEqual(self.result(document_id)["status"], "PASS")

    def test_endpoint_is_officer_only_audited_and_non_mutating(self):
        document_id, submission_id = self.add_record(self.valid_headers(), [self.valid_row()])
        self.login_as(self.citizen_id)
        self.assertEqual(self.client.get(f"/api/officer/documents/{document_id}/rule-validation").status_code, 403)
        self.login_as(self.officer_id)
        response = self.client.get(f"/api/officer/documents/{document_id}/rule-validation")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "PASS")
        with self.sessions() as db:
            self.assertEqual(db.get(models.Submission, submission_id).status, "SUBMITTED")
            audit = db.query(models.AuditLog).filter_by(document_id=document_id, action="RULE_VALIDATION_RUN").first()
            self.assertTrue(audit)


if __name__ == "__main__":
    unittest.main()
