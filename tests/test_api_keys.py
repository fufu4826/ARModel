"""Admin-managed Gemini API keys: encrypted storage, import/list/test/delete, roles, key rotation."""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import HTTPError

import app as module
import test_site_management as base
from admin_session import grant_admin_session
from armodel.repositories import api_keys as repo
from armodel.services import narration

KEY_A = "AIzaSyTESTkeyAAAAAAAAAAAAAAAAAAAAAAAAAA1"
KEY_B = "AIzaSyTESTkeyBBBBBBBBBBBBBBBBBBBBBBBBBB2"
SECRET = "unit-test-secret"


def http_error(code, body):
    return HTTPError("https://example.test", code, "error", {}, io.BytesIO(json.dumps(body).encode()))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def audio_response():
    import base64
    data = base64.b64encode(b"\x00\x00" * 50).decode()
    body = {"candidates": [{"content": {"parts": [{"inlineData": {"data": data, "mimeType": "audio/L16;rate=24000"}}]}}]}
    return FakeResponse(json.dumps(body).encode())


class ApiKeyRepositoryTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def db(self):
        return module.admin_db()

    def test_keys_are_encrypted_deduplicated_and_listed_without_plaintext(self):
        result = repo.add_keys(self.db(), f"{KEY_A}\n\n{KEY_B}\n{KEY_A}\nnot a key", "ทีม", "owner", SECRET)
        self.assertEqual(len(result["added"]), 2)
        self.assertEqual(result["invalid"], 1)
        again = repo.add_keys(self.db(), KEY_A, "", "owner", SECRET)
        self.assertEqual((again["added"], again["duplicates"]), ([], 1))
        stored = self.db().batch([("SELECT * FROM api_keys", [])])[0]
        self.assertEqual(len(stored), 2)
        for row in stored:
            self.assertNotIn("AIza", row["ciphertext"] + row["fingerprint"] + row["hint"])
        listed = repo.list_keys(self.db(), SECRET)
        self.assertEqual(sorted(k["hint"] for k in listed), ["••••AAA1", "••••BBB2"])
        self.assertTrue(all(k["readable"] for k in listed))
        self.assertNotIn("ciphertext", listed[0])
        # another site's secret cannot read them
        self.assertFalse(any(k["readable"] for k in repo.list_keys(self.db(), "other-secret")))
        self.assertEqual(repo.usable_keys(self.db(), "other-secret"), [])

    def test_quota_cooldown_and_invalid_keys_are_skipped(self):
        added = repo.add_keys(self.db(), f"{KEY_A}\n{KEY_B}", "", "owner", SECRET)["added"]
        now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        repo.record_result(self.db(), added[0], "quota", "HTTP 429 key=AIzaSySECRETSECRETSECRET", now=now)
        repo.record_result(self.db(), added[1], "invalid", "API key not valid", now=now)
        self.assertEqual(repo.usable_keys(self.db(), SECRET, now=now + timedelta(minutes=5)), [])
        later = repo.usable_keys(self.db(), SECRET, now=now + timedelta(hours=2))
        self.assertEqual([k for k, _ in later], [added[0]])
        row = repo.get_plain(self.db(), added[0], SECRET)[0]
        self.assertNotIn("AIzaSySECRET", row["last_error"])

    def test_delete_removes_only_that_key(self):
        added = repo.add_keys(self.db(), f"{KEY_A}\n{KEY_B}", "", "owner", SECRET)["added"]
        self.assertEqual(repo.delete_key(self.db(), added[0])["hint"], "••••AAA1")
        self.assertEqual(repo.count_keys(self.db()), 1)
        self.assertIsNone(repo.delete_key(self.db(), added[0]))


