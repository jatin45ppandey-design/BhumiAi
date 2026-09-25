"""One-time BhumiAI demo-data reset.

Run from ``backend`` only after reviewing the printed inspection report:

    .venv/Scripts/python.exe scripts/reset_demo_data.py --inspect
    .venv/Scripts/python.exe scripts/reset_demo_data.py \
        --execute RESET-BHUMIAI-DEMO-DATA

This script is never imported by application startup. It preserves the schema,
indexes, officer rows, officer credentials, and officer sessions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DATABASE_PATH = BACKEND_ROOT / "sql_app.db"
STORAGE_ROOTS = (BACKEND_ROOT / "uploads", BACKEND_ROOT / "storage")
CONFIRMATION = "RESET-BHUMIAI-DEMO-DATA"

os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

import models  # noqa: E402


MODEL_TABLES = {
    model.__tablename__
    for model in (
        models.User,
        models.UserSession,
        models.PhoneOtpChallenge,
        models.EmailVerificationChallenge,
        models.Document,
        models.Submission,
        models.OCRResult,
        models.ExtractedField,
        models.DynamicExtractedItem,
        models.DynamicExtractedTable,
        models.DynamicExtractedCell,
        models.DynamicDigitizationAudit,
        models.VerifiedRecord,
        models.AuditLog,
        models.UserNotification,
    )
}


def connect(*, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def scalar(connection: sqlite3.Connection, sql: str, parameters: tuple[Any, ...] = ()) -> int:
    return int(connection.execute(sql, parameters).fetchone()[0])


def require_expected_database(connection: sqlite3.Connection) -> None:
    if not DATABASE_PATH.is_file() or DATABASE_PATH.stat().st_size <= 0:
        raise RuntimeError(f"Active database is missing or empty: {DATABASE_PATH}")
    actual = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    missing = sorted(MODEL_TABLES - actual)
    if missing:
        raise RuntimeError(f"Active database is missing model tables: {', '.join(missing)}")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Active database failed SQLite integrity_check")


def schema_signature(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, COALESCE(sql, '')
            FROM sqlite_master
            WHERE type IN ('table', 'index', 'trigger')
            ORDER BY type, name
            """
        )
    ]


def officer_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(users)")]
    selected = ", ".join(f'"{column}"' for column in columns)
    return [
        tuple(row)
        for row in connection.execute(
            f"SELECT {selected} FROM users WHERE role='officer' ORDER BY id"
        )
    ]


def file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    if root != (BACKEND_ROOT / root.name).resolve():
        raise RuntimeError(f"Refusing unexpected storage root: {root}")
    if not root.exists():
        return {}
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink in operational storage: {path}")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            manifest[path.relative_to(root).as_posix()] = {
                "size": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
    return manifest


