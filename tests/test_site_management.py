import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import app as module
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


class SiteManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.original_paths = {
            "CATALOG_FILE": module.CATALOG_FILE,
            "PROJECTS_FILE": module.PROJECTS_FILE,
            "SITE_SETTINGS_FILE": module.SITE_SETTINGS_FILE,
            "SLIDER_ITEMS_FILE": module.SLIDER_ITEMS_FILE,
            "SITE_UPLOAD_DIR": module.SITE_UPLOAD_DIR,
            "SLIDER_UPLOAD_DIR": module.SLIDER_UPLOAD_DIR,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.SITE_UPLOAD_DIR = data_dir / "static" / "uploads" / "site"
        module.SLIDER_UPLOAD_DIR = data_dir / "static" / "uploads" / "sliders"
        module._JSON_CACHE.clear()
        module.write_json(module.CATALOG_FILE, module.DEFAULT_MODELS)
        module.write_json(module.PROJECTS_FILE, module.DEFAULT_PROJECTS)
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
        self.assertEqual(sitemap.content_type, "application/xml; charset=utf-8")
        self.assertTrue(
            sitemap.data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        )
        sitemap_text = sitemap.get_data(as_text=True)
        for path in ("/", "/home", "/models", "/projects/garden", "/models/lychee"):
            self.assertIn(f"https://phuphan-ar.vercel.app{path}", sitemap_text)
        self.assertNotIn("/admin", sitemap_text)
        sitemap_xml = ET.fromstring(sitemap.data)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for location in sitemap_xml.findall("sitemap:url/sitemap:loc", namespace):
            parsed_url = urlparse(location.text)
            self.assertEqual(parsed_url.scheme, "https")
            self.assertEqual(parsed_url.netloc, "phuphan-ar.vercel.app")

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

    def test_model_preview_gallery_and_thumbnail_fallback(self):
        projects = module.load_projects(include_hidden=True)
        legacy_model = module.normalize_model(
            {
                "id": "legacy",
                "name": "Legacy model",
                "project_id": projects[0]["id"],
                "model": "model/legacy.glb",
            },
            projects,
        )
        self.assertEqual(legacy_model["preview_images"], [])

        models = module.load_models(include_hidden=True)
        models.append(
            {
                "id": "gallery-model",
                "name": "Gallery model",
                "description": "",
                "department": "",
                "project_id": projects[0]["id"],
                "model": "https://example.com/model.glb",
                "model_url": "https://example.com/model.glb",
                "model_path": "",
                "image": "",
                "thumbnail_url": "",
                "thumbnail_path": "",
                "preview_images": [
                    "https://example.com/preview-1.jpg",
                    "https://example.com/preview-2.jpg",
                ],
                "rotate_x": 0,
                "scale": 0.2,
                "visible": True,
            }
        )
        models.append(
            {
                "id": "no-preview-model",
                "name": "No preview model",
                "project_id": projects[0]["id"],
                "model": "https://example.com/no-preview.glb",
                "model_url": "https://example.com/no-preview.glb",
                "preview_images": [],
                "visible": True,
            }
        )
        module.save_models(models)

        gallery_html = self.client.get("/models/gallery-model").get_data(as_text=True)
        self.assertIn("https://example.com/preview-1.jpg", gallery_html)
        self.assertIn("https://example.com/preview-2.jpg", gallery_html)
        self.assertIn("model-gallery-thumbnails", gallery_html)
        no_preview_html = self.client.get("/models/no-preview-model").get_data(as_text=True)
        self.assertIn("ไม่มีรูปภาพตัวอย่าง", no_preview_html)

        api_models = self.client.get("/api/models").get_json()
        gallery_payload = next(item for item in api_models if item["id"] == "gallery-model")
        self.assertEqual(
            gallery_payload["preview_images"],
            [
                "https://example.com/preview-1.jpg",
                "https://example.com/preview-2.jpg",
            ],
        )

        lychee_payload = next(item for item in api_models if item["id"] == "lychee")
        self.assertEqual(len(lychee_payload["preview_images"]), 1)
        self.assertTrue(lychee_payload["preview_images"][0].endswith("/static/pic/Lychee.jpg"))

    def test_admin_add_and_edit_model_preview_images(self):
        self.sign_in()
        with patch.object(module, "is_supabase_enabled", return_value=False):
            response = self.client.post(
                "/admin/models",
                data={
                    "name": "Gallery admin model",
                    "project_id": module.DEFAULT_PROJECTS[0]["id"],
                    "model_url": "https://example.com/admin-model.glb",
                    "thumbnail_url": "",
                    "preview_images": (
                        "https://example.com/admin-preview-1.jpg\n"
                        "https://example.com/admin-preview-2.jpg"
                    ),
                    "rotate_x": "0",
                    "scale": "0.2",
                    "visible": "on",
                },
            )
            self.assertEqual(response.status_code, 302)
            saved_model = next(
                item for item in module.load_models(include_hidden=True)
                if item["name"] == "Gallery admin model"
            )
            self.assertEqual(len(saved_model["preview_images"]), 2)

            response = self.client.post(
                f"/admin/models/{saved_model['id']}/edit",
                data={
                    "name": saved_model["name"],
                    "project_id": saved_model["project_id"],
                    "model_url": saved_model["model_url"],
                    "thumbnail_url": "",
                    "preview_images": "https://example.com/admin-preview-updated.jpg",
                    "rotate_x": "0",
                    "scale": "0.2",
                    "visible": "on",
                },
            )
            self.assertEqual(response.status_code, 302)
            updated_model = next(
                item for item in module.load_models(include_hidden=True)
                if item["id"] == saved_model["id"]
            )
            self.assertEqual(
                updated_model["preview_images"],
                ["https://example.com/admin-preview-updated.jpg"],
            )

    def test_supabase_model_preview_images_normalization(self):
        without_gallery = module.normalize_supabase_model({"id": "one", "name": "One"})
        with_gallery = module.normalize_supabase_model(
            {
                "id": "two",
                "name": "Two",
                "preview_images": ["https://example.com/two.jpg"],
            }
        )
        self.assertEqual(without_gallery["preview_images"], [])
        self.assertEqual(with_gallery["preview_images"], ["https://example.com/two.jpg"])

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
            "add column if not exists preview_images jsonb not null default '[]'::jsonb",
        ):
            self.assertIn(required, sql)


if __name__ == "__main__":
    unittest.main()
