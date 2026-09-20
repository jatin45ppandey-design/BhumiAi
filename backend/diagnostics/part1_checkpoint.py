"""Part 1 additive workflow checkpoint.

Runs through upload -> preprocess -> OCR -> extract -> officer correction ->
approve -> verified search/detail using the active local FastAPI app. It adds a
new test record but never deletes or resets existing data.
"""

from __future__ import annotations

import contextlib
import io
import json
import uuid
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


client = TestClient(main.app)


def expect(response, status=200):
    assert response.status_code == status, f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text[:300]}"
    return response.json()


def main_checkpoint() -> None:
    sample = Path("uploads/synthetic_land_record_test.png")
    if not sample.exists():
        sample = Path("storage/synthetic_land_record_test.png")
    assert sample.exists(), "No checkpoint sample image found"

    officer = expect(client.post("/api/auth/login", json={
        "email": "officer@example.com",
        "name": "Demo Officer",
        "role": "officer",
        "password": "demo123",
    }))["user"]

    filename = f"part1-checkpoint-{uuid.uuid4().hex}{sample.suffix}"
    with sample.open("rb") as handle:
        uploaded = expect(client.post("/api/documents/officer-upload", data={
            "document_type": "Khatauni",
            "state": "Checkpoint",
            "district": "Checkpoint",
            "tehsil": "Checkpoint",
            "village": "Checkpoint",
            "officer_id": str(officer["id"]),
        }, files={"file": (filename, handle, "image/png")}))

    document_id = uploaded["document_id"]
    prefix = f"/api/officer/documents/{document_id}"
    duplicate = expect(client.post(f"/api/documents/{document_id}/duplicate-check"))
    preprocess = expect(client.post(f"{prefix}/preprocess"))

    # OCR route prints a short raw-text preview for manual debugging. Keep this
    # checkpoint output summary-only.
    with contextlib.redirect_stdout(io.StringIO()):
        ocr = expect(client.post(f"{prefix}/ocr", params={"processed_path": preprocess["processed_file_path"]}))
    assert ocr["status"] == "COMPLETED"
    assert ocr["tokens"], "OCR should preserve token evidence"

    extraction = expect(client.post(f"{prefix}/extract", params={"ocr_id": ocr["ocr_id"]}))
    assert extraction["digital_khatauni"]["schema_version"] == "digital_khatauni_part1_v1"
    assert "khatauni_details" in extraction["digital_khatauni"]
    assert isinstance(extraction["digital_khatauni"]["land_details"], list)

    editable = next((item for item in extraction["items"] if item.get("ai_value")), None)
    assert editable, "Expected at least one OCR-derived field for correction check"
    expect(client.patch(f"{prefix}/dynamic-fields/{editable['id']}", params={"officer_id": officer["id"]}, json={
        "officer_value": editable["ai_value"],
    }))

    table = extraction["tables"][0]
    cell = next((candidate for candidate in table["cells"] if candidate.get("ai_value")), None)
    assert cell, "Expected at least one OCR-derived table cell for correction check"
    expect(client.patch(f"{prefix}/tables/{table['id']}/cells/{cell['id']}", params={"officer_id": officer["id"]}, json={
        "officer_value": cell["ai_value"],
    }))

    approved = expect(client.post(f"{prefix}/approve", params={"officer_id": officer["id"]}))
    dashboard = expect(client.get("/api/officer/dashboard"))
    audit = expect(client.get("/api/officer/audit"))
    records = expect(client.get("/api/verified-records/", params={"search": filename}))
    assert records, "Verified record search should find the checkpoint document"
    detail = expect(client.get(f"/api/verified-records/{records[0]['id']}"))
    assert detail["record"]["verification_status"] == "VERIFIED"
    assert detail["digitized"]["summary"]["fields_detected"] >= 1
    assert any(row["document_id"] == document_id for row in audit), "Audit should include checkpoint document"

    print(json.dumps({
        "status": "PASS",
        "document_id": document_id,
        "ocr_tokens": ocr["token_count"],
        "ocr_confidence": ocr["overall_confidence"],
        "quality_warnings": preprocess["quality"]["warnings"],
        "duplicate_detected": duplicate["duplicate"],
        "fields_detected": extraction["summary"]["fields_detected"],
        "rows_digitized": extraction["summary"]["rows_digitized"],
        "cells_populated": extraction["summary"]["ocr_cells_populated"],
        "digital_schema": extraction["digital_khatauni"]["schema_version"],
        "approved_message": approved["message"],
        "dashboard_verified": dashboard["verified"],
        "record_id": detail["record"]["record_id"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main_checkpoint()
