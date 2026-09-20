from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import auth, users, officer
from security import SESSION_COOKIE_NAME, new_session


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bhumi-auth-")
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'auth.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine); self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            self.officer = models.User(name="Officer", email="officer@example.test", role="officer", officer_id="GOV-TEST-1", password_hash=auth.hash_password("issued-password"))
            self.other = models.User(name="Other", email="other@example.test", role="user", phone_number="+919876543211", phone_verified_at=datetime.datetime.utcnow(), state="UP", district="Lucknow", profile_completed_at=datetime.datetime.utcnow())
            self.legacy = models.User(name="Legacy", email="legacy@example.test", role="user", password_hash=auth.hash_password("legacy-password"))
            db.add_all([self.officer, self.other, self.legacy]); db.commit(); self.officer_id, self.other_id, self.legacy_id = self.officer.id, self.other.id, self.legacy.id
        app = FastAPI(); app.include_router(auth.router, prefix="/api/auth"); app.include_router(users.router, prefix="/api/user"); app.include_router(officer.router, prefix="/api/officer")
        def database():
            with self.sessions() as db: yield db
        app.dependency_overrides[get_db] = database; self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def request_code(self, phone="9876543210"):
        response = self.client.post("/api/auth/phone/request-otp", json={"phone_number": phone})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["development_otp"]

    def authenticate_citizen(self):
        code = self.request_code(); response = self.client.post("/api/auth/phone/verify-otp", json={"phone_number": "+919876543210", "otp": code})
        self.assertEqual(response.status_code, 200, response.text); return response

    def complete_profile(self):
        response = self.client.put("/api/auth/profile", json={"name":"Jatin", "email":"jatin@example.test", "state":"UP", "district":"Lucknow"})
        self.assertEqual(response.status_code, 200, response.text)

    def test_phone_normalization_and_hashed_single_use_otp(self):
        code = self.request_code("+919876543210")
        with self.sessions() as db:
            challenge = db.query(models.PhoneOtpChallenge).one()
            self.assertEqual(challenge.phone_number, "+919876543210")
            self.assertNotEqual(challenge.otp_hash, code)
        verified = self.client.post("/api/auth/phone/verify-otp", json={"phone_number": "9876543210", "otp": code})
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/phone/verify-otp", json={"phone_number": "9876543210", "otp": code}).status_code, 401)

    def test_invalid_expired_and_attempt_limited_phone_codes(self):
        self.assertEqual(self.client.post("/api/auth/phone/request-otp", json={"phone_number": "123"}).status_code, 422)
        code = self.request_code()
        for _ in range(5): self.assertEqual(self.client.post("/api/auth/phone/verify-otp", json={"phone_number": "9876543210", "otp": "000000"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/phone/verify-otp", json={"phone_number": "9876543210", "otp": code}).status_code, 401)
        with self.sessions() as db:
            db.query(models.PhoneOtpChallenge).update({models.PhoneOtpChallenge.expires_at: datetime.datetime.utcnow() - datetime.timedelta(seconds=1)}); db.commit()

    def test_resend_cooldown_and_expired_session_are_rejected(self):
        self.request_code()
        self.assertEqual(self.client.post("/api/auth/phone/request-otp", json={"phone_number": "+919876543210"}).status_code, 429)
        with self.sessions() as db:
            user = db.get(models.User, self.other_id); session, token = new_session(db, user)
            session.expires_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=1); db.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_session_me_logout_and_citizen_scoping(self):
        self.authenticate_citizen()
        self.assertTrue(self.client.cookies.get(SESSION_COOKIE_NAME))
        me = self.client.get("/api/auth/me"); self.assertEqual(me.status_code, 200); self.assertTrue(me.json()["phone_verified"])
        self.assertEqual(self.client.get("/api/user/dashboard", params={"user_id": self.other_id}).status_code, 403)
        self.complete_profile()
        self.assertEqual(self.client.get("/api/user/dashboard", params={"user_id": self.other_id}).status_code, 200)
        self.assertEqual(self.client.get("/api/user/submissions", params={"user_id": self.other_id}).json(), [])
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/user/dashboard").status_code, 401)

    def test_profile_aadhaar_mask_and_optional_email_verification(self):
        self.authenticate_citizen()
        profile = self.client.put("/api/auth/profile", json={"name":"Jatin", "email":"JATIN@Example.Test", "state":"UP", "district":"Lucknow", "aadhaar_number":"1234 5678 9012"})
        self.assertEqual(profile.status_code, 200, profile.text); self.assertEqual(profile.json()["aadhaar_masked"], "XXXX-XXXX-9012"); self.assertFalse(profile.json()["email_verified"])
        with self.sessions() as db: self.assertFalse(hasattr(db.query(models.User).filter_by(email="jatin@example.test").one(), "aadhaar_number"))
        code = self.client.post("/api/auth/email/request-verification").json()["development_code"]
        self.assertEqual(self.client.post("/api/auth/email/verify", json={"code": code}).status_code, 200)
        self.assertTrue(self.client.get("/api/auth/me").json()["email_verified"])

    def test_officer_session_and_role_enforcement(self):
        officer_login = self.client.post("/api/auth/login", json={"role":"officer", "officer_id":"GOV-TEST-1", "password":"issued-password"})
        self.assertEqual(officer_login.status_code, 200, officer_login.text); self.assertEqual(self.client.get("/api/officer/dashboard").status_code, 200)
        self.client.cookies.clear()
        self.authenticate_citizen()
        self.assertEqual(self.client.get("/api/officer/dashboard").status_code, 403)

    def test_legacy_password_citizen_links_phone_without_new_user(self):
        login = self.client.post("/api/auth/login", json={"role":"user", "email":"legacy@example.test", "password":"legacy-password"})
        self.assertEqual(login.status_code, 200, login.text)
        code = self.request_code("9876543210")
        verified = self.client.post("/api/auth/phone/verify-otp", json={"phone_number":"9876543210", "otp":code})
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["user"]["id"], self.legacy_id)
        with self.sessions() as db:
            self.assertEqual(db.query(models.User).filter_by(phone_number="+919876543210").count(), 1)


if __name__ == "__main__":
    unittest.main()
