import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as module


class ProductionAdminWritesTests(unittest.TestCase):
    def setUp(self):
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
        module._JSON_CACHE.clear()
        module.write_json(module.CATALOG_FILE, module.DEFAULT_MODELS)
        module.write_json(module.PROJECTS_FILE, module.DEFAULT_PROJECTS)
        module.write_json(module.SITE_SETTINGS_FILE, module.DEFAULT_SITE_SETTINGS)
        module.write_json(module.SLIDER_ITEMS_FILE, [])
        module.app.config.update(TESTING=True, SECRET_KEY="production-write-test")
        self.client = module.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True

    def tearDown(self):
        for name, value in self.original_paths.items():
            setattr(module, name, value)
        module._JSON_CACHE.clear()
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

    def test_admin_forms_are_enabled_when_production_write_env_is_configured(self):
        with patch.dict(module.os.environ, self.production_env(), clear=False):
            html = self.client.get("/admin").get_data(as_text=True)

        self.assertIn('data-admin-read-only="false"', html)
        self.assertIn('name="model_file" type="file"', html)
        self.assertNotIn('name="model_file" type="file" accept=".glb" data-upload-kind="model" data-upload-target="model_url" data-max-bytes="52428800" data-max-size-label="50 MB" disabled', html)

    def test_add_model_uploads_to_r2_and_commits_json_on_vercel(self):
        committed = {}

        def fake_r2_upload(_data, object_key, _content_type):
            return f"https://pub.example.r2.dev/{object_key}"

        def fake_commit(relative_path, value):
            committed["relative_path"] = relative_path
            committed["value"] = value

        with (
            patch.dict(module.os.environ, self.production_env(), clear=False),
            patch.object(module, "r2_upload_bytes", side_effect=fake_r2_upload),
            patch.object(module, "github_commit_json", side_effect=fake_commit),
        ):
            response = self.client.post(
                "/admin/models",
                data={
                    "name": "Production Upload Model",
                    "description": "Uploaded through production admin",
                    "department": "QA",
                    "project_id": "garden",
                    "model_file": (io.BytesIO(b"glb-data"), "production-model.glb"),
                    "image_file": (io.BytesIO(b"image-data"), "production-image.jpg"),
                    "scale": "0.2",
                    "rotate_x": "0",
                    "rotate_y": "0",
                    "rotate_z": "0",
                    "visible": "on",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(committed["relative_path"], "data/models.json")
        saved = next(
            item
            for item in committed["value"]
            if item["name"] == "Production Upload Model"
        )
        self.assertTrue(saved["model_url"].startswith("https://pub.example.r2.dev/models/"))
        self.assertEqual(saved["model_path"], "")
        self.assertTrue(saved["thumbnail_url"].startswith("https://pub.example.r2.dev/images/"))
        self.assertEqual(saved["thumbnail_path"], "")


if __name__ == "__main__":
    unittest.main()
