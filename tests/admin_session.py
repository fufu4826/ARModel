"""Sign a test client in as a real D1 admin user (the app re-reads the user every request)."""
import uuid

from werkzeug.security import generate_password_hash

import app as module
from armodel.repositories import admin_users

TEST_PASSWORD_HASH = generate_password_hash("test-owner-password")


def ensure_user(role="owner", username=None):
    db = module.admin_db()
    if role == "owner":
        return admin_users.owner(db) or admin_users.create_owner(db, username or "test-owner", TEST_PASSWORD_HASH)
    user_id = uuid.uuid4().hex
    stamp = admin_users.now_iso()
    db.batch([(f"INSERT INTO admin_users({admin_users.USER_COLUMNS}) VALUES (?,?,?,?,?,1,1,'',?,?)",
               [user_id, username or f"test-{role}-{user_id[:6]}", role, TEST_PASSWORD_HASH, role, stamp, stamp])])
    return admin_users.get_user(db, user_id)


def grant_admin_session(session, role="owner", username=None):
    user = ensure_user(role, username)
    session["admin"] = True
    session["admin_user_id"] = user["id"]
    session["admin_session_version"] = user["session_version"]
    session.setdefault("admin_session_id", uuid.uuid4().hex)
    return user
