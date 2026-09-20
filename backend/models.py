from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    role = Column(String, default="user") # "user" or "officer"
    password_hash = Column(String, nullable=True)
    # Google assigns this stable, immutable identifier to an account. Email is
    # useful for contact, but the subject is the identity we bind to OAuth.
    google_subject = Column(String, unique=True, index=True, nullable=True)
    # Issued by the authorized administrator; never selected by a public user.
    officer_id = Column(String, unique=True, index=True, nullable=True)
    
    submissions = relationship("Submission", back_populates="user")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String)
    original_filename = Column(String)
    document_type = Column(String)
    state = Column(String)
    district = Column(String)
    tehsil = Column(String)
    village = Column(String)
    file_hash = Column(String, index=True)
    file_size = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)
    processed_file_path = Column(String, nullable=True)
    duplicate_checked_at = Column(DateTime, nullable=True)
    duplicate_of_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    
    submissions = relationship("Submission", back_populates="document")
    ocr_results = relationship("OCRResult", back_populates="document")
    # These are deliberately separate from the legacy, fixed ExtractedField
    # relationship. A land record can contain any number of labels, tables, and
    # cells, so its digitized shape must come from the document rather than a
    # predefined list of fields.
    dynamic_extracted_items = relationship("DynamicExtractedItem", back_populates="document")
    dynamic_extracted_tables = relationship("DynamicExtractedTable", back_populates="document")
    dynamic_extracted_cells = relationship("DynamicExtractedCell", back_populates="document")
    dynamic_digitization_audits = relationship("DynamicDigitizationAudit", back_populates="document")

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="SUBMITTED") # UPLOADED, SUBMITTED, PROCESSING, NEEDS_REVIEW, VERIFIED, REJECTED
    submitted_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    document = relationship("Document", back_populates="submissions")
    user = relationship("User", back_populates="submissions")
    verified_record = relationship("VerifiedRecord", back_populates="submission", uselist=False)

class OCRResult(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    engine = Column(String)
    script = Column(String)
    raw_text = Column(Text)
    processed_image_path = Column(String)
    languages = Column(String, nullable=True)
    overall_confidence = Column(Float, nullable=True)
    token_count = Column(Integer, nullable=True)
    token_confidence_json = Column(Text, nullable=True)
    # Full image-to-data token records, including coordinates, belong here. The
    # existing token_confidence_json is retained for backwards compatibility.
    token_layout_json = Column(Text, nullable=True)
    layout_metadata_json = Column(Text, nullable=True)
    
    document = relationship("Document", back_populates="ocr_results")
    extracted_fields = relationship("ExtractedField", back_populates="ocr_result")
    dynamic_extracted_items = relationship("DynamicExtractedItem", back_populates="ocr_result")
    dynamic_extracted_tables = relationship("DynamicExtractedTable", back_populates="ocr_result")
    dynamic_extracted_cells = relationship("DynamicExtractedCell", back_populates="ocr_result")
    dynamic_digitization_audits = relationship("DynamicDigitizationAudit", back_populates="ocr_result")

class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    
    id = Column(Integer, primary_key=True, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"))
    field_name = Column(String) # owner_name, khasra_number, etc.
    ai_value = Column(String)
    ai_confidence = Column(Float)
    confidence_source = Column(String, nullable=True)
    officer_value = Column(String, nullable=True)
    final_value = Column(String, nullable=True)
    edited = Column(Boolean, default=False)
    
    ocr_result = relationship("OCRResult", back_populates="extracted_fields")


class DynamicExtractedItem(Base):
    """A document-native key/value or free-form digitization item.

    This model intentionally has no field-name enum. ``original_label`` is the
    label detected from the source document (including Hindi or any other
    language); ``normalized_label`` is optional metadata for later indexing.
    """
    __tablename__ = "dynamic_extracted_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"), nullable=True, index=True)
    item_type = Column(String, nullable=False, default="key_value")
    display_order = Column(Integer, nullable=True)

    original_label = Column(Text, nullable=True)
    normalized_label = Column(String, nullable=True, index=True)
    raw_ocr_value = Column(Text, nullable=True)
    ai_value = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    confidence_source = Column(String, nullable=True)
    row_index = Column(Integer, nullable=True)
    column_index = Column(Integer, nullable=True)
    bounding_box = Column(JSON, nullable=True)
    source_token_ids = Column(JSON, nullable=True)

    officer_value = Column(Text, nullable=True)
    final_value = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edited_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    audit_metadata_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="dynamic_extracted_items")
    ocr_result = relationship("OCRResult", back_populates="dynamic_extracted_items")

    @property
    def field_id(self):
        """Stable API-friendly synonym for the primary key."""
        return self.id


