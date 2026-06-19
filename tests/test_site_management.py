import io
import json
import tempfile
import unittest
from pathlib import Path

import app as module
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge


class SiteManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
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
            "/health": 200,
            "/missing-route": 404,
        }
        for route, expected in expected_statuses.items():
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, expected)

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


if __name__ == "__main__":
    unittest.main()
