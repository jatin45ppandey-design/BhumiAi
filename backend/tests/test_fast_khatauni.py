"""Regression checks use temporary SQLite/uploads, never operational records."""
import contextlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import khatauni_fast as fast
import khatauni_hybrid as hybrid
import models
from routers import documents, officer
from security import SESSION_COOKIE_NAME, new_session

SAMPLE = Path(__file__).resolve().parents[1] / "uploads/Screenshot 2026-09-10 021642.png"


class FastTemplateTests(unittest.TestCase):
    def test_normal_backend_startup_with_isolated_database(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0))
            port=listener.getsockname()[1]
        backend=str(SAMPLE.parents[1])
        command=(f"import sys; sys.path.insert(0,{backend!r}); import uvicorn; "
                 f"uvicorn.run('main:app',host='127.0.0.1',port={port},log_level='warning')")
        with tempfile.TemporaryDirectory(prefix="bhumi-startup-") as directory:
            process=subprocess.Popen([sys.executable,"-c",command],cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=1) as response:
                            self.assertEqual(json.load(response),{"status":"ok"})
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail("Backend failed to start: "+process.stderr.read().decode(errors="replace"))
                        time.sleep(.1)
                else:
                    self.fail("Backend startup timed out")
            finally:
                process.terminate()
                process.communicate(timeout=10)

    def test_unknown_layout_does_not_force_rois(self):
        self.assertIsNone(fast.recognize(Image.new("L", (600, 800), 255)))

    def test_cleaning_preserves_names_and_validates_types(self):
        self.assertEqual(fast.clean_value("का नाम - अरविंद कुमार", "lekhpal_name"), "अरविंद कुमार")
        self.assertEqual(fast.clean_value("४ मुरादाबाद", "district"), "मुरादाबाद")
        self.assertEqual(fast.clean_value("नाम देव", "holder_name"), "नाम देव")
        self.assertFalse(fast.valid_value("feat", "hindi"))
        self.assertFalse(fast.valid_value("2022garbage23", "year"))
        self.assertTrue(fast.valid_value("1430-1435", "year"))

    @unittest.skipUnless(SAMPLE.exists(), "Local acceptance document unavailable")
    def test_scaled_template_and_label_guard(self):
        with Image.open(SAMPLE) as image:
            for scale in (1, 2):
                candidate = image.resize((image.width*scale, image.height*scale))
                self.assertIsNotNone(fast.prepare_page(candidate))
            blank_title = image.convert("RGB")
            ImageDraw.Draw(blank_title).rectangle((70, 25, 480, 70), fill="white")
            self.assertIsNone(fast.recognize(blank_title))

    @unittest.skipUnless(SAMPLE.exists(), "Local acceptance document unavailable")
    def test_real_upload_recognize_edit_verify_and_cached_reopen(self):
        with tempfile.TemporaryDirectory(prefix="bhumi-workflow-") as directory:
            engine = create_engine("sqlite:///" + str(Path(directory)/"test.db"), connect_args={"check_same_thread":False})
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine)
            with sessions() as db:
                account = models.User(name="Test Officer", email="controlled@example.test", role="officer")
                db.add(account)
                db.commit(); _, session_token = new_session(db, account); db.commit()
                officer_id = account.id
            app = FastAPI()
            app.include_router(documents.router, prefix="/api/documents")
            app.include_router(officer.router, prefix="/api/officer")
            def database():
                with sessions() as db:
                    yield db
            app.dependency_overrides[get_db] = database
            def ok(response):
                self.assertEqual(response.status_code, 200, response.text[:500])
                return response.json()
            try:
                with TestClient(app) as client, patch.object(documents,"UPLOAD_DIR",directory):
                    client.cookies.set(SESSION_COOKIE_NAME, session_token)
                    with SAMPLE.open("rb") as source:
                        uploaded=ok(client.post("/api/documents/officer-upload",data={"document_type":"Khatauni","state":"Test","district":"Test","tehsil":"Test","village":"Test"},files={"file":("sample.png",source,"image/png")}))
                    prefix=f"/api/officer/documents/{uploaded['document_id']}"
                    started=time.perf_counter()
                    prepared=ok(client.post(prefix+"/preprocess"))
                    with patch.object(hybrid,"_htr_candidate",side_effect=AssertionError("Clean document must not load HTR")), contextlib.redirect_stdout(io.StringIO()):
                        ocr=ok(client.post(prefix+"/ocr",params={"processed_path":prepared["processed_file_path"]}))
                    with patch.object(officer.KhatauniExtractor,"extract",side_effect=AssertionError("Reuse persisted crop recognition")):
                        extracted=ok(client.post(prefix+"/extract",params={"ocr_id":ocr["ocr_id"]}))
                    elapsed=time.perf_counter()-started
                    fields={item["normalized_label"]:item for item in extracted["items"]}
                    expected={"district":"मुरादाबाद","tehsil":"बिलारी","revenue_village":"नेरपुर","village_name":"नेरपुर","village_code":"302114","pargana":"बिलारी","crop_year":"2022-23","khata_number":"125","holder_name":"राम कुमार","guardian_name":"मोहन लाल","patwari_circle":"नेरपुर","patwari_name":"अजय सिंह","lekhpal_name":"अरविन्द कुमार","issue_date":"12/05/2023"}
                    self.assertEqual({k:v["raw_ocr_value"] for k,v in fields.items()},expected)
                    table=extracted["tables"][0]
                    self.assertEqual(table["row_count"],6)
                    self.assertEqual(len([c for c in table["cells"] if c["raw_ocr_value"]]),42)
                    # A real officer correction survives reads and extraction.
                    field=fields["district"]
                    correction="Officer corrected district"
                    ok(client.patch(prefix+f"/dynamic-fields/{field['id']}",json={"officer_value":correction}))
                    cell=table["cells"][0]
                    ok(client.patch(prefix+f"/tables/{table['id']}/cells/{cell['id']}",json={"officer_value":"7"}))
                    with patch.object(officer,"recognize_fast_khatauni",side_effect=AssertionError("Reopen must not OCR")):
                        reopened=ok(client.get(prefix+"/digitization"))
                        repeated=ok(client.post(prefix+"/extract",params={"ocr_id":ocr["ocr_id"]}))
                    self.assertEqual(next(f for f in reopened["items"] if f["id"]==field["id"])["officer_value"],correction)
                    self.assertEqual(next(f for f in repeated["items"] if f["id"]==field["id"])["officer_value"],correction)
                    self.assertEqual(len(repeated["items"]),14)
                    self.assertEqual(next(c for c in repeated["tables"][0]["cells"] if c["id"]==cell["id"])["officer_value"],"7")
                    ok(client.post(prefix + "/mark-review"))
                    ok(client.post(prefix + "/approve"))
                    self.assertEqual(
                        client.post(prefix + "/reject", json={"reason_category": "Incomplete Document", "officer_note": "Test rejection reason"}).status_code,
                        409,
                    )
                    with sessions() as db:
                        self.assertEqual(db.query(models.VerifiedRecord).count(),1)
                        self.assertEqual(db.query(models.Submission).first().status,"VERIFIED")
                        self.assertGreater(db.query(models.DynamicDigitizationAudit).count(),0)
                        stored_source = Path(db.query(models.Document).first().file_path)
                    self.assertEqual(client.patch(prefix+f"/dynamic-fields/{field['id']}",json={"officer_value":"late edit"}).status_code,409)
                    self.assertEqual(client.post(prefix+"/preprocess").status_code,409)
                    print(f"Acceptance: 14/14 source-matching headers, 42 table cells, zero HTR; preprocess/OCR/extract {elapsed:.3f}s")
                    # A source edit must invalidate saved recognition.
                    with Image.open(stored_source) as original:
                        changed=original.convert("RGB")
                    ImageDraw.Draw(changed).rectangle((30,80,100,100),fill="white")
                    changed.save(stored_source)
                    self.assertEqual(client.post(prefix+"/extract").status_code,409)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