class DynamicExtractedTable(Base):
    """A table reconstructed from OCR layout, with an arbitrary number of cells."""
    __tablename__ = "dynamic_extracted_tables"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"), nullable=True, index=True)
    table_index = Column(Integer, nullable=False, default=0)
    original_label = Column(Text, nullable=True)
    normalized_label = Column(String, nullable=True, index=True)
    detected_headers = Column(JSON, nullable=True)
    officer_headers = Column(JSON, nullable=True)
    final_headers = Column(JSON, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    bounding_box = Column(JSON, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    confidence_source = Column(String, nullable=True)
    source_token_ids = Column(JSON, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edited_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    audit_metadata_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="dynamic_extracted_tables")
    ocr_result = relationship("OCRResult", back_populates="dynamic_extracted_tables")
    cells = relationship("DynamicExtractedCell", back_populates="table", cascade="all, delete-orphan")

    @property
    def table_id(self):
        """Stable API-friendly synonym for the primary key."""
        return self.id


class DynamicExtractedCell(Base):
    """One detected or officer-added table cell; column labels stay document-native."""
    __tablename__ = "dynamic_extracted_cells"

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("dynamic_extracted_tables.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"), nullable=True, index=True)
    row_index = Column(Integer, nullable=False)
    column_index = Column(Integer, nullable=False)
    header_label = Column(Text, nullable=True)
    raw_ocr_value = Column(Text, nullable=True)
    ai_value = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    confidence_source = Column(String, nullable=True)
    bounding_box = Column(JSON, nullable=True)
    source_token_ids = Column(JSON, nullable=True)

    officer_value = Column(Text, nullable=True)
    final_value = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edited_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    audit_metadata_json = Column(JSON, nullable=True)

    table = relationship("DynamicExtractedTable", back_populates="cells")
    document = relationship("Document", back_populates="dynamic_extracted_cells")
    ocr_result = relationship("OCRResult", back_populates="dynamic_extracted_cells")

    @property
    def cell_id(self):
        """Stable API-friendly synonym for the primary key."""
        return self.id


class DynamicDigitizationAudit(Base):
    """Append-only provenance for dynamic field, table, and cell corrections."""
    __tablename__ = "dynamic_digitization_audits"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"), nullable=True, index=True)
    item_id = Column(Integer, ForeignKey("dynamic_extracted_items.id"), nullable=True, index=True)
    table_id = Column(Integer, ForeignKey("dynamic_extracted_tables.id"), nullable=True, index=True)
    cell_id = Column(Integer, ForeignKey("dynamic_extracted_cells.id"), nullable=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True, index=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    document = relationship("Document", back_populates="dynamic_digitization_audits")
    ocr_result = relationship("OCRResult", back_populates="dynamic_digitization_audits")

    @property
    def audit_id(self):
        """Stable API-friendly synonym for the primary key."""
        return self.id

class VerifiedRecord(Base):
    __tablename__ = "verified_records"
    
    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String, unique=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"))
    owner_name = Column(String)
    father_guardian_name = Column(String, nullable=True)
    khasra_number = Column(String)
    khata_number = Column(String)
    area = Column(String)
    village = Column(String)
    tehsil = Column(String)
    district = Column(String)
    state = Column(String)
    verification_status = Column(String)
    verified_by = Column(Integer, ForeignKey("users.id"))
    verified_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    submission = relationship("Submission", back_populates="verified_record")
    officer = relationship("User")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=True)
    record_id = Column(Integer, ForeignKey("verified_records.id"), nullable=True)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    metadata_json = Column(String, nullable=True)
