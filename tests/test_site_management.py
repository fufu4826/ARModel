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
            "ANALYTICS_FILE": module.ANALYTICS_FILE,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.SITE_UPLOAD_DIR = data_dir / "static" / "uploads" / "site"
        module.SLIDER_UPLOAD_DIR = data_dir / "static" / "uploads" / "sliders"
        module.AUDIO_DIR = data_dir / "static" / "audio"
        module.ANALYTICS_FILE = data_dir / "analytics_events.json"
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
        self.assertEqual(settings["site_name"], "ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์")
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

    def test_public_pages_do_not_show_usage_text(self):
        for route in ("/", "/home", "/models", "/models/lychee"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(
                    "วิธี" + "ใช้งาน",
                    response.get_data(as_text=True),
                )

    def test_homepage_project_description_is_updated(self):
        old_text = "ค้นหาเว็บไซต์ได้ทั้งคำว่า ภูพาน, พูพาน, ภูพาน สกลนคร และของดีสกลนคร"
        new_text = "โครงการเพิ่มศักยภาพแหล่งเรียนรู้และพิพิธภัณฑ์ท้องถิ่นจังหวัดสกลนครในรูปแบบออนไลน์เสมือนจริง"

        landing_html = self.client.get("/").get_data(as_text=True)
        home_html = self.client.get("/home").get_data(as_text=True)

        self.assertNotIn(old_text, landing_html)
        self.assertNotIn(old_text, home_html)
        self.assertIn(new_text, landing_html)
        self.assertIn(new_text, home_html)
        self.assertEqual(self.client.get("/models").status_code, 200)

    def test_home_omits_guide_and_about_sections(self):
        home_html = self.client.get("/home").get_data(as_text=True)
        for removed_text in (
            "AR " + "Guide",
            "ดูโมเดลด้วย " + "AR ได้อย่างไร",
            "เกี่ยวกับ" + "เว็บไซต์",
            "แหล่งเรียนรู้ภูพานและของดีสกลนคร" + "ผ่านภาพสามมิติ",
        ):
            self.assertNotIn(removed_text, home_html)

        self.assertIn('id="home-title"', home_html)
        self.assertIn('href="/models"', home_html)
        self.assertIn('id="projects"', home_html)
        self.assertEqual(self.client.get("/models").status_code, 200)
        model_html = self.client.get("/models/lychee").get_data(as_text=True)
        self.assertIn('id="mainModelViewer"', model_html)
        self.assertIn('data-model-src="', model_html)
        self.assertIn("meshoptDecoderLocation", model_html)
        self.assertNotIn(
            '<model-viewer\n          id="mainModelViewer"\n          src="',
            model_html,
        )
        self.assertIn("การควบคุมโมเดล", model_html)

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
        self.assertIn(".eyebrow.landing-eyebrow", stylesheet)
        self.assertIn("color: #0f4d36;", stylesheet)

        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn(
            '<p class="eyebrow landing-eyebrow">ภูพาน สกลนคร</p>',
            landing_html,
        )

        self.sign_in()
        preview_html = self.client.get("/admin/landing/preview").get_data(as_text=True)
        self.assertIn("eyebrow landing-eyebrow", preview_html)

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

    def test_landing_typography_settings_are_admin_editable_and_sanitized(self):
        self.sign_in()
        admin_html = self.client.get("/admin/landing").get_data(as_text=True)
        self.assertIn("การจัดวางตัวหนังสือหน้าปก", admin_html)
        for field_name in module.LANDING_TYPOGRAPHY_SETTINGS:
            self.assertIn(f'name="{field_name}"', admin_html)

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
                "landing_text_max_width_desktop": "1200",
                "landing_headline_font_size_desktop": "72",
                "landing_subheadline_font_size_desktop": "invalid);color:red",
                "landing_description_font_size_desktop": "12",
                "landing_badge_font_size_desktop": "18",
                "landing_button_font_size_desktop": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = module.load_site_settings()
        self.assertEqual(settings["landing_text_max_width_desktop"], "900")
        self.assertEqual(settings["landing_headline_font_size_desktop"], "72")
        self.assertEqual(
            settings["landing_subheadline_font_size_desktop"],
            module.DEFAULT_SITE_SETTINGS["landing_subheadline_font_size_desktop"],
        )
        self.assertEqual(settings["landing_description_font_size_desktop"], "14")
        self.assertEqual(settings["landing_badge_font_size_desktop"], "18")
        self.assertEqual(settings["landing_button_font_size_desktop"], "24")

        landing_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("--landing-text-max-width-desktop: 900px", landing_html)
        self.assertIn("--landing-headline-font-size-desktop: 72px", landing_html)
        self.assertIn("--landing-description-font-size-desktop: 14px", landing_html)
        self.assertNotIn("invalid);color:red", landing_html)
        self.assertIn("landing-mobile-hero", landing_html)
        self.assertIn("landing-mobile-details", landing_html)
        self.assertEqual(
            self.client.get("/api/settings").get_json()["landing_text_max_width_desktop"],
            "900",
        )

        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn("font-size: 16px !important;", stylesheet)

        self.assertEqual(self.client.get("/home").status_code, 200)
        self.assertEqual(self.client.get("/models").status_code, 200)
        self.assertEqual(self.client.get("/models/lychee").status_code, 200)

    def test_admin_landing_includes_realtime_preview(self):
        self.sign_in()
        admin_html = self.client.get("/admin/landing").get_data(as_text=True)
        self.assertIn("พรีวิวหน้าปกแบบเรียลไทม์", admin_html)
        self.assertIn("admin-landing-layout", admin_html)
        self.assertIn("admin-landing-form", admin_html)
        self.assertIn("admin-landing-preview", admin_html)
        self.assertIn("admin-preview-frame-shell", admin_html)
        self.assertIn("data-landing-preview", admin_html)
        self.assertIn("data-landing-preview-frame", admin_html)
        self.assertIn('src="/admin/landing/preview"', admin_html)
        self.assertIn('src="/static/js/admin-landing-preview.js?v=2"', admin_html)

        for field_name in module.LANDING_TYPOGRAPHY_SETTINGS:
            self.assertIn(f'name="{field_name}"', admin_html)

        preview_html = self.client.get("/admin/landing/preview").get_data(as_text=True)
        for shared_class in (
            "landing-hero",
            "landing-overlay",
            "landing-content",
            "landing-hero-center",
            "landing-eyebrow",
            "landing-title",
            "landing-subtitle",
            "landing-description",
            "landing-actions",
            "landing-button",
        ):
            self.assertIn(shared_class, preview_html)
        for variable_name in module.LANDING_TYPOGRAPHY_SETTINGS:
            css_variable = "--" + variable_name.replace("_", "-")
            self.assertIn(css_variable, preview_html)
        self.assertIn('href="/static/css/style.css"', preview_html)

        script = (
            Path(module.BASE_DIR) / "static" / "js" / "admin-landing-preview.js"
        ).read_text(encoding="utf-8")
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertIn("Math.min", script)
        self.assertIn("Math.max", script)
        self.assertIn("URL.createObjectURL", script)
        self.assertIn("--landing-text-max-width-desktop", script)
        self.assertIn("--landing-headline-font-size-desktop", script)

        admin_stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "admin.css"
        ).read_text(encoding="utf-8")
        self.assertNotIn(".landing-preview-headline", admin_stylesheet)
        self.assertNotIn(".landing-preview-subheadline", admin_stylesheet)
        self.assertNotIn(".landing-preview-description", admin_stylesheet)

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/home").status_code, 200)
        self.assertEqual(self.client.get("/models").status_code, 200)

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
        model_detail_html = self.client.get("/models/lychee").get_data(as_text=True)

        # 1. / contains improved title/description
        self.assertIn("<title>ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์</title>", landing_html)
        self.assertIn('property="og:title" content="ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์"', landing_html)
        self.assertIn('property="og:description" content="เรียนรู้ของดีสกลนคร แหล่งเรียนรู้ภูพาน และพิพิธภัณฑ์ท้องถิ่นผ่านโมเดล 3D และ AR ในรูปแบบออนไลน์เสมือนจริง ค้นพบผลิตภัณฑ์ท้องถิ่นสกลนคร"', landing_html)

        # 2. /home contains natural SEO phrase
        self.assertIn("<title>ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์</title>", home_html)
        self.assertIn("เว็บไซต์นี้รวบรวมของดีสกลนคร แหล่งเรียนรู้ภูพาน และพิพิธภัณฑ์ท้องถิ่นออนไลน์ผ่านโมเดล 3D และ AR เสมือนจริง", home_html)

        # 3. /models renders SEO title/meta
        self.assertIn("<title>โมเดล 3D ภูพาน AR สกลนคร | ของดีสกลนครและแหล่งเรียนรู้ท้องถิ่นออนไลน์</title>", models_html)
        self.assertIn('name="description" content="สำรวจและค้นหาโมเดล 3D และ AR ของดีสกลนคร เช่น ลูกประคบ ลิ้นจี่ ข้าวสกลนคร และแหล่งเรียนรู้ภูพานในพิพิธภัณฑ์ออนไลน์เสมือนจริง"', models_html)

        # 4. model detail page title includes model name and 3D/AR
        self.assertIn("โมเดล 3D AR ภูพาน สกลนคร ของดีสกลนคร", model_detail_html)

        # 5. sitemap includes /models and model detail URLs
        sitemap_text = self.client.get("/sitemap.xml").get_data(as_text=True)
        self.assertIn("https://phuphan-ar.vercel.app/models", sitemap_text)
        self.assertIn("https://phuphan-ar.vercel.app/models/lychee", sitemap_text)

        # 6. robots references sitemap
        robots_text = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Sitemap: https://phuphan-ar.vercel.app/sitemap.xml", robots_text)

        # 7. JSON-LD includes alternateName values
        self.assertIn("alternateName", landing_html)
        self.assertIn("PhuPhan AR", landing_html)
        self.assertIn("\\u0e20\\u0e39\\u0e1e\\u0e32\\u0e19 AR", landing_html)
        self.assertIn("\\u0e1e\\u0e39\\u0e1e\\u0e32\\u0e19 AR", landing_html)
        self.assertIn("\\u0e20\\u0e39\\u0e1e\\u0e32\\u0e19 \\u0e2a\\u0e01\\u0e25\\u0e19\\u0e04\\u0e23", landing_html)

        # 8. no hidden keyword spam block added
        self.assertNotIn('style="display:none"', landing_html.replace(" ", ""))
        self.assertNotIn('style="visibility:hidden"', landing_html.replace(" ", ""))
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
        self.assertEqual(legacy_model["rotate_y"], 0)
        self.assertEqual(legacy_model["rotate_z"], 0)

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
            patch.object(module, "is_vercel_runtime", return_value=False),
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

        generated_url = module.save_generated_narration_audio(
            "lychee",
            wav_data,
            ".wav",
        )
        self.assertIn("audio/lychee-gemini-", generated_url)
        self.assertTrue(generated_url.endswith(".wav"))
        self.assertTrue(
            (module.AUDIO_DIR / Path(generated_url).name).is_file()
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
        add_form_html = self.client.get("/admin").get_data(as_text=True)
        self.assertIn(
            'id="scale" name="scale" type="number" value="0.2" step="any" min="0.001"',
            add_form_html,
        )
        with patch.object(module, "is_vercel_runtime", return_value=False):
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
            self.assertEqual(saved_model["scale"], 0.2)
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
                    "scale": "0.15",
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
            self.assertEqual(updated_model["scale"], 0.15)

        add_form = self.client.get("/admin").get_data(as_text=True)
        edit_form = self.client.get(
            f"/admin/models/{saved_model['id']}/edit"
        ).get_data(as_text=True)
        self.assertIn("ไฟล์เสียงคำบรรยาย", add_form)
        self.assertIn('data-upload-kind="model_narration_audio"', add_form)
        self.assertIn("ไฟล์เสียงคำบรรยาย", edit_form)
        self.assertIn(
            'name="scale" type="number" value="0.15" step="any" min="0.001"',
            edit_form,
        )

    def test_admin_pages_include_busy_submission_guard(self):
        self.sign_in()
        admin_routes = (
            "/admin",
            "/admin/models/lychee/edit",
            "/admin/projects/garden/edit",
            "/admin/landing",
            "/admin/branding",
            "/admin/intro",
            "/admin/sliders",
            "/admin/recommended-models",
        )
        for route in admin_routes:
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertIn("data-admin-busy-modal", html)
                self.assertIn("admin-busy.js", html)
                self.assertIn("กำลังบันทึกข้อมูล...", html)

        admin_html = self.client.get("/admin").get_data(as_text=True)
        edit_model_html = self.client.get(
            "/admin/models/lychee/edit"
        ).get_data(as_text=True)
        landing_html = self.client.get("/admin/landing").get_data(as_text=True)
        recommended_html = self.client.get(
            "/admin/recommended-models"
        ).get_data(as_text=True)
        self.assertIn('action="/admin/models" method="post"', admin_html)
        self.assertIn('method="post" enctype="multipart/form-data"', edit_model_html)
        self.assertIn('action="/admin/settings" method="post"', landing_html)
        self.assertIn('method="post" class="admin-recommended-form"', recommended_html)
        self.assertIn("data-admin-no-busy", admin_html)

        busy_script = (
            Path(module.BASE_DIR) / "static" / "js" / "admin-busy.js"
        ).read_text(encoding="utf-8")
        self.assertIn("form.checkValidity()", busy_script)
        self.assertIn("event.defaultPrevented", busy_script)
        self.assertIn("submittingForms.has(form)", busy_script)
        self.assertIn("textContent", busy_script)

    def test_public_pages_do_not_include_admin_busy_assets(self):
        for route in ("/", "/home", "/models", "/models/lychee"):
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertNotIn("data-admin-busy-modal", html)
                self.assertNotIn("admin-busy.js", html)

    def test_runtime_source_has_no_legacy_backend_dependency(self):
        source = (Path(module.BASE_DIR) / "app.py").read_text(encoding="utf-8")
        forbidden = (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_STORAGE_BUCKET",
            "storage/v1/object/public",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_model_scale_rejects_non_numeric_input(self):
        self.sign_in()
        with patch.object(module, "is_vercel_runtime", return_value=False):
            response = self.client.post(
                "/admin/models/lychee/edit",
                data={
                    "name": "ลิ้นจี่",
                    "project_id": "garden",
                    "model_path": "model/Lychee.glb",
                    "thumbnail_url": "",
                    "preview_images": "",
                    "rotate_x": "0",
                    "scale": "not-a-number",
                    "visible": "on",
                },
            )
        self.assertEqual(response.status_code, 400)

    def test_json_model_preview_images_normalization(self):
        projects = module.load_projects(include_hidden=True)
        without_gallery = module.normalize_model(
            {"id": "one", "name": "One"},
            projects,
        )
        with_gallery = module.normalize_model(
            {
                "id": "two",
                "name": "Two",
                "preview_images": ["https://example.com/two.jpg"],
            },
            projects,
        )
        self.assertEqual(without_gallery["preview_images"], [])
        self.assertEqual(with_gallery["preview_images"], ["https://example.com/two.jpg"])
        self.assertEqual(without_gallery["narration_audio"], "")
        self.assertEqual(
            module.normalize_model(
                {"id": "three", "narration_audio": "https://example.com/three.mp3"},
                projects,
            )["narration_audio"],
            "https://example.com/three.mp3",
        )

    def test_admin_management_routes_require_login(self):
        for route in (
            "/admin",
            "/admin/landing",
            "/admin/landing/preview",
            "/admin/branding",
            "/admin/intro",
            "/admin/sliders",
        ):
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

    def test_direct_upload_endpoint_is_disabled(self):
        self.sign_in()
        response = self.client.post(
            "/admin/api/create-upload-url",
            json={
                "filename": "learning-model.glb",
                "kind": "model",
                "file_size": module.MAX_MODEL_FILE_SIZE_BYTES,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_model_forms_expose_direct_upload_limit_and_metadata_post(self):
        self.sign_in()
        add_form = self.client.get("/admin").get_data(as_text=True)
        edit_form = self.client.get("/admin/models/lychee/edit").get_data(as_text=True)
        expected_limit = f'data-max-bytes="{module.MAX_MODEL_FILE_SIZE_BYTES}"'

        for html in (add_form, edit_form):
            self.assertIn('data-upload-kind="model"', html)
            self.assertIn('data-upload-target="model_url"', html)
            self.assertIn(expected_limit, html)
            self.assertIn("ขนาดไม่เกิน 50 MB", html)
            self.assertIn("พรีวิวการแสดงผลโมเดล", html)
            self.assertIn("data-admin-model-preview", html)
            self.assertIn("admin-model-preview.js", html)

        with patch.object(module, "is_vercel_runtime", return_value=False):
            response = self.client.post(
                "/admin/models",
                data={
                    "name": "Metadata-only model",
                    "project_id": "garden",
                    "model_url": "https://example.com/model.glb",
                    "scale": "0.2",
                    "rotate_x": "0",
                    "visible": "on",
                },
            )
        self.assertEqual(response.status_code, 302)

    def test_direct_upload_frontend_is_removed(self):
        script = Path(module.BASE_DIR) / "static" / "js" / "admin-direct-upload.js"
        self.assertFalse(script.exists())
        for template_name in (
            "admin.html",
            "edit_model.html",
            "edit_project.html",
            "admin_branding.html",
            "admin_intro.html",
            "admin_landing.html",
            "admin_sliders.html",
            "edit_slider.html",
        ):
            template = (
                Path(module.BASE_DIR) / "templates" / template_name
            ).read_text(encoding="utf-8")
            self.assertNotIn("admin-direct-upload.js", template)
            self.assertNotIn("data-direct-uploads", template)

    def test_json_reads_are_the_only_runtime_source(self):
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
        self.assertIn('<h1>โมเดล 3D และ AR แหล่งเรียนรู้สกลนคร</h1>', models_html)
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

    def test_default_runtime_data_directory_is_versioned_data(self):
        self.assertEqual(module.DATA_DIR, Path(module.BASE_DIR) / "data")
        self.assertEqual(
            self.original_paths["CATALOG_FILE"],
            module.DATA_DIR / "models.json",
        )
        self.assertEqual(
            self.original_paths["PROJECTS_FILE"],
            module.DATA_DIR / "projects.json",
        )
        self.assertEqual(
            self.original_paths["SITE_SETTINGS_FILE"],
            module.DATA_DIR / "site_settings.json",
        )
        self.assertEqual(
            self.original_paths["SLIDER_ITEMS_FILE"],
            module.DATA_DIR / "slider_items.json",
        )

    def test_learning_source_labels_and_model_department_field(self):
        # 1. Check that public pages /, /home, /models render successfully and do not contain generic labels like "ดูโครงการทั้งหมด" or "รายการโครงการ" but instead say "แหล่งเรียนรู้"
        for route in ("/", "/home", "/models"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertNotIn("ดูโครงการทั้งหมด", html)
            self.assertNotIn("รายการโครงการ", html)

        # 2. Check model detail page renders and displays department
        # First with a model that has department
        response = self.client.get("/models/lychee")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("หน่วยงาน/แผนก", html)
        self.assertIn("งานกิจกรรมพืชสวน", html)

        # Second with a model that has NO department
        models = module.load_models(include_hidden=True)
        for m in models:
            if m["id"] == "lychee":
                m["department"] = ""
        module.save_models(models)

        response = self.client.get("/models/lychee")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("หน่วยงาน/แผนก", html)

        # 3. Check admin page renders with แหล่งเรียนรู้ labels
        self.sign_in()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("เพิ่มแหล่งเรียนรู้", html)
        self.assertIn("จัดการแหล่งเรียนรู้", html)
        self.assertIn("รายการแหล่งเรียนรู้", html)
        self.assertNotIn("เพิ่มโครงการ", html)
        self.assertNotIn("จัดการโครงการ", html)

    def test_mobile_model_detail_layout_ordering_and_elements(self):
        # 1. Check model detail page still renders correctly and contains info-header wrapper
        response = self.client.get("/models/lychee")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("class=\"info-header\"", html)
        self.assertIn("id=\"mainModelViewer\"", html)
        self.assertIn("หน่วยงาน/แผนก", html)

        # 2. Check CSS contains mobile ordering rules for model detail layout
        css_path = Path(module.BASE_DIR) / "static" / "css" / "style.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".viewer-stage {", css)
        self.assertIn("display: contents;", css)
        self.assertIn(".viewer-card {", css)
        self.assertIn("order: 1;", css)
        self.assertIn(".info-panel {", css)
        self.assertIn(".info-header {", css)
        self.assertIn(".meta-list {", css)

        # 3. Check /models and /home still render successfully
        for path in ("/models", "/home", "/"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)

    def test_recommended_models_admin_and_public(self):
        # 1. Admin page requires login
        response = self.client.get("/admin/recommended-models")
        self.assertEqual(response.status_code, 302)  # redirects to login

        # 2. Renders checkbox list after login
        self.sign_in()
        response = self.client.get("/admin/recommended-models")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("admin-recommended-form", html)
        self.assertIn("admin-recommended-list", html)
        self.assertIn("admin-recommended-model", html)
        self.assertIn("name=\"recommended_ids\"", html)
        self.assertIn("name=\"sort_order_lychee\"", html)
        self.assertIn("ลูกประคบ", html)
        self.assertIn("ลิ้นจี่", html)
        self.assertIn("เลือกได้สูงสุด 10 โมเดล", html)
        self.assertIn("ใส่เลขลำดับน้อยกว่าเพื่อให้แสดงก่อน", html)
        self.assertIn("ถ้าไม่เลือก ระบบจะแสดงโมเดลล่าสุดอัตโนมัติ", html)

        # 3. Default/fallback homepage still renders recommended models
        home_res = self.client.get("/home")
        self.assertEqual(home_res.status_code, 200)
        home_html = home_res.get_data(as_text=True)
        self.assertIn("แสดงตัวอย่างสูงสุด 10 รายการ", home_html)

        # 4. Saving recommended models in admin settings persists and changes /home output
        save_res = self.client.post("/admin/recommended-models", data={
            "recommended_ids": ["lychee", "lukplakob"],
            "sort_order_lychee": "1",
            "sort_order_lukplakob": "2",
        })
        self.assertEqual(save_res.status_code, 302)

        # 5. Check persistence in site settings
        settings = module.get_site_settings()
        self.assertEqual(settings.get("recommended_model_ids"), "lychee,lukplakob")

        # 6. Check homepage output changes
        home_res = self.client.get("/home")
        self.assertEqual(home_res.status_code, 200)
        home_html = home_res.get_data(as_text=True)
        self.assertIn("แสดงโมเดลแนะนำ 2 รายการจากทั้งหมด", home_html)
        self.assertIn("ลิ้นจี่", home_html)
        self.assertIn("ลูกประคบ", home_html)

        # 7. Unselected models do not appear if custom settings are used
        featured_section = home_html.split('id="featured-models"')[1].split('</section>')[0]
        self.assertNotIn("ธัญพืชอัดแท่ง", featured_section)

        # 8. Invalid/deleted IDs are ignored
        save_res = self.client.post("/admin/recommended-models", data={
            "recommended_ids": ["lychee", "invalid-id"],
            "sort_order_lychee": "1",
            "sort_order_invalid-id": "2",
        })
        self.assertEqual(save_res.status_code, 302)
        home_res = self.client.get("/home")
        home_html = home_res.get_data(as_text=True)
        featured_section = home_html.split('id="featured-models"')[1].split('</section>')[0]
        self.assertIn("ลิ้นจี่", featured_section)
        self.assertNotIn("invalid-id", featured_section)

        # 9. Saving more than 10 clamps to 10
        many_ids = [f"model-{i}" for i in range(15)]
        many_data = {"recommended_ids": many_ids}
        for mid in many_ids:
            many_data[f"sort_order_{mid}"] = "1"
        self.client.post("/admin/recommended-models", data=many_data)
        settings = module.get_site_settings()
        saved_ids = settings.get("recommended_model_ids", "").split(",")
        self.assertEqual(len(saved_ids), 10)

    def test_narration_audio_badge_on_public_cards(self):
        # Modify default models to have/not have narration
        models = module.load_models(include_hidden=True)
        for m in models:
            if m["id"] == "lychee":
                m["narration_audio"] = "audio/lychee.mp3"
            elif m["id"] == "lukplakob":
                m["narration_audio"] = ""
        module.save_models(models)

        # 1. Model with narration_audio shows มีเสียงบรรยาย on /models
        response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("มีเสียงบรรยาย", html)

        # 2. No visible "ไม่มีเสียง" exists on public pages
        self.assertNotIn("ไม่มีเสียง", html)

        # 3. Homepage recommended cards also show badge when applicable
        self.sign_in()
        self.client.post("/admin/recommended-models", data={
            "recommended_ids": ["lychee", "lukplakob"],
            "sort_order_lychee": "1",
            "sort_order_lukplakob": "2",
        })

        home_html = self.client.get("/home").get_data(as_text=True)
        featured_section = home_html.split('id="featured-models"')[1].split('</section>')[0]
        self.assertIn("มีเสียงบรรยาย", featured_section)

        # Model detail narration page still works
        detail_res = self.client.get("/models/lychee")
        self.assertEqual(detail_res.status_code, 200)
        detail_html = detail_res.get_data(as_text=True)
        self.assertIn("ฟังคำบรรยาย", detail_html)

    def test_model_rotation_controls_and_presets(self):
        self.sign_in()
        with patch.object(module, "is_vercel_runtime", return_value=False):
            response = self.client.post(
                "/admin/models",
                data={
                    "name": "Rotation Test Model",
                    "project_id": "garden",
                    "model_url": "https://example.com/rotate-test.glb",
                    "scale": "0.3",
                    "rotate_x": "1.23",
                    "rotate_y": "4.56",
                    "rotate_z": "-1.57",
                    "visible": "on",
                },
            )
            self.assertEqual(response.status_code, 302)
            saved = next(
                item for item in module.load_models(include_hidden=True)
                if item["name"] == "Rotation Test Model"
            )
            self.assertEqual(saved["rotate_x"], 1.23)
            self.assertEqual(saved["rotate_y"], 4.56)
            self.assertEqual(saved["rotate_z"], -1.57)

            # Public page orientation check
            detail_html = self.client.get(f"/models/{saved['id']}").get_data(as_text=True)
            self.assertIn('orientation="1.23rad 4.56rad -1.57rad"', detail_html)

            # Admin preview JS validation
            js_content = (Path(module.BASE_DIR) / "static" / "js" / "admin-model-preview.js").read_text(encoding="utf-8")
            self.assertIn("rotateYInput", js_content)
            self.assertIn("rotateZInput", js_content)
            self.assertIn("preset-btn", js_content)

            # Check that admin pages render preset buttons
            admin_add_html = self.client.get("/admin").get_data(as_text=True)
            self.assertIn('class="preset-btn"', admin_add_html)
            self.assertIn('data-preset-x="3.1416"', admin_add_html)


class ZeroSupabaseRuntimeTests(unittest.TestCase):
    def setUp(self):
        module._JSON_CACHE.clear()
        module.app.config.update(TESTING=True, SECRET_KEY="test-only-key")
        self.client = module.app.test_client()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["admin"] = True

    def test_versioned_json_counts_and_public_apis(self):
        models = json.loads((module.DATA_DIR / "models.json").read_text("utf-8"))
        projects = json.loads((module.DATA_DIR / "projects.json").read_text("utf-8"))
        settings = json.loads(
            (module.DATA_DIR / "site_settings.json").read_text("utf-8")
        )
        sliders = json.loads(
            (module.DATA_DIR / "slider_items.json").read_text("utf-8")
        )
        self.assertEqual(
            (len(models), len(projects), len(settings), len(sliders)),
            (41, 10, 31, 2),
        )

        api_models = self.client.get("/api/models")
        api_projects = self.client.get("/api/projects")
        api_settings = self.client.get("/api/settings")
        api_sliders = self.client.get("/api/sliders")
        for response in (api_models, api_projects, api_settings, api_sliders):
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("supabase.co", response.get_data(as_text=True).lower())

        model_payload = api_models.get_json()
        self.assertEqual(len(model_payload), 41)
        self.assertTrue(
            all(
                item["model_url"].startswith(
                    "https://pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev/"
                )
                for item in model_payload
            )
        )
        self.assertEqual(len(api_projects.get_json()), 10)
        self.assertTrue(set(settings).issubset(api_settings.get_json()))
        self.assertEqual(len(api_sliders.get_json()), 2)

    def test_public_runtime_works_without_legacy_environment(self):
        with patch.dict(module.os.environ, {}, clear=False):
            for name in (
                "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY",
                "SUPABASE_STORAGE_BUCKET",
            ):
                module.os.environ.pop(name, None)
            for route in (
                "/",
                "/home",
                "/models",
                "/models/lukplakob",
                "/models/lychee",
                "/models/audtang",
                "/api/models",
                "/api/projects",
                "/api/settings",
                "/api/sliders",
            ):
                with self.subTest(route=route):
                    response = self.client.get(route)
                    self.assertEqual(response.status_code, 200)
                    if route.startswith("/api/"):
                        self.assertNotIn(
                            "supabase.co",
                            response.get_data(as_text=True).lower(),
                        )

    def test_production_admin_mutations_are_read_only(self):
        self.sign_in()
        project_id = module.get_projects(True)[0]["id"]
        model_id = module.get_models(True)[0]["id"]
        slider_id = module.get_slider_items(True)[0]["id"]
        requests = (
            ("/admin/settings", {}),
            ("/admin/intro", {}),
            ("/admin/sliders", {}),
            (f"/admin/sliders/{slider_id}/edit", {}),
            (f"/admin/sliders/{slider_id}", {}),
            ("/admin/recommended-models", {}),
            ("/admin/projects", {}),
            (f"/admin/projects/{project_id}/edit", {}),
            (f"/admin/projects/{project_id}/delete", {}),
            ("/admin/models", {}),
            (f"/admin/models/{model_id}/edit", {}),
            (f"/admin/models/{model_id}/delete", {}),
            (f"/admin/models/{model_id}/generate-narration", {}),
            (
                "/admin/api/create-upload-url",
                {
                    "json": {
                        "filename": "blocked.glb",
                        "kind": "model",
                        "file_size": 1024,
                    }
                },
            ),
        )
        with patch.dict(
            module.os.environ,
            {"VERCEL": "1", "GEMINI_API_KEY": "test-only"},
        ):
            admin_html = self.client.get("/admin").get_data(as_text=True)
            self.assertIn('data-admin-read-only="true"', admin_html)
            self.assertIn("admin-read-only.js", admin_html)
            self.assertNotIn("admin-direct-upload.js", admin_html)
            for route, kwargs in requests:
                with self.subTest(route=route):
                    response = self.client.post(route, **kwargs)
                    self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
