"""Multi-user admin: four roles, owner-only one-time invite/reset links, immediate revocation."""
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as module
import test_site_management as base
from admin_session import ensure_user, grant_admin_session
from armodel.repositories import admin_users as users


class AdminUsersTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown

    def db(self):
        return module.admin_db()

    def client_as(self, role, username=None):
        client = module.app.test_client()
        with client.session_transaction() as session:
            user = grant_admin_session(session, role, username)
            session["csrf_token"] = "test-csrf-token"
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"
        return client, user

    def invite_link(self, owner_client, role="editor"):
        response = owner_client.post("/admin/users/invite", data={"role": role, "note": "ทีมตรวจ"})
        self.assertEqual(response.status_code, 302)
        page = owner_client.get("/admin/users").get_data(as_text=True)
        match = re.search(r'value="(http[^"]+/admin/invite/([^"]+))"', page)
        self.assertIsNotNone(match, "invite link is shown once to the owner")
        return match.group(2)

    def accept(self, token, username="team-editor", password="team-password-123", client=None):
        client = client or module.app.test_client()
        client.get(f"/admin/invite/{token}")
        with client.session_transaction() as session:
            csrf = session["csrf_token"]
        response = client.post(f"/admin/invite/{token}", data={
            "username": username, "display_name": "Team", "password": password,
            "confirm_password": password, "csrf_token": csrf})
        return client, response

    def first_project(self):
        return module.load_projects(include_hidden=True)[0]

    # ---- role permissions -------------------------------------------------
    def test_reviewer_can_view_but_never_save(self):
        client, _ = self.client_as("reviewer")
        page = client.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-admin-read-only="true"', page.get_data(as_text=True))
        project = self.first_project()
        self.assertEqual(client.post(f"/admin/projects/{project['id']}/edit", data={"name": "x"}).status_code, 403)
        self.assertEqual(client.post("/admin/projects", data={"name": "new"}).status_code, 403)
        self.assertEqual(client.get("/admin/audit-logs").status_code, 403)
        self.assertEqual(client.get("/admin/users").status_code, 403)
        self.assertEqual(client.post("/admin/logout").status_code, 302)
        self.assertEqual(self.first_project()["name"], project["name"])

    def test_editor_saves_content_but_not_site_settings(self):
        client, _ = self.client_as("editor")
        project = self.first_project()
        response = client.post(f"/admin/projects/{project['id']}/edit", data={"name": "แก้โดยผู้แก้ไข"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.first_project()["name"], "แก้โดยผู้แก้ไข")
        self.assertEqual(client.post("/admin/settings", data={"section": "branding"}).status_code, 403)
        self.assertIn('data-admin-read-only="true"', client.get("/admin/branding").get_data(as_text=True))
        self.assertIn('data-admin-read-only="false"', client.get("/admin").get_data(as_text=True))
        self.assertEqual(client.get("/admin/audit-logs").status_code, 403)

    def test_admin_manages_everything_except_users(self):
        client, _ = self.client_as("admin")
        self.assertNotEqual(client.post("/admin/settings", data={"section": "branding"}).status_code, 403)
        self.assertEqual(client.get("/admin/audit-logs").status_code, 200)
        self.assertEqual(client.get("/admin/users").status_code, 403)
        self.assertEqual(client.post("/admin/users/invite", data={"role": "admin"}).status_code, 403)
        nav = client.get("/admin").get_data(as_text=True)
        self.assertNotIn("ผู้ใช้และสิทธิ์", nav)
        self.assertIn("บันทึกการใช้งาน", nav)

    def test_every_admin_route_has_a_known_permission(self):
        for rule in module.app.url_map.iter_rules():
            if not rule.rule.startswith("/admin") or rule.endpoint in {
                    "admin_login", "admin_logout", "admin_accept_invite", "admin_accept_reset"}:
                continue
            view = module.app.view_functions[rule.endpoint]
            with self.subTest(endpoint=rule.endpoint):
                self.assertTrue(hasattr(view, "__wrapped__"), "every Admin view uses admin_required")
                for method in rule.methods - {"HEAD", "OPTIONS"}:
                    self.assertIn(module.required_role(rule.endpoint, method), module.ROLE_RANK)

    # ---- invites ------------------------------------------------------------
    def test_owner_invite_creates_user_with_chosen_role_once(self):
        owner_client, owner = self.client_as("owner")
        token = self.invite_link(owner_client, "editor")
        stored = self.db().batch([("SELECT token_hash FROM admin_invites", [])])[0]
        self.assertEqual(stored, [{"token_hash": users.token_hash(token)}], "only the hash is stored")
        self.assertNotIn(token, owner_client.get("/admin/users").get_data(as_text=True), "link shown only once")
        landing = module.app.test_client().get(f"/admin/invite/{token}")
        self.assertEqual(landing.status_code, 200)
        self.assertIn("ผู้แก้ไขเนื้อหา", landing.get_data(as_text=True))
        client, response = self.accept(token)
        self.assertEqual(response.status_code, 302)
        created = next(user for user in users.list_users(self.db()) if user["username"] == "team-editor")
        self.assertEqual((created["role"], created["invited_by"]), ("editor", owner["id"]))
        self.assertEqual(client.get("/admin").status_code, 200)
        _, again = self.accept(token, username="second-user")
        self.assertEqual(again.status_code, 410)
        self.assertEqual(len(users.list_users(self.db())), 2)

    def test_invite_post_requires_csrf_and_strong_password(self):
        owner_client, _ = self.client_as("owner")
        token = self.invite_link(owner_client)
        no_csrf = module.app.test_client().post(f"/admin/invite/{token}", data={
            "username": "x-user", "password": "team-password-123", "confirm_password": "team-password-123"})
        self.assertEqual(no_csrf.status_code, 400)
        _, weak = self.accept(token, password="short")
        self.assertEqual(weak.status_code, 400)
        self.assertEqual(len(users.list_users(self.db())), 1, "failed attempts do not consume the link")
        _, ok = self.accept(token)
        self.assertEqual(ok.status_code, 302)

    def test_duplicate_username_keeps_invite_unused(self):
        owner_client, _ = self.client_as("owner", "chief")
        token = self.invite_link(owner_client)
        _, response = self.accept(token, username="CHIEF")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ชื่อผู้ใช้นี้ถูกใช้แล้ว", response.get_data(as_text=True))
        self.assertIsNotNone(users.open_link(self.db(), token, "invite"))

    def test_expired_and_revoked_links_are_rejected(self):
        owner = ensure_user("owner")
        past = datetime.now(timezone.utc) - timedelta(hours=49)
        expired = users.create_link(self.db(), kind="invite", role="reviewer", created_by=owner["id"], now=past)
        self.assertEqual(module.app.test_client().get(f"/admin/invite/{expired}").status_code, 410)
        revoked = users.create_link(self.db(), kind="invite", role="reviewer", created_by=owner["id"])
        owner_client, _ = self.client_as("owner")
        self.assertEqual(owner_client.post(f"/admin/users/links/{users.token_hash(revoked)}/revoke").status_code, 302)
        self.assertEqual(module.app.test_client().get(f"/admin/invite/{revoked}").status_code, 410)
        self.assertEqual(module.app.test_client().get("/admin/invite/not-a-token").status_code, 410)

    def test_only_invitable_roles_can_be_invited(self):
        owner_client, _ = self.client_as("owner")
        owner_client.post("/admin/users/invite", data={"role": "owner"})
        self.assertEqual(self.db().batch([("SELECT COUNT(*) AS n FROM admin_invites", [])])[0][0]["n"], 0)
        with self.assertRaises(users.AccountError):
            users.create_link(self.db(), kind="invite", role="owner", created_by="x")

    # ---- immediate effect of role changes, suspension and resets ---------------
    def test_role_change_and_suspension_apply_to_open_sessions(self):
        owner_client, _ = self.client_as("owner")
        editor_client, editor = self.client_as("editor", "editor-one")
        project = self.first_project()
        owner_client.post(f"/admin/users/{editor['id']}/update", data={"role": "reviewer", "active": "1"})
        self.assertEqual(editor_client.post(f"/admin/projects/{project['id']}/edit", data={"name": "x"}).status_code, 403)
        owner_client.post(f"/admin/users/{editor['id']}/update", data={"role": "reviewer", "active": "0"})
        response = editor_client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])
        self.assertIsNone(users.authenticate(self.db(), "editor-one", "test-owner-password"))

    def test_owner_cannot_be_changed_from_the_web(self):
        owner_client, owner = self.client_as("owner")
        owner_client.post(f"/admin/users/{owner['id']}/update", data={"role": "reviewer", "active": "0"})
        self.assertEqual(users.owner(self.db())["role"], "owner")
        self.assertTrue(users.owner(self.db())["active"])
        owner_client.post(f"/admin/users/{owner['id']}/reset-link")
        self.assertEqual(self.db().batch([("SELECT COUNT(*) AS n FROM admin_invites", [])])[0][0]["n"], 0)

    def test_reset_link_sets_new_password_and_ends_old_sessions(self):
        owner_client, _ = self.client_as("owner")
        member_client, member = self.client_as("editor", "forgetful")
        self.assertEqual(owner_client.post(f"/admin/users/{member['id']}/reset-link").status_code, 302)
        page = owner_client.get("/admin/users").get_data(as_text=True)
        token = re.search(r'/admin/reset/([^"]+)"', page).group(1)
        anonymous = module.app.test_client()
        self.assertIn("forgetful", anonymous.get(f"/admin/reset/{token}").get_data(as_text=True))
        with anonymous.session_transaction() as session:
            csrf = session["csrf_token"]
        response = anonymous.post(f"/admin/reset/{token}", data={
            "password": "brand-new-password", "confirm_password": "brand-new-password", "csrf_token": csrf})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(member_client.get("/admin").status_code, 302, "old session ended")
        self.assertIsNotNone(users.authenticate(self.db(), "forgetful", "brand-new-password"))
        self.assertEqual(anonymous.get(f"/admin/reset/{token}").status_code, 410, "one-time link")

    # ---- audit ----------------------------------------------------------------
    def test_audit_records_actor_and_user_management(self):
        owner_client, owner = self.client_as("owner", "chief")
        events = []
        with patch.object(module.audit_service, "sign_event", side_effect=lambda event, _key: events.append(event) or event):
            self.invite_link(owner_client, "reviewer")
        invite = next(event for event in events if event.get("action") == "invite_create")
        self.assertEqual(invite["metadata"]["actor"], "chief")
        self.assertEqual(invite["metadata"]["actor_role"], "owner")


if __name__ == "__main__":
    unittest.main()
