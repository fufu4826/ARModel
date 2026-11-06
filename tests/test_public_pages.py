"""Storyboard fixes: one menu and footer on every public page, Thai 404 page, Thai admin wording."""
import unittest

import app as module
import test_site_management as base


class PublicPageConsistencyTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def pages(self):
        client = module.app.test_client()
        model = module.get_models()[0]
        paths = ["/home", "/models", f"/models/{model['id']}"]
        if model.get("project_id"):
            paths.append(f"/projects/{model['project_id']}")
        return client, {path: client.get(path) for path in paths}

    def test_every_public_page_has_the_same_menu_and_footer(self):
        _, pages = self.pages()
        for path, response in pages.items():
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200, path)
            menu = html.split('id="nav-menu"', 1)[1].split("</nav>", 1)[0]
            for label in ("หน้าแรก", "แหล่งเรียนรู้", "รายการโมเดล", "รู้จักศูนย์ภูพาน / ติดต่อ"):
                self.assertIn(label, menu, path)
            self.assertNotIn("ผู้ดูแล", menu, f"admin link only in the footer ({path})")
            self.assertIn('href="/home#projects"', menu, path)
            footer = html.split('<footer class="site-footer', 1)[1]
            self.assertIn("ผู้ดูแลระบบ", footer, path)
            self.assertNotIn("PhuPhan AR", footer.split("</footer>", 1)[0], path)

    def test_header_shows_the_short_brand_name(self):
        _, pages = self.pages()
        html = pages["/home"].get_data(as_text=True)
        brand = html.split('class="brand-mark"', 1)[1].split("</a>", 1)[0]
        self.assertNotIn("|", brand.split("<strong>", 1)[1].split("</strong>", 1)[0])

    def test_hero_buttons_go_to_different_sections(self):
        _, pages = self.pages()
        html = pages["/home"].get_data(as_text=True)
        self.assertIn('href="#featured-models"', html)
        self.assertIn('id="featured-models"', html)

    def test_slide_dialog_has_no_image_without_src(self):
        _, pages = self.pages()
        html = pages["/home"].get_data(as_text=True)
        self.assertNotIn("data-slide-dialog-image ", html)
        self.assertNotIn('src=""', html)


class NotFoundPageTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def test_unknown_page_is_thai_with_links_back(self):
        response = module.app.test_client().get("/projects")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn("ไม่พบหน้าที่ต้องการ", html)
        self.assertIn("กลับหน้าแรก", html)
        self.assertIn('id="nav-menu"', html)
        self.assertIn('name="robots" content="noindex"', html)

    def test_trailing_slash_redirects(self):
        client = module.app.test_client()
        response = client.get("/admin/")
        self.assertEqual((response.status_code, response.headers["Location"]), (301, "/admin"))
        self.assertIn("/admin/login", client.get("/admin").headers.get("Location", ""))
        self.assertEqual(client.get("/models/").headers["Location"], "/models")

    def test_unknown_api_path_stays_json(self):
        response = module.app.test_client().get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "not_found"})


class ThaiWordingTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def test_login_page_is_thai(self):
        html = module.app.test_client().get("/admin/login").get_data(as_text=True)
        self.assertIn("เข้าสู่ระบบผู้ดูแล", html)
        self.assertNotIn("Admin Login", html)


if __name__ == "__main__":
    unittest.main()


class ArQrTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def test_model_page_has_hidden_qr_to_open_ar_on_a_phone(self):
        model = module.get_models()[0]
        html = module.app.test_client().get(f"/models/{model['id']}").get_data(as_text=True)
        card = html.split('id="arQrCard"', 1)[1].split("</div>\n      </div>", 1)[0]
        self.assertIn("<svg", card)
        self.assertIn(f"/models/{model['id']}?mode=ar", card)
        self.assertIn('id="arQrCard" hidden', html)
