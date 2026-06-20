import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as module
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


class SiteManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.original_paths = {
            "SITE_SETTINGS_FILE": module.SITE_SETTINGS_FILE,
            "SLIDER_ITEMS_FILE": module.SLIDER_ITEMS_FILE,
            "SITE_UPLOAD_DIR": module.SITE_UPLOAD_DIR,
            "SLIDER_UPLOAD_DIR": module.SLIDER_UPLOAD_DIR,
        }
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.SITE_UPLOAD_DIR = data_dir / "static" / "uploads" / "site"
        module.SLIDER_UPLOAD_DIR = data_dir / "static" / "uploads" / "sliders"
        module._JSON_CACHE.clear()
        module.write_json(module.SITE_SETTINGS_FILE, module.DEFAULT_SITE_SETTINGS)
        module.write_json(module.SLIDER_ITEMS_FILE, [])
        module.app.config.update(TESTING=True, SECRET_KEY="test-only-key")
        self.client = module.app.test_client()

    def tearDown(self):
        for name, value in self.original_paths.items():
            setattr(module, name, value)
        module._JSON_CACHE.clear()
        self.temp_dir.cleanup()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["admin"] = True

    def test_public_routes_and_apis_render(self):
        expected_statuses = {
            "/": 200,
            "/home": 200,
            "/models": 200,
            "/projects/garden": 200,
            "/models/lychee": 200,
            "/api/settings": 200,
            "/api/sliders": 200,
            "/sitemap.xml": 200,
            "/robots.txt": 200,
            "/googleaf10e1de09a9b1b8.html": 200,
            "/health": 200,
            "/missing-route": 404,
        }
        for route, expected in expected_statuses.items():
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, expected)

        settings = self.client.get("/api/settings").get_json()
        self.assertEqual(settings["site_name"], "PhuPhan-AR | ภูพาน AR สกลนคร")
        self.assertTrue(settings["landing_cover_url"].endswith("/static/pic/og-cover.jpg"))

    def test_public_seo_metadata_and_structured_data(self):
        landing_html = self.client.get("/").get_data(as_text=True)
        home_html = self.client.get("/home").get_data(as_text=True)
        models_html = self.client.get("/models").get_data(as_text=True)

        self.assertIn("<title>ภูพาน AR สกลนคร | ศูนย์ศึกษาการพัฒนาภูพาน</title>", landing_html)
        self.assertIn(
            "<title>ศูนย์ศึกษาการพัฒนาภูพาน | โมเดล 3D และ AR สกลนคร</title>",
            home_html,
        )
        self.assertIn("<title>โมเดล 3D ภูพาน | ของดีสกลนครในรูปแบบ AR</title>", models_html)
        self.assertIn('name="keywords"', landing_html)
        self.assertIn("พูพาน สกลนคร", landing_html)
        self.assertIn('type="application/ld+json"', landing_html)
        self.assertIn("Phu Phan Royal Development Study Centre", landing_html)
        self.assertIn('rel="canonical" href="https://phuphan-ar.vercel.app/"', landing_html)
        for alternate_term in ("ศูนย์ภูพาน", "พูพาน สกลนคร", "Phu Phan", "Sakon Nakhon"):
            self.assertIn(alternate_term, home_html)

    def test_sitemap_and_robots_include_public_discovery_routes(self):
        sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap.mimetype, "application/xml")
        sitemap_text = sitemap.get_data(as_text=True)
        for path in ("/", "/home", "/models", "/projects/garden", "/models/lychee"):
            self.assertIn(f"https://phuphan-ar.vercel.app{path}", sitemap_text)
        self.assertNotIn("/admin", sitemap_text)

        robots = self.client.get("/robots.txt")
        self.assertEqual(robots.mimetype, "text/plain")
        robots_text = robots.get_data(as_text=True)
        self.assertIn("Allow: /", robots_text)
        self.assertIn("Disallow: /admin", robots_text)
        self.assertIn("Sitemap: https://phuphan-ar.vercel.app/sitemap.xml", robots_text)

    def test_google_site_verification_route(self):
        response = self.client.get("/googleaf10e1de09a9b1b8.html")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertEqual(
            response.get_data(as_text=True),
            "google-site-verification: googleaf10e1de09a9b1b8.html",
        )

    def test_admin_management_routes_require_login(self):
        for route in ("/admin", "/admin/landing", "/admin/branding", "/admin/sliders"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

    def test_settings_and_slider_crud(self):
        self.sign_in()
        response = self.client.post(
            "/admin/settings",
            data={
                "section": "landing",
                "return_to": "/admin/landing",
                "landing_cover": "pic/og-cover.jpg",
                "landing_headline": "Test headline",
                "landing_subheadline": "Test subheadline",
                "landing_description": "Test description",
                "landing_cta_text": "Enter",
                "landing_cta_url": "/home",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(module.load_site_settings()["landing_headline"], "Test headline")

        response = self.client.post(
            "/admin/settings",
            data={
                "section": "branding",
                "return_to": "/admin/branding",
                "site_name": "Test Brand",
                "meta_description": "Test metadata description",
                "site_logo": "",
                "favicon": "favicon.ico",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(module.load_site_settings()["site_name"], "Test Brand")
        home_html = self.client.get("/home").get_data(as_text=True)
        self.assertIn(
            "<title>ศูนย์ศึกษาการพัฒนาภูพาน | โมเดล 3D และ AR สกลนคร</title>",
            home_html,
        )
        self.assertIn("Test Brand", home_html)
        self.assertIn('content="Test metadata description"', home_html)
        self.assertIn('href="/static/favicon.ico"', home_html)

        response = self.client.post(
            "/admin/sliders",
            data={
                "title": "Test slide",
                "description": "Slide description",
                "image_url": "pic/og-cover.jpg",
                "button_text": "Open",
                "button_url": "/models",
                "sort_order": "2",
                "visible": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        slider = module.load_slider_items()[0]
        self.assertTrue(slider["active"])
        self.assertEqual(len(self.client.get("/api/sliders").get_json()), 1)

        response = self.client.post(
            f"/admin/sliders/{slider['id']}/edit",
            data={
                "title": "Updated slide",
                "description": "",
                "image_url": "pic/og-cover.jpg",
                "button_text": "",
                "button_url": "",
                "sort_order": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(module.load_slider_items()[0]["active"])
        self.assertEqual(self.client.get("/api/sliders").get_json(), [])

        response = self.client.post(f"/admin/sliders/{slider['id']}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(module.load_slider_items(), [])

    def test_content_links_reject_unsafe_schemes(self):
        self.sign_in()
        landing_response = self.client.post(
            "/admin/settings",
            data={
                "section": "landing",
                "return_to": "/admin/landing",
                "landing_cover": "pic/og-cover.jpg",
                "landing_headline": "Test headline",
                "landing_subheadline": "Test subheadline",
                "landing_description": "Test description",
                "landing_cta_text": "Enter",
                "landing_cta_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(landing_response.status_code, 400)

        slider_response = self.client.post(
            "/admin/sliders",
            data={
                "title": "Unsafe slide",
                "image_url": "pic/og-cover.jpg",
                "button_text": "Open",
                "button_url": "data:text/html,unsafe",
                "sort_order": "0",
                "visible": "on",
            },
        )
        self.assertEqual(slider_response.status_code, 400)

    def test_slider_button_text_and_url_must_be_paired(self):
        self.sign_in()
        response = self.client.post(
            "/admin/sliders",
            data={
                "title": "Incomplete CTA",
                "image_url": "pic/og-cover.jpg",
                "button_text": "Open",
                "button_url": "",
                "sort_order": "0",
                "visible": "on",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_managed_upload_rejects_files_over_five_mb(self):
        upload = FileStorage(
            stream=io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)),
            filename="too-large.png",
            content_type="image/png",
        )
        with self.assertRaises(RequestEntityTooLarge):
            module.save_site_upload(
                upload,
                module.SITE_UPLOAD_DIR,
                "uploads/site",
                module.IMAGE_EXTENSIONS,
            )

    def test_managed_upload_rejects_invalid_file_type(self):
        upload = FileStorage(
            stream=io.BytesIO(b"not-an-image"),
            filename="payload.exe",
            content_type="application/octet-stream",
        )
        with self.assertRaises(BadRequest):
            module.save_site_upload(
                upload,
                module.SITE_UPLOAD_DIR,
                "uploads/site",
                module.IMAGE_EXTENSIONS,
            )

    def test_direct_upload_uses_random_names_and_rejects_invalid_types(self):
        with module.app.test_request_context():
            first_path, _ = module.direct_upload_target("cover.png", "landing_cover", 1024)
            second_path, _ = module.direct_upload_target("cover.png", "landing_cover", 1024)
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(first_path.startswith("site/landing/"))
            self.assertTrue(first_path.endswith(".png"))
            with self.assertRaises(BadRequest):
                module.direct_upload_target("payload.exe", "landing_cover", 1024)

    def test_supabase_read_failure_falls_back_to_local_json(self):
        module.save_site_settings({**module.DEFAULT_SITE_SETTINGS, "site_name": "Fallback Brand"})
        module.save_slider_items(
            [
                {
                    "id": "fallback-slide",
                    "title": "Fallback slide",
                    "image_url": "pic/og-cover.jpg",
                    "sort_order": 1,
                    "active": True,
                }
            ]
        )
        with (
            patch.object(module, "is_supabase_enabled", return_value=True),
            patch.object(module, "fetch_supabase_site_settings", side_effect=module.SupabaseError("missing table")),
            patch.object(module, "fetch_supabase_slider_items", side_effect=module.SupabaseError("missing table")),
        ):
            self.assertEqual(module.get_site_settings()["site_name"], "Fallback Brand")
            self.assertEqual(module.get_slider_items(False)[0]["id"], "fallback-slide")

    def test_active_slider_renders_on_landing_and_home(self):
        module.save_slider_items(
            [
                {
                    "id": "test-slide",
                    "title": "Test slide",
                    "description": "Slide description",
                    "image_url": "pic/og-cover.jpg",
                    "button_text": "Open",
                    "button_url": "/models",
                    "sort_order": 1,
                    "active": True,
                }
            ]
        )
        for route in ("/", "/home"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertIn("Test slide", response.get_data(as_text=True))

        payload = json.loads(self.client.get("/api/sliders").get_data(as_text=True))
        self.assertEqual(payload[0]["id"], "test-slide")

    def test_supabase_schema_is_hardened_and_non_destructive(self):
        sql = (Path(module.BASE_DIR) / "docs" / "supabase_schema.sql").read_text(encoding="utf-8").lower()
        for forbidden in ("drop table", "truncate", "delete from", "alter table site_settings drop", "alter table slider_items drop"):
            self.assertNotIn(forbidden, sql)
        for required in (
            "begin;",
            "commit;",
            "armodel_site_content_set_updated_at",
            "add column if not exists updated_at",
            "slider_items_active_sort_idx",
            "on conflict (key) do nothing",
            "alter table site_settings enable row level security",
            "alter table slider_items enable row level security",
        ):
            self.assertIn(required, sql)


if __name__ == "__main__":
    unittest.main()
