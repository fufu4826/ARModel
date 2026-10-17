"""Regression tests for defects found in the 2026-10-16 review (docs/CLAUDE_REVIEW_20261016.md)."""
import importlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app as module
import test_site_management as base
from armodel.repositories import database as database_repository
from scripts import import_admin_to_d1, prepare_cloud_d1


class ReviewFixTests(unittest.TestCase):
    setUp = base.SiteManagementTests.setUp
    tearDown = base.SiteManagementTests.tearDown
    sign_in = base.SiteManagementTests.sign_in
    login_post = base.SiteManagementTests.login_post

    def admin_account(self):
        return module.admin_users_repository.list_users(module.admin_db())

    # P0-1: browser first-run setup must not exist outside isolated tests.
    def test_first_run_setup_is_only_allowed_in_testing(self):
        self.assertTrue(module.first_run_setup_allowed())
        with patch.dict(module.app.config, {"TESTING": False}):
            self.assertFalse(module.first_run_setup_allowed())

    def test_missing_account_blocks_web_setup_when_not_allowed(self):
        with patch.object(module, "first_run_setup_allowed", return_value=False):
            page = self.client.get("/admin/login").get_data(as_text=True)
            self.assertIn("ระบบไม่เปิดให้ตั้งบัญชีครั้งแรกผ่านหน้าเว็บ", page)
            self.assertNotIn('name="confirm_password"', page)
            response = self.login_post({"username": "intruder", "password": "intruder-pass", "confirm_password": "intruder-pass"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.admin_account(), [])
        with self.client.session_transaction() as session:
            self.assertFalse(session.get("admin"))

    def test_cross_site_login_post_without_csrf_is_rejected(self):
        response = module.app.test_client().post(
            "/admin/login",
            data={"username": "intruder", "password": "intruder-pass", "confirm_password": "intruder-pass"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.admin_account(), [])

    def test_login_form_carries_csrf_token_and_rotates_it_after_login(self):
        module.save_admin_password("review-password", "curator")
        page = self.client.get("/admin/login").get_data(as_text=True)
        self.assertIn('name="csrf_token"', page)
        with self.client.session_transaction() as session:
            before = session["csrf_token"]
        with patch.object(module, "write_audit_event"):
            response = self.login_post({"username": "curator", "password": "review-password"})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(session["admin"])
            self.assertNotEqual(session.get("csrf_token"), before)

    # P2-4: tests must not inherit cloud credentials from the environment or .env.
    def test_testing_mode_ignores_d1_environment_credentials(self):
        cloud_env = {"D1_ACCOUNT_ID": "a" * 32, "D1_DATABASE_ID": "b" * 8 + "-" + "c" * 27,
                     "D1_API_TOKEN": "not-a-real-token", "D1_GATEWAY_URL": "https://gateway.example"}
        with patch.dict(module.os.environ, cloud_env):
            database = module.get_database()
            self.assertEqual(database.api_url, "")
            self.assertEqual(database.gateway_url, "")
            self.assertIsNotNone(database.local_path)
            self.assertFalse(module.d1_configured())

    # R1: a public page reads all content tables in one round trip.
    def test_public_page_reads_content_in_one_round_trip(self):
        calls = []
        original = database_repository.Database.batch

        def counting(database, statements):
            calls.append([sql.split()[0:4] for sql, _ in statements])
            return original(database, statements)

        with patch.object(module, "analytics_tracking_enabled", return_value=False), \
                patch.object(database_repository.Database, "batch", counting):
            for path in ("/home", "/models"):
                calls.clear()
                self.assertEqual(self.client.get(path).status_code, 200)
                self.assertEqual(len(calls), 1, (path, calls))

    def test_page_view_write_uses_short_timeout(self):
        with patch.object(module, "analytics_tracking_enabled", return_value=True), \
                patch.object(database_repository.Database, "append_event") as append:
            self.assertEqual(self.client.get("/home").status_code, 200)
        self.assertEqual(append.call_args.kwargs["timeout"], module.ANALYTICS_WRITE_TIMEOUT_SECONDS)
        seen = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(_request, timeout):
            seen["timeout"] = timeout
            return Response(b'{"success": true, "result": [{"success": true, "results": []}]}')

        database = database_repository.Database(account_id="a" * 32, database_id="b" * 8 + "-" + "c" * 27,
                                                api_token="test", opener=opener)
        database.append_event("analytics", {"timestamp": "2026-10-16T00:00:00+00:00"}, timeout=3)
        self.assertEqual(seen["timeout"], 3)

    def test_read_many_matches_individual_reads(self):
        database = module.get_database()
        combined = database.read_many(["projects", "models", "site_settings", "slider_items"])
        for name, value in combined.items():
            self.assertEqual(value, database.read(name))

    # P2-3: an Admin save without the rendered revision cannot blindly overwrite newer data.
    def test_admin_save_without_revision_is_rejected(self):
        self.sign_in()
        project = module.load_projects(include_hidden=True)[0]
        response = self.client.post(f"/admin/projects/{project['id']}/edit",
                                    data={"name": "blind overwrite"}, omit_revisions=True)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("blind overwrite", [item["name"] for item in module.load_projects(True)])

    def test_admin_save_with_stale_revision_is_rejected_and_current_one_saves(self):
        self.sign_in()
        project = module.load_projects(include_hidden=True)[0]
        stale = module.get_database().read("projects")[1]
        module.save_projects(module.load_projects(include_hidden=True))  # someone else saves first
        response = self.client.post(f"/admin/projects/{project['id']}/edit",
                                    data={"name": "stale edit", "revision_projects": str(stale)})
        self.assertEqual(response.status_code, 409)
        response = self.client.post(f"/admin/projects/{project['id']}/edit", data={"name": "fresh edit"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("fresh edit", [item["name"] for item in module.load_projects(True)])

    def test_rendered_admin_forms_carry_every_dataset_revision(self):
        self.sign_in()
        html = self.client.get("/admin").get_data(as_text=True)
        for name in database_repository.COLLECTIONS:
            self.assertIn(f'name="revision_{name}"', html)

    # Staging review copy: never indexed, no visible banner; production output unchanged.
    def test_staging_mode_blocks_indexing_without_banner(self):
        with patch.dict(module.os.environ, {"ARMODEL_STAGING": "1"}):
            home = self.client.get("/home")
            robots = self.client.get("/robots.txt").get_data(as_text=True)
        html = home.get_data(as_text=True)
        self.assertEqual(home.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn('content="noindex, nofollow"', html)
        self.assertNotIn("staging-banner", html)
        self.assertNotIn("เว็บไซต์ทดสอบสำหรับทีมงานตรวจ", html)
        self.assertEqual(robots, "User-agent: *\nDisallow: /\n")
        with patch.dict(module.os.environ, {"ARMODEL_STAGING": ""}):
            normal = self.client.get("/home")
            self.assertNotIn("staging-banner", normal.get_data(as_text=True))
            self.assertNotIn("X-Robots-Tag", normal.headers)
            self.assertIn("Sitemap:", self.client.get("/robots.txt").get_data(as_text=True))

    # P3: a database failure while preparing an admin form returns 503, not a bare 500.
    def test_admin_form_revision_lookup_failure_returns_503(self):
        self.sign_in()
        self.assertEqual(self.client.get("/admin").status_code, 200)
        original = database_repository.Database.batch

        def fail_versions(database, statements):
            if statements and statements[0][0].startswith("SELECT name,version FROM dataset_versions"):
                raise database_repository.DatabaseError("unavailable")
            return original(database, statements)

        with patch.object(database_repository.Database, "batch", fail_versions):
            response = self.client.get("/admin")
        self.assertEqual(response.status_code, 503)

    # P2-2: a committed narration is reported as saved; old permanent audio stays in R2.
    def test_narration_confirm_cleanup_failure_still_reports_saved(self):
        self.sign_in()
        models = module.load_models(include_hidden=True)
        model_id = models[0]["id"]
        with patch.dict(module.os.environ, {"NARRATION_PREVIEW_MOCK": "1"}, clear=False):
            response = self.client.post(f"/admin/narrations/{model_id}/draft")
        token = response.headers["Location"].split("draft=", 1)[1].split("&", 1)[0]
        with (
            patch.object(module, "save_generated_narration_audio", return_value="audio/confirmed.wav"),
            patch.object(module, "delete_pending_narration_audio", side_effect=module.NarrationDraftError("R2 down")),
            patch.object(module, "r2_delete_object") as r2_delete,
        ):
            confirmed = self.client.post(f"/admin/narrations/drafts/{token}/confirm", follow_redirects=True)
        page = confirmed.get_data(as_text=True)
        self.assertIn("ยืนยันและบันทึกเสียงบรรยายแล้ว", page)
        self.assertNotIn("ข้อมูลเดิมยังไม่ถูกแทนที่", page)
        r2_delete.assert_not_called()
        saved = next(item for item in module.load_models(True) if item["id"] == model_id)
        self.assertEqual(saved["narration_audio"], "audio/confirmed.wav")


class ResponsiveCssTests(unittest.TestCase):
    css = (Path(module.BASE_DIR) / "static" / "css" / "style.css").read_text(encoding="utf-8")

    def media_block(self, query, marker):
        start = self.css.index(marker)
        opening = self.css.rindex(f"@media ({query})", 0, start)
        return self.css[opening:start + 400]

    def test_mobile_header_clamps_long_site_name(self):
        block = self.media_block("max-width: 768px", ".site-nav .brand-mark strong")
        self.assertIn("-webkit-line-clamp: 2", block)
        self.assertIn(".site-nav .brand-mark small", block)

    def test_mobile_ar_guide_is_ordered_after_viewer(self):
        block = self.media_block("max-width: 920px", ".viewer-stage > .viewer-instructions")
        self.assertRegex(block, r"\.viewer-stage > \.viewer-instructions \{\s*order: 7;")

    def test_desktop_hover_media_query_is_untouched(self):
        self.assertIn("@media (hover: hover) and (pointer: fine) and (min-width: 921px)", self.css)


class ToolingFixTests(unittest.TestCase):
    def test_cloud_review_runner_disables_analytics(self):
        with patch.dict(module.os.environ, {"ARMODEL_ANALYTICS_ENABLED": "1"}):
            sys.modules.pop("scripts.run_cloud_d1_review", None)
            importlib.import_module("scripts.run_cloud_d1_review")
            self.assertFalse(module.analytics_tracking_enabled())
        sys.modules.pop("scripts.run_cloud_d1_review", None)

    def sqlite(self, name="admin.sqlite3"):
        import tempfile
        directory = tempfile.mkdtemp()
        return database_repository.Database(local_path=Path(directory) / name)

    def test_admin_import_requires_explicit_valid_username(self):
        database = self.sqlite()
        hash_value = module.generate_password_hash("existing-password")
        for username in ("", "x", "has space"):
            with self.subTest(username=username), self.assertRaises(ValueError):
                import_admin_to_d1.import_admin(database, username, hash_value)
        self.assertIsNone(module.admin_users_repository.owner(database))

    def test_admin_import_cloud_option_refuses_existing_account(self):
        database = self.sqlite()
        import_admin_to_d1.import_admin(database, "someone", module.generate_password_hash("x" * 12))
        with patch.dict(module.os.environ, {"ADMIN_PASSWORD_HASH": module.generate_password_hash("y" * 12)}),                 patch.object(prepare_cloud_d1, "cloud_database", return_value=database):
            with self.assertRaises(ValueError):
                import_admin_to_d1.main(["--cloud", "--username", "curator"])
        self.assertEqual(module.admin_users_repository.owner(database)["username"], "someone")

    def test_admin_replace_requires_current_username(self):
        database = self.sqlite()
        owner = module.admin_users_repository.owner
        old_hash = module.generate_password_hash("old-password-123")
        new_hash = module.generate_password_hash("new-password-456")
        import_admin_to_d1.import_admin(database, "test1234", old_hash)
        first_id = owner(database)["id"]
        for wrong in ("", "someone-else"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                import_admin_to_d1.import_admin(database, "team-review", new_hash, wrong)
        self.assertEqual(owner(database)["username"], "test1234")
        import_admin_to_d1.import_admin(database, "team-review", new_hash, "test1234")
        account = owner(database)
        self.assertEqual((account["username"], account["id"], account["session_version"]), ("team-review", first_id, 2))
        self.assertTrue(module.check_password_hash(account["password_hash"], "new-password-456"))
        with self.assertRaises(ValueError):
            import_admin_to_d1.import_admin(self.sqlite("empty.sqlite3"), "team-review", new_hash, "test1234")

    def test_migration_0002_is_additive_and_promotes_legacy_account_to_owner(self):
        import contextlib
        import sqlite3
        from scripts import apply_d1_migrations
        database = self.sqlite("legacy.sqlite3")
        path = database.local_path
        connection = sqlite3.connect(path)  # a database created before 0002 existed
        connection.executescript(database_repository.SCHEMA.read_text(encoding="utf-8"))
        connection.execute("INSERT INTO admin_accounts(id,username,password_hash) VALUES (1,'test1234',?)",
                           [module.generate_password_hash("legacy-password")])
        connection.commit()
        connection.close()
        legacy = database_repository.Database(local_path=path)
        legacy_batch = legacy.batch

        def without_auto_migrations(statements, *args, **kwargs):
            raw = sqlite3.connect(path)
            raw.row_factory = sqlite3.Row
            try:
                results = []
                for sql, params in statements:
                    cursor = raw.execute(sql, params)
                    results.append([dict(row) for row in cursor.fetchall()] if cursor.description else [])
                raw.commit()
                return results
            finally:
                raw.close()

        legacy.batch = without_auto_migrations
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIn("admin_users", apply_d1_migrations.main([], database=legacy))  # dry run writes nothing
            self.assertIn("admin_users", apply_d1_migrations.table_report(legacy))
            self.assertEqual(apply_d1_migrations.main(["--apply"], database=legacy), [])
            apply_d1_migrations.main(["--apply"], database=legacy)  # idempotent
        legacy.batch = legacy_batch
        owner = module.admin_users_repository.owner(legacy)
        self.assertEqual((owner["username"], owner["role"]), ("test1234", "owner"))
        self.assertTrue(module.admin_users_repository.authenticate(legacy, "test1234", "legacy-password"))
        self.assertEqual(len(module.admin_users_repository.list_users(legacy)), 1)
        self.assertEqual(legacy.read("admin_accounts")[0]["admin_username"], "test1234")  # legacy row kept

    def test_model_description_plan_changes_only_descriptions(self):
        import contextlib
        from scripts import apply_model_descriptions as amd
        from scripts.migrate_to_d1 import import_snapshot
        database = self.sqlite("descriptions.sqlite3")
        import_snapshot(database, Path(module.BASE_DIR) / "data")
        before, _ = database.read("models")
        with contextlib.redirect_stdout(io.StringIO()):
            expected = amd.main(["--apply"], database=database)
            amd.main(["--apply"], database=database)  # second run must not append twice
        after, _ = database.read("models")
        self.assertEqual(amd.verify(before, after, expected), [])
        by_name = {model["name"]: model for model in after}
        self.assertIn("ขอบคุณภาพจาก", by_name["สุกรภูพาน"]["description"])  # image credit kept
        self.assertEqual(by_name["เห็ดนางฟ้า"]["description"].count("หนึ่งในเห็ด 14 ชนิด"), 1)
        untouched = [m for m in before if m["id"] not in expected]
        self.assertTrue(any(m["name"].startswith("ไก่ดำภูพาน3") for m in untouched))
        tampered = [dict(m) for m in after]
        tampered[0]["scale"] = 9.9
        self.assertTrue(amd.verify(before, tampered, expected))
        with self.assertRaises(SystemExit):
            amd.build(before, {"replace": {"ไก่ดำภูพาน4 /สีหวายดำ": "x"}})

    def test_make_admin_hash_writes_private_file_without_printing_secrets(self):
        import contextlib
        import json
        import tempfile
        from scripts import make_admin_hash
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "account.json"
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                make_admin_hash.main(["--username", "team-review", "--out", str(out)],
                                     prompt=lambda _label: "a-long-team-password")
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["admin_username"], "team-review")
            self.assertTrue(module.check_password_hash(saved["admin_password_hash"], "a-long-team-password"))
            self.assertNotIn("a-long-team-password", printed.getvalue())
            self.assertNotIn(saved["admin_password_hash"], printed.getvalue())
        with self.assertRaises(SystemExit):  # never inside the repository
            make_admin_hash.main(["--username", "team-review", "--out", str(Path(module.BASE_DIR) / "x.json")],
                                 prompt=lambda _label: "a-long-team-password")

    def test_admin_import_rejects_remote_gateway(self):
        with self.assertRaises(SystemExit):
            import_admin_to_d1.main(["--gateway", "https://gateway.example", "--username", "curator"])

    def test_prepare_initializes_existing_target_without_schema(self):
        database = Mock()
        database.batch.side_effect = [[[]], [[]] * len(prepare_cloud_d1.schema_statements())]
        target = {"name": "armodel-production", "uuid": "c" * 8 + "-" + "d" * 27}
        with (
            patch.object(prepare_cloud_d1, "stored_token", return_value="cfat_test"),
            patch.object(prepare_cloud_d1, "api", return_value=[target]),
            patch.object(prepare_cloud_d1, "Database", return_value=database),
            patch.object(prepare_cloud_d1.Path, "home", return_value=Path(self.id_dir())),
            patch.object(sys, "argv", ["prepare", "--account", "a" * 32]),
        ):
            prepare_cloud_d1.main()
        self.assertEqual(database.batch.call_count, 2)
        self.assertEqual(database.batch.call_args_list[1].args[0], prepare_cloud_d1.schema_statements())

    def test_prepare_never_reinitializes_existing_schema(self):
        database = Mock()
        database.batch.return_value = [[{"name": "dataset_versions"}]]
        target = {"name": "armodel-production", "uuid": "c" * 8 + "-" + "d" * 27}
        with (
            patch.object(prepare_cloud_d1, "stored_token", return_value="cfat_test"),
            patch.object(prepare_cloud_d1, "api", return_value=[target]),
            patch.object(prepare_cloud_d1, "Database", return_value=database),
            patch.object(prepare_cloud_d1.Path, "home", return_value=Path(self.id_dir())),
            patch.object(sys, "argv", ["prepare", "--account", "a" * 32]),
        ):
            prepare_cloud_d1.main()
        self.assertEqual(database.batch.call_count, 1)

    def test_export_round_trips_snapshot_without_admin_hash(self):
        import json
        import tempfile
        from scripts import export_d1_snapshot
        from scripts.migrate_to_d1 import import_snapshot
        root = Path(module.BASE_DIR)
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "export.sqlite3"
            database = database_repository.Database(local_path=database_path)
            import_snapshot(database, root / "data")
            database.save("admin_accounts", {"admin_username": "curator",
                                             "admin_password_hash": module.generate_password_hash("x" * 12)})
            out = Path(directory) / "export"
            export_d1_snapshot.main(["--local-path", str(database_path), "--out", str(out)])
            for name in ("projects", "models", "site_settings", "slider_items"):
                source = json.loads((root / "data" / f"{name}.json").read_text(encoding="utf-8"))
                exported = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
                if isinstance(source, dict):
                    self.assertEqual(exported, source)
                else:
                    self.assertEqual([item["id"] for item in exported], [item["id"] for item in source])
                    for before, after in zip(source, exported):
                        self.assertEqual({key: after[key] for key in before}, before)
            everything = "".join(path.read_text(encoding="utf-8") for path in out.rglob("*.json"))
            self.assertNotIn("password_hash", everything)
            self.assertNotIn("scrypt:", everything)
            with self.assertRaises(SystemExit):  # never into a non-empty folder
                export_d1_snapshot.main(["--local-path", str(database_path), "--out", str(out)])
        with self.assertRaises(SystemExit):  # never into data/
            export_d1_snapshot.main(["--local-path", "unused.sqlite3", "--out", str(root / "data" / "x")])

    def id_dir(self):
        import tempfile
        directory = tempfile.mkdtemp()
        (Path(directory) / ".armodel-secrets").mkdir()
        return directory


if __name__ == "__main__":
    unittest.main()
