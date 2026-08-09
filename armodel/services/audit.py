"""Tamper-evident audit event construction and local immutable storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote


SIGNATURE_VERSION = "hmac-sha256-v1"
REDACTED = "[ปกปิด]"
SENSITIVE_WORDS = (
    "password", "token", "secret", "authorization", "cookie", "api_key",
    "api-key", "apikey", "credential", "signature",
)


def redact(value):
    if isinstance(value, dict):
        return {
            str(key): REDACTED if any(word in str(key).lower() for word in SENSITIVE_WORDS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return {"kind": "binary", "byte_size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    return value


def browser_summary(user_agent: str) -> str:
    ua = user_agent.lower()
    browser = "Chrome" if "chrome/" in ua and "edg/" not in ua else "Edge" if "edg/" in ua else "Firefox" if "firefox/" in ua else "Safari" if "safari/" in ua else "ไม่ทราบเบราว์เซอร์"
    os_name = "iPhone" if "iphone" in ua else "Android" if "android" in ua else "Windows" if "windows" in ua else "macOS" if "mac os" in ua else "Linux" if "linux" in ua else ""
    return f"{browser} บน {os_name}".strip() if os_name else browser


def request_context(*, trusted_vercel: bool, remote_addr: str, headers) -> dict:
    forwarded = headers.get("x-vercel-forwarded-for", "") if trusted_vercel else remote_addr
    ip = str(forwarded or "").split(",")[0].strip()
    city = headers.get("x-vercel-ip-city", "") if trusted_vercel else ""
    user_agent = headers.get("User-Agent", "")
    return {
        "source_ip": ip or "ไม่ทราบ IP",
        "country": headers.get("x-vercel-ip-country", "") if trusted_vercel else "",
        "region": headers.get("x-vercel-ip-country-region", "") if trusted_vercel else "",
        "city": unquote(city) if city else "",
        "location_source": "Vercel headers" if trusted_vercel else "ไม่ทราบตำแหน่งโดยประมาณ",
        "user_agent": user_agent,
        "browser_summary": browser_summary(user_agent),
    }


def changes(before: dict, after: dict, labels: dict[str, str] | None = None) -> list[dict]:
    labels = labels or {}
    return [
        {"field": key, "label_th": labels.get(key, key), "before": redact(before.get(key)), "after": redact(after.get(key))}
        for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)
    ]


def canonical_bytes(event: dict) -> bytes:
    unsigned = dict(event)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_event(event: dict, signing_key: bytes) -> dict:
    signed = dict(event)
    signed["signature"] = hmac.new(signing_key, canonical_bytes(signed), hashlib.sha256).hexdigest()
    return signed


def verify_event(event: dict, signing_key: bytes) -> bool:
    signature = str(event.get("signature") or "")
    expected = hmac.new(signing_key, canonical_bytes(event), hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(signature, expected)


def build_event(
    category: str, action: str, outcome: str, summary_th: str, *,
    context: dict, admin_session_id: str, request_id: str, request_method: str,
    request_path: str, resource_type: str = "", resource_id: str = "",
    resource_name: str = "", changes_value=None, metadata=None,
    severity: str = "info", now: datetime | None = None, event_id: str | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    return {
        "event_id": event_id or uuid.uuid4().hex,
        "timestamp_utc": now.isoformat(),
        "timestamp_local": now.astimezone(timezone(timedelta(hours=7))).isoformat(),
        "event_type": f"{category}.{action}", "category": category, "action": action,
        "outcome": outcome, "severity": severity, "actor": "ผู้ดูแลระบบ",
        "admin_session_id": admin_session_id, "request_id": request_id,
        "request_method": request_method, "request_path": sanitize_request_path(request_path),
        "resource_type": resource_type, "resource_id": resource_id,
        "resource_name": resource_name, "summary_th": summary_th,
        "changes": redact(changes_value or []), "metadata": redact(metadata or {}),
        "signature_version": SIGNATURE_VERSION, **context,
    }


def sanitize_request_path(path: str) -> str:
    return re.sub(
        r"(/admin/narrations/drafts/)[^/]+(?=/|$)",
        rf"\1{REDACTED}",
        str(path or ""),
    )


def object_key(event: dict, prefix: str) -> str:
    now = datetime.fromisoformat(str(event["timestamp_utc"]).replace("Z", "+00:00"))
    return f"{prefix}{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%S.%fZ}-{event['event_id']}.json"


def serialize(event: dict) -> bytes:
    return json.dumps(event, ensure_ascii=False, indent=2).encode("utf-8")


def write_local(root: Path, key: str, data: bytes) -> Path:
    target = root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def list_local(root: Path, limit: int) -> list[dict]:
    events = []
    if root.exists():
        for path in sorted(root.rglob("*.json"), reverse=True)[:limit]:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    events.append(value)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
    return events