def operational_file_count() -> int:
    return sum(len(file_manifest(root)) for root in STORAGE_ROOTS)


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    statuses = {
        row[0]: int(row[1])
        for row in connection.execute(
            "SELECT status, COUNT(*) FROM submissions GROUP BY status"
        )
    }
    extraction_tables = (
        "ocr_results",
        "extracted_fields",
        "dynamic_extracted_items",
        "dynamic_extracted_tables",
        "dynamic_extracted_cells",
    )
    return {
        "officer_accounts": scalar(connection, "SELECT COUNT(*) FROM users WHERE role='officer'"),
        "citizen_accounts": scalar(connection, "SELECT COUNT(*) FROM users WHERE role='user'"),
        "citizen_profiles": scalar(connection, "SELECT COUNT(*) FROM users WHERE role='user' AND profile_completed_at IS NOT NULL"),
        "citizen_sessions": scalar(connection, "SELECT COUNT(*) FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE role='user')"),
        "otp_challenges": scalar(connection, "SELECT COUNT(*) FROM phone_otp_challenges"),
        "email_challenges": scalar(connection, "SELECT COUNT(*) FROM email_verification_challenges"),
        "documents": scalar(connection, "SELECT COUNT(*) FROM documents"),
        "submissions": scalar(connection, "SELECT COUNT(*) FROM submissions"),
        "uploaded_drafts": statuses.get("UPLOADED", 0),
        "submitted": statuses.get("SUBMITTED", 0),
        "processing": statuses.get("PROCESSING", 0),
        "needs_review": statuses.get("NEEDS_REVIEW", 0),
        "review_queue": sum(statuses.get(value, 0) for value in ("SUBMITTED", "PROCESSING", "NEEDS_REVIEW")),
        "verified_submissions": statuses.get("VERIFIED", 0),
        "rejected_submissions": statuses.get("REJECTED", 0),
        "verified_records": scalar(connection, "SELECT COUNT(*) FROM verified_records"),
        "ocr_results": scalar(connection, "SELECT COUNT(*) FROM ocr_results"),
        "ocr_extraction_rows": sum(scalar(connection, f"SELECT COUNT(*) FROM {table}") for table in extraction_tables),
        "corrections": scalar(connection, "SELECT COUNT(*) FROM dynamic_digitization_audits"),
        "notifications": scalar(connection, "SELECT COUNT(*) FROM user_notifications"),
        "duplicate_cases": scalar(connection, "SELECT COUNT(*) FROM documents WHERE duplicate_of_id IS NOT NULL"),
        "document_audit_provenance": scalar(
            connection,
            "SELECT COUNT(*) FROM audit_logs WHERE document_id IS NOT NULL OR submission_id IS NOT NULL OR record_id IS NOT NULL",
        ) + scalar(connection, "SELECT COUNT(*) FROM dynamic_digitization_audits"),
        "operational_files": operational_file_count(),
    }


def create_backup(connection: sqlite3.Connection) -> tuple[Path, dict[str, dict[str, dict[str, Any]]]]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = PROJECT_ROOT / "backup" / f"pre_demo_reset_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=False)

    database_backup = backup_path / DATABASE_PATH.name
    backup_connection = sqlite3.connect(database_backup)
    try:
        connection.backup(backup_connection)
    finally:
        backup_connection.close()
    if database_backup.stat().st_size <= 0:
        raise RuntimeError("Database backup is empty")
    with sqlite3.connect(f"file:{database_backup}?mode=ro", uri=True) as verification:
        if verification.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Database backup failed integrity_check")

    manifests: dict[str, dict[str, dict[str, Any]]] = {}
    for root in STORAGE_ROOTS:
        root.mkdir(parents=True, exist_ok=True)
        source_manifest = file_manifest(root)
        destination = backup_path / root.name
        shutil.copytree(root, destination)
        destination_manifest = file_manifest_for_backup(destination)
        if source_manifest != destination_manifest:
            raise RuntimeError(f"Backup verification failed for {root}")
        manifests[root.name] = source_manifest
    return backup_path, manifests


def file_manifest_for_backup(root: Path) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink in backup: {path}")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            manifest[path.relative_to(root).as_posix()] = {
                "size": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
    return manifest


def clear_storage() -> None:
    for root in STORAGE_ROOTS:
        expected = (BACKEND_ROOT / root.name).resolve()
        resolved = root.resolve()
        if resolved != expected or resolved.parent != BACKEND_ROOT.resolve():
            raise RuntimeError(f"Refusing unexpected storage root: {resolved}")
        root.mkdir(parents=True, exist_ok=True)
        for path in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if path.is_symlink():
                raise RuntimeError(f"Refusing symlink in operational storage: {path}")
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        with tempfile.NamedTemporaryFile(dir=root, prefix=".write-check-", delete=True) as probe:
            probe.write(b"ok")
            probe.flush()


def restore_storage(backup_path: Path) -> None:
    for root in STORAGE_ROOTS:
        root.mkdir(parents=True, exist_ok=True)
        for path in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        shutil.copytree(backup_path / root.name, root, dirs_exist_ok=True)