class RotationTests(unittest.TestCase):
    def test_rotation_moves_past_quota_and_invalid_keys(self):
        calls, results = [], []

        def opener(request_obj, timeout=0):
            key = request_obj.headers.get("X-goog-api-key")
            calls.append(key)
            if key == "k1":
                raise http_error(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
            if key == "k2":
                raise http_error(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}})
            return audio_response()

        audio, ext = narration.generate_with_keys(
            "ทดสอบ", [("a", "k1"), ("b", "k2"), ("c", "k3")],
            on_result=lambda *r: results.append(r[:2]), opener=opener)
        self.assertEqual(ext, ".wav")
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(calls, ["k1", "k2", "k3"])
        self.assertEqual(results, [("a", "quota"), ("b", "invalid"), ("c", "ok")])

    def test_all_keys_exhausted_gives_clear_message(self):
        def opener(request_obj, timeout=0):
            raise http_error(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        with self.assertRaises(narration.GeminiTTSError) as ctx:
            narration.generate_with_keys("x", [("a", "k1")], opener=opener)
        self.assertIn("โควตา", str(ctx.exception))
        with self.assertRaises(narration.GeminiTTSError):
            narration.generate_with_keys("x", [], opener=opener)

    def test_check_key_does_not_call_generate(self):
        seen = []

        def opener(request_obj, timeout=0):
            seen.append((request_obj.get_method(), request_obj.full_url))
            return FakeResponse(b'{"name": "models/x"}')
        self.assertEqual(narration.check_gemini_key("k", opener=opener)[0], "ok")
        self.assertEqual(seen[0][0], "GET")
        self.assertNotIn("generateContent", seen[0][1])


class ApiKeyAdminPageTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def client_as(self, role):
        client = module.app.test_client()
        with client.session_transaction() as session:
            grant_admin_session(session, role)
            session["csrf_token"] = "test-csrf-token"
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"
        return client

    def test_only_admins_and_owner_manage_keys(self):
        for role in ("editor", "reviewer"):
            client = self.client_as(role)
            self.assertEqual(client.get("/admin/api-keys").status_code, 403)
            self.assertEqual(client.post("/admin/api-keys", data={"keys": KEY_A}).status_code, 403)
        self.assertEqual(self.client_as("admin").get("/admin/api-keys").status_code, 200)

    def test_import_test_and_delete_through_the_page(self):
        client = self.client_as("owner")
        with patch.object(narration, "check_gemini_key", return_value=("ok", "ใช้งานได้")) as check:
            response = client.post("/admin/api-keys", data={"keys": f"{KEY_A}\n{KEY_B}", "label": "ชุดทดสอบ", "test_now": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(check.call_count, 2)
        page = client.get("/admin/api-keys").get_data(as_text=True)
        self.assertIn("••••AAA1", page)
        self.assertIn("ใช้งานได้", page)
        self.assertNotIn(KEY_A, page, "the full key is never shown again")
        key_id = repo.list_keys(module.admin_db(), module.api_keys_secret())[0]["id"]
        with patch.object(narration, "check_gemini_key", return_value=("invalid", "HTTP 400: API key not valid")):
            client.post(f"/admin/api-keys/{key_id}/test")
        self.assertEqual(repo.get_plain(module.admin_db(), key_id, module.api_keys_secret())[0]["status"], "invalid")
        self.assertEqual(client.post(f"/admin/api-keys/{key_id}/delete").status_code, 302)
        self.assertEqual(repo.count_keys(module.admin_db()), 1)
        audit = json.dumps(module.read_audit_events() if hasattr(module, "read_audit_events") else [], ensure_ascii=False)
        self.assertNotIn(KEY_A, audit)

    def test_narration_uses_stored_keys_before_env_key(self):
        client = self.client_as("owner")
        with patch.object(narration, "check_gemini_key", return_value=("ok", "")):
            client.post("/admin/api-keys", data={"keys": KEY_A})
        used = []

        def fake_generate(text, api_key, opener=None):
            used.append(api_key)
            return b"RIFF....", ".wav"
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key-value-123456789"}), \
                patch.object(narration, "generate_gemini_tts_audio", side_effect=fake_generate):
            module.generate_gemini_tts_audio("สวัสดี")
        self.assertEqual(used, [KEY_A])
        stored = repo.list_keys(module.admin_db(), module.api_keys_secret())[0]
        self.assertEqual((stored["use_count"], stored["status"]), (1, "ok"))


if __name__ == "__main__":
    unittest.main()
