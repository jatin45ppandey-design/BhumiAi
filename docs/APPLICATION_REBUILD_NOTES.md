# BhumiAI — Complete Application Rebuild Notes

Reviewed against this project's active code on **12 September 2026**.

Purpose: understand **which technology was used, what it does, where it fits, and in what order to build this type of application again**. These are practical learning notes, not just a list of tools.

Scope: documentation only. Existing code/comments are left as they were. The build order below is a recommended reconstruction sequence, not a claim about the project's exact historical development order. Current features and future improvements are identified separately.

## Contents

1. [Application purpose and roles](#1-application-purpose-and-roles)
2. [Complete architecture](#2-complete-architecture)
3. [Technology map — what was used for what](#3-technology-map--what-was-used-for-what)
4. [Active project structure](#4-active-project-structure)
5. [Step-by-step rebuild order](#5-step-by-step-rebuild-order)
6. [Setup and environment configuration](#6-setup-and-environment-configuration)
7. [Login, signup and Google OAuth](#7-login-signup-and-google-oauth)
8. [Database design and relationships](#8-database-design-and-relationships)
9. [Document processing explained](#9-document-processing-explained)
10. [Frontend and API communication](#10-frontend-and-api-communication)
11. [File-by-file study order](#11-file-by-file-study-order)
12. [Testing and troubleshooting](#12-testing-and-troubleshooting)
13. [Current limitations and production improvements](#13-current-limitations-and-production-improvements)
14. [Reusing the design and quick revision](#14-reusing-the-design-and-quick-revision)

## 1. Application purpose and roles

BhumiAI helps turn scanned or photographed land records into editable, searchable digital records. Its current recognition/review workflow is particularly focused on Hindi/English **Khatauni** documents.

The central idea is:

```text
Paper document / scan
  -> uploaded image or PDF
  -> readable image
  -> recognized text
  -> structured fields and table rows
  -> officer corrections
  -> application verification and searchable record
```

The machine assists with reading. The officer makes the review decision. This application does **not** prove legal ownership or automatically verify a record against a government registry.

| Role | Account creation | Login methods | Main responsibilities |
| --- | --- | --- | --- |
| Record Submitter (`user`) | Public email/password signup, or first successful Google sign-in | Existing email/password option **plus** Google | Upload, check exact duplicates, submit, track submissions, browse verified records |
| Officer (`officer`) | Authorized developer/admin provisions credentials on the server | Issued Government Officer ID and password | Process documents, inspect OCR, correct data, approve/reject/request review |

Officers cannot self-register or sign in with Google. Developer-controlled provisioning currently represents an authority issuing credentials; it is not actual government SSO integration.

## 2. Complete architecture

```text
USER'S BROWSER
Next.js + React + custom CSS                port 3000
  |
  | HTTP requests: native fetch, JSON, FormData
  v
BACKEND SERVER
FastAPI running on Uvicorn                  port 8000
  |
  |-- SQLAlchemy -> SQLite
  |     Users, submissions, OCR results, corrections, audits, records
  |
  |-- Local filesystem -> uploads/ and processed images
  |
  |-- OpenCV + Pillow + PyMuPDF -> image preparation
  |-- Tesseract -> text, confidence and word coordinates
  |-- Khatauni extraction rules -> labelled values and table cells
  |       |-- optional cached TrOCR -> handwriting candidates
  |
  `-- Google OAuth endpoints -> submitter account identity
```

**Why two servers?** Next.js handles pages and browser interactions. FastAPI handles data operations, Python OCR libraries and persistence. Keeping them separate makes the API reusable for another frontend or mobile client.

**Why a database and file storage?** SQL stores structured information and relationships. The filesystem stores uploaded image/PDF bytes. A database row contains a path/reference to the file rather than being the image itself.

**Why an officer stage?** OCR can misread handwriting, digits, table boundaries and poor-quality scans. Human correction is part of the core workflow, not an afterthought.

## 3. Technology map — what was used for what

Versions mentioned here are the repository's declared versions, not a promise that all pins install together on a fresh machine or a recommendation to deploy them indefinitely.

### 3.1 Frontend technologies

| Technology | What it does here | Why / where it is used |
| --- | --- | --- |
| JavaScript + JSX | Describes interface components and browser behavior | Most active pages under `frontend/src` |
| React 19.0.0 | Components, state, effects and event handling | Login forms, uploads, dashboards, editable review |
| Next.js 15.1.2 App Router | Routes, shared layouts, navigation, dev server and builds | `frontend/src/app`, `next.config.ts` |
| TypeScript 5.7.2 | Configuration and some source files; type tooling | `tsconfig.json`, `next.config.ts`; active UI is mostly JSX, not entirely TypeScript |
| Custom CSS | Colors, layout, spacing, responsive behavior and source/review panes | `globals.css`, `polish.css`, `khatauni-review.css`, `review-polish.css`, `login.css` |
| Lucide React | Consistent icons | Sidebar, upload, OCR, edit and decision controls |
| Native `fetch` | Calls the Python backend over HTTP | `frontend/src/lib/api.js` |
| `FormData` + file input | Sends a file together with location/document metadata | Submitter and officer upload pages |
| Browser `localStorage` | Remembers the returned display identity in the demo | `frontend/src/lib/auth.js`; **not secure server authentication** |
| Node.js + npm | Runs frontend tooling and installs dependencies | `package.json`, `package-lock.json`, npm commands |

`axios`, `react-dropzone`, `date-fns`, `clsx` and Tailwind/PostCSS-related packages are listed in the frontend manifest. However, the active workflow examined uses native fetch, native file inputs and custom CSS. **Installed does not mean actively used.** Do not copy every dependency without understanding its role.

### 3.2 Backend and database technologies

| Technology | What it does here | Why / where it is used |
| --- | --- | --- |
| Python | Backend logic and image-processing code | OCR ecosystem and API implementation |
| FastAPI 0.115.6 | HTTP routes, validation integration, dependencies and generated API docs | `backend/main.py`, `backend/routers/` |
| Uvicorn 0.34.0 | Runs the FastAPI ASGI application | Backend startup command |
| Pydantic | Defines/validates API payload shapes and serializes responses | `backend/schemas.py` |
| SQLAlchemy 2.0.36 | Maps Python objects to SQL tables; manages queries/transactions | `database.py`, `models.py`, routers |
| SQLite | Local relational persistence without a separate DB service | `sql_app.db`, relative to backend process working directory |
| python-dotenv | Reads local environment configuration | `main.py`, `config.py`, auth router |
| python-multipart | Enables FastAPI multipart file/form parsing | Upload endpoints |
| Python `hashlib`, `hmac`, `secrets` | File digests, password hashing, signed state, random tickets | Upload/auth code; different constructions solve different problems |
| Python `urllib` | Backend HTTP requests | Google token/UserInfo calls and optional remote OCR |

Pydantic schemas do not create database tables. SQLAlchemy models do not automatically authenticate API callers. Each layer has a separate job.

### 3.3 OCR and image-processing technologies

| Technology | What it does here | Why / where it is used |
| --- | --- | --- |
| OpenCV headless 4.10.0.84 | Perspective correction, deskew, denoise, contrast/thresholding and grid detection | Image preprocessing and layout recognition |
| NumPy | Holds/manipulates image pixels as arrays | Used alongside OpenCV |
| Pillow 11.0.0 | Cropping, resizing, format conversions, TIFF batching | Preparing OCR input regions |
| PyMuPDF 1.24.14 (`fitz`) | Renders a PDF page into an image | Current flow processes **page one only** |
| Native Tesseract | Actual local OCR executable | Reads Hindi/English printed text and crop candidates |
| pytesseract 0.3.13 | Python wrapper around Tesseract | Receives text, confidence and bounding-box data |
| PyTorch + Transformers | Optional local TrOCR inference | Handwriting candidates in `khatauni_hybrid.py` |
| Hugging Face model cache | Supplies already-downloaded model weights/tokenizer resources | Runtime HTR loader is local-only |
| SentencePiece, Safetensors, torchvision | Declared model-stack support dependencies | Not separate application features |
| RapidFuzz / `difflib.SequenceMatcher` | Approximate text comparison / label matching | Candidate agreement and Khatauni aliases |

Some directly imported modules arrive transitively rather than appearing explicitly in `requirements.txt`. A clean rebuild should review direct dependencies and record a tested compatible environment.

## 4. Active project structure

```text
sihh/
  APPLICATION_REBUILD_NOTES.md        These notes
  frontend/
    package.json / package-lock.json  Frontend dependency definitions
    next.config.ts                   Build/dev configuration
    src/
      app/layout.jsx                 Root document and CSS imports
      app/login/page.jsx             Submitter/officer login screen
      app/user/                      Submitter workspace
      app/officer/                   Officer workspace and review/[id]
      components/                    Reusable UI/navigation
      lib/api.js                     Shared backend request functions
      lib/auth.js                    Demo identity storage
  backend/
    main.py                          ACTIVE API entry point
    database.py                      DB engine and request sessions
    models.py                        SQLAlchemy tables
    schemas.py                       API payload definitions
    config.py                        OCR configuration
    routers/                         auth, users, documents, officer, records
    digitization.py                  Generic OCR token/layout helpers
    khatauni_fast.py                  Guarded template-based fast path
    khatauni_extractor.py             Khatauni field/table mapping
    khatauni_hybrid.py                Recognition candidates and fallbacks
    khatauni_schema.py                Labels, aliases, table columns
    khatauni_structured.py            Validation and structured evidence
    tests/ and diagnostics/          Regression/evaluation helpers
    .env                             PRIVATE local backend configuration
    sql_app.db                       DB if launched from backend/
    uploads/ and storage/            Runtime file directories
```

Important: `backend/app/` is an older separate implementation, not what the active `main.py` imports. Likewise, legacy/prototype/backup frontend directories and `land-record-site` are not the active `frontend/src/app` workflow. Start your study from the paths above.

The active database URL is `sqlite:///./sql_app.db`. The `./` is relative to the **process working directory**, not automatically the directory containing `database.py`. Starting the backend from the repository root can select a different DB and file-storage location.

## 5. Step-by-step rebuild order

Build one working layer at a time. Each step should have a small observable completion check.

### Step 1 — Define the problem and permissions

Write down the document types, required metadata, users, reviewer responsibilities and final outcomes. Separate account creation from permission assignment. Use non-sensitive sample records while developing.

**Output:** a role matrix and a simple upload-to-review flow. You should be able to explain the application without naming any framework.

### Step 2 — Create the interface shell

Use Next.js/React to create `/login`, `/user` and `/officer`. Build reusable navigation, buttons, status badges, loading/error states and responsive CSS. Use state for inputs and active operations.

**Output:** both workspaces can be navigated before OCR exists. Any temporary demonstration data must be clearly labelled.

### Step 3 — Build the backend skeleton

Create the FastAPI app and routers. Introduce Pydantic request/response models and use `/docs` to inspect contracts. Decide what information belongs in JSON and what requires multipart upload.

**Output:** the API starts independently of the frontend and returns predictable responses/errors.

### Step 4 — Design persistence

Implement `database.py`, SQLAlchemy models and request sessions. Separate identity, document metadata, submission status, recognition attempts and corrections. Add migrations rather than deleting older databases when fields change.

**Output:** a test record persists after restart in an isolated development database.

### Step 5 — Implement ordinary authentication and officer provisioning

Create submitter registration with salted password hashes, then password verification. Keep officer creation outside public signup. For a production rebuild, implement server-validated sessions and role/ownership checks at this stage; do not copy the current localStorage-only security boundary.

**Output:** bad passwords fail, public signup cannot create officers, issued officer credentials work.

### Step 6 — Connect the frontend and add Google

Centralize requests in `api.js`. Connect existing email/password forms first. Then add Google's start/callback/exchange flow as an extra submitter option, without removing ordinary signup/login or enabling officer Google access.

**Output:** both submitter methods work independently; Google identities cannot silently become officers.

### Step 7 — Add uploads, duplicate checks and submissions

Use FormData for the file plus metadata. Persist a `Document`, calculate SHA-256, expose an exact-file duplicate check and create a separate `Submission`. In a new build, generate unique storage keys immediately instead of reusing original filenames.

**Output:** upload stores a file; submit separately puts it in the officer queue.

### Step 8 — Preprocess images

Use OpenCV/Pillow for geometry and contrast. Render PDFs with PyMuPDF before image OCR. Keep source and enhanced views separate. Inspect images before trying complex extraction rules.

**Output:** the officer can compare source and enhanced images, and bad inputs fail clearly.

### Step 9 — Add real OCR, then structured extraction

Install native Tesseract and Hindi/English data. Persist raw text and token coordinates. Next map labels and geometry into fields/rows. Only after this works, add a guarded fast template and optional handwriting/remote fallbacks.

**Output:** every candidate value comes from source evidence; unsupported templates fall back; no fake successful OCR.

### Step 10 — Add correction and review

Show source and structured data side by side. Save officer edits separately from machine values. Add row/cell editing and audit history. Preserve empty corrections and low-confidence/engine-disagreement warnings.

**Output:** corrections survive reopening and raw OCR remains available for comparison.

### Step 11 — Add decisions and search

Implement approve/reject/needs-review and verified record references. Search final values and record identifiers. Decide whether approval should freeze a version; the current dynamic read view uses current data, not an immutable approval snapshot.

**Output:** approved data can be found and traced back to its document, recognition and corrections.

### Step 12 — Test, package and harden

Test negative cases and repeat actions, not just one successful scan. Evaluate accuracy separately using verified ground truth. Resolve clean dependency installation and complete the security checklist before public deployment.

**Output:** reproducible tests, documented limitations and a deliberate production plan.

## 6. Setup and environment configuration

### 6.1 Requirements and installation

You need Node.js/npm, a compatible Python environment, native Tesseract with `hin`/`eng` data, and Google OAuth credentials if testing Google login. Optional HTR needs compatible model packages and locally available weights.

For a **fresh environment**, Python 3.12 is a starting point from the project's setup guidance; compatibility must still be verified against all recorded requirements. The manifest includes heavy `torch`, `torchvision` and `transformers` pins. These notes do not certify that those pins resolve on every machine.

```powershell
# From the project root. Create a new .venv only if it does not already exist.
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

For an existing checkout, use its working interpreter instead; it may be `venv2` rather than `.venv`. Do not overwrite a working environment or copy a venv from another machine. Virtual environments can contain paths to Python installations that no longer exist.

```powershell
# From the project root, in another terminal. Fresh frontend checkout:
cd frontend
npm ci
```

`npm ci` installs the lockfile's dependency tree. `npm run dev` starts development. `npm run build` builds the app. `npm start` serves that build; none of these automatically deploy it.

Tesseract is installed separately from `pytesseract`. Verify your actual executable path and languages:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

### 6.2 Where configuration lives

Use `backend/.env` for server settings. `.env.example` is a template, not the runtime file. Create a missing `.env` from the example in your editor, but never overwrite an existing configured file with placeholders. Use `frontend/.env.local` for the browser-visible API origin.

| Variable | Purpose / source |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Public identifier of the Google OAuth Web application client |
| `GOOGLE_CLIENT_SECRET` | Secret issued for that client; backend only |
| `GOOGLE_OAUTH_STATE_SECRET` | Independently generated random application secret, at least 32 characters |
| `GOOGLE_REDIRECT_URI` | Exact backend callback registered with Google |
| `FRONTEND_URL` | Frontend origin to return to after the callback |
| `CORS_ORIGINS` | Additional allowed browser origins, comma-separated |
| `GOVERNMENT_OFFICER_ID` | Admin-issued string ID, for example `GOV-DEV-001` |
| `GOVERNMENT_OFFICER_EMAIL` | Separate officer email; not an existing submitter email |
| `GOVERNMENT_OFFICER_NAME` | Officer display name; a default exists |
| `GOVERNMENT_OFFICER_PASSWORD` | Private issued password; hashed for database storage |
| `TESSERACT_CMD` | Native executable path |
| `TESSERACT_LANGUAGES` | Defaults to `hin+eng` |
| `KHATAUNI_ENABLE_HTR` | Optional local handwriting recognition; default on, `0` disables |
| `KHATAUNI_HTR_MODEL` | Local model directory or cached model ID; default `aayushpuri01/TrOCR-Devanagari` |
| `KHATAUNI_HTR_MAX_CROPS` | HTR crop budget, default 4 |
| `LANDSIGHT_ENV` | `production` disables the development reset route; it does not secure the entire app |
| `NEXT_PUBLIC_API_URL` | Browser-visible backend origin, set on the frontend |

Local URL settings:

```dotenv
# backend/.env — addresses only; add your private credentials separately
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
FRONTEND_URL=http://127.0.0.1:3000
CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
TESSERACT_LANGUAGES=hin+eng
```

```dotenv
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Generate a private state secret locally; the command prints it in your terminal, so do not share its output:

```powershell
# From backend/, with your working interpreter
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste that output after `GOOGLE_OAUTH_STATE_SECRET=`. It is **not** a Google-issued secret. Never use the literal `replace-with-a-random-secret...` placeholder. Write ordinary underscores in variable names, not backslashes such as `GOOGLE\_CLIENT\_ID`.

Secrets must not go into `NEXT_PUBLIC_*`, screenshots, source control or these notes. Existing process environment values take precedence over the active dotenv loads; a stale shell variable can override an edited `.env`.

### 6.3 Starting the application

```powershell
# Terminal 1: working directory backend/
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
# Terminal 2: working directory frontend/
npm run dev
```

Open `http://127.0.0.1:3000`; API docs are at `http://127.0.0.1:8000/docs`.

Restart the **backend** after backend environment changes; restarting only npm does not reload Python settings. Restart/rebuild the frontend after public environment changes. Use one frontend hostname consistently because `localhost` and `127.0.0.1` have different browser storage origins.

On import, `main.py` creates missing tables, applies additive SQLite changes and provisions the configured officer. Officer ID/email/password must be set together. Changing the configured officer password updates its database hash on startup. Do not import the real app just to inspect settings if you want to avoid startup writes.

## 7. Login, signup and Google OAuth

### 7.1 Ordinary signup and login

Submitter registration validates name, email and password, normalizes email, and creates `role="user"`. It stores a PBKDF2-SHA256 password hash using a random salt and 600,000 iterations. Login recalculates the hash and uses `hmac.compare_digest` for verification.

The server does not need to store the plaintext password. A salt prevents equal passwords having identical stored hashes; the stored algorithm/work factor lets verification reproduce the calculation.

Officer login uses the issued **string identifier** and password. Other workflow endpoints often call their numeric `User.id` parameter `officer_id`; do not confuse that database number with the issued login identifier.

### 7.2 Google client configuration

Create/select a Google OAuth client of type **Web application**. Put its client ID and client secret in backend settings. A Gemini API key, Gmail password or service-account key is not the OAuth client secret. Save a newly issued secret privately when shown; if it is lost, use Google's secret management rather than assuming it remains viewable. See [Google's web-server OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server).

Register the exact backend callback under **Authorized redirect URIs**:

```text
http://127.0.0.1:8000/api/auth/google/callback
```

The scheme, host, port, path and trailing slash must match the request. Adding only the frontend origin under JavaScript origins does not register the backend callback. This exact-match rule is described by [Google](https://developers.google.com/identity/protocols/oauth2/web-server#redirect-uri).

Use appropriate consent/audience settings for your testers. After saving configuration, start a fresh sign-in from the application instead of refreshing an old error URL.

### 7.3 Complete Google flow

```text
Continue with Google
  -> GET /api/auth/google/start
  -> Google account selection, with signed state
  -> Google redirects to backend /api/auth/google/callback
  -> backend exchanges authorization code for access token
  -> backend calls Google UserInfo and checks verified email + stable subject
  -> find/link/create submitter, or reject an officer identity
  -> frontend /login?oauth_ticket=...
  -> POST /api/auth/google/exchange
  -> save display identity -> navigate to /user
```

The scopes are `openid email profile`: identity, **not Gmail messages**. The implementation reads UserInfo with the access token; it does not implement a separate ID-token validation flow.

An existing password submitter can link Google without losing their password hash. A new Google-only account has no password hash, so it must use Google until a password-setting feature is added. Keeping email/password as a UI option does not automatically give Google-created accounts a password.

State is HMAC-signed and expires after 10 minutes. The frontend handoff ticket expires after 5 minutes and is consumed once. Tickets are stored in one Python process and disappear on restart. Neither mechanism creates a persistent authenticated server session in this implementation.

### 7.4 Two different errors from this project

- **`redirect_uri_mismatch`:** Google rejected the callback address. Compare the actual request's `redirect_uri` with the registered URI on the same client as `GOOGLE_CLIENT_ID`.
- **`google_error=submitter_only`:** the application found that Google identity under a non-submitter role. Selecting “Record Submitter” in the dropdown does not change a stored database role. Use the correct account or perform an explicitly reviewed admin migration; never silently convert officers.

One error is Google configuration; the other is the application's account-role rule. Changing the state secret does not fix either of these causes.

## 8. Database design and relationships

| Model | What it stores | Why it is separate |
| --- | --- | --- |
| `User` | Identity, role, password hash, Google subject, issued officer ID | Identity is separate from document content |
| `Document` | Source path/name, location metadata, digest, processed path, duplicate result | Uploading does not necessarily mean submitting |
| `Submission` | User/document references, status and time | Tracks the review lifecycle |
| `OCRResult` | One attempt's text, engine, confidence, token coordinates and layout metadata | Multiple recognition attempts can coexist |
| `ExtractedField` | Older fixed-field extraction representation | Legacy compatibility |
| `DynamicExtractedItem` | Labelled value, machine reading, correction/final value and evidence | Varying document labels need not become new SQL columns |
| `DynamicExtractedTable` / `DynamicExtractedCell` | Headers, row/column positions, values and evidence | Preserves editable tabular information |
| `DynamicDigitizationAudit` | Structured changes and before/after evidence | Explains edits |
| `VerifiedRecord` | Record identifier, submission/officer references, legacy summary | Represents the review outcome |
| `AuditLog` | Lifecycle events and metadata | Tracks upload, processing and decisions |

Relationships: User -> many Submissions; Document -> many Submissions/OCRResults; OCRResult -> dynamic extracted data; Submission -> verified record reference. A database relationship is not an access-control rule.

**Important value layers:** raw OCR/AI values preserve machine output; `officer_value` preserves a correction; `final_value` represents the saved final reading. The UI prefers corrected/final values but keeps OCR evidence visible.

An intentional empty string is different from `null`. JavaScript `??` preserves `""`; replacing it with `||` could make a cleared wrong value reappear from OCR fallback.

Dynamic entities use soft deletion to hide removed data while retaining evidence. Re-extraction retires unedited automatic output for that OCR and preserves human edits. Current views select the latest OCR generation plus manual entries, rather than mixing every historical OCR attempt.

`Base.metadata.create_all` creates missing tables; it is not a complete migration system. `main.py` performs particular additive column/index changes for older SQLite databases.

Transaction vocabulary: `db.add` schedules a row; `db.flush` sends pending changes and can obtain IDs without committing; `db.commit` commits; `db.refresh` reloads saved attributes. `get_db` closes the request session in `finally`; closing is not a commit. Multiple commits in one workflow do not make the entire workflow atomic.

## 9. Document processing explained

### 9.1 Upload, hash and submit

The browser sends binary file plus metadata using FormData. FastAPI saves the file and commits a Document. SHA-256 is calculated in chunks, avoiding loading the entire file merely to hash it.

Equal hashes detect an **exact-byte duplicate**. Two photos of the same paper can have different hashes. A duplicate flag is not a fraud or legal finding. The check is advisory; the current submit flow does not require it to have run.

Submitting creates `SUBMITTED`; officer upload creates `PROCESSING` directly. The officer submission-detail GET can also move `SUBMITTED` to `PROCESSING`, so the current API is not a strictly read-only GET design.

### 9.2 Preprocessing — improve pixels before reading

OpenCV and Pillow handle geometry/contrast, potentially including perspective correction, grayscale, deskew, denoise, contrast enhancement and thresholding. Different processing paths do not necessarily apply every transformation.

PyMuPDF renders the first PDF page at scale 2. The enhanced result is saved separately for review. Browser PDF preview does not imply that every PDF page was recognized.

### 9.3 OCR — convert pixels into text and coordinates

The guarded fast path detects Khatauni geometry and validates printed header anchors before assuming its seven-column layout. It groups isolated crops by field type and batches Tesseract calls. PSM 7 treats each crop as a line. A mismatched template must fall back rather than forcing an unrelated document into those columns.

The generic OCR path uses Tesseract word data, normally `hin+eng` with PSM 6. It stores text, confidence, word boxes and metadata. Source/processed digests guard layout reuse so cached geometry is not applied to changed image bytes.

An HTTP `200` response can still contain `status="OCR_FAILED"`. The frontend must check recognition status in the body, not just whether the network request succeeded.

### 9.4 Extraction — interpret recognized words

`digitization.py` handles words, lines and geometry. `khatauni_extractor.py` maps Khatauni labels/table positions into candidate fields. `khatauni_schema.py` contains label/column definitions, **not answers**. `khatauni_structured.py` adds format validation, warnings and evidence views.

Example concept: OCR produces a word with text and coordinates; extraction associates that word with a “district” label or a specific table column. OCR answers “what characters are visible?” Extraction answers “what field do they belong to?”

Dynamic tables support varying data shapes, but current recognition and review remain Khatauni-oriented. An upload dropdown listing other document types is not evidence of full extraction support for them.

### 9.5 Optional local handwriting recognition

TrOCR runs through PyTorch/Transformers for selected crop candidates. Loading is lazy and synchronized; the model is reused, not reloaded for every field. It uses CUDA if available or CPU otherwise. The loader accepts local model files/an already-cached snapshot and does not download weights during inference. Missing/incompatible resources produce an unavailable fallback.

Candidate selection uses validity, confidence and agreement. Missing confidence must remain unavailable, not receive an invented percentage. A valid-looking number can still be the wrong number.

### 9.6 Correction, decision and records

The review screen displays source/enhanced image, fields, table cells, raw OCR and token evidence. It currently displays the first table, even though storage/API can represent multiple tables. Field/cell edits save on blur; the mutation helper then refreshes structure and audits. “Save Corrections” refreshes persisted data rather than performing a separate bulk-save transaction.

```text
Intended progression:
SUBMITTED -> PROCESSING -> VERIFIED
                       -> NEEDS_REVIEW
                       -> REJECTED
```

This is not yet a fully enforced immutable state machine. Approval requires OCR or manual digitization and creates/updates a record with an ID derived from location prefixes and submission number. That check does not prove that recognition succeeded or all values were reviewed.

Verified-record views combine legacy summary with current dynamic information. They are not frozen snapshots of the exact values at approval time; versioning is an important future design decision.

## 10. Frontend and API communication

Next.js page folders define routes and layouts wrap pages. Interactive components use `'use client'` for browser state, effects and navigation. The root layout imports CSS layers; shared components keep both workspaces consistent. See the [Next.js 15 layout reference](https://nextjs.org/docs/15/app/api-reference/file-conventions/layout).

The shared `request` helper builds the API URL, calls native fetch, parses JSON and throws backend error messages. React pages set loading/error state around asynchronous operations. The Google button uses full browser navigation: fetch alone would not open Google's account-selection page.

For file uploads, let the browser generate multipart `Content-Type` and its boundary. Do not set `application/json` for FormData.

| Request | Purpose |
| --- | --- |
| `POST /api/auth/register` | Submitter signup |
| `POST /api/auth/login` | Email/password or issued-ID/password login |
| `GET /api/auth/google/start` | Begin Google browser redirect |
| `GET /api/auth/google/callback` | Receive Google's code/state on the backend |
| `POST /api/auth/google/exchange` | Consume the one-use frontend handoff ticket |
| `GET /api/user/dashboard?user_id=...` | Submitter dashboard |
| `GET /api/user/submissions?user_id=...` | Submitter history |
| `POST /api/documents/upload` | Store file/metadata, return document ID |
| `POST /api/documents/{id}/duplicate-check` | Compare file digests |
| `POST /api/documents/{id}/submit?user_id=...` | Put uploaded document into review |
| `POST /api/documents/officer-upload` | Officer upload and processing entry |
| `GET /api/officer/submissions` | Officer queue |
| `POST /api/officer/documents/{id}/preprocess` | Save enhanced image |
| `POST /api/officer/documents/{id}/ocr` | Recognize text/boxes |
| `POST /api/officer/documents/{id}/extract?ocr_id=...` | Create structured fields/tables |
| `GET /api/officer/documents/{id}/digitization` | Read current structure |
| `/api/officer/documents/{id}/dynamic-fields` and `/tables/...` | POST/PATCH/DELETE structure editing routes |
| `POST /api/officer/documents/{id}/{action}?officer_id=...` | `approve`, `reject`, `mark-review` |
| `GET /api/verified-records/?search=...` and `/{id}` | Search and record detail |
| `GET /api/officer/audit` | Audit history |

Use the running `/docs` for complete payload definitions and editing endpoints. `{id}` in document actions/review is a **document ID**, not necessarily a submission ID. Officer routes also have `/api` aliases; the active frontend primarily uses `/api/officer`.

## 11. File-by-file study order

Open these source files alongside these notes; no new code comments are necessary to follow the flow.

| Order | Source | Focus / what to learn |
| --- | --- | --- |
| 1 | [database.py](backend/database.py) | Relative DB path, engine, session lifecycle |
| 2 | [models.py](backend/models.py) | Entities, foreign keys, machine versus human values |
| 3 | [schemas.py](backend/schemas.py) | Request validation and ORM response serialization |
| 4 | [main.py](backend/main.py) | Startup writes, officer provisioning, mounts, CORS, router prefixes |
| 5 | [auth router](backend/routers/auth.py) | Password hashing, roles, state, callback, ticket exchange |
| 6 | [login page](frontend/src/app/login/page.jsx) | Form state, login/signup switch, Google redirect handling |
| 7 | [api.js](frontend/src/lib/api.js) / [auth.js](frontend/src/lib/auth.js) | Transport helpers versus browser identity storage |
| 8 | [upload page](frontend/src/app/user/upload/page.jsx) / [documents router](backend/routers/documents.py) | Upload -> check -> submit as separate actions |
| 9 | [officer router](backend/routers/officer.py) | `_load_document_image` -> preprocess -> OCR -> extract -> edit -> verify |
| 10 | [digitization.py](backend/digitization.py) / [khatauni_fast.py](backend/khatauni_fast.py) | Token geometry and guarded recognition |
| 11 | [extractor](backend/khatauni_extractor.py) / [hybrid](backend/khatauni_hybrid.py) | Domain mapping and local recognition candidates |
| 12 | [schema](backend/khatauni_schema.py) / [structured](backend/khatauni_structured.py) | Labels, validation and evidence |
| 13 | [review page](frontend/src/app/officer/review/[id]/page.jsx) | `valueOf`, `normalizeDigitization`, `execute`, `mutate`, `decide` |
| 14 | [records router](backend/routers/records.py) | Latest OCR/manual view, final values and search |
| 15 | [PortalShell](frontend/src/components/layout/PortalShell.jsx) / [root layout](frontend/src/app/layout.jsx) | Shared navigation and stylesheet layering |
| 16 | [hybrid tests](backend/tests/test_part2_hybrid.py) / [fast-path tests](backend/tests/test_fast_khatauni.py) | Regression expectations and fixtures |

The key learning question at each boundary is: **What input arrives here, what transformation happens, what is persisted, and what can fail?**

## 12. Testing and troubleshooting

### 12.1 Validation commands

Use the working environment's interpreter; substitute `venv2` for `.venv` if appropriate.

```powershell
# From backend/: parse without importing main or changing the database.
.\.venv\Scripts\python.exe -c "import ast,pathlib; paths=list(pathlib.Path('.').glob('*.py'))+list(pathlib.Path('routers').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8-sig')) for p in paths]; print('Python syntax OK')"

# Regression tests, from backend/.
.\.venv\Scripts\python.exe -m unittest tests.test_part2_hybrid -v
.\.venv\Scripts\python.exe -m unittest tests.test_fast_khatauni -v
```

```powershell
# From frontend/
npm run build
```

Read tests before running them in a new environment. API regression tests use temporary DB/uploads, but provider configuration can still read local environment settings. Some real OCR checks need a local acceptance image and native Tesseract; missing fixtures can skip tests. TestClient needs `httpx`, not explicitly listed in the current requirements. Record passes, failures and skips separately.

The frontend build skips linting in `next.config.ts`, and `checkJs` is false. Build success is not full lint/type/security validation. Development uses `.next`; builds use `.next-build` to avoid overwriting an active dev session's assets.

### 12.2 Manual acceptance checklist

- Register a new submitter; check wrong and correct password login.
- Sign in with Google as a new user and an existing password submitter.
- Verify that officer signup/Google are unavailable and issued credentials work.
- Upload a non-sensitive, uniquely named scan; check duplicate and submit separately.
- Preprocess, OCR and extract; inspect source, raw text and coordinates.
- Correct a field/cell, add/delete a row, reopen and check saved values/audit.
- Approve and search for a corrected value; inspect record detail.
- Test reject, needs-review, poor scans, blank files and template mismatch.
- Test PDF first-page behavior, missing model/executable, restart and second accounts.

Mocked tests check logic, not actual OCR accuracy. Accuracy claims need representative samples and human-verified ground truth. Never run the development reset endpoint against records you want to keep.

### 12.3 Common errors

| Symptom | What to check |
| --- | --- |
| Google not configured | Backend ID/secret/state settings, state length, literal underscores, actual `.env`, stale process variables, backend restart |
| `redirect_uri_mismatch` | Actual request URI versus saved callback on the correct OAuth client; host/port/path/trailing slash |
| `submitter_only` | Stored role of the Google identity, not just the selected UI dropdown |
| Google succeeds but login page returns | Callback result, ticket expiry/reuse, backend restart, frontend origin and duplicate ticket-exchange requests |
| Expired state/ticket | Start a new flow; do not reuse an old callback URL |
| Officer provisioning failure | Required variables set together, ID format, email/account collision |
| Users/data seem missing | Backend working directory and selected `sql_app.db` |
| CORS/failed fetch | API running, correct public API URL, allowed frontend origin; another device's `127.0.0.1` points to itself |
| Tesseract unavailable | Native executable path and installed `hin`/`eng` traineddata |
| PDF visible but OCR fails | Preprocess/rasterization result; PyMuPDF availability; only first page supported |
| HTR unavailable | Model files/cache, compatible packages, enable flag; no automatic inference-time downloads |
| Unexpected displayed values | Correct document ID, latest OCR generation, soft deletion, correction/final precedence |

Do not paste secrets, OAuth codes or tickets into debugging messages. Error text and non-secret URL/configuration names are normally enough to begin diagnosis.

## 13. Current limitations and production improvements

These are **observed limitations and proposed next steps**, not changes performed while writing these notes.

1. **Authentication/authorization:** the app saves display identity in editable localStorage; it does not have a complete server-session layer. Several routes use caller-supplied IDs or lack authentication. Add server-validated sessions, per-route role/ownership checks, and derive actor identity on the server. CORS and frontend role redirects are not security boundaries.
2. **OAuth:** state is signed/age-limited but not browser-session-bound. Add replay protection and reviewed code-flow protections; consider a maintained OAuth/OIDC implementation. Replace process-local tickets for multiple workers and handle duplicate exchanges robustly. Review automatic email linking policy.
3. **File safety/privacy:** original basenames are used for storage, so same-name uploads can overwrite evidence. Add unique server-generated keys, content/type/size validation and safe processed-path handling. `/uploads` and `/storage` are public mounts; replace them with authorized delivery for confidential files.
4. **Workflow integrity:** enforce allowed transitions, idempotency and meaningful completion requirements. Avoid state changes on GET. Decide how later edits/rejection affect verified records; use immutable approved versions where required.
5. **Persistence/operations:** add versioned migrations, constraints, transaction review, backups and restore tests. Consider a server database/object storage when operational requirements justify them; neither is currently implemented here.
6. **Long tasks:** OCR runs within the request workflow. At scale, add durable jobs/workers, progress/status, time limits, retries and cancellation. There is no distributed OCR queue in the current implementation.
7. **Provider privacy:** optional remote OCR sends document crops externally. Validate service contracts, permissions, data handling and retention before using real records. SQL audit rows are not tamper-proof merely because they are called audits.
8. **Account operations:** add rate limits, password reset, ordinary email verification, controlled officer administration/rotation and stronger officer authentication as needed. There is no universal safe demo password to share.
9. **Coverage:** add multi-page/multi-table review, more document recognizers and verified-ground-truth benchmarks. Selecting “Other” in a dropdown does not implement another recognizer.
10. **Deployment:** review supported dependency versions, clean installation, tests/linting, HTTPS, private secrets and monitoring. `LANDSIGHT_ENV=production` disables reset but does not fix the above. No deployment, CI guarantee or real government integration is implied by these notes.

Do not commit real `.env` files, account passwords, private databases, confidential uploads or model artifacts without an explicit distribution/licensing decision.

## 14. Reusing the design and quick revision

### 14.1 What to keep and what to replace

Keep the conceptual pattern: **intake -> evidence -> recognition -> structured draft -> human review -> searchable outcome -> audit**. Reuse modular API boundaries, validation, source previews and correction provenance after fixing the listed security/storage gaps.

| Another application | Domain-specific parts to replace | Concepts that transfer |
| --- | --- | --- |
| Invoice processing | Vendor/invoice/tax/line-item labels and validation | OCR evidence, editable tables, approval audit |
| Certificate review | Certificate layout, fields and authority checks | Identity separation, source comparison, reviewer decision |
| Form/application processing | Form schema, reviewer roles and workflow rules | Upload queue, corrections, statuses, searchable records |

For broader support, introduce recognizer interfaces by document type, versioned schemas, page-aware coordinates and a generic multi-table UI. These are future improvements, not existing universal-document capability.

### 14.2 Quick revision

| Term | Remember it as |
| --- | --- |
| Frontend | What users see and interact with |
| Backend | Validates/processes requests and coordinates persistence |
| API | Contract between interface and server |
| ORM | Python objects mapped to SQL rows |
| OCR | Pixels -> characters/words |
| HTR | Handwriting recognition |
| Extraction | Words/geometry -> labelled fields and cells |
| Bounding box | Where recognized content came from |
| Confidence | Recognition evidence, not certainty or legal truth |
| SHA-256 file digest | Exact-file duplicate comparison |
| Password hash | One-way password verification, with salt/work factor |
| HMAC state | Tamper detection for OAuth state, not a complete session |
| Callback | Google returns to the backend, not directly to the dashboard |
| Provenance/audit | Source of a value and history of changes |

### 14.3 Questions to answer before rebuilding independently

1. Why are Next.js, FastAPI and SQLite separate responsibilities?
2. Why are Document, Submission, OCRResult and VerifiedRecord separate entities?
3. Why does adding Google not remove password login or grant officer permissions?
4. Why must machine readings and officer corrections remain separate?
5. Why is a template allowed to define positions/labels but not answers?
6. Why do browser role checks and CORS not protect database records?
7. Which work is currently local, which can call external services, and what data leaves the server?
8. What must be fixed before using real confidential documents?

### 14.4 Primary learning references

- [Next.js 15 layouts](https://nextjs.org/docs/15/app/api-reference/file-conventions/layout) — page/layout conventions.
- [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server) — client credentials, callback and authorization flow.
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) — API routes, validation, dependencies and uploads.
- [SQLAlchemy tutorial](https://docs.sqlalchemy.org/en/20/tutorial/) — engine, ORM models, sessions and transactions.
- [Tesseract documentation](https://tesseract-ocr.github.io/) — OCR installation, languages and recognition options.
- [OpenCV documentation](https://docs.opencv.org/4.x/) — image-processing operations.

Repository-specific descriptions come from the active source/manifests linked in section 11. External references explain technologies and can evolve independently of this checkout.
