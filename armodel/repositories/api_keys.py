"""Admin-managed provider API keys (Gemini text-to-speech) stored encrypted in D1.

The plaintext key never leaves this module except to call the provider: it is encrypted with
AES-GCM (secret from API_KEYS_SECRET, falling back to SECRET_KEY) before storage, only the last
4 characters are kept readable, and duplicates are detected with a keyed fingerprint.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROVIDER = "gemini"
KEY_PATTERN = re.compile(r"[A-Za-z0-9_\-.]{20,200}")
MAX_KEYS_PER_IMPORT = 50
QUOTA_COOLDOWN = timedelta(hours=1)
LIST_COLUMNS = ("id,provider,label,hint,status,last_error,cooldown_until,last_used_at,last_checked_at,"
                "use_count,failure_count,created_by,created_at")
STATUS_LABELS = {"unknown": "ยังไม่ได้ทดสอบ", "ok": "ใช้งานได้", "invalid": "คีย์ใช้ไม่ได้", "quota": "โควตาเต็ม (พักไว้)"}


class ApiKeyError(ValueError):
    """User-facing validation problem (message is safe to show)."""


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _secret(secret: str) -> bytes:
    if not secret:
        raise ApiKeyError("ยังไม่ได้ตั้งค่า API_KEYS_SECRET หรือ SECRET_KEY จึงเก็บคีย์อย่างปลอดภัยไม่ได้")
    return hashlib.sha256(("armodel-api-keys-v1:" + secret).encode("utf-8")).digest()


def fingerprint(api_key: str, secret: str) -> str:
    return hmac.new(_secret(secret), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def encrypt(api_key: str, secret: str, key_id: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_secret(secret)).encrypt(nonce, api_key.encode("utf-8"), key_id.encode("utf-8"))
    return base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(ciphertext: str, secret: str, key_id: str) -> str | None:
    """None when the key was stored with another secret (e.g. by a different site)."""
    try:
        raw = base64.b64decode(ciphertext)
        return AESGCM(_secret(secret)).decrypt(raw[:12], raw[12:], key_id.encode("utf-8")).decode("utf-8")
    except (InvalidTag, ValueError):
        return None


def hint(api_key: str) -> str:
    return "••••" + api_key[-4:]


def parse_keys(raw_text: str) -> tuple[list[str], int]:
    """One key per line (blank lines and spaces ignored). Returns (unique valid keys, invalid count)."""
    keys, invalid, seen = [], 0, set()
    for line in (raw_text or "").replace(",", "\n").splitlines():
        value = line.strip().strip('"').strip("'")
        if not value:
            continue
        if not KEY_PATTERN.fullmatch(value):
            invalid += 1
            continue
        if value not in seen:
            seen.add(value)
            keys.append(value)
    if len(keys) > MAX_KEYS_PER_IMPORT:
        raise ApiKeyError(f"นำเข้าได้ครั้งละไม่เกิน {MAX_KEYS_PER_IMPORT} คีย์")
    return keys, invalid


def add_keys(db, raw_text: str, label: str, actor: str, secret: str, *, now: datetime | None = None) -> dict:
    keys, invalid = parse_keys(raw_text)
    if not keys and not invalid:
        raise ApiKeyError("กรุณาวางคีย์อย่างน้อย 1 คีย์")
    label = (label or "").strip()[:80]
    stamp = now_iso(now)
    existing = {row["fingerprint"] for row in db.batch([("SELECT fingerprint FROM api_keys", [])])[0]}
    statements, added, duplicates = [], [], 0
    for value in keys:
        fp = fingerprint(value, secret)
        if fp in existing:
            duplicates += 1
            continue
        existing.add(fp)
        key_id = uuid.uuid4().hex
        statements.append((
            "INSERT OR IGNORE INTO api_keys(id,provider,label,fingerprint,hint,ciphertext,status,created_by,created_at) "
            "VALUES (?,?,?,?,?,?,'unknown',?,?)",
            [key_id, PROVIDER, label, fp, hint(value), encrypt(value, secret, key_id), actor or "", stamp]))
        added.append(key_id)
    if statements:
        db.batch(statements)
    return {"added": added, "duplicates": duplicates, "invalid": invalid}


def _row(row: dict, secret: str | None = None, ciphertext: str | None = None) -> dict:
    item = dict(row)
    item["status_label"] = STATUS_LABELS.get(item.get("status"), item.get("status"))
    if secret is not None and ciphertext is not None:
        item["readable"] = decrypt(ciphertext, secret, item["id"]) is not None
    return item


def list_keys(db, secret: str) -> list[dict]:
    rows = db.batch([(f"SELECT {LIST_COLUMNS},ciphertext FROM api_keys WHERE provider=? ORDER BY created_at, id",
                      [PROVIDER])])[0]
    return [_row({k: v for k, v in r.items() if k != "ciphertext"}, secret, r["ciphertext"]) for r in rows]


def count_keys(db) -> int:
    rows = db.batch([("SELECT COUNT(*) AS n FROM api_keys WHERE provider=?", [PROVIDER])])[0]
    return int(rows[0]["n"]) if rows else 0


def get_plain(db, key_id: str, secret: str) -> tuple[dict, str | None] | None:
    rows = db.batch([(f"SELECT {LIST_COLUMNS},ciphertext FROM api_keys WHERE id=?", [key_id])])[0]
    if not rows:
        return None
    row = rows[0]
    return _row({k: v for k, v in row.items() if k != "ciphertext"}), decrypt(row["ciphertext"], secret, key_id)


def delete_key(db, key_id: str) -> dict | None:
    rows = db.batch([(f"SELECT {LIST_COLUMNS} FROM api_keys WHERE id=?", [key_id]),
                     ("DELETE FROM api_keys WHERE id=?", [key_id])])[0]
    return _row(rows[0]) if rows else None


def usable_keys(db, secret: str, *, now: datetime | None = None) -> list[tuple[str, str]]:
    """(id, plaintext) of keys worth trying now: not invalid, not cooling down after a quota error,
    readable with this site's secret. Least recently used first so traffic spreads across keys."""
    stamp = now_iso(now)
    rows = db.batch([(
        "SELECT id,ciphertext,last_used_at FROM api_keys WHERE provider=? AND status!='invalid' "
        "AND (cooldown_until='' OR cooldown_until<=?) ORDER BY last_used_at, created_at", [PROVIDER, stamp])])[0]
    keys = []
    for row in rows:
        plain = decrypt(row["ciphertext"], secret, row["id"])
        if plain:
            keys.append((row["id"], plain))
    return keys


