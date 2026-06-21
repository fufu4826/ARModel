import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

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
            "AUDIO_DIR": module.AUDIO_DIR,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.SITE_UPLOAD_DIR = data_dir / "static" / "uploads" / "site"
        module.SLIDER_UPLOAD_DIR = data_dir / "static" / "uploads" / "sliders"
        module.AUDIO_DIR = data_dir / "static" / "audio"
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
        self.assertEqual(settings["site_social_image"], "")
        self.assertEqual(
            settings["social_image_absolute_url"],
            "https://phuphan-ar.vercel.app/static/pic/og-cover.jpg",
        )
        favicon_url = urlparse(settings["favicon_url"])
        self.assertEqual(favicon_url.path, "/static/favicon.ico")
        self.assertIn("v", parse_qs(favicon_url.query))
        self.assertFalse(settings["intro_enabled_bool"])
        self.assertEqual(settings["intro_logo_duration_ms_value"], 1400)
        self.assertEqual(settings["intro_display_mode"], "sequence")

    def test_hidden_image_placeholders_do_not_take_space(self):
        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".image-placeholder[hidden]", stylesheet)
        self.assertIn("display: none;", stylesheet)

    def test_mobile_card_grids_use_two_columns(self):
        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 640px)", stylesheet)
        self.assertIn(".card-grid.model-grid", stylesheet)
        self.assertIn(".card-grid.project-grid", stylesheet)
        self.assertIn(
            "grid-template-columns: repeat(2, minmax(0, 1fr));",
            stylesheet,
        )

    def test_landing_cover_is_right_aligned(self):
        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".landing-logo-strip", stylesheet)
        self.assertIn(".landing-logo-strip__item", stylesheet)
        self.assertIn("background-position: right center;", stylesheet)

    def test_landing_mobile_layout_elements(self):
        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("mobile landing override active", landing_html)
        self.assertIn("landing-mobile-hero", landing_html)
        self.assertIn("landing-mobile-details", landing_html)
        self.assertNotIn("mobile-only-title", landing_html)
        self.assertIn("ภูพาน AR สกลนคร", landing_html)
        self.assertIn("เลื่อนเพื่อดูข้อมูล", landing_html)
        self.assertIn('href="/home"', landing_html)
        self.assertIn('href="/models"', landing_html)

    def test_landing_mobile_headline_dynamic(self):
        settings = module.load_site_settings()
        unique_headline = "DYNAMIC_MOBILE_HEADLINE_12345"
        settings.update({
            "landing_headline": unique_headline,
        })
        module.save_site_settings(settings)

        landing_html = self.client.get("/").get_data(as_text=True)
        # Verify the unique admin-managed headline is rendered in the mobile hero title markup
        self.assertIn(f'class="landing-mobile-hero-title">{unique_headline}</h1>', landing_html)

    def test_home_hero_text_is_admin_editable_without_changing_links(self):
        home_html = self.client.get("/home").get_data(as_text=True)
        self.assertIn("นิทรรศการดิจิทัล 3D / AR", home_html)
        self.assertIn("ศูนย์ศึกษาการพัฒนาภูพาน", home_html)
        self.assertIn("เริ่มชมโมเดล 3D", home_html)
        self.assertIn('href="/models"', home_html)
        self.assertIn('href="#projects"', home_html)

        self.sign_in()
        admin_html = self.client.get("/admin/landing").get_data(as_text=True)
        for field_name in (
            "home_hero_badge",
            "home_hero_heading",
            "home_hero_subheading",
            "home_hero_description",
            "home_hero_primary_cta_text",
            "home_hero_secondary_cta_text",
        ):
            self.assertIn(f'name="{field_name}"', admin_html)

        response = self.client.post(
            "/admin/settings",
            data={
                "section": "landing",
                "return_to": "/admin/landing",
                "landing_cover": "pic/og-cover.jpg",
                "landing_headline": "Test landing headline",
                "landing_subheadline": "Test landing subheadline",
                "landing_description": "Test landing description",
                "landing_cta_text": "Enter",
                "landing_cta_url": "/home",
                "home_hero_badge": "Test badge",
                "home_hero_heading": "Test home heading",
                "home_hero_subheading": "Test home subheading",
                "home_hero_description": "Test home description",
                "home_hero_primary_cta_text": "Test primary action",
                "home_hero_secondary_cta_text": "Test secondary action",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = module.load_site_settings()
        self.assertEqual(settings["home_hero_heading"], "Test home heading")

        home_html = self.client.get("/home").get_data(as_text=True)
        self.assertIn("Test badge", home_html)
        self.assertIn("Test home heading", home_html)
        self.assertIn("Test home subheading", home_html)
        self.assertIn("Test home description", home_html)
        self.assertIn("Test primary action", home_html)
        self.assertIn("Test secondary action", home_html)
        self.assertIn('href="/models"', home_html)
        self.assertIn('href="#projects"', home_html)

    def test_landing_mobile_cover_image(self):
        # 1. Renders admin landing page and includes mobile cover inputs/preview
        self.sign_in()
        admin_landing_html = self.client.get("/admin/landing").get_data(as_text=True)
        self.assertIn('name="landing_mobile_cover_image"', admin_landing_html)
        self.assertIn('name="landing_mobile_cover_image_file"', admin_landing_html)
        self.assertIn('name="landing_mobile_cover_image_remove"', admin_landing_html)

        # 2. Saving settings through POST preserves/updates mobile cover URL
        response = self.client.post(
            "/admin/settings",
            data={
                "section": "landing",
                "return_to": "/admin/landing",
                "landing_cover": "pic/og-cover.jpg",
                "landing_mobile_cover_image": "https://example.com/mobile-cover.jpg",
                "landing_headline": "Test headline",
                "landing_subheadline": "Test subheadline",
                "landing_description": "Test description",
                "landing_cta_text": "Enter",
                "landing_cta_url": "/home",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = module.load_site_settings()
        self.assertEqual(settings["landing_mobile_cover_image"], "https://example.com/mobile-cover.jpg")

        # 3. Landing page includes the mobile cover URL when configured
        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("--landing-cover-mobile: url('https://example.com/mobile-cover.jpg')", landing_html)

        # 4. Clear/remove mobile cover image reverts to empty and falls back to desktop cover
        response = self.client.post(
            "/admin/settings",
            data={
                "section": "landing",
                "return_to": "/admin/landing",
                "landing_cover": "pic/og-cover.jpg",
                "landing_mobile_cover_image_remove": "on",
                "landing_headline": "Test headline",
                "landing_subheadline": "Test subheadline",
                "landing_description": "Test description",
                "landing_cta_text": "Enter",
                "landing_cta_url": "/home",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = module.load_site_settings()
        self.assertEqual(settings["landing_mobile_cover_image"], "")

        # 5. Fallback works when empty (it matches the desktop cover URL)
        with module.app.test_request_context():
            public_settings = module.site_settings_with_urls(settings)
            self.assertEqual(public_settings["landing_mobile_cover_image_url"], public_settings["landing_cover_url"])

            # 6. Preload list includes mobile cover image if configured
            settings["landing_mobile_cover_image"] = "https://example.com/preload-mobile.jpg"
            public_settings = module.site_settings_with_urls(settings)
            preloads = module.landing_preload_image_urls(public_settings, [], [], [])
            self.assertIn("https://example.com/preload-mobile.jpg", preloads)

    def test_public_seo_metadata_and_structured_data(self):
        landing_html = self.client.get("/").get_data(as_text=True)
        home_html = self.client.get("/home").get_data(as_text=True)
        models_html = self.client.get("/models").get_data(as_text=True)

        self.assertIn("<title>PhuPhan-AR | ภูพาน AR สกลนคร</title>", landing_html)
        self.assertIn("<title>PhuPhan-AR | ภูพาน AR สกลนคร</title>", home_html)
        self.assertIn("<title>โมเดล 3D ภูพาน | ของดีสกลนครในรูปแบบ AR</title>", models_html)
        self.assertIn('property="og:title" content="PhuPhan-AR | ภูพาน AR สกลนคร"', landing_html)
        self.assertIn('property="og:description"', landing_html)
        self.assertIn(
            'property="og:image" content="https://phuphan-ar.vercel.app/static/pic/og-cover.jpg"',
            landing_html,
        )
        self.assertIn('name="keywords"', landing_html)
        self.assertIn("พูพาน สกลนคร", landing_html)
        self.assertIn('type="application/ld+json"', landing_html)
        self.assertIn("Phu Phan Royal Development Study Centre", landing_html)
        self.assertIn('rel="canonical" href="https://phuphan-ar.vercel.app/"', landing_html)
        for alternate_term in ("ศูนย์ภูพาน", "พูพาน สกลนคร", "Phu Phan", "Sakon Nakhon"):
            self.assertIn(alternate_term, home_html)

    def test_configured_favicon_is_cache_busted_on_public_pages(self):
        settings = {
            **module.DEFAULT_SITE_SETTINGS,
            "favicon": "https://cdn.example/favicon.png?size=32",
        }
        module.save_site_settings(settings)

        api_settings = self.client.get("/api/settings").get_json()
        favicon_url = urlparse(api_settings["favicon_url"])
        favicon_query = parse_qs(favicon_url.query)
        self.assertEqual(favicon_url.path, "/favicon.png")
        self.assertEqual(favicon_query["size"], ["32"])
        self.assertIn("v", favicon_query)
        self.assertEqual(len(favicon_query["v"][0]), 10)

        expected_link = f'<link rel="icon" href="{api_settings["favicon_url"]}" />'
        for route in (
            "/",
            "/home",
            "/models",
            "/projects/garden",
            "/models/lychee",
        ):
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertIn(expected_link.replace("&", "&amp;"), html)
                self.assertNotIn('rel="icon" type="image/png" sizes="192x192"', html)

    def test_social_preview_image_override_and_fallback(self):
        fallback_html = self.client.get("/").get_data(as_text=True)
        self.assertIn(
            'property="og:image" content="https://phuphan-ar.vercel.app/static/pic/og-cover.jpg"',
            fallback_html,
        )

        module.save_site_settings(
            {
                **module.DEFAULT_SITE_SETTINGS,
                "site_social_image": "https://cdn.example/social-card.jpg",
            }
        )
        api_settings = self.client.get("/api/settings").get_json()
        self.assertEqual(
            api_settings["social_image_absolute_url"],
            "https://cdn.example/social-card.jpg",
        )
        for route in ("/", "/home", "/models", "/projects/garden", "/models/lychee"):
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertIn(
                    'property="og:image" content="https://cdn.example/social-card.jpg"',
                    html,
                )
                self.assertIn(
                    'name="twitter:image" content="https://cdn.example/social-card.jpg"',
                    html,
                )

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
        self.assertEqual(legacy_model["narration_audio"], "")

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

    def test_model_detail_includes_narration_controls(self):
        model_html = self.client.get("/models/lychee").get_data(as_text=True)
        self.assertIn("data-model-narration", model_html)
        self.assertIn("data-narration-toggle", model_html)
        self.assertIn("data-narration-status", model_html)
        self.assertIn("ฟังคำบรรยาย", model_html)
        self.assertNotIn("data-narration-toggle disabled", model_html)
        self.assertIn('src="/static/js/model-narration.js?v=3"', model_html)
        self.assertEqual(self.client.get("/models").status_code, 200)

        narration_script = (
            Path(module.BASE_DIR) / "static" / "js" / "model-narration.js"
        ).read_text(encoding="utf-8")
        self.assertIn("speech.speak(utterance)", narration_script)
        self.assertIn("voiceschanged", narration_script)
        self.assertIn("utterance.onstart", narration_script)
        self.assertIn("utterance.onend", narration_script)
        self.assertIn("utterance.onerror", narration_script)
        self.assertIn("control.audio.play()", narration_script)
        self.assertIn("speech.speaking", narration_script)

    def test_gemini_narration_generation_requires_admin_and_api_key(self):
        route = "/admin/models/lychee/generate-narration"
        response = self.client.post(route)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        self.sign_in()
        with patch.dict(module.os.environ, {"GEMINI_API_KEY": ""}):
            response = self.client.post(route, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "ยังไม่ได้ตั้งค่า GEMINI_API_KEY",
            response.get_data(as_text=True),
        )

    def test_gemini_narration_generation_updates_model_audio(self):
        self.sign_in()
        fake_wav = module.pcm_to_wav(b"\x00\x00" * 40)
        source_model = next(
            item for item in module.load_models(include_hidden=True)
            if item["id"] == "lychee"
        )
        with (
            patch.dict(
                module.os.environ,
                {"GEMINI_API_KEY": "test-secret-not-for-rendering"},
            ),
            patch.object(
                module,
                "generate_gemini_tts_audio",
                return_value=(fake_wav, ".wav"),
            ) as generate_audio,
            patch.object(module, "is_supabase_enabled", return_value=False),
            patch.object(
                module,
                "resolve_narration_audio_url",
                return_value="/static/audio/generated.wav",
            ),
        ):
            response = self.client.post(
                "/admin/models/lychee/generate-narration",
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("สร้างไฟล์เสียงคำบรรยายเรียบร้อยแล้ว", html)
        self.assertIn("สร้างเสียงคำบรรยายด้วย Gemini", html)
        self.assertNotIn("test-secret-not-for-rendering", html)
        generate_audio.assert_called_once()
        prompt_text = generate_audio.call_args.args[0]
        self.assertIn(source_model["name"], prompt_text)
        self.assertIn(source_model["description"], prompt_text)

        model = next(
            item for item in module.load_models(include_hidden=True)
            if item["id"] == "lychee"
        )
        self.assertTrue(model["narration_audio"].startswith("audio/lychee-gemini-"))
        self.assertTrue(model["narration_audio"].endswith(".wav"))
        self.assertTrue(
            (module.AUDIO_DIR / Path(model["narration_audio"]).name).is_file()
        )
        with patch.object(
            module,
            "resolve_narration_audio_url",
            return_value="/static/audio/generated.wav",
        ):
            detail_html = self.client.get("/models/lychee").get_data(as_text=True)
        self.assertIn("data-narration-audio", detail_html)

    def test_gemini_dependency_and_audio_format_helpers(self):
        requirements = (
            Path(module.BASE_DIR) / "requirements.txt"
        ).read_text(encoding="utf-8")
        app_source = (Path(module.BASE_DIR) / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("google-genai", requirements)
        self.assertNotIn("google.genai", app_source)
        self.assertNotIn("from google import genai", app_source)

        sample_rate, channels, sample_width = module.parse_audio_mime_type(
            "audio/L16;rate=22050;channels=2"
        )
        self.assertEqual((sample_rate, channels, sample_width), (22050, 2, 2))
        wav_data = module.pcm_to_wav(
            b"\x00\x00" * 10,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        self.assertTrue(wav_data.startswith(b"RIFF"))

        with (
            patch.dict(
                module.os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
                    "SUPABASE_STORAGE_BUCKET": "test-assets",
                },
            ),
            patch.object(module, "is_supabase_enabled", return_value=True),
            patch.object(module, "supabase_request") as storage_request,
        ):
            generated_url = module.save_generated_narration_audio(
                "lychee",
                wav_data,
                ".wav",
            )
        self.assertIn("/models/narration/lychee-gemini-", generated_url)
        self.assertTrue(generated_url.endswith(".wav"))
        self.assertEqual(storage_request.call_args.kwargs["method"], "PUT")
        self.assertTrue(
            storage_request.call_args.kwargs["content_type"].startswith("audio/")
        )

    def test_gemini_tts_rest_request_and_error_handling(self):
        pcm_data = b"\x01\x02" * 20
        response_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/L16;rate=24000",
                                    "data": module.base64.b64encode(pcm_data).decode(
                                        "ascii"
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(response_payload).encode("utf-8")

        with (
            patch.dict(
                module.os.environ,
                {"GEMINI_API_KEY": "rest-test-key"},
            ),
            patch.object(module, "urlopen", return_value=FakeResponse()) as open_url,
        ):
            audio_data, extension = module.generate_gemini_tts_audio(
                "ลิ้นจี่ งานกิจกรรมพืชสวน"
            )

        request_obj = open_url.call_args.args[0]
        request_headers = {
            key.lower(): value for key, value in request_obj.header_items()
        }
        request_payload = json.loads(request_obj.data.decode("utf-8"))
        self.assertNotIn("rest-test-key", request_obj.full_url)
        self.assertEqual(request_headers["x-goog-api-key"], "rest-test-key")
        self.assertEqual(request_obj.get_method(), "POST")
        self.assertEqual(
            request_payload["generationConfig"]["responseModalities"],
            ["AUDIO"],
        )
        self.assertEqual(
            request_payload["generationConfig"]["speechConfig"]["voiceConfig"][
                "prebuiltVoiceConfig"
            ]["voiceName"],
            "Iapetus",
        )
        self.assertTrue(audio_data.startswith(b"RIFF"))
        self.assertEqual(extension, ".wav")

        error_body = io.BytesIO(b'{"error":{"message":"quota exceeded"}}')
        http_error = module.HTTPError(
            "https://generativelanguage.googleapis.com/test",
            429,
            "Too Many Requests",
            {},
            error_body,
        )
        try:
            with (
                patch.dict(
                    module.os.environ,
                    {"GEMINI_API_KEY": "rest-test-key"},
                ),
                patch.object(module, "urlopen", side_effect=http_error),
                self.assertRaises(module.GeminiTTSError) as error_context,
            ):
                module.generate_gemini_tts_audio("ทดสอบ")
        finally:
            http_error.close()
        self.assertIn("HTTP 429", str(error_context.exception))
        self.assertNotIn("rest-test-key", str(error_context.exception))

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
                    "narration_audio": "https://example.com/admin-narration.mp3",
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
            self.assertEqual(
                saved_model["narration_audio"],
                "https://example.com/admin-narration.mp3",
            )
            detail_html = self.client.get(
                f"/models/{saved_model['id']}"
            ).get_data(as_text=True)
            self.assertIn("data-narration-audio", detail_html)
            self.assertIn(
                'src="https://example.com/admin-narration.mp3"',
                detail_html,
            )
            api_model = next(
                item for item in self.client.get("/api/models").get_json()
                if item["id"] == saved_model["id"]
            )
            self.assertEqual(
                api_model["narration_audio_url"],
                "https://example.com/admin-narration.mp3",
            )

            response = self.client.post(
                f"/admin/models/{saved_model['id']}/edit",
                data={
                    "name": saved_model["name"],
                    "project_id": saved_model["project_id"],
                    "model_url": saved_model["model_url"],
                    "thumbnail_url": "",
                    "preview_images": "https://example.com/admin-preview-updated.jpg",
                    "narration_audio": "https://example.com/admin-narration-updated.ogg",
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
            self.assertEqual(
                updated_model["narration_audio"],
                "https://example.com/admin-narration-updated.ogg",
            )

        add_form = self.client.get("/admin").get_data(as_text=True)
        edit_form = self.client.get(
            f"/admin/models/{saved_model['id']}/edit"
        ).get_data(as_text=True)
        self.assertIn("ไฟล์เสียงคำบรรยาย", add_form)
        self.assertIn('data-upload-kind="model_narration_audio"', add_form)
        self.assertIn("ไฟล์เสียงคำบรรยาย", edit_form)

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
        self.assertEqual(without_gallery["narration_audio"], "")
        self.assertEqual(
            module.normalize_supabase_model(
                {"id": "three", "narration_audio": "https://example.com/three.mp3"}
            )["narration_audio"],
            "https://example.com/three.mp3",
        )

    def test_admin_management_routes_require_login(self):
        for route in ("/admin", "/admin/landing", "/admin/branding", "/admin/intro", "/admin/sliders"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

    def test_landing_intro_settings_and_admin_page(self):
        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/home"', landing_html)
        self.assertIn("data-landing-intro-trigger", landing_html)
        self.assertIn('"enabled": false', landing_html)
        self.assertIn('"mode": "sequence"', landing_html)
        self.assertIn('data-mode="sequence"', landing_html)

        settings = {
            **module.DEFAULT_SITE_SETTINGS,
            "intro_enabled": "true",
            "intro_logo_1": "https://example.com/logo-1.png",
            "intro_logo_2": "pic/logo-2.webp",
            "intro_logo_3": "",
            "intro_logo_duration_ms": "1200",
            "intro_display_mode": "all_at_once",
        }
        module.save_site_settings(settings)
        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn('"enabled": true', landing_html)
        self.assertIn("https://example.com/logo-1.png", landing_html)
        self.assertIn("/static/pic/logo-2.webp", landing_html)
        self.assertIn('"durationMs": 1200', landing_html)
        self.assertIn('"mode": "all_at_once"', landing_html)
        self.assertIn('data-mode="all_at_once"', landing_html)
        self.assertIn("landingIntroLogoGroup", landing_html)
        self.assertIn("landingIntroOverlay", landing_html)
        self.assertIn("landing-logo-strip", landing_html)
        logo_1_position = landing_html.index('data-intro-logo-index="1"')
        logo_2_position = landing_html.index('data-intro-logo-index="2"')
        self.assertLess(logo_1_position, logo_2_position)
        self.assertNotIn('data-intro-logo-index="3"', landing_html)
        self.assertIn('alt="โลโก้อินโทร 1"', landing_html)
        self.assertIn('alt="โลโก้อินโทร 2"', landing_html)
        self.assertIn('href="/home"', landing_html)

        self.sign_in()
        admin_page = self.client.get("/admin/intro")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn("โลโก้จะแสดงทีละภาพ", admin_page.get_data(as_text=True))
        self.assertIn('name="intro_display_mode"', admin_page.get_data(as_text=True))
        self.assertIn('value="all_at_once"', admin_page.get_data(as_text=True))

        response = self.client.post(
            "/admin/intro",
            data={
                "intro_enabled": "on",
                "intro_logo_1": "https://example.com/updated-1.png",
                "intro_logo_2": "https://example.com/updated-2.webp",
                "intro_logo_3": "pic/updated-3.png",
                "intro_logo_duration_ms": "1500",
                "intro_display_mode": "all_at_once",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved = module.load_site_settings()
        self.assertEqual(saved["intro_enabled"], "true")
        self.assertEqual(saved["intro_logo_1"], "https://example.com/updated-1.png")
        self.assertEqual(saved["intro_logo_2"], "https://example.com/updated-2.webp")
        self.assertEqual(saved["intro_logo_3"], "pic/updated-3.png")
        self.assertEqual(saved["intro_logo_duration_ms"], "1500")
        self.assertEqual(saved["intro_display_mode"], "all_at_once")

        api_settings = self.client.get("/api/settings").get_json()
        self.assertTrue(api_settings["intro_enabled_bool"])
        self.assertEqual(api_settings["intro_logo_duration_ms_value"], 1500)
        self.assertEqual(api_settings["intro_display_mode"], "all_at_once")

        response = self.client.post(
            "/admin/intro",
            data={
                "intro_enabled": "on",
                "intro_logo_1": "https://example.com/updated-1.png",
                "intro_logo_2": "",
                "intro_logo_3": "",
                "intro_logo_duration_ms": "1200",
                "intro_display_mode": "invalid-mode",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            module.load_site_settings()["intro_display_mode"],
            "sequence",
        )

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
                "site_social_image": "https://cdn.example/social-preview.jpg",
                "favicon": "https://cdn.example/test-favicon.png",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(module.load_site_settings()["site_name"], "Test Brand")
        self.assertEqual(
            module.load_site_settings()["site_social_image"],
            "https://cdn.example/social-preview.jpg",
        )
        home_html = self.client.get("/home").get_data(as_text=True)
        self.assertIn("<title>Test Brand</title>", home_html)
        self.assertIn("Test Brand", home_html)
        self.assertIn('content="Test metadata description"', home_html)
        self.assertIn(
            'content="https://cdn.example/social-preview.jpg"',
            home_html,
        )
        self.assertIn('href="https://cdn.example/test-favicon.png?v=', home_html)

        response = self.client.post(
            "/admin/settings",
            data={
                "section": "branding",
                "return_to": "/admin/branding",
                "site_name": "Test Brand",
                "meta_description": "Test metadata description",
                "site_logo": "",
                "site_social_image": "https://cdn.example/social-preview.jpg",
                "site_social_image_remove": "on",
                "favicon": "https://cdn.example/test-favicon.png",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(module.load_site_settings()["site_social_image"], "")

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

    def test_narration_audio_upload_validation(self):
        with module.app.test_request_context():
            object_path, public_url = module.direct_upload_target(
                "narration.mp3",
                "model_narration_audio",
                file_size=1024,
            )
            self.assertTrue(object_path.startswith("models/narration/"))
            self.assertTrue(public_url.endswith(".mp3"))

            with self.assertRaises(RequestEntityTooLarge):
                module.direct_upload_target(
                    "too-large.mp3",
                    "model_narration_audio",
                    file_size=module.NARRATION_AUDIO_MAX_BYTES + 1,
                )
            with self.assertRaises(BadRequest):
                module.direct_upload_target(
                    "unsafe.svg",
                    "model_narration_audio",
                    file_size=1024,
                )
            self.assertEqual(
                module.parse_narration_audio_field(
                    "https://example.com/narration.mp3?version=1"
                ),
                "https://example.com/narration.mp3?version=1",
            )
            with self.assertRaises(BadRequest):
                module.parse_narration_audio_field("javascript:alert(1)")
            with self.assertRaises(BadRequest):
                module.parse_narration_audio_field(
                    "https://example.com/not-audio.svg"
                )

    def test_direct_upload_uses_random_names_and_rejects_invalid_types(self):
        with module.app.test_request_context():
            first_path, _ = module.direct_upload_target("cover.png", "landing_cover", 1024)
            second_path, _ = module.direct_upload_target("cover.png", "landing_cover", 1024)
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(first_path.startswith("site/landing/"))
            self.assertTrue(first_path.endswith(".png"))
            intro_path, _ = module.direct_upload_target("intro.webp", "intro_logo_1", 1024)
            self.assertTrue(intro_path.startswith("site/intro/"))
            self.assertTrue(intro_path.endswith(".webp"))
            social_path, _ = module.direct_upload_target(
                "social.jpg", "site_social_image", 1024
            )
            self.assertTrue(social_path.startswith("site/social/"))
            self.assertTrue(social_path.endswith(".jpg"))
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

    def test_public_logos_display(self):
        # 1. Test with intro logos configured
        settings = module.load_site_settings()
        settings.update({
            "intro_logo_1": "https://example.com/logo-1.png",
            "intro_logo_2": "https://example.com/logo-2.png",
            "intro_logo_3": "https://example.com/logo-3.png",
            "site_logo": "https://example.com/site-logo.png",
        })
        module.save_site_settings(settings)

        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("public-logo-strip", landing_html)
        self.assertIn("landing-logo-strip", landing_html)
        # Verify the landing page doesn't render site_logo image
        self.assertNotIn('src="https://example.com/site-logo.png"', landing_html)

        # Check required strings on landing
        self.assertIn("mobile landing override active", landing_html)
        self.assertIn("ศูนย์ศึกษาการพัฒนาภูพาน", landing_html)
        self.assertIn("เลื่อนเพื่อดูข้อมูล", landing_html)
        self.assertIn('href="/home"', landing_html)
        self.assertIn('href="/models"', landing_html)

        home_html = self.client.get("/home").get_data(as_text=True)
        self.assertIn("public-logo-strip", home_html)
        self.assertNotIn('src="https://example.com/site-logo.png"', home_html)

        # 2. Test without intro logos (fallback clean text)
        settings.update({
            "intro_logo_1": "",
            "intro_logo_2": "",
            "intro_logo_3": "",
        })
        module.save_site_settings(settings)

        home_html_no_logos = self.client.get("/home").get_data(as_text=True)
        self.assertNotIn("public-logo-strip", home_html_no_logos)
        self.assertIn("brand-symbol", home_html_no_logos)
        self.assertIn("AR", home_html_no_logos)
        self.assertNotIn('src="https://example.com/site-logo.png"', home_html_no_logos)

    def test_models_search_and_filter(self):
        models_html = self.client.get("/models").get_data(as_text=True)
        # Verify search input and filter form elements render
        self.assertIn('id="modelSearch"', models_html)
        self.assertIn('id="projectFilter"', models_html)
        self.assertIn('id="modelsGrid"', models_html)
        self.assertIn('id="modelsNoResults"', models_html)
        # Verify script is included
        self.assertIn('src="/static/js/models-filter.js"', models_html)
        # Verify Thai labels
        self.assertIn('<h1>รายการโมเดล</h1>', models_html)
        self.assertIn('<span>รายการโมเดล</span>', models_html)
        self.assertIn('<p class="eyebrow">รายการโมเดล</p>', models_html)
        # Verify model card markup attributes
        self.assertIn('data-model-card', models_html)
        self.assertIn('data-search-text', models_html)

    def test_site_wide_kanit_font(self):
        # 1. Test public pages render successfully and load Kanit Font
        for path in ("/", "/home", "/models"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn("fonts.googleapis.com/css2?family=Kanit", html)

        # 2. Test admin login page renders successfully and loads Kanit Font
        response = self.client.get("/admin/login")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("fonts.googleapis.com/css2?family=Kanit", html)

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
            "add column if not exists narration_audio text not null default ''",
        ):
            self.assertIn(required, sql)


if __name__ == "__main__":
    unittest.main()
