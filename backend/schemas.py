from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    name: str

class UserCreate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    officer_id: Optional[str] = None
    password: str
    role: Optional[str] = None

class UserRegistration(UserBase):
    password: str

class User(UserBase):
    id: int
    role: str

    class Config:
        from_attributes = True

class GoogleOAuthTicket(BaseModel):
    ticket: str

class DocumentBase(BaseModel):
    document_type: str
    state: str
    district: str
    tehsil: str
    village: str

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    file_path: str
    original_filename: str
    file_hash: str
    file_size: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    processed_file_path: Optional[str] = None
    duplicate_checked_at: Optional[datetime] = None
    duplicate_of_id: Optional[int] = None

    class Config:
        from_attributes = True

class SubmissionBase(BaseModel):
    status: str

class SubmissionCreate(BaseModel):
    document_id: int

class Submission(SubmissionBase):
    id: int
    document_id: int
    user_id: int
    submitted_at: datetime
    document: Document
    user: User
    rejection: Optional[Dict[str, Any]] = None
    verified_record_id: Optional[int] = None

    class Config:
        from_attributes = True


class RejectionDecision(BaseModel):
    reason_category: str
    officer_note: Optional[str] = None


class UserNotification(BaseModel):
    id: int
    type: str
    title: str
    message: str
    document_id: Optional[int] = None
    record_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ExtractedFieldBase(BaseModel):
    field_name: str
    ai_value: Optional[str] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    officer_value: Optional[str] = None
    final_value: Optional[str] = None
    edited: bool = False

class ExtractedField(ExtractedFieldBase):
    id: int

    class Config:
        from_attributes = True

class OCRResultBase(BaseModel):
    engine: str
    script: str
    raw_text: str
    processed_image_path: str

class OCRResult(OCRResultBase):
    id: int
    extracted_fields: List[ExtractedField] = []

    class Config:
        from_attributes = True

class ExtractedFieldUpdate(BaseModel):
    officer_value: str


# Dynamic digitization schemas -------------------------------------------------
#
# These models are intentionally document-native: labels, headers, rows, and
# cells are supplied by OCR/layout detection or by an officer. They do not use
# the legacy, fixed land-record field list above.

class DynamicExtractedItemBase(BaseModel):
    item_type: str = "key_value"
    display_order: Optional[int] = None
    original_label: Optional[str] = None
    normalized_label: Optional[str] = None
    raw_ocr_value: Optional[str] = None
    ai_value: Optional[str] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    source_token_ids: Optional[List[int]] = None
    officer_value: Optional[str] = None
    final_value: Optional[str] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedItemCreate(DynamicExtractedItemBase):
    document_id: int
    ocr_result_id: Optional[int] = None


class DynamicExtractedItemUpdate(BaseModel):
    item_type: Optional[str] = None
    display_order: Optional[int] = None
    original_label: Optional[str] = None
    normalized_label: Optional[str] = None
    raw_ocr_value: Optional[str] = None
    ai_value: Optional[str] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    source_token_ids: Optional[List[int]] = None
    officer_value: Optional[str] = None
    final_value: Optional[str] = None
    is_deleted: Optional[bool] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedItem(DynamicExtractedItemBase):
    id: int
    field_id: int
    document_id: int
    ocr_result_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    edited_by: Optional[int] = None
    edited_at: Optional[datetime] = None
    updated_at: datetime
    is_deleted: bool = False
    deleted_by: Optional[int] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DynamicExtractedTableBase(BaseModel):
    table_index: int = 0
    original_label: Optional[str] = None
    normalized_label: Optional[str] = None
    detected_headers: Optional[List[Optional[str]]] = None
    officer_headers: Optional[List[Optional[str]]] = None
    final_headers: Optional[List[Optional[str]]] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    source_token_ids: Optional[List[int]] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedTableCreate(DynamicExtractedTableBase):
    document_id: int
    ocr_result_id: Optional[int] = None


