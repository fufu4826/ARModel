import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as module
from admin_session import grant_admin_session


class ProductionAdminWritesTests(unittest.TestCase):
    def setUp(self):
        module.app.config["TESTING"] = True
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.original_paths = {
            "DATA_DIR": module.DATA_DIR,
            "CATALOG_FILE": module.CATALOG_FILE,
            "PROJECTS_FILE": module.PROJECTS_FILE,
            "SITE_SETTINGS_FILE": module.SITE_SETTINGS_FILE,
            "SLIDER_ITEMS_FILE": module.SLIDER_ITEMS_FILE,
        }
        module.DATA_DIR = data_dir
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.write_dataset(module.PROJECTS_FILE, module.DEFAULT_PROJECTS)
        module.write_dataset(module.CATALOG_FILE, module.DEFAULT_MODELS)
        module.write_dataset(module.PROJECTS_FILE, module.DEFAULT_PROJECTS)
        module.write_dataset(module.SITE_SETTINGS_FILE, module.DEFAULT_SITE_SETTINGS)
        module.write_dataset(module.SLIDER_ITEMS_FILE, [])
        module.app.config.update(TESTING=True, SECRET_KEY="production-write-test")
        self.client = module.app.test_client()
        with self.client.session_transaction() as session:
            grant_admin_session(session)
            session["csrf_token"] = "test-csrf-token"
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"

    def tearDown(self):
        for name, value in self.original_paths.items():
            setattr(module, name, value)
        self.temp_dir.cleanup()

    @staticmethod
    def production_env():
        return {
            "VERCEL": "1",
            "GITHUB_REPOSITORY": "fufu4826/ARModel",
            "GITHUB_CONTENTS_TOKEN": "test-token",
            "R2_ACCOUNT_ID": "test-account",
            "R2_ACCESS_KEY_ID": "test-access-key",
            "R2_SECRET_ACCESS_KEY": "test-secret-key",
            "R2_BUCKET": "phuphan-ar-assets",
            "R2_PUBLIC_BASE_URL": "https://pub.example.r2.dev",
        }

    def test_admin_forms_are_enabled_when_d1_is_configured(self):
        with patch.object(module, "d1_configured", return_value=True), patch.object(module, "is_vercel_runtime", return_value=True):
            html = self.client.get("/admin").get_data(as_text=True)
        self.assertIn('data-admin-read-only="false"', html)

    def test_add_model_uploads_to_r2_and_persists_d1(self):
        def upload(_data, object_key, _content_type):
            return f"https://pub.example.r2.dev/{object_key}"
        with (
            patch.dict(module.os.environ, self.production_env()),
            patch.object(module, "d1_configured", return_value=True),
            patch.object(module, "r2_upload_bytes", side_effect=upload),
        ):
            response = self.client.post("/admin/models", data={
                "name": "D1 Upload Model", "project_id": "garden",
                "model_file": (io.BytesIO(b"glb-data"), "review.glb"),
                "image_file": (io.BytesIO(b"image-data"), "review.jpg"),
                "visible": "on"
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        saved = next(item for item in module.load_models(True) if item["name"] == "D1 Upload Model")
        self.assertTrue(saved["model_url"].startswith("https://pub.example.r2.dev/models/"))
        self.assertTrue(saved["thumbnail_url"].startswith("https://pub.example.r2.dev/images/"))


if __name__ == "__main__":
    unittest.main()