def pre_reset_authorization_checks() -> dict[str, Any]:
    from dotenv import dotenv_values
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import SessionLocal, engine
    from routers import auth, documents, officer, records, users
    from security import SESSION_COOKIE_NAME, new_session

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users.router, prefix="/api/user")
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(officer.router, prefix="/api/officer")
    app.include_router(records.router, prefix="/api/verified-records")

    result: dict[str, Any] = {
        "citizen_export": "FAILED",
        "officer_login_before": "FAILED",
        "old_citizen_phone": None,
    }
    with SessionLocal() as database:
        row = (
            database.query(models.VerifiedRecord, models.User)
            .join(models.Submission, models.VerifiedRecord.submission_id == models.Submission.id)
            .join(models.User, models.Submission.user_id == models.User.id)
            .filter(models.User.role == "user", models.VerifiedRecord.verification_status == "VERIFIED")
            .order_by(models.VerifiedRecord.id)
            .first()
        )
        if not row:
            raise RuntimeError("No citizen-owned verified record exists for the required pre-reset authorization check")
        record, citizen = row
        if not citizen.phone_number:
            raise RuntimeError("Verified-record citizen has no phone identity")
        _, citizen_token = new_session(database, citizen)
        database.commit()
        result["old_citizen_phone"] = citizen.phone_number
        record_id = record.id

    settings = dotenv_values(BACKEND_ROOT / ".env")
    officer_id = str(settings.get("GOVERNMENT_OFFICER_ID") or "").strip()
    officer_password = str(settings.get("GOVERNMENT_OFFICER_PASSWORD") or "")
    if not officer_id or not officer_password:
        raise RuntimeError("Officer credentials are not configured in backend/.env")

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, citizen_token)
        export = client.get(f"/api/user/records/{record_id}/export/json")
        if export.status_code != 200:
            raise RuntimeError(f"Citizen verified-record export precheck failed with HTTP {export.status_code}")
        result["citizen_export"] = "PASS"
        client.cookies.clear()
        login = client.post("/api/auth/login", json={
            "role": "officer",
            "officer_id": officer_id,
            "password": officer_password,
        })
        if login.status_code != 200:
            raise RuntimeError(f"Officer login precheck failed with HTTP {login.status_code}")
        result["officer_login_before"] = "PASS"

    engine.dispose()
    return result


def delete_operational_rows(connection: sqlite3.Connection) -> None:
    # Delete dependent operational rows first. All names come from active models.
    connection.execute("DELETE FROM user_notifications")
    connection.execute("DELETE FROM dynamic_digitization_audits")
    connection.execute(
        """
        DELETE FROM audit_logs
        WHERE document_id IS NOT NULL
           OR submission_id IS NOT NULL
           OR record_id IS NOT NULL
           OR user_id IN (SELECT id FROM users WHERE role='user')
        """
    )
    connection.execute("DELETE FROM dynamic_extracted_cells")
    connection.execute("DELETE FROM dynamic_extracted_tables")
    connection.execute("DELETE FROM dynamic_extracted_items")
    connection.execute("DELETE FROM extracted_fields")
    connection.execute("DELETE FROM verified_records")
    connection.execute("DELETE FROM ocr_results")
    connection.execute("DELETE FROM submissions")
    connection.execute("UPDATE documents SET duplicate_of_id=NULL")
    connection.execute("DELETE FROM documents")
    connection.execute("DELETE FROM email_verification_challenges")
    connection.execute("DELETE FROM phone_otp_challenges")
    connection.execute("DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE role='user')")
    connection.execute("DELETE FROM users WHERE role='user'")