class DynamicExtractedTableUpdate(BaseModel):
    table_index: Optional[int] = None
    original_label: Optional[str] = None
    normalized_label: Optional[str] = None
    detected_headers: Optional[List[Optional[str]]] = None
    officer_headers: Optional[List[Optional[str]]] = None
    final_headers: Optional[List[Optional[str]]] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    source_token_ids: Optional[List[int]] = None
    is_deleted: Optional[bool] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedCellBase(BaseModel):
    row_index: int
    column_index: int
    header_label: Optional[str] = None
    raw_ocr_value: Optional[str] = None
    ai_value: Optional[str] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    bounding_box: Optional[Dict[str, Any]] = None
    source_token_ids: Optional[List[int]] = None
    officer_value: Optional[str] = None
    final_value: Optional[str] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedCellCreate(DynamicExtractedCellBase):
    table_id: int
    document_id: int
    ocr_result_id: Optional[int] = None


class DynamicExtractedCellUpdate(BaseModel):
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    header_label: Optional[str] = None
    raw_ocr_value: Optional[str] = None
    ai_value: Optional[str] = None
    ai_confidence: Optional[float] = None
    confidence_source: Optional[str] = None
    bounding_box: Optional[Dict[str, Any]] = None
    source_token_ids: Optional[List[int]] = None
    officer_value: Optional[str] = None
    final_value: Optional[str] = None
    is_deleted: Optional[bool] = None
    audit_metadata_json: Optional[Dict[str, Any]] = None


class DynamicExtractedCell(DynamicExtractedCellBase):
    id: int
    cell_id: int
    table_id: int
    document_id: int
    ocr_result_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    edited_by: Optional[int] = None
    edited_at: Optional[datetime] = None
    updated_at: datetime
    is_deleted: bool = False
    deleted_by: Optional[int] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DynamicExtractedTable(DynamicExtractedTableBase):
    id: int
    table_id: int
    document_id: int
    ocr_result_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    edited_by: Optional[int] = None
    edited_at: Optional[datetime] = None
    updated_at: datetime
    is_deleted: bool = False
    deleted_by: Optional[int] = None
    deleted_at: Optional[datetime] = None
    cells: List[DynamicExtractedCell] = Field(default_factory=list)

    class Config:
        from_attributes = True


class DynamicDigitizationAuditBase(BaseModel):
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    before_json: Optional[Dict[str, Any]] = None
    after_json: Optional[Dict[str, Any]] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DynamicDigitizationAuditCreate(DynamicDigitizationAuditBase):
    document_id: int
    ocr_result_id: Optional[int] = None
    item_id: Optional[int] = None
    table_id: Optional[int] = None
    cell_id: Optional[int] = None
    actor_id: Optional[int] = None


class DynamicDigitizationAudit(DynamicDigitizationAuditBase):
    id: int
    audit_id: int
    document_id: int
    ocr_result_id: Optional[int] = None
    item_id: Optional[int] = None
    table_id: Optional[int] = None
    cell_id: Optional[int] = None
    actor_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DynamicDigitizationSummary(BaseModel):
    fields_detected: int = 0
    tables_detected: int = 0
    rows_digitized: int = 0
    columns_detected: int = 0
    high_confidence_items: int = 0
    medium_confidence_items: int = 0
    low_confidence_items: int = 0
    unavailable_confidence_items: int = 0


class DynamicDigitizationResponse(BaseModel):
    """Suggested read shape for a document-specific digitization endpoint."""
    document_id: int
    ocr_result_id: Optional[int] = None
    items: List[DynamicExtractedItem] = Field(default_factory=list)
    tables: List[DynamicExtractedTable] = Field(default_factory=list)
    summary: DynamicDigitizationSummary = Field(default_factory=DynamicDigitizationSummary)
    
class VerifiedRecordBase(BaseModel):
    owner_name: str
    father_guardian_name: Optional[str] = None
    khasra_number: str
    khata_number: str
    area: str
    village: str
    tehsil: str
    district: str
    state: str

class VerifiedRecord(VerifiedRecordBase):
    id: int
    record_id: str
    verification_status: str
    verified_at: datetime

    class Config:
        from_attributes = True
