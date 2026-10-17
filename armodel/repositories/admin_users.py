"""Administrator accounts, roles, and one-time invite/reset links stored in D1.

Only SHA-256 hashes of link tokens are stored. Every change is a single bound batch whose
WHERE clauses make it safe against double use and concurrent edits.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .database import DatabaseError

ROLES = ("owner", "admin", "editor", "reviewer")
INVITABLE_ROLES = ("admin", "editor", "reviewer")
ROLE_LABELS = {"owner": "เจ้าของ", "admin": "ผู้ดูแล", "editor": "ผู้แก้ไขเนื้อหา", "reviewer": "ผู้ตรวจ"}
USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,64}")
MIN_PASSWORD_LENGTH = 12
LINK_LIFETIME = timedelta(hours=48)
# Checked when the username is unknown so failed logins take the same time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")
USER_COLUMNS = "id,username,display_name,password_hash,role,active,session_version,invited_by,created_at,updated_at"


class AccountError(ValueError):
    """A user-facing validation problem (message is safe to show)."""


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_credentials(username: str, password: str, confirm: str) -> None:
    if not USERNAME.fullmatch(username or ""):
        raise AccountError("ชื่อผู้ใช้ต้องมี 3–64 ตัวอักษร ใช้อักษรอังกฤษ ตัวเลข จุด ขีดกลาง หรือขีดล่าง")
    validate_password(password, confirm)


def validate_password(password: str, confirm: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(f"รหัสผ่านต้องมีอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร")
    if password != confirm:
        raise AccountError("รหัสผ่านยืนยันไม่ตรงกัน")


def _user(row: dict | None) -> dict | None:
    if not row:
        return None
    user = dict(row)
    user["active"] = bool(user["active"])
    user["role_label"] = ROLE_LABELS.get(user["role"], user["role"])
    return user


def get_user(db, user_id: str) -> dict | None:
    rows = db.batch([(f"SELECT {USER_COLUMNS} FROM admin_users WHERE id=?", [user_id])])[0]
    return _user(rows[0] if rows else None)


def list_users(db) -> list[dict]:
    rows = db.batch([(f"SELECT {USER_COLUMNS} FROM admin_users ORDER BY CASE role WHEN 'owner' THEN 0 "
                      "WHEN 'admin' THEN 1 WHEN 'editor' THEN 2 ELSE 3 END, username", [])])[0]
    return [_user(row) for row in rows]


def has_users(db) -> bool:
    return bool(db.batch([("SELECT 1 AS present FROM admin_users LIMIT 1", [])])[0])


def owner(db) -> dict | None:
    rows = db.batch([(f"SELECT {USER_COLUMNS} FROM admin_users WHERE role='owner'", [])])[0]
    return _user(rows[0] if rows else None)


def authenticate(db, username: str, password: str) -> dict | None:
    rows = db.batch([(f"SELECT {USER_COLUMNS} FROM admin_users WHERE username=? COLLATE NOCASE", [username or ""])])[0]
    user = _user(rows[0] if rows else None)
    valid = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password or "")
    if not user or not valid or not user["active"]:
        return None
    return user


def create_owner(db, username: str, password_hash: str, now: datetime | None = None,
                 replace_username: str = "") -> dict:
    """Create the single owner, or replace it only when its current username is named."""
    if not USERNAME.fullmatch(username or ""):
        raise AccountError("ชื่อผู้ใช้ไม่ถูกต้อง")
    if not password_hash.startswith(("scrypt:", "pbkdf2:")) or "$" not in password_hash:
        raise AccountError("ต้องใช้ password hash ของ Werkzeug")
    current = owner(db)
    if current and not replace_username:
        raise AccountError("มีเจ้าของระบบอยู่แล้ว")
    if current and current["username"] != replace_username:
        raise AccountError("ชื่อเจ้าของเดิมไม่ตรงกับที่ระบุ")
    if not current and replace_username:
        raise AccountError("ยังไม่มีเจ้าของระบบให้แทนที่")
    stamp = now_iso(now)
    if current:
        # Same row id keeps audit history linked; bumping the version ends the old owner's sessions.
        db.batch([("UPDATE admin_users SET username=?,display_name=?,password_hash=?,active=1,"
                   "session_version=session_version+1,updated_at=? WHERE id=? AND role='owner'",
                   [username, username, password_hash, stamp, current["id"]])])
        return get_user(db, current["id"])
    user_id = uuid.uuid4().hex
    db.batch([(f"INSERT INTO admin_users({USER_COLUMNS}) VALUES (?,?,?,?,'owner',1,1,'',?,?)",
               [user_id, username, username, password_hash, stamp, stamp])])
    return get_user(db, user_id)


def create_link(db, *, kind: str, created_by: str, role: str = "", user_id: str = "", note: str = "",
                now: datetime | None = None) -> str:
    """Return a new one-time token; only its hash is stored."""
    if kind == "invite" and role not in INVITABLE_ROLES:
        raise AccountError("สิทธิ์ที่เชิญไม่ถูกต้อง")
    if kind == "reset":
        target = get_user(db, user_id)
        if not target or target["role"] == "owner":
            raise AccountError("สร้างลิงก์รีเซ็ตให้ผู้ใช้นี้ไม่ได้")
        role = ""
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.batch([("INSERT INTO admin_invites(token_hash,kind,role,user_id,note,created_by,created_at,expires_at) "
               "VALUES (?,?,?,?,?,?,?,?)",
               [token_hash(token), kind, role, user_id, (note or "")[:120], created_by, now_iso(now),
                now_iso(now + LINK_LIFETIME)])])
    return token


def open_link(db, token: str, kind: str, now: datetime | None = None) -> dict | None:
    rows = db.batch([("SELECT token_hash,kind,role,user_id,note,created_by,expires_at FROM admin_invites "
                      "WHERE token_hash=? AND kind=? AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?",
                      [token_hash(token or ""), kind, now_iso(now)])])[0]
    return rows[0] if rows else None


def list_open_links(db, now: datetime | None = None) -> list[dict]:
    return db.batch([("SELECT i.token_hash,i.kind,i.role,i.user_id,i.note,i.created_at,i.expires_at,"
                      "u.username AS target_username FROM admin_invites i LEFT JOIN admin_users u ON u.id=i.user_id "
                      "WHERE i.used_at IS NULL AND i.revoked_at IS NULL AND i.expires_at>? ORDER BY i.created_at DESC",
                      [now_iso(now)])])[0]


def revoke_link(db, link_hash: str, now: datetime | None = None) -> bool:
    db.batch([("UPDATE admin_invites SET revoked_at=? WHERE token_hash=? AND used_at IS NULL AND revoked_at IS NULL",
               [now_iso(now), link_hash])])
    rows = db.batch([("SELECT revoked_at FROM admin_invites WHERE token_hash=?", [link_hash])])[0]
    return bool(rows and rows[0]["revoked_at"])


def accept_invite(db, token: str, username: str, display_name: str, password: str, confirm: str,
                  now: datetime | None = None) -> dict:
    validate_credentials(username, password, confirm)
    stamp = now_iso(now)
    user_id = uuid.uuid4().hex
    link = token_hash(token or "")
    try:
        # Claim the link and create the user in one transaction; a used/expired link inserts nothing.
        db.batch([
            ("UPDATE admin_invites SET used_at=?,used_by=? WHERE token_hash=? AND kind='invite' "
             "AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?", [stamp, user_id, link, stamp]),
            (f"INSERT INTO admin_users({USER_COLUMNS}) SELECT ?,?,?,?,role,1,1,created_by,?,? "
             "FROM admin_invites WHERE token_hash=? AND used_by=?",
             [user_id, username, (display_name or username)[:80], generate_password_hash(password),
              stamp, stamp, link, user_id]),
        ])
    except DatabaseError as exc:
        if "UNIQUE" in str(exc).upper() or "constraint" in str(exc).lower():
            raise AccountError("ชื่อผู้ใช้นี้ถูกใช้แล้ว") from exc
        raise
    user = get_user(db, user_id)
    if not user:
        raise AccountError("ลิงก์เชิญหมดอายุหรือถูกใช้ไปแล้ว")
    return user


def accept_reset(db, token: str, password: str, confirm: str, now: datetime | None = None) -> dict:
    validate_password(password, confirm)
    stamp = now_iso(now)
    marker = uuid.uuid4().hex
    link = token_hash(token or "")
    db.batch([
        ("UPDATE admin_invites SET used_at=?,used_by=? WHERE token_hash=? AND kind='reset' "
         "AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?", [stamp, marker, link, stamp]),
        ("UPDATE admin_users SET password_hash=?,session_version=session_version+1,updated_at=? "
         "WHERE role<>'owner' AND id=(SELECT user_id FROM admin_invites WHERE token_hash=? AND used_by=?)",
         [generate_password_hash(password), stamp, link, marker]),
    ])
    rows = db.batch([("SELECT user_id FROM admin_invites WHERE token_hash=? AND used_by=?", [link, marker])])[0]
    if not rows:
        raise AccountError("ลิงก์รีเซ็ตหมดอายุหรือถูกใช้ไปแล้ว")
    return get_user(db, rows[0]["user_id"])


def update_user(db, user_id: str, *, role: str | None = None, active: bool | None = None,
                now: datetime | None = None) -> dict:
    target = get_user(db, user_id)
    if not target:
        raise AccountError("ไม่พบผู้ใช้")
    if target["role"] == "owner":
        raise AccountError("แก้สิทธิ์หรือระงับเจ้าของระบบผ่านหน้านี้ไม่ได้")
    if role is not None and role not in INVITABLE_ROLES:
        raise AccountError("สิทธิ์ไม่ถูกต้อง")
    new_role = role or target["role"]
    new_active = target["active"] if active is None else bool(active)
    bump = 1 if (new_active != target["active"]) else 0
    db.batch([("UPDATE admin_users SET role=?,active=?,session_version=session_version+?,updated_at=? "
               "WHERE id=? AND role<>'owner'", [new_role, int(new_active), bump, now_iso(now), user_id])])
    return get_user(db, user_id)
