# BhumiAI Frontend

This directory contains the current BhumiAI web interface for **SIH 2026 • PS26018**.

It is not a stock Create Next App demo. The active UI contains separate citizen and officer workflows for land-record submission, review, verification and export.

## Stack

- Next.js 15 App Router
- React 19
- JavaScript / JSX
- custom CSS
- Lucide React icons
- native `fetch` / `FormData` through the project API wrapper

## Main UI Areas

### Citizen

- phone-OTP register/login
- profile completion
- document upload / camera capture
- submission tracking
- in-app notifications
- verified-record access and exports

### Officer

- Officer ID/password login
- dashboard and review queue
- officer direct upload
- Source Document ↔ Structured Record review workspace
- Khatauni table correction
- confidence and validation indicators
- EN / deterministic Hindi phonetic correction mode
- duplicate-match evidence
- Save Corrections / Needs Review / Verify / Reject
- read-only terminal records
- verified-record browsing/export

## Officer Review Flow

```text
Upload → Enhance → Recognize → Extract → Review → Verified
```

Desktop review layout:

```text
Source Document        | Structured Record
-------------------------------------------
Khatauni / Parcel Table| Officer Decision
```

The original source remains available while the officer reviews machine-recognized values.

## Run Locally

Install dependencies:

```powershell
cd frontend
npm install
```

Start development mode:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

The backend is expected at the configured API origin (local default: `http://127.0.0.1:8000`).

## Production Build Check

```powershell
npm run build
```

## Important Behavior

- Authentication is enforced by the backend; the browser UI is not the security boundary.
- Document content is loaded through authenticated backend routes.
- Hindi correction is deterministic client-side phonetic transliteration only.
- Numeric/revenue identifiers are excluded from phonetic conversion.
- Switching EN/हिंदी typing mode does not create a dirty edit.
- VERIFIED and REJECTED records are read-only.
- The frontend does not call a GenAI/LLM/RAG service for land-record correction.

For the full project architecture, OCR/HTR setup, limitations and backend instructions, see the repository root **README.md**.
