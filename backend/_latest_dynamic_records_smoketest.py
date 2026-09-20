"""Transactional smoke test for latest-OCR dynamic record serialization."""

import main  # noqa: F401 - ensures additive local tables exist
import models
from database import SessionLocal
from routers.records import get_verified_record_detail, get_verified_records


db = SessionLocal()
try:
    record = db.query(models.VerifiedRecord).first()
    assert record is not None, "A verified record is required for this smoke test"
    document_id = record.submission.document_id

    stale_ocr = models.OCRResult(
        document_id=document_id,
        engine="transactional-test",
        script="test",
        raw_text="stale generation",
        processed_image_path="",
    )
    current_ocr = models.OCRResult(
        document_id=document_id,
        engine="transactional-test",
        script="test",
        raw_text="current generation",
        processed_image_path="",
    )
    db.add_all([stale_ocr, current_ocr])
    db.flush()

    stale_item = models.DynamicExtractedItem(
        document_id=document_id,
        ocr_result_id=stale_ocr.id,
        original_label="Stale generation item",
        ai_value="stale value",
    )
    current_item = models.DynamicExtractedItem(
        document_id=document_id,
        ocr_result_id=current_ocr.id,
        original_label="Current generation item",
        ai_value="current value",
    )
    manual_item = models.DynamicExtractedItem(
        document_id=document_id,
        ocr_result_id=None,
        original_label="Manual item",
        officer_value="manual value",
        final_value="manual final value",
    )
    stale_table = models.DynamicExtractedTable(
        document_id=document_id,
        ocr_result_id=stale_ocr.id,
        table_index=501,
        detected_headers=["Stale header"],
        row_count=1,
        column_count=1,
    )
    current_table = models.DynamicExtractedTable(
        document_id=document_id,
        ocr_result_id=current_ocr.id,
        table_index=502,
        detected_headers=["Current header"],
        row_count=1,
        column_count=1,
    )
    manual_table = models.DynamicExtractedTable(
        document_id=document_id,
        ocr_result_id=None,
        table_index=503,
        detected_headers=["Manual header"],
        row_count=1,
        column_count=1,
    )
    db.add_all([stale_item, current_item, manual_item, stale_table, current_table, manual_table])
    db.flush()
    db.add_all([
        models.DynamicExtractedCell(
            document_id=document_id, table_id=stale_table.id, ocr_result_id=stale_ocr.id,
            row_index=0, column_index=0, raw_ocr_value="stale cell",
        ),
        models.DynamicExtractedCell(
            document_id=document_id, table_id=current_table.id, ocr_result_id=current_ocr.id,
            row_index=0, column_index=0, raw_ocr_value="current cell",
        ),
        models.DynamicExtractedCell(
            document_id=document_id, table_id=current_table.id, ocr_result_id=None,
            row_index=1, column_index=0, officer_value="manual current-table cell",
        ),
        models.DynamicExtractedCell(
            document_id=document_id, table_id=manual_table.id, ocr_result_id=None,
            row_index=0, column_index=0, officer_value="manual table cell",
        ),
    ])
    db.add(models.DynamicDigitizationAudit(
        document_id=document_id,
        ocr_result_id=stale_ocr.id,
        action="STALE_GENERATION_RETAINED_IN_AUDIT",
        entity_type="field",
        entity_id=stale_item.id,
    ))
    db.flush()

    detail = get_verified_record_detail(id=record.id, db=db)
    labels = {item["original_label"] for item in detail["digitized"]["fields"]}
    table_labels = {table["detected_headers"][0] for table in detail["digitized"]["tables"]}
    assert detail["digitized"]["ocr_result_id"] == current_ocr.id
    assert "Current generation item" in labels and "Manual item" in labels
    assert "Stale generation item" not in labels
    assert {"Current header", "Manual header"}.issubset(table_labels)
    assert "Stale header" not in table_labels
    assert any(event["action"] == "STALE_GENERATION_RETAINED_IN_AUDIT" for event in detail["digitization_audit"])

    records = get_verified_records(db=db)
    listed = next(item for item in records if item["id"] == record.id)
    assert listed["digitization_summary"]["fields_detected"] >= 2
    assert listed["digitization_summary"]["tables_detected"] >= 2
    print("latest OCR dynamic serializer smoke test: PASS (rolled back)")
finally:
    db.rollback()
    db.close()