def record_result(db, key_id: str, outcome: str, error: str = "", *, now: datetime | None = None,
                  cooldown: timedelta = QUOTA_COOLDOWN, used: bool = False) -> None:
    """outcome: ok / quota / invalid / error (transient: counted, status unchanged)."""
    current = now or datetime.now(timezone.utc)
    stamp = now_iso(current)
    error = sanitize_error(error)
    if outcome == "ok":
        sql = ("UPDATE api_keys SET status='ok', last_error='', cooldown_until='', last_checked_at=?"
               + (", last_used_at=?, use_count=use_count+1" if used else "") + " WHERE id=?")
        params = [stamp, stamp, key_id] if used else [stamp, key_id]
    elif outcome == "quota":
        sql = ("UPDATE api_keys SET status='quota', last_error=?, cooldown_until=?, last_checked_at=?, "
               "last_used_at=?, failure_count=failure_count+1 WHERE id=?")
        params = [error, now_iso(current + cooldown), stamp, stamp, key_id]
    elif outcome == "invalid":
        sql = ("UPDATE api_keys SET status='invalid', last_error=?, last_checked_at=?, "
               "failure_count=failure_count+1 WHERE id=?")
        params = [error, stamp, key_id]
    else:
        sql = "UPDATE api_keys SET last_error=?, last_checked_at=?, failure_count=failure_count+1 WHERE id=?"
        params = [error, stamp, key_id]
    db.batch([(sql, params)])


def sanitize_error(message: str) -> str:
    """Keep provider messages short and never echo anything that looks like a key."""
    text = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "[key]", str(message or ""))
    text = re.sub(r"key=[^&\s]+", "key=[key]", text)
    return text[:300]
