"""Admin uploads go straight to R2 with a short-lived signed link (Vercel rejects bodies over 4.5 MB)."""
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import app as module
import test_site_management as base
from admin_session import grant_admin_session

R2_ENV = {
    "R2_ACCOUNT_ID": "acc123",
    "R2_ACCESS_KEY_ID": "AKTEST",
    "R2_SECRET_ACCESS_KEY": "secret-test",
    "R2_BUCKET": "bucket-test",
    "R2_PUBLIC_BASE_URL": "https://pub.example.r2.dev",
}


class DirectUploadTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def client_as(self, role):
        client = module.app.test_client()
        with client.session_transaction() as session:
            grant_admin_session(session, role)
            session["csrf_token"] = "test-csrf-token"
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"
        return client

    def ask(self, client, **payload):
        with patch.dict("os.environ", R2_ENV):
            return client.post("/admin/api/create-upload-url", json=payload)

    def test_model_link_is_signed_for_r2_and_returns_public_url(self):
        response = self.ask(self.client_as("editor"), kind="model", filename="โค เนื้อ.glb", size=40 * 1024 * 1024)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        url = urlparse(data["upload_url"])
        self.assertEqual(url.netloc, "acc123.r2.cloudflarestorage.com")
        self.assertTrue(url.path.startswith("/bucket-test/models/"))
        self.assertTrue(url.path.endswith(".glb"))
        query = parse_qs(url.query)
        self.assertEqual(query["X-Amz-Expires"], ["900"])
        self.assertIn("X-Amz-Signature", query)
        self.assertNotIn("secret-test", data["upload_url"])
        self.assertEqual(data["headers"]["Content-Type"], "model/gltf-binary")
        self.assertTrue(data["public_url"].startswith("https://pub.example.r2.dev/models/"))
        self.assertEqual(data["public_url"].split("/models/")[1], url.path.split("/models/")[1])

    def test_limits_and_types_are_checked(self):
        client = self.client_as("editor")
        self.assertEqual(self.ask(client, kind="model", filename="a.glb", size=51 * 1024 * 1024).status_code, 413)
        self.assertEqual(self.ask(client, kind="model", filename="a.exe", size=10).status_code, 400)
        self.assertEqual(self.ask(client, kind="thumbnail", filename="a.glb", size=10).status_code, 400)
        self.assertEqual(self.ask(client, kind="nope", filename="a.png", size=10).status_code, 400)
        self.assertEqual(self.ask(client, kind="thumbnail", filename="a.png", size=0).status_code, 400)
        self.assertEqual(self.ask(client, kind="slider_image", filename="a.jpg", size=12 * 1024 * 1024).status_code, 200)
        self.assertEqual(self.ask(client, kind="model_narration_audio", filename="a.wav", size=19 * 1024 * 1024).status_code, 200)

    def test_site_settings_uploads_need_an_administrator(self):
        self.assertEqual(self.ask(self.client_as("editor"), kind="site_logo", filename="a.png", size=10).status_code, 403)
        self.assertEqual(self.ask(self.client_as("admin"), kind="site_logo", filename="a.png", size=10).status_code, 200)
        self.assertEqual(self.ask(self.client_as("reviewer"), kind="model", filename="a.glb", size=10).status_code, 403)

    def test_needs_login_and_csrf(self):
        anonymous = module.app.test_client()
        self.assertEqual(self.ask(anonymous, kind="model", filename="a.glb", size=10).status_code, 302)
        client = self.client_as("owner")
        client.environ_base.pop("HTTP_X_CSRF_TOKEN")
        self.assertEqual(self.ask(client, kind="model", filename="a.glb", size=10).status_code, 400)

    def test_every_admin_file_input_has_a_known_kind(self):
        import re
        from pathlib import Path
        kinds = set()
        for template in Path(module.app.root_path, "templates").glob("*.html"):
            kinds |= set(re.findall(r'data-upload-kind="([a-z_]+)"', template.read_text(encoding="utf-8")))
        kinds.discard("")
        missing = {k for k in kinds if k not in module.DIRECT_UPLOAD_KINDS}
        self.assertFalse(missing, f"file inputs without an upload rule: {missing}")

    def test_admin_pages_load_the_upload_script(self):
        html = self.client_as("owner").get("/admin").get_data(as_text=True)
        self.assertIn("js/admin-direct-upload.js", html)


if __name__ == "__main__":
    unittest.main()
