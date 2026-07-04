import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as module


R2_BASE = "https://pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev"


class AdminDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.original_paths = {
            "CATALOG_FILE": module.CATALOG_FILE,
            "PROJECTS_FILE": module.PROJECTS_FILE,
            "SITE_SETTINGS_FILE": module.SITE_SETTINGS_FILE,
            "SLIDER_ITEMS_FILE": module.SLIDER_ITEMS_FILE,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module._JSON_CACHE.clear()
        module._DASHBOARD_ASSET_CACHE.clear()

        module.write_json(
            module.CATALOG_FILE,
            [
                {
                    "id": "model-1",
                    "project_id": "project-1",
                    "model_url": f"{R2_BASE}/models/model-1.glb",
                    "thumbnail_url": f"{R2_BASE}/images/model-1.webp",
                    "preview_images": [f"{R2_BASE}/images/model-1-preview.webp"],
                    "narration_audio": "",
                },
                {
                    "id": "model-2",
                    "project_id": "project-1",
                    "model_url": f"{R2_BASE}/models/model-2.glb",
                    "thumbnail_url": "https://legacy.supabase.co/storage/model-2.webp",
                    "preview_images": [],
                    "narration_audio": "",
                },
            ],
        )
        module.write_json(
            module.PROJECTS_FILE,
            [{"id": "project-1", "image_url": f"{R2_BASE}/projects/project-1.webp"}],
        )
        module.write_json(
            module.SITE_SETTINGS_FILE,
            {"site_logo": f"{R2_BASE}/site/logo.webp", "site_name": "Test"},
        )
        module.write_json(
            module.SLIDER_ITEMS_FILE,
            [{"id": "slider-1", "image_url": f"{R2_BASE}/sliders/slider-1.webp"}],
        )
        module.app.config.update(TESTING=True, SECRET_KEY="dashboard-test-key")
        self.client = module.app.test_client()

    def tearDown(self):
        for name, value in self.original_paths.items():
            setattr(module, name, value)
        module._JSON_CACHE.clear()
        module._DASHBOARD_ASSET_CACHE.clear()
        self.temp_dir.cleanup()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["admin"] = True

    @staticmethod
    def successful_head(_url):
        return {
            "reachable": True,
            "size_bytes": 1024,
            "status_code": 200,
            "error": None,
        }

    def test_dashboard_page_and_api_use_admin_protection(self):
        for route in ("/admin/dashboard", "/admin/api/dashboard/summary"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

        self.sign_in()
        page = self.client.get("/admin/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn("แดชบอร์ดผู้ดูแลระบบ", page.get_data(as_text=True))
        self.assertIn("admin-dashboard.js", page.get_data(as_text=True))

    def test_summary_reports_json_counts_supabase_and_disabled_analytics(self):
        self.sign_in()
        with patch.object(module, "dashboard_asset_head", side_effect=self.successful_head):
            response = self.client.get("/admin/api/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload["content"],
            {"models": 2, "projects": 1, "site_settings": 2, "sliders": 1},
        )
        self.assertEqual(payload["assets"]["supabase_urls"], 1)
        self.assertEqual(payload["runtime"]["source"], "JSON")
        self.assertFalse(payload["analytics"]["enabled"])
        self.assertIsNone(payload["analytics"]["provider"])
        self.assertEqual(
            payload["analytics"]["message"],
            "ยังไม่ได้ตั้งค่าระบบวิเคราะห์ผู้เข้าชม",
        )

    def test_storage_soft_limit_uses_default_and_environment_override(self):
        with patch.dict(module.os.environ, {}, clear=False):
            module.os.environ.pop("R2_STORAGE_SOFT_LIMIT_GB", None)
            self.assertEqual(module.dashboard_storage_soft_limit(), (10.0, "default"))

        with patch.dict(module.os.environ, {"R2_STORAGE_SOFT_LIMIT_GB": "25.5"}):
            self.assertEqual(
                module.dashboard_storage_soft_limit(),
                (25.5, "environment"),
            )

    def test_unknown_asset_head_does_not_break_summary(self):
        self.sign_in()

        def mixed_head(url):
            if url.endswith("model-1.glb"):
                return {
                    "reachable": False,
                    "size_bytes": None,
                    "status_code": None,
                    "error": "TimeoutError",
                }
            return self.successful_head(url)

        with patch.object(module, "dashboard_asset_head", side_effect=mixed_head):
            response = self.client.get("/admin/api/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        storage = response.get_json()["storage"]
        self.assertEqual(storage["unknown_size_count"], 1)
        self.assertEqual(storage["failed_count"], 1)
        self.assertFalse(storage["is_complete_bucket_inventory"])

    def test_production_dashboard_reports_read_only_without_mutation(self):
        self.sign_in()
        with (
            patch.dict(module.os.environ, {"VERCEL": "1"}),
            patch.object(module, "dashboard_asset_head", side_effect=self.successful_head),
        ):
            payload = self.client.get("/admin/api/dashboard/summary").get_json()
            blocked = self.client.post("/admin/projects", data={})
        self.assertEqual(payload["runtime"]["admin_mode"], "read-only")
        self.assertTrue(
            payload["health"]["admin_read_only_protection"]["details"][
                "production_read_only"
            ]
        )
        self.assertEqual(blocked.status_code, 403)


if __name__ == "__main__":
    unittest.main()
