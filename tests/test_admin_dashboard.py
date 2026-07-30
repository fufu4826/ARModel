import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

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
            "ANALYTICS_FILE": module.ANALYTICS_FILE,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.ANALYTICS_FILE = data_dir / "analytics_events.json"
        module._JSON_CACHE.clear()
        module._PRODUCTION_JSON_CACHE.clear()
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
        module._PRODUCTION_JSON_CACHE.clear()
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

    def test_summary_reports_json_counts_supabase_and_ready_analytics(self):
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
        self.assertEqual(payload["analytics"]["provider"], "local-json")
        self.assertEqual(payload["analytics"]["metrics"]["total_events"], 0)
        self.assertEqual(len(payload["analytics"]["trend"]), 30)
        self.assertEqual(
            payload["analytics"]["trend_ranges"]["default_range"],
            "daily_7d",
        )
        self.assertEqual(len(payload["analytics"]["trend_ranges"]["hourly_24h"]), 24)
        self.assertEqual(len(payload["analytics"]["trend_ranges"]["daily_7d"]), 7)
        self.assertEqual(len(payload["analytics"]["trend_ranges"]["daily_30d"]), 30)
        self.assertEqual(len(payload["analytics"]["trend_ranges"]["monthly_12m"]), 12)

    def test_local_analytics_records_public_page_views(self):
        self.client.get("/", headers={"Referer": "https://google.com/search?q=phuphan"})
        self.client.get("/models")
        self.sign_in()
        with patch.object(module, "dashboard_asset_head", side_effect=self.successful_head):
            payload = self.client.get("/admin/api/dashboard/summary").get_json()

        analytics = payload["analytics"]
        self.assertTrue(analytics["enabled"])
        self.assertEqual(analytics["provider"], "local-json")
        self.assertEqual(analytics["metrics"]["pageviews_today"], 2)
        self.assertEqual(analytics["metrics"]["visitors_today"], 1)
        self.assertEqual(analytics["metrics"]["visitors_7d"], 1)
        self.assertEqual(analytics["metrics"]["visitors_30d"], 1)
        self.assertEqual(analytics["trend_ranges"]["daily_7d"][-1]["pageviews"], 2)
        self.assertEqual(analytics["trend_ranges"]["daily_7d"][-1]["visitors"], 1)
        self.assertIn({"label": "Landing", "value": 1}, analytics["top_pages"])
        self.assertIn({"label": "google.com", "value": 1}, analytics["top_referrers"])

    def test_project_and_model_routes_resolve_current_names_by_id_and_slug(self):
        module.write_json(
            module.PROJECTS_FILE,
            [
                {
                    "id": "project-dynamic-id",
                    "slug": "project-dynamic-slug",
                    "name": "Dynamic Project Name",
                    "visible": True,
                }
            ],
        )
        module.write_json(
            module.CATALOG_FILE,
            [
                {
                    "id": "model-dynamic-id",
                    "slug": "model-dynamic-slug",
                    "name": "Dynamic Model Name",
                    "project_id": "project-dynamic-id",
                    "visible": True,
                }
            ],
        )

        with patch.dict(module.os.environ, {"ARMODEL_ANALYTICS_ENABLED": "0"}):
            for path, expected_name in (
                ("/projects/project-dynamic-id", "Dynamic Project Name"),
                ("/projects/project-dynamic-slug", "Dynamic Project Name"),
                ("/models/model-dynamic-id", "Dynamic Model Name"),
                ("/models/model-dynamic-slug", "Dynamic Model Name"),
            ):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(expected_name, response.get_data(as_text=True))

    def test_dashboard_relabels_historical_paths_without_mutating_events(self):
        module.write_json(
            module.PROJECTS_FILE,
            [
                {
                    "id": "project-current-id",
                    "slug": "project-current-slug",
                    "name": "Hidden Historical Project",
                    "visible": False,
                }
            ],
        )
        module.write_json(
            module.CATALOG_FILE,
            [
                {
                    "id": "model-current-id",
                    "slug": "model-current-slug",
                    "name": "Hidden Historical Model",
                    "project_id": "project-current-id",
                    "visible": False,
                }
            ],
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        events = [
            {
                "timestamp": timestamp,
                "visitor_id": "project-visitor",
                "path": "/projects/project-current-id",
                "page": "Project: project-current-id",
                "referrer": "Direct",
                "country": "TH",
            },
            {
                "timestamp": timestamp,
                "visitor_id": "model-visitor",
                "path": "/models/model-current-slug",
                "page": "Model: model-current-slug",
                "referrer": "Direct",
                "country": "TH",
            },
            {
                "timestamp": timestamp,
                "visitor_id": "missing-project-visitor",
                "path": "/projects/deleted-project-id",
                "page": "Project: deleted-project-id",
                "referrer": "Direct",
                "country": "TH",
            },
            {
                "timestamp": timestamp,
                "visitor_id": "missing-model-visitor",
                "path": "/models/deleted-model-slug",
                "page": "Model: deleted-model-slug",
                "referrer": "Direct",
                "country": "TH",
            },
        ]
        module.write_json(module.ANALYTICS_FILE, events)
        before = module.ANALYTICS_FILE.read_bytes()

        analytics = module.dashboard_analytics_status()

        self.assertEqual(analytics["metrics"]["total_events"], 4)
        self.assertEqual(analytics["metrics"]["pageviews_today"], 4)
        self.assertEqual(
            analytics["top_pages"],
            [
                {"label": "Model: Hidden Historical Model", "value": 1},
                {"label": "Project: Hidden Historical Project", "value": 1},
                {"label": "โครงการที่ไม่พบ", "value": 1},
                {"label": "โมเดลที่ไม่พบ", "value": 1},
            ],
        )
        self.assertEqual(module.ANALYTICS_FILE.read_bytes(), before)

        self.assertEqual(
            module.analytics_page_label("/projects/project-current-slug"),
            "Project: Hidden Historical Project",
        )
        self.assertEqual(
            module.analytics_page_label("/models/model-current-id"),
            "Model: Hidden Historical Model",
        )

    def test_new_analytics_events_store_human_readable_content_names(self):
        module.write_json(
            module.PROJECTS_FILE,
            [
                {
                    "id": "project-new-id",
                    "slug": "project-new-slug",
                    "name": "New Project Name",
                    "visible": True,
                }
            ],
        )
        module.write_json(
            module.CATALOG_FILE,
            [
                {
                    "id": "model-new-id",
                    "slug": "model-new-slug",
                    "name": "New Model Name",
                    "project_id": "project-new-id",
                    "visible": True,
                }
            ],
        )

        self.assertEqual(self.client.get("/projects/project-new-slug").status_code, 200)
        self.assertEqual(self.client.get("/models/model-new-id").status_code, 200)

        labels_by_path = {
            event["path"]: event["page"]
            for event in module.read_analytics_events()
        }
        self.assertEqual(
            labels_by_path["/projects/project-new-slug"],
            "Project: New Project Name",
        )
        self.assertEqual(
            labels_by_path["/models/model-new-id"],
            "Model: New Model Name",
        )

    def test_production_analytics_uses_r2_when_configured(self):
        r2_env = {
            "VERCEL": "1",
            "R2_ACCOUNT_ID": "account",
            "R2_ACCESS_KEY_ID": "access",
            "R2_SECRET_ACCESS_KEY": "secret",
            "R2_BUCKET": "bucket",
            "R2_PUBLIC_BASE_URL": "https://example-r2.test",
        }
        not_found = HTTPError("https://example-r2.test/analytics/analytics_events.json", 404, "Not Found", {}, None)
        self.sign_in()
        with (
            patch.dict(module.os.environ, r2_env),
            patch.object(module, "dashboard_asset_head", side_effect=self.successful_head),
            patch.object(module, "urlopen", side_effect=not_found),
        ):
            payload = self.client.get("/admin/api/dashboard/summary").get_json()

        self.assertFalse(payload["analytics"]["enabled"])
        self.assertEqual(payload["analytics"]["provider"], "cloudflare-r2-json")

        event = {
            "timestamp": "2026-07-11T00:00:00+00:00",
            "visitor_id": "visitor",
            "path": "/",
            "page": "Landing",
            "referrer": "Direct",
            "country": "TH",
        }
        with (
            patch.dict(module.os.environ, r2_env),
            patch.object(module, "urlopen", side_effect=not_found),
            patch.object(module, "r2_upload_bytes") as upload,
        ):
            module.append_analytics_event(event)

        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[1], module.ANALYTICS_R2_OBJECT_KEY)
        self.assertEqual(upload.call_args.args[2], "application/json; charset=utf-8")
        self.assertEqual(upload.call_args.kwargs["cache_control"], "no-store, max-age=0")

    def test_production_analytics_appends_existing_r2_events(self):
        r2_env = {
            "VERCEL": "1",
            "R2_ACCOUNT_ID": "account",
            "R2_ACCESS_KEY_ID": "access",
            "R2_SECRET_ACCESS_KEY": "secret",
            "R2_BUCKET": "bucket",
            "R2_PUBLIC_BASE_URL": "https://example-r2.test",
        }
        existing = [
            {
                "timestamp": "2026-07-10T00:00:00+00:00",
                "visitor_id": "old",
                "path": "/home",
                "page": "Home",
                "referrer": "Direct",
                "country": "TH",
            }
        ]
        new_event = {
            "timestamp": "2026-07-11T00:00:00+00:00",
            "visitor_id": "new",
            "path": "/models",
            "page": "Models",
            "referrer": "Internal",
            "country": "TH",
        }
        with (
            patch.dict(module.os.environ, r2_env),
            patch.object(module, "r2_get_bytes", return_value=json.dumps(existing).encode("utf-8")),
            patch.object(module, "r2_upload_bytes") as upload,
        ):
            module.append_analytics_event(new_event)

        uploaded = json.loads(upload.call_args.args[0].decode("utf-8"))
        self.assertEqual([item["path"] for item in uploaded], ["/home", "/models"])

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
