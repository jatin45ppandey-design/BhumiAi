from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import officer, records, users


class DashboardWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-dashboard-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'workspace.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            self.officer = models.User(name="Officer", email="officer@example.test", role="officer")
            self.citizen = models.User(name="Ram Citizen", email="ram@example.test", role="user")
            self.other_citizen = models.User(name="Other Citizen", email="other@example.test", role="user")
            db.add_all([self.officer, self.citizen, self.other_citizen]); db.flush()
            self.submissions = {}
            for index, status in enumerate(("SUBMITTED", "PROCESSING", "NEEDS_REVIEW", "VERIFIED", "REJECTED"), start=1):
                document = models.Document(file_path=f"/safe/{index}.png", original_filename=f"{status.lower()}-rampur.png",
                    document_type="Khatauni", state="Uttar Pradesh", district="Lucknow", tehsil="Sadar", village="Rampur", file_hash=f"hash-{index}")
                submission = models.Submission(document=document, user=self.citizen, status=status)
                db.add(submission); db.flush(); self.submissions[status] = submission.id
                if status == "VERIFIED":
                    db.add(models.VerifiedRecord(record_id="LR-UP-LUC-000001", submission_id=submission.id, owner_name="Ram",
                        father_guardian_name="", khasra_number="1", khata_number="2", area="3", village="Rampur", tehsil="Sadar", district="Lucknow", state="Uttar Pradesh", verification_status="VERIFIED", verified_by=self.officer.id))
            other_document = models.Document(file_path="/safe/other.png", original_filename="other-secret.png", document_type="Khatauni", state="UP", district="Other", tehsil="Other", village="Elsewhere", file_hash="other-hash")
            self.other_submission = models.Submission(document=other_document, user=self.other_citizen, status="REJECTED")
            db.add(self.other_submission); db.commit()
            self.officer_id, self.citizen_id, self.other_citizen_id = self.officer.id, self.citizen.id, self.other_citizen.id
            self.rejected_document_id = db.get(models.Submission, self.submissions["REJECTED"]).document_id
            db.add(models.AuditLog(document_id=self.rejected_document_id, submission_id=self.submissions["REJECTED"], user_id=self.officer_id,
                action="REJECTED", metadata_json='{"reason_category":"Poor Scan Quality","officer_note":"Plot number is unreadable.","actor_role":"OFFICER"}'))
            db.add(models.AuditLog(document_id=other_document.id, submission_id=self.other_submission.id, user_id=self.officer_id,
                action="REJECTED", metadata_json='{"reason_category":"Incorrect Document","officer_note":"Private other-user note","actor_role":"OFFICER"}'))
            db.commit()
        app = FastAPI()
        app.include_router(officer.router, prefix="/api/officer")
        app.include_router(users.router, prefix="/api/user")
        app.include_router(records.router, prefix="/api/verified-records")
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def test_officer_default_status_filters_and_search_are_database_only(self):
        with patch.object(officer, "_load_document_image", side_effect=AssertionError("dashboard must not load documents")), \
                patch.object(officer, "recognize_fast_khatauni", side_effect=AssertionError("dashboard must not run OCR")):
            default = self.client.get("/api/officer/submissions")
            self.assertEqual(default.status_code, 200)
            self.assertEqual(len(default.json()), 6)
            for status in ("SUBMITTED", "PROCESSING", "NEEDS_REVIEW", "VERIFIED", "REJECTED"):
                response = self.client.get("/api/officer/submissions", params={"status": status})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json())
                self.assertTrue(all(row["status"] == status for row in response.json()))
            self.assertEqual(len(self.client.get("/api/officer/submissions", params={"search": "rampur"}).json()), 5)
            self.assertEqual(len(self.client.get("/api/officer/submissions", params={"search": "Ram Citizen"}).json()), 5)
            self.assertEqual(len(self.client.get("/api/officer/submissions", params={"search": "submitted-rampur"}).json()), 1)

    def test_rejection_reason_persists_and_is_returned(self):
        response = self.client.get("/api/officer/submissions", params={"status": "REJECTED"})
        self.assertEqual(response.status_code, 200)
        own = next(row for row in response.json() if row["id"] == self.submissions["REJECTED"])
        self.assertEqual(own["rejection"]["reason_category"], "Poor Scan Quality")
        self.assertEqual(own["rejection"]["officer_note"], "Plot number is unreadable.")
        created = self.client.post(f"/api/officer/documents/{self.rejected_document_id}/reject", params={"officer_id": self.officer_id}, json={"reason_category": "Information Mismatch", "officer_note": "Verified mismatch."})
        self.assertEqual(created.status_code, 200)
        events = self.client.get("/api/officer/audit").json()
        self.assertTrue(any(event["action"] == "REJECTED" and "Information Mismatch" in event.get("metadata_json", "") for event in events))

    def test_citizen_filter_scope_and_rejection_visibility(self):
        rejected = self.client.get("/api/user/submissions", params={"user_id": self.citizen_id, "status": "REJECTED"})
        self.assertEqual(rejected.status_code, 200)
        rows = rejected.json()
        self.assertEqual([row["id"] for row in rows], [self.submissions["REJECTED"]])
        self.assertEqual(rows[0]["rejection"]["reason_category"], "Poor Scan Quality")
        self.assertNotIn("Private other-user note", str(rows))
        own_search = self.client.get("/api/user/submissions", params={"user_id": self.citizen_id, "search": "other-secret"})
        self.assertEqual(own_search.status_code, 200)
        self.assertEqual(own_search.json(), [])

    def test_existing_verified_record_search_remains_available(self):
        response = self.client.get("/api/verified-records/", params={"search": "LR-UP-LUC-000001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["record_id"], "LR-UP-LUC-000001")


if __name__ == "__main__":
    unittest.main()