def cleanup_temporary_citizen(phone_number: str) -> None:
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        citizen_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM users WHERE role='user' AND phone_number=?", (phone_number,)
            )
        ]
        for citizen_id in citizen_ids:
            connection.execute("DELETE FROM user_notifications WHERE user_id=?", (citizen_id,))
            connection.execute("DELETE FROM email_verification_challenges WHERE user_id=?", (citizen_id,))
            connection.execute("DELETE FROM user_sessions WHERE user_id=?", (citizen_id,))
            connection.execute("DELETE FROM audit_logs WHERE user_id=?", (citizen_id,))
            connection.execute("DELETE FROM users WHERE id=?", (citizen_id,))
        connection.execute("DELETE FROM phone_otp_challenges WHERE phone_number=?", (phone_number,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def post_reset_readiness(old_phone: str) -> dict[str, Any]:
    from dotenv import dotenv_values
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import engine
    from routers import auth, documents, officer, records, users

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users.router, prefix="/api/user")
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(officer.router, prefix="/api/officer")
    app.include_router(records.router, prefix="/api/verified-records")

    route_paths = {route.path for route in app.routes}
    settings = dotenv_values(BACKEND_ROOT / ".env")
    officer_id = str(settings.get("GOVERNMENT_OFFICER_ID") or "").strip()
    officer_password = str(settings.get("GOVERNMENT_OFFICER_PASSWORD") or "")
    temp_phone = "+919000000001"
    result: dict[str, Any] = {
        "officer_login": "FAILED",
        "officer_dashboard_zero": "FAILED",
        "old_citizen_login": "FAILED",
        "fresh_registration": "FAILED",
        "citizen_upload_route": "PASS" if "/api/documents/upload" in route_paths else "FAILED",
        "officer_upload_route": "PASS" if "/api/documents/officer-upload" in route_paths else "FAILED",
        "verified_record_route": "PASS" if any(
            path.startswith("/api/verified-records/") for path in route_paths
        ) else "FAILED",
    }

    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "role": "officer",
                "officer_id": officer_id,
                "password": officer_password,
            })
            if login.status_code == 200:
                result["officer_login"] = "PASS"
                dashboard = client.get("/api/officer/dashboard")
                if dashboard.status_code == 200 and all(
                    dashboard.json().get(key) == 0
                    for key in ("total_received", "pending", "processing", "verified", "needs_review", "rejected")
                ):
                    result["officer_dashboard_zero"] = "PASS"
            client.cookies.clear()

            missing = client.post("/api/auth/phone/request-otp", json={
                "phone_number": old_phone,
                "intent": "login",
            })
            if missing.status_code == 404:
                result["old_citizen_login"] = "PASS"

            requested = client.post("/api/auth/phone/request-otp", json={
                "phone_number": temp_phone,
                "intent": "register",
            })
            development_otp = requested.json().get("development_otp") if requested.status_code == 200 else None
            if development_otp:
                verified = client.post("/api/auth/phone/verify-otp", json={
                    "phone_number": temp_phone,
                    "otp": development_otp,
                    "intent": "register",
                })
                profiled = client.put("/api/auth/profile", json={
                    "name": "Reset Verification Citizen",
                    "email": f"reset-verification-{datetime.now().strftime('%Y%m%d%H%M%S')}@example.test",
                    "state": "Uttar Pradesh",
                    "district": "Verification",
                }) if verified.status_code == 200 else None
                dashboard = client.get("/api/user/dashboard") if profiled and profiled.status_code == 200 else None
                if dashboard and dashboard.status_code == 200 and dashboard.json().get("total_submitted") == 0:
                    result["fresh_registration"] = "PASS"
            else:
                result["fresh_registration"] = "PARTIAL"
    finally:
        cleanup_temporary_citizen(temp_phone)
        engine.dispose()
    return result


def orphan_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "submission_document": scalar(connection, "SELECT COUNT(*) FROM submissions s LEFT JOIN documents d ON d.id=s.document_id WHERE d.id IS NULL"),
        "submission_user": scalar(connection, "SELECT COUNT(*) FROM submissions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL"),
        "verified_submission": scalar(connection, "SELECT COUNT(*) FROM verified_records v LEFT JOIN submissions s ON s.id=v.submission_id WHERE s.id IS NULL"),
        "ocr_document": scalar(connection, "SELECT COUNT(*) FROM ocr_results o LEFT JOIN documents d ON d.id=o.document_id WHERE d.id IS NULL"),
        "field_ocr": scalar(connection, "SELECT COUNT(*) FROM extracted_fields f LEFT JOIN ocr_results o ON o.id=f.ocr_result_id WHERE o.id IS NULL"),
        "dynamic_item_document": scalar(connection, "SELECT COUNT(*) FROM dynamic_extracted_items i LEFT JOIN documents d ON d.id=i.document_id WHERE d.id IS NULL"),
        "dynamic_table_document": scalar(connection, "SELECT COUNT(*) FROM dynamic_extracted_tables t LEFT JOIN documents d ON d.id=t.document_id WHERE d.id IS NULL"),
        "dynamic_cell_document": scalar(connection, "SELECT COUNT(*) FROM dynamic_extracted_cells c LEFT JOIN documents d ON d.id=c.document_id WHERE d.id IS NULL"),
    }


