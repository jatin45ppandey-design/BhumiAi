# BhumiAI — SIH Demo & Claim Guide

This guide is for presenting the **current implementation** of BhumiAI for **Smart India Hackathon 2026 • PS26018**.

## 1. One-Line Positioning

**BhumiAI is an evidence-first land-record digitization and verification platform that combines local OCR/HTR, deterministic validation and accountable officer review before a verified digital record is created.**

## 2. Recommended Demo Flow

```text
Citizen Login / Register
→ Upload Khatauni
→ Submit
→ Officer opens Review
→ Enhance
→ Recognize
→ Extract
→ Compare Source vs Structured Record
→ Correct uncertain values
→ Save Corrections
→ Verify / Needs Review / Reject
→ Citizen sees status notification
→ Verified record can be exported
```

## 3. What Is Implemented

- citizen phone-OTP authentication
- officer ID/password authentication
- protected uploads and authenticated document access
- OpenCV/Pillow preprocessing
- Tesseract `hin+eng`
- optional local TrOCR/HTR for selected handwritten regions
- deterministic Khatauni field/table extraction
- Recognition Evidence with HIGH/MEDIUM/LOW bands
- separate rule-based validation
- source-vs-structured officer review
- deterministic Hindi phonetic correction for textual fields
- correction/audit provenance
- Needs Review / Verify / Reject workflow
- exact SHA-256 duplicate detection
- citizen in-app notifications
- verified-only JSON/CSV/PDF export
- terminal verified/rejected record immutability

## 4. Claims to Use

Good phrasing:

> Recognition assists the officer; it does not autonomously create a legal record.

> Confidence and validation are separate: confidence represents recognition evidence, while validation checks deterministic record rules.

> The handwriting model is local-only at runtime; document images are not sent to a generative AI service.

> Duplicate detection currently identifies exact file matches using SHA-256.

> The current validated prototype is focused on Hindi/English Khatauni-style records.

## 5. Claims to Avoid

Do not claim that BhumiAI currently provides:

- universal support for every Indian land-record format
- all Indian language recognition
- visual/similarity duplicate detection
- live LRMS/DILRMP/GIS integration
- automatic legal ownership verification
- production SMS delivery
- autonomous model retraining from officer corrections
- multi-page PDF OCR across the full document
- PostgreSQL as the current database
- GenAI/LLM/RAG-based correction

## 6. Likely Judge Questions

### Why not use an LLM to correct OCR?

Because land-record values are high-integrity data. BhumiAI avoids semantic guessing. Uncertain values remain visible to the officer with recognition evidence instead of being silently invented.

### Where is AI/ML used?

The system uses local TrOCR/HTR for handwriting recognition together with Tesseract OCR and computer-vision preprocessing. Final verification remains human-controlled.

### What happens when confidence is low?

The value is surfaced with LOW/MEDIUM/HIGH recognition evidence and separate validation status. The officer can compare it directly against the original source, correct it, mark the record for further review, reject it, or verify it.

### How are duplicates handled?

The uploaded file is SHA-256 hashed. Exact byte-identical files are detected even if their filenames differ. The officer decides whether to continue or reject a verified exact match as a duplicate.

### Does the prototype connect to government databases?

No live government integration is claimed. The current prototype implements digitization, verification, provenance and export. Authorized LRMS/GIS/cadastral adapters are a production integration step.

### What are the current scale limits?

The prototype uses SQLite, local filesystem storage and local inference. A production architecture would move to PostgreSQL, private object storage, background recognition workers, monitoring and authorized identity/integration services.

## 7. Current Limitations

- validated primarily on Khatauni-style records
- Hindi + English recognition scope
- PDF processing currently uses page 1
- exact duplicate detection only
- SQLite/local filesystem prototype infrastructure
- production SMS provider not integrated
- real-device camera testing still required for production confidence
- Recognition Evidence is heuristic, not a calibrated probability
- no live government/GIS integration
- no autonomous legal decision

## 8. Demo Safety Checklist

Before presenting:

- start backend successfully
- confirm Tesseract executable and `hin` + `eng` trained data
- confirm local TrOCR model cache if HTR is part of the demo
- confirm frontend build/run
- prepare one clean record
- prepare one difficult/uncertain record
- prepare one exact duplicate example
- verify citizen and officer credentials
- verify export output
- avoid relying on external network services during the core recognition demo

## 9. Core Message

The strongest BhumiAI story is not “we built OCR.”

It is:

> **We built a reliable path from imperfect paper evidence to an auditable digital record without allowing recognition uncertainty to become an unreviewed legal fact.**
