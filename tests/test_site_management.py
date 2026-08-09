import io
import json
import base64
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
            "LOCAL_LOGIN_RATE_LIMIT_DIR": module.LOCAL_LOGIN_RATE_LIMIT_DIR,
        }
        module.CATALOG_FILE = data_dir / "models.json"
        module.PROJECTS_FILE = data_dir / "projects.json"
        module.SITE_SETTINGS_FILE = data_dir / "site_settings.json"
        module.SLIDER_ITEMS_FILE = data_dir / "slider_items.json"
        module.SITE_UPLOAD_DIR = data_dir / "static" / "uploads" / "site"
        module.SLIDER_UPLOAD_DIR = data_dir / "static" / "uploads" / "sliders"
        module.AUDIO_DIR = data_dir / "static" / "audio"
        module.ANALYTICS_FILE = data_dir / "analytics_events.json"
        module.LOCAL_LOGIN_RATE_LIMIT_DIR = data_dir / "login-rate-limit"
        module._JSON_CACHE.clear()
        module._PRODUCTION_JSON_CACHE.clear()
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
        module._PRODUCTION_JSON_CACHE.clear()
        self.temp_dir.cleanup()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf_token"] = "test-csrf-token"
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"

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

    def test_security_headers_are_applied_without_breaking_local_http(self):
        response = self.client.get("/home")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertNotIn("Strict-Transport-Security", response.headers)

    def test_login_rate_limit_records_failures_and_blocks_before_password_check(self):
        audit_events = []
        with (
            patch.dict(module.os.environ, {"ADMIN_PASSWORD": "correct-password"}, clear=False),
            patch.object(module, "write_audit_event", side_effect=lambda *args, **kwargs: audit_events.append((args, kwargs))),
            patch.object(module, "verify_admin_password", wraps=module.verify_admin_password) as verified,
        ):
            for _ in range(module.LOGIN_FAILURE_LIMIT):
                response = self.client.post("/admin/login", data={"password": "wrong-password"})
                self.assertEqual(response.status_code, 200)
            blocked = self.client.post("/admin/login", data={"password": "correct-password"})

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(verified.call_count, module.LOGIN_FAILURE_LIMIT)
        self.assertNotIn("correct-password", blocked.get_data(as_text=True))
        self.assertEqual(len(list(module.LOCAL_LOGIN_RATE_LIMIT_DIR.rglob("*.json"))), module.LOGIN_FAILURE_LIMIT)
        self.assertTrue(any(args[2] == "rejected" for args, _ in audit_events))
        persisted = "".join(path.read_text(encoding="utf-8") for path in module.LOCAL_LOGIN_RATE_LIMIT_DIR.rglob("*.json"))
        self.assertNotIn("wrong-password", persisted)

    def test_login_rate_limit_expiry_reset_and_separate_clients(self):
        now = module.datetime(2026, 8, 10, 12, tzinfo=module.timezone.utc)
        first = "a" * 64
        second = "b" * 64
        for _ in range(module.LOGIN_FAILURE_LIMIT):
            self.assertTrue(module.record_login_attempt(first, "failure", now))
        self.assertTrue(module.login_is_rate_limited(first, now))
        self.assertFalse(module.login_is_rate_limited(second, now))
        self.assertFalse(module.login_is_rate_limited(first, now + module.LOGIN_FAILURE_WINDOW + module.timedelta(seconds=1)))
        module.record_login_attempt(first, "success", now + module.timedelta(seconds=1))
        self.assertFalse(module.login_is_rate_limited(first, now + module.timedelta(seconds=1)))

    def test_login_rate_limit_identity_uses_only_trusted_ip(self):
        with module.app.test_request_context("/admin/login", environ_base={"REMOTE_ADDR": "127.0.0.10"}, headers={"User-Agent": "One", "X-Forwarded-For": "198.51.100.2"}):
            local_one = module.login_rate_limit_identity()
        with module.app.test_request_context("/admin/login", environ_base={"REMOTE_ADDR": "127.0.0.10"}, headers={"User-Agent": "Two", "X-Forwarded-For": "203.0.113.9"}):
            local_two = module.login_rate_limit_identity()
        self.assertEqual(local_one, local_two)
        with patch.dict(module.os.environ, {"VERCEL": "1"}, clear=False):
            with module.app.test_request_context("/admin/login", environ_base={"REMOTE_ADDR": "127.0.0.10"}, headers={"x-vercel-forwarded-for": "198.51.100.8"}):
                trusted = module.login_rate_limit_identity()
        self.assertNotEqual(local_one, trusted)

    def test_login_rate_limit_r2_keys_are_unique_and_storage_failures_fail_open(self):
        now = module.datetime(2026, 8, 10, 12, tzinfo=module.timezone.utc)
        uploaded = []
        with (
            patch.object(module, "is_vercel_runtime", return_value=True),
            patch.object(module, "r2_upload_bytes", side_effect=lambda data, key, *args: uploaded.append((data, key))),
        ):
            self.assertTrue(module.record_login_attempt("c" * 64, "failure", now))
            self.assertTrue(module.record_login_attempt("c" * 64, "failure", now))
        self.assertEqual(len({key for _, key in uploaded}), 2)
        self.assertNotIn("password", b"".join(data for data, _ in uploaded).decode("utf-8"))
        with patch.object(module, "is_vercel_runtime", return_value=True), patch.object(module, "r2_upload_bytes", side_effect=OSError("offline")):
            self.assertFalse(module.record_login_attempt("c" * 64, "failure", now))
        with patch.object(module, "is_vercel_runtime", return_value=True), patch.object(module, "r2_list_object_keys", side_effect=OSError("offline")):
            self.assertFalse(module.login_is_rate_limited("c" * 64, now))

    def test_https_responses_receive_hsts(self):
        response = self.client.get("/home", base_url="https://localhost")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

    def test_public_apis_exclude_hidden_content_and_hidden_relationships(self):
        module.save_projects(
            [
                {"id": "visible-project", "name": "Visible project", "visible": True},
                {"id": "hidden-project", "name": "Hidden project", "visible": False},
            ]
        )
        module.save_models(
            [
                {
                    "id": "visible-model",
                    "name": "Visible model",
                    "project_id": "visible-project",
                    "visible": True,
                },
                {
                    "id": "hidden-model",
                    "name": "Hidden model",
                    "project_id": "visible-project",
                    "visible": False,
                    "narration_audio": "https://example.com/hidden.mp3",
                },
                {
                    "id": "orphaned-visible-model",
                    "name": "Visible model in hidden project",
                    "project_id": "hidden-project",
                    "visible": True,
                },
                {
                    "id": "hidden-project-model",
                    "name": "Hidden model in hidden project",
                    "project_id": "hidden-project",
                    "visible": False,
                },
            ]
        )

        models = self.client.get("/api/models").get_json()
        projects = self.client.get("/api/projects").get_json()

        self.assertEqual([item["id"] for item in models], ["visible-model"])
        self.assertEqual([item["id"] for item in projects], ["visible-project"])
        self.assertNotIn("Hidden model", str(models))
        self.assertNotIn("Hidden project", str(projects))

    def test_vercel_runtime_reads_slider_json_from_github(self):
        remote_sliders = [
            {
                "id": "remote-slider",
                "title": "Remote Updated Title",
                "description": "Updated remotely",
                "image_url": "https://example.com/remote.webp",
                "active": True,
            }
        ]

        def fake_github_request(method, api_path, payload=None):
            self.assertEqual(method, "GET")
            self.assertIn("data/slider_items.json", api_path)
            encoded = base64.b64encode(
                json.dumps(remote_sliders).encode("utf-8")
            ).decode("ascii")
            return {"content": encoded}

        with (
            patch.dict(
                module.os.environ,
                {
                    "VERCEL": "1",
                    "GITHUB_CONTENTS_TOKEN": "token",
                    "GITHUB_REPOSITORY": "fufu4826/ARModel",
                    "GITHUB_BRANCH": "main",
                },
            ),
            patch.object(module, "github_api_request", side_effect=fake_github_request),
            patch.object(module, "production_data_relative_path", return_value="data/slider_items.json"),
        ):
            response = self.client.get("/api/sliders")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload[0]["title"], "Remote Updated Title")

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

    def test_home_stats_keep_dynamic_counts_and_remove_static_cards(self):
        template = (Path(module.BASE_DIR) / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("{{ total_project_count }}", template)
        self.assertIn("{{ total_model_count }}", template)
        self.assertNotIn("<strong>10</strong>", template)
        self.assertNotIn("<strong>41</strong>", template)
        self.assertNotIn("3D/AR", template)
        self.assertNotIn("R2 + JSON", template)

        module.save_projects(
            [
                {"id": "project-a", "name": "Project A", "visible": True},
                {"id": "project-b", "name": "Project B", "visible": True},
                {"id": "project-hidden", "name": "Project Hidden", "visible": False},
            ]
        )
        module.save_models(
            [
                {"id": "model-a", "name": "Model A", "project_id": "project-a", "visible": True},
                {"id": "model-b", "name": "Model B", "project_id": "project-a", "visible": True},
                {"id": "model-c", "name": "Model C", "project_id": "project-b", "visible": True},
                {"id": "model-d", "name": "Model D", "project_id": "project-b", "visible": True},
                {"id": "model-hidden", "name": "Model Hidden", "project_id": "project-b", "visible": False},
            ]
        )

        home_html = self.client.get("/home").get_data(as_text=True)
        stats_html = home_html.split('<section class="stats-section"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(stats_html.count('class="stat-card"'), 2)
        self.assertIn("<strong>2</strong>", stats_html)
        self.assertIn("<strong>4</strong>", stats_html)
        self.assertIn("<span>แหล่งเรียนรู้</span>", stats_html)
        self.assertIn("<span>โมเดล</span>", stats_html)
        self.assertNotIn("3D/AR", stats_html)
        self.assertNotIn("R2 + JSON", stats_html)

    def test_hidden_image_placeholders_do_not_take_space(self):
        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".image-placeholder[hidden]", stylesheet)
        self.assertIn("display: none;", stylesheet)

    def test_home_slider_cards_show_unified_hover_panel(self):
        stylesheet = (
            Path(module.BASE_DIR) / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")
        self.assertIn("body:not(.landing-page) .site-slider-section .site-slider", stylesheet)
        self.assertIn("height: 320px;", stylesheet)
        self.assertIn("height: 276px;", stylesheet)
        self.assertIn("position: absolute;", stylesheet)
        self.assertIn("-webkit-line-clamp: 2;", stylesheet)
        self.assertIn("-webkit-line-clamp: 4;", stylesheet)
        self.assertIn(".site-slide-preview__title", stylesheet)
        self.assertIn(".site-slide-preview__description", stylesheet)
        self.assertIn("overflow-wrap: anywhere;", stylesheet)
        self.assertIn("-webkit-line-clamp: 3;", stylesheet)
        self.assertIn("height: clamp(280px, 46svh, 460px);", stylesheet)
        self.assertIn("overflow: visible;", stylesheet)
        self.assertIn(".site-slide-hover-panel", stylesheet)
        self.assertIn(".site-slide-hover-media", stylesheet)
        self.assertIn(".site-slide-hover-image", stylesheet)
        self.assertIn(".site-slide-hover-content", stylesheet)
        self.assertIn("width: min(460px, calc(100vw - 32px));", stylesheet)
        self.assertIn("height: 312px;", stylesheet)
        self.assertIn("place-items: center;", stylesheet)
        self.assertIn("border-radius: calc(var(--radius) + 4px);", stylesheet)
        self.assertIn("box-shadow: 0 24px 56px", stylesheet)
        self.assertIn("overflow: hidden;", stylesheet)
        self.assertIn("pointer-events: none;", stylesheet)
        self.assertIn("transform: translate(-50%, -50%) scale(1);", stylesheet)
        self.assertIn("@media (hover: hover) and (pointer: fine) and (min-width: 921px)", stylesheet)
        self.assertIn("body:not(.landing-page) .site-slider-section .site-slide.is-hover-active .site-slide-hover-panel", stylesheet)
        self.assertIn("body:not(.landing-page) .site-slider-section .site-slide.is-hover-active > img", stylesheet)
        self.assertNotIn(".site-slide:hover .site-slide-hover-panel", stylesheet)
        self.assertNotIn(".site-slide:focus-within .site-slide-hover-panel", stylesheet)
        self.assertIn("opacity: 0;", stylesheet)
        self.assertIn("max-height: 6.3em;", stylesheet)
        self.assertIn("object-fit: contain;", stylesheet)
        self.assertIn(".site-slide-modal", stylesheet)
        self.assertIn(".site-slide-modal__image", stylesheet)
        self.assertIn(".site-slide-modal__scroll-area", stylesheet)
        self.assertIn("overflow-y: auto;", stylesheet)
        self.assertIn("max-height: min(86dvh, 760px);", stylesheet)
        self.assertIn(".site-slide-modal[hidden]", stylesheet)
        self.assertIn("pointer-events: none;", stylesheet)
        self.assertIn(".site-slide-modal.site-slide-modal--open", stylesheet)
        self.assertIn(".site-slide-modal__close svg", stylesheet)
        self.assertIn(".site-slide-modal__close path", stylesheet)
        self.assertIn("stroke-linecap: round;", stylesheet)
        self.assertIn("body.slide-dialog-open", stylesheet)
        self.assertIn("html.slide-dialog-open", stylesheet)
        self.assertIn(".site-slide.site-slide--dialog-return-focus .site-slide-hover-panel", stylesheet)

        script = (
            Path(module.BASE_DIR) / "static" / "js" / "site-carousel.js"
        ).read_text(encoding="utf-8")
        self.assertIn("window.__siteCarouselInitialized", script)
        self.assertIn("let activeHoverCard = null;", script)
        self.assertIn("let hoverHideTimer = null;", script)
        self.assertIn("function clearActiveHoverCard()", script)
        self.assertIn("function setActiveHoverCard(card)", script)
        self.assertIn("function setupHoverPanel(slide)", script)
        self.assertIn("function createHoverPanelPortal(slide)", script)
        self.assertIn("site-slide-hover-panel--portal", script)
        self.assertIn("document.body.append(portal)", script)
        self.assertIn(".forEach(setupHoverPanel)", script)
        self.assertIn("document.querySelectorAll(\".site-slide.is-hover-active, .site-slide.site-slide--dialog-return-focus\")", script)
        self.assertIn("card.classList.add(\"is-hover-active\")", script)
        self.assertIn("activeHoverCard = card", script)
        self.assertIn("pointerenter", script)
        self.assertIn("pointerleave", script)
        self.assertIn("slideChange: clearActiveHoverCard", script)
        self.assertIn("window.addEventListener(\"blur\", clearActiveHoverCard)", script)
        self.assertIn("document.addEventListener(\"visibilitychange\"", script)
        self.assertIn("function closeDialog", script)
        self.assertIn("dialog.classList.remove(\"site-slide-modal--open\")", script)
        self.assertIn("dialog.setAttribute(\"aria-hidden\", \"true\")", script)
        self.assertIn("unlockPageScroll();", script)
        self.assertIn("document.documentElement.classList.remove(\"slide-dialog-open\")", script)
        self.assertIn("document.body.classList.remove(\"slide-dialog-open\")", script)
        self.assertIn("image.removeAttribute(\"src\")", script)
        self.assertIn("site-slide--dialog-return-focus", script)
        self.assertIn("closeButtons.forEach((button) => button.addEventListener(\"click\", closeDialog))", script)
        self.assertIn("event.key === \"Escape\" && !dialog.hidden) closeDialog()", script)

    def test_home_news_marquee_is_scoped_to_slider_cards(self):
        home_html = self.client.get("/home").get_data(as_text=True)
        template = (Path(module.BASE_DIR) / "templates" / "index.html").read_text(encoding="utf-8")
        stylesheet = (Path(module.BASE_DIR) / "static" / "css" / "style.css").read_text(encoding="utf-8")
        script = (Path(module.BASE_DIR) / "static" / "js" / "site-carousel.js").read_text(encoding="utf-8")

        self.assertEqual(home_html.count('id="projects"'), 1)
        self.assertIn('<a class="button" href="#projects">เริ่มชมโมเดล 3D</a>', home_html)
        self.assertIn('class="card-grid project-grid"', template)
        self.assertNotIn("data-project-carousel", template)
        self.assertNotIn("project-carousel", script)
        self.assertIn("[data-site-slider]", script)
        self.assertIn("site-slider--marquee", script)
        self.assertIn("function makeMarqueeClones", script)
        self.assertIn("? { delay: 5000, disableOnInteraction: false", script)
        self.assertIn('aria-hidden", "true"', script)
        self.assertIn('tabindex", "-1"', script)
        self.assertIn("reduceMotion", script)
        self.assertIn("body:not(.landing-page) .site-slider-section .site-slider--marquee", stylesheet)
        self.assertIn("flex: 0 0 280px;", stylesheet)
        self.assertIn("object-fit: cover;", stylesheet)
        self.assertIn("font-family: var(--font-primary);", stylesheet)
        self.assertIn(".site-slider--marquee::before", stylesheet)
        self.assertIn(".site-slider--marquee::after", stylesheet)
        self.assertIn("pointer-events: none;", stylesheet)
        self.assertIn("rgba(255, 255, 255, 0.78)", stylesheet)
        self.assertIn(".site-slide-preview__description", stylesheet)
        self.assertIn(".site-slide-modal__scroll-area", stylesheet)

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
        self.assertNotIn('href="/models"', landing_html)

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
        self.assertIn('<a class="button" href="#projects">เริ่มชมโมเดล 3D</a>', home_html)
        self.assertEqual(home_html.count('id="projects"'), 1)

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
        self.assertIn('<a class="button" href="#projects">Test primary action</a>', home_html)
        self.assertEqual(home_html.count('id="projects"'), 1)

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
        models = module.load_models(include_hidden=True)
        lychee = next(item for item in models if item["id"] == "lychee")
        lychee["narration_audio"] = "https://example.com/lychee.mp3"
        module.save_models(models)

        model_html = self.client.get("/models/lychee").get_data(as_text=True)
        self.assertIn("data-model-narration", model_html)
        self.assertIn("data-narration-toggle", model_html)
        self.assertIn("data-narration-status", model_html)
        self.assertIn("ฟังเสียงบรรยาย", model_html)
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
        route = "/admin/narrations/lychee/draft"
        response = self.client.post(route)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        self.sign_in()
        with patch.dict(module.os.environ, {"GEMINI_API_KEY": ""}):
            response = self.client.post(route, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "สร้างเสียงรอตรวจสอบไม่สำเร็จ",
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
                "/admin/narrations/lychee/draft",
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("รอตรวจสอบ", html)
        self.assertIn("ยืนยันใช้เสียงนี้", html)
        self.assertNotIn("test-secret-not-for-rendering", html)
        generate_audio.assert_called_once()
        prompt_text = generate_audio.call_args.args[0]
        self.assertIn(source_model["name"], prompt_text)
        self.assertIn(source_model["description"], prompt_text)

        model = next(
            item for item in module.load_models(include_hidden=True)
            if item["id"] == "lychee"
        )
        self.assertEqual(model["narration_audio"], source_model["narration_audio"])

    def test_admin_narrations_lists_models_and_keeps_drafts_unpublished(self):
        self.assertEqual(self.client.get("/admin/narrations").status_code, 302)
        self.sign_in()
        models = module.load_models(include_hidden=True)
        models[0]["narration_audio"] = "https://example.com/current.wav"
        models[1]["visible"] = False
        module.save_models(models)
        page = self.client.get("/admin/narrations").get_data(as_text=True)
        self.assertIn("จัดการเสียงบรรยาย", page)
        self.assertIn("data-narration-search", page)
        self.assertIn("data-narration-project", page)
        self.assertIn("data-narration-audio-status", page)
        self.assertIn("data-narration-visibility", page)
        self.assertIn("css/admin-narrations.css", page)
        self.assertIn("data-narration-reset", page)
        self.assertIn("data-narration-empty", page)
        self.assertIn('src="/static/js/admin-narrations.js?v=2"', page)
        narration_styles = (Path(module.BASE_DIR) / "static" / "css" / "admin-narrations.css").read_text(encoding="utf-8")
        self.assertIn("[data-narration-item][hidden]", narration_styles)
        self.assertIn("ฟังเสียงปัจจุบัน", page)
        self.assertIn("data-audio-toggle", page)
        self.assertIn("ซ่อนอยู่", page)

        before = module.load_models(include_hidden=True)
        with patch.dict(module.os.environ, {"NARRATION_PREVIEW_MOCK": "1"}, clear=False):
            response = self.client.post(f"/admin/narrations/{models[0]['id']}/draft")
        self.assertEqual(response.status_code, 302)
        self.assertIn("draft=", response.headers["Location"])
        self.assertEqual(module.load_models(include_hidden=True), before)
        token = response.headers["Location"].split("draft=", 1)[1].split("&", 1)[0]
        draft_page = self.client.get(response.headers["Location"]).get_data(as_text=True)
        self.assertIn("รอตรวจสอบ", draft_page)
        self.assertIn("เสียงใหม่รอตรวจสอบ", draft_page)
        self.assertIn("ยืนยันใช้เสียงนี้", draft_page)
        self.assertIn('aria-labelledby="dialog-title-', draft_page)
        self.assertEqual(self.client.post(f"/admin/narrations/drafts/{token}x/confirm").status_code, 302)
        with patch.object(module, "save_generated_narration_audio", return_value="audio/confirmed.wav"):
            confirmed = self.client.post(f"/admin/narrations/drafts/{token}/confirm")
        self.assertEqual(confirmed.status_code, 302)
        selected = next(item for item in module.load_models(True) if item["id"] == models[0]["id"])
        self.assertEqual(selected["narration_audio"], "audio/confirmed.wav")
        self.assertEqual(self.client.post(f"/admin/narrations/drafts/{token}/confirm").status_code, 302)

    def test_audit_logs_are_signed_private_and_require_admin(self):
        self.assertEqual(self.client.get("/admin/audit-logs").status_code, 302)
        with tempfile.TemporaryDirectory() as audit_dir, patch.object(module, "LOCAL_AUDIT_LOG_DIR", Path(audit_dir)):
            with self.client.session_transaction() as audit_session:
                audit_session["admin"] = True
                audit_session["admin_session_id"] = "test-session"
            with self.client:
                self.client.get("/admin")
                event = module.write_audit_event(
                    "model", "edit", "success", "แก้ไขโมเดลทดสอบสำเร็จ",
                    resource_type="model", resource_id="test", resource_name="โมเดลทดสอบ",
                    metadata={"password": "never-store", "token": "never-store", "bytes": b"file"},
                )
            self.assertIsNotNone(event)
            self.assertTrue(module.verify_audit_event(event))
            self.assertEqual(event["metadata"]["password"], "[ปกปิด]")
            self.assertEqual(event["metadata"]["token"], "[ปกปิด]")
            self.assertEqual(event["metadata"]["bytes"]["kind"], "binary")
            self.assertTrue(list(Path(audit_dir).rglob("*.json")))
            page = self.client.get("/admin/audit-logs").get_data(as_text=True)
            self.assertIn("บันทึกการใช้งาน", page)
            self.assertIn("แก้ไขโมเดลทดสอบสำเร็จ", page)
            self.assertEqual(self.client.get("/admin/audit-logs/export/csv").status_code, 200)

    def test_settings_mutations_are_audited_and_audit_failure_is_visible(self):
        self.sign_in()
        with patch.object(module, "write_audit_event", return_value={}) as audited:
            intro = self.client.post(
                "/admin/intro",
                data={"intro_enabled": "on", "intro_display_mode": "sequence", "intro_logo_duration_ms": "1400"},
            )
            branding = self.client.post(
                "/admin/settings",
                data={"section": "branding", "return_to": "/admin/branding"},
            )
        self.assertEqual(intro.status_code, 302)
        self.assertEqual(branding.status_code, 302)
        sections = [call.kwargs.get("metadata", {}).get("section") for call in audited.call_args_list]
        self.assertIn("intro", sections)
        self.assertIn("branding", sections)

        with patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")):
            response = self.client.post(
                "/admin/intro",
                data={"intro_enabled": "on", "intro_display_mode": "sequence", "intro_logo_duration_ms": "1400"},
                follow_redirects=True,
            )
        page = response.get_data(as_text=True)
        self.assertIn("บันทึกข้อมูลสำเร็จ แต่ไม่สามารถเขียนบันทึกการใช้งานได้", page)

    def test_production_audit_logs_are_listed_from_r2(self):
        with self.client.session_transaction() as audit_session:
            audit_session["admin"] = True
            audit_session["admin_session_id"] = "r2-session"
        with self.client:
            self.client.get("/admin")
            first = module.write_audit_event("auth", "login", "success", "เข้าสู่ระบบสำเร็จ")
            second = module.write_audit_event("model", "edit", "success", "แก้ไขโมเดลสำเร็จ")
        first["timestamp_utc"] = "2026-07-01T00:00:00+00:00"
        first["timestamp_local"] = "2026-07-01T07:00:00+07:00"
        first["signature"] = ""  # Re-sign after making the sort order deterministic.
        unsigned_first = dict(first); unsigned_first.pop("signature")
        first["signature"] = module.hmac.new(module.audit_signing_key(), module.json.dumps(unsigned_first, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), module.hashlib.sha256).hexdigest()
        objects = {"audit/2026/07/01/first.json": first, "audit/2026/07/01/second.json": second}
        with (
            patch.object(module, "is_vercel_runtime", return_value=True),
            patch.object(module, "r2_list_object_keys", return_value=(list(objects), "")) as listed,
            patch.object(module, "r2_get_bytes", side_effect=lambda key: module.json.dumps(objects[key]).encode("utf-8")),
        ):
            events = module.list_audit_events(2)
        self.assertEqual([event["summary_th"] for event in events], ["แก้ไขโมเดลสำเร็จ", "เข้าสู่ระบบสำเร็จ"])
        self.assertTrue(all(event["signature_valid"] for event in events))
        self.assertEqual(listed.call_args.args[0], f"{module.AUDIT_PREFIX}{module.datetime.now(module.timezone.utc):%Y/%m/%d}/")

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
        long_title = ("Long title " * 80).strip()
        long_description = (
            "First paragraph with enough detail to exercise the preview.\n\n"
            + ("second-paragraph " * 300)
            + "\n\n"
            + ("unbroken-text-" * 300)
        )
        module.save_slider_items(
            [
                {
                    "id": "test-slide",
                    "title": long_title,
                    "description": long_description,
                    "image_url": "pic/og-cover.jpg",
                    "button_text": "Open",
                    "button_url": "/models",
                    "sort_order": 1,
                    "active": True,
                },
                {
                    "id": "empty-description-slide",
                    "title": "Short title",
                    "description": "",
                    "image_url": "pic/og-cover.jpg",
                    "sort_order": 2,
                    "active": True,
                },
            ]
        )
        for route in ("/", "/home"):
            with self.subTest(route=route):
                response = self.client.get(route)
                html = response.get_data(as_text=True)
                self.assertIn(long_title, html)
                self.assertIn(long_description, html)
                self.assertIn("data-slide-dialog-trigger", html)
                self.assertIn("data-slide-dialog", html)
                self.assertIn("data-slide-dialog-title", html)
                self.assertIn("data-slide-dialog-description", html)
                self.assertIn('class="site-slide-modal"', html)
                self.assertIn('aria-hidden="true"', html)
                self.assertIn('class="site-slide-modal__close"', html)
                self.assertIn('type="button"', html)
                self.assertIn('aria-label="Close"', html)
                self.assertIn("<svg viewBox=\"0 0 24 24\"", html)
                self.assertIn('<path d="M6 6L18 18"></path>', html)
                self.assertIn('<path d="M18 6L6 18"></path>', html)
                self.assertNotIn("&times;", html)
                self.assertNotIn(">×<", html)
                self.assertIn("site-slide-hover-panel", html)
                self.assertIn("site-slide-hover-media", html)
                self.assertIn("site-slide-hover-content", html)
                self.assertIn("site-slide-preview", html)
                self.assertIn("site-slide-preview__title", html)
                self.assertIn("site-slide-preview__description", html)
                self.assertIn("site-slide-modal__scroll-area", html)

                if route == "/":
                    self.assertIn('data-landing-slider-toggle', html)
                    self.assertIn('aria-expanded="false"', html)
                    self.assertIn('aria-controls="landing-slider-region"', html)
                    self.assertIn('id="landing-slider-region"', html)
                    self.assertIn('data-landing-slider-region hidden', html)
                    self.assertIn("ข่าวสาร", html)
                else:
                    self.assertNotIn("data-landing-slider-toggle", html)
                    self.assertNotIn("data-landing-slider-region", html)

        payload = json.loads(self.client.get("/api/sliders").get_data(as_text=True))
        self.assertEqual([item["id"] for item in payload], ["test-slide", "empty-description-slide"])

    def test_landing_omits_slider_toggle_when_no_active_sliders_exist(self):
        landing_html = self.client.get("/").get_data(as_text=True)
        home_html = self.client.get("/home").get_data(as_text=True)

        self.assertNotIn("data-landing-slider-toggle", landing_html)
        self.assertNotIn("data-landing-slider-region", landing_html)
        self.assertNotIn("data-site-slider", landing_html)
        self.assertNotIn("data-site-slider", home_html)

    def test_landing_slider_toggle_script_handles_hidden_carousels_safely(self):
        script = (
            Path(module.BASE_DIR) / "static" / "js" / "site-carousel.js"
        ).read_text(encoding="utf-8")
        self.assertIn("const carouselInstances = new WeakMap();", script)
        self.assertIn("function pauseCarouselAutoplay", script)
        self.assertIn("function resumeCarouselAutoplay", script)
        self.assertIn("function refreshCarousel", script)
        self.assertIn('document.querySelectorAll("[data-landing-slider-toggle]")', script)
        self.assertIn('region.hidden = false;', script)
        self.assertIn('region.hidden = true;', script)
        self.assertIn('toggle.setAttribute("aria-expanded", "true")', script)
        self.assertIn('toggle.setAttribute("aria-expanded", "false")', script)
        self.assertIn('toggle.textContent = "ปิดสไลด์"', script)
        self.assertIn('toggle.textContent = "ข่าวสาร"', script)
        self.assertIn('window.requestAnimationFrame(() => {', script)
        self.assertIn('element.closest("[data-landing-slider-region][hidden]")', script)
        self.assertIn('const landingSliderMobileQuery = window.matchMedia("(max-width: 768px)");', script)
        self.assertIn("function synchronizeMobileVisibility()", script)
        self.assertIn("landingSliderMobileQuery.addEventListener(\"change\", synchronizeMobileVisibility);", script)

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
        self.assertNotIn('href="/models"', landing_html)

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
                m["narration_audio"] = "https://example.com/lychee.mp3"
            elif m["id"] == "lukplakob":
                m["narration_audio"] = ""
        module.save_models(models)

        # 1. Model with narration_audio shows มีเสียงบรรยาย on /models
        response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("มีเสียงบรรยาย", html)

        # 2. Listing cards retain the Home-page badge-only presentation.
        self.assertNotIn("ไม่มีเสียงบรรยาย", html)

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
        self.assertIn("ฟังเสียงบรรยาย", detail_html)

    def test_model_detail_shows_narration_status_and_audio_action(self):
        module.save_models(
            [
                {
                    "id": "project-narrated",
                    "name": "Narrated project model",
                    "project_id": "garden",
                    "model_url": "https://example.com/narrated.glb",
                    "thumbnail_url": "https://example.com/narrated.jpg",
                    "narration_audio": "https://example.com/narrated.wav",
                    "visible": True,
                },
                {
                    "id": "project-silent",
                    "name": "Silent project model",
                    "project_id": "garden",
                    "model_url": "https://example.com/silent.glb",
                    "thumbnail_url": "https://example.com/silent.jpg",
                    "narration_audio": "",
                    "visible": True,
                },
                {
                    "id": "project-missing-audio",
                    "name": "Missing audio field model",
                    "project_id": "garden",
                    "model_url": "https://example.com/missing.glb",
                    "thumbnail_url": "https://example.com/missing.jpg",
                    "visible": True,
                },
                {
                    "id": "project-hidden-audio",
                    "name": "Hidden narrated project model",
                    "project_id": "garden",
                    "model_url": "https://example.com/hidden.glb",
                    "thumbnail_url": "https://example.com/hidden.jpg",
                    "narration_audio": "https://example.com/hidden.ogg",
                    "visible": False,
                },
            ]
        )

        response = self.client.get("/models/project-narrated")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Narrated project model", html)
        self.assertIn("มีเสียงบรรยาย", html)
        self.assertIn("ฟังเสียงบรรยาย", html)
        self.assertIn('data-narration-label="ฟังเสียงบรรยาย"', html)
        self.assertIn('src="https://example.com/narrated.wav"', html)
        self.assertEqual(html.count("data-narration-audio"), 1)
        self.assertEqual(html.count("model-detail-narration__button"), 1)

        project_html = self.client.get("/projects/garden").get_data(as_text=True)
        self.assertNotIn("data-model-narration", project_html)
        self.assertIn("มีเสียงบรรยาย", project_html)
        self.assertIn("ไม่มีเสียงบรรยาย", project_html)
        self.assertIn("model-audio-status--unavailable", project_html)

        silent_html = self.client.get("/models/project-silent").get_data(as_text=True)
        missing_html = self.client.get("/models/project-missing-audio").get_data(as_text=True)
        self.assertIn("ไม่มีเสียงบรรยาย", silent_html)
        self.assertIn("ไม่มีเสียงบรรยาย", missing_html)
        self.assertNotIn("ฟังเสียงบรรยาย", silent_html)
        self.assertNotIn("ฟังเสียงบรรยาย", missing_html)

        stylesheet = (Path(module.BASE_DIR) / "static" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".model-detail-narration__button", stylesheet)
        self.assertIn("model-detail-narration-attention", stylesheet)
        self.assertIn("animation: model-detail-narration-attention 5.6s", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
        self.assertIn(".model-detail-narration__button {\n    animation: none;", stylesheet)
        self.assertNotIn(".model-narration__button {\n  animation: model-detail-narration-attention", stylesheet)

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

    def test_authenticated_admin_forms_include_session_csrf_token(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf_token"] = "test-csrf-token"
        html = self.client.get("/admin").get_data(as_text=True)
        self.assertIn('name="csrf_token" value="test-csrf-token"', html)
        self.assertEqual(
            html.count('name="csrf_token" value="test-csrf-token"'),
            html.count('method="post"'),
        )


class ZeroSupabaseRuntimeTests(unittest.TestCase):
    def setUp(self):
        module._JSON_CACHE.clear()
        module.app.config.update(TESTING=True, SECRET_KEY="test-only-key")
        self.client = module.app.test_client()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf_token"] = "test-csrf-token"
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"

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
        active_slider_ids = [item["id"] for item in sliders if item.get("active")]
        self.assertEqual(
            [item["id"] for item in api_sliders.get_json()],
            active_slider_ids,
        )

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