def run_reset() -> dict[str, Any]:
    connection = connect()
    backup_path: Path | None = None
    try:
        require_expected_database(connection)
        before = counts(connection)
        if before["officer_accounts"] <= 0:
            raise RuntimeError("No officer account exists; reset refused")
        schema_before = schema_signature(connection)
        officers_before = officer_rows(connection)
        backup_path, manifests = create_backup(connection)

        # Authorization checks exercise real routes and therefore may create
        # disposable session/audit rows. Preserve the untouched database first.
        prechecks = pre_reset_authorization_checks()

        connection.execute("BEGIN IMMEDIATE")
        try:
            delete_operational_rows(connection)
            interim = counts(connection)
            required_zero = (
                "citizen_accounts", "citizen_profiles", "documents", "submissions",
                "verified_records", "ocr_extraction_rows", "notifications",
                "duplicate_cases", "document_audit_provenance",
            )
            nonzero = {key: interim[key] for key in required_zero if interim[key] != 0}
            if nonzero:
                raise RuntimeError(f"Database reset did not reach zero counts: {nonzero}")
            if officer_rows(connection) != officers_before:
                raise RuntimeError("Officer rows changed during reset")
            if schema_signature(connection) != schema_before:
                raise RuntimeError("Schema or indexes changed during reset")
            clear_storage()
            connection.commit()
        except Exception:
            connection.rollback()
            if backup_path is not None:
                restore_storage(backup_path)
            raise
    finally:
        connection.close()

    readiness = post_reset_readiness(str(prechecks["old_citizen_phone"]))
    final_connection = connect(read_only=True)
    try:
        require_expected_database(final_connection)
        after = counts(final_connection)
        officers_after = officer_rows(final_connection)
        schema_after = schema_signature(final_connection)
        integrity = final_connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = len(final_connection.execute("PRAGMA foreign_key_check").fetchall())
        orphans = orphan_counts(final_connection)
    finally:
        final_connection.close()

    if officers_after != officers_before:
        raise RuntimeError("Officer rows differ after readiness checks")
    if schema_after != schema_before:
        raise RuntimeError("Schema or indexes differ after readiness checks")
    if after["operational_files"] != 0:
        raise RuntimeError("Operational files remain after reset")
    if any(orphans.values()) or foreign_key_violations:
        raise RuntimeError("Post-reset orphan or foreign-key validation failed")

    report = {
        "backup_path": str(backup_path),
        "backup_database_verified": True,
        "backup_operational_files_verified": sum(len(value) for value in manifests.values()),
        "before": before,
        "after": after,
        "prechecks": {key: value for key, value in prechecks.items() if key != "old_citizen_phone"},
        "readiness": readiness,
        "database": {
            "integrity": integrity,
            "foreign_key_violations": foreign_key_violations,
            "orphans": orphans,
            "schema_preserved": schema_after == schema_before,
            "indexes_preserved": schema_after == schema_before,
        },
        "officer_rows_preserved": officers_after == officers_before,
    }
    return report


def inspect() -> dict[str, Any]:
    connection = connect(read_only=True)
    try:
        require_expected_database(connection)
        return {
            "database": str(DATABASE_PATH),
            "model_tables": sorted(MODEL_TABLES),
            "counts": counts(connection),
            "officer_rows_to_preserve": scalar(connection, "SELECT COUNT(*) FROM users WHERE role='officer'"),
            "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "schema_objects": len(schema_signature(connection)),
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up and reset BhumiAI demo/runtime data while preserving officers.")
    parser.add_argument("--inspect", action="store_true", help="Print the resolved database, model tables, and current counts without changing data.")
    parser.add_argument("--execute", metavar="CONFIRMATION", help=f"Required exact value: {CONFIRMATION}")
    arguments = parser.parse_args()
    if arguments.inspect:
        print(json.dumps(inspect(), ensure_ascii=False, indent=2))
        return 0
    if arguments.execute != CONFIRMATION:
        parser.error(f"Destructive reset refused. Pass --execute {CONFIRMATION}")
    print(json.dumps(run_reset(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
