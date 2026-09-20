# Inspection and baseline (2026-09-05)

Active implementation: frontend/src/app (Next.js 15.1.2) → frontend/src/lib/api.js → backend/main.py → routers/documents.py and routers/officer.py → khatauni_extractor.py → khatauni_hybrid.py. SQLite: backend/sql_app.db; uploads: backend/uploads. backend/app is an older implementation, and land-record-site is a static prototype. No backup or abandoned implementation was used.

WORKING / protected: startup in backend/.venv (Python 3.12.10), frontend routes returning 200, original file serving, dashboard/submission/audit/record read APIs, existing persisted OCR tokens and extraction, form value bindings (including low confidence), correction provenance code and existing persistence schema. Browser interaction still requires verification: no enabled browser surface was exposed by the computer-use tool. No backend was running at inspection; the existing main:app was started on port 8000.

PARTIALLY WORKING: preprocessing, Tesseract handwriting/numeric recognition, fixed header ROIs, table grid extraction, label mapping. The saved form has two populated priority categories (Tehsil and plot number), both incorrect. Saved metadata and OCR are in baseline_saved_form.json and baseline_saved_ocr.json.

BROKEN: HTR AutoProcessor cannot resolve the model's legacy ViTFeatureExtractor configuration on installed Transformers 5.16.1. HTR scores are a constant 70, not model evidence. Header crops overlap adjacent rows. Table summary is treated as a land row. Numeric recognition drops leading digits. Hybrid thresholds (82/55) disagree with UI thresholds (90/70).

MISSING: meaningful HTR scores, cross-pass evidence, layout validation before using template ROIs, compact field diagnostics, measured complete regression test.

Fresh pre-change extraction on the existing uploaded WhatsApp JPEG with persisted real OCR took 86.66 seconds, produced seven table rows (including the total), and populated nine priority categories with mostly incorrect values. This differs from the saved form because the on-disk hybrid code was newer than its saved extraction. See baseline_current_code.json for exact candidates and confidences. Village is correct; some holder/revenue row cells are correct, but most numerical rows and all other priority header values are incorrect. Share is absent on the source and must remain unavailable.

Tesseract: C:/Program Files/Tesseract-OCR/tesseract.exe, 5.4.0.20240606, hin+eng plus osd installed. All requested packages are already present. Torch 2.14.0+cpu, CUDA unavailable. No package installation needed.

Source values are never taken from upload metadata, filenames, or manual transcription. Baseline recognition outputs are diagnostic evidence only, never runtime inputs to new recognition.
