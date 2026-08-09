from datetime import datetime, timezone

from armodel.services import audit


def base_event(**overrides):
    values = dict(
        category="model", action="edit", outcome="success", summary_th="แก้ไขโมเดล",
        context={"source_ip": "127.0.0.1", "country": "", "region": "", "city": "", "location_source": "ไม่ทราบตำแหน่งโดยประมาณ", "user_agent": "UA", "browser_summary": "ไม่ทราบเบราว์เซอร์"},
        admin_session_id="session", request_id="request", request_method="POST",
        request_path="/admin/models/x", now=datetime(2026, 8, 10, tzinfo=timezone.utc),
        event_id="event-id",
    )
    values.update(overrides)
    return audit.build_event(**values)


def test_recursive_redaction_preserves_safe_values():
    redacted = audit.redact({"name": "safe", "password": "bad", "nested": {"api_token": "bad", "Authorization": "bad"}, "cookie_value": "bad"})
    assert redacted["name"] == "safe"
    assert redacted["password"] == audit.REDACTED
    assert redacted["nested"]["api_token"] == audit.REDACTED
    assert redacted["nested"]["Authorization"] == audit.REDACTED
    assert redacted["cookie_value"] == audit.REDACTED


def test_signed_narration_token_is_redacted_from_request_path():
    value = base_event(request_path="/admin/narrations/drafts/secret-signed-token/confirm")
    assert value["request_path"] == f"/admin/narrations/drafts/{audit.REDACTED}/confirm"
    assert "secret-signed-token" not in audit.serialize(value).decode("utf-8")


def test_signatures_are_canonical_and_tamper_evident():
    key = b"test-signing-key"
    first = audit.sign_event(base_event(metadata={"b": 2, "a": 1}), key)
    second = audit.sign_event(base_event(metadata={"a": 1, "b": 2}), key)
    assert first["signature"] == second["signature"]
    assert audit.verify_event(first, key)
    first["summary_th"] = "แก้ไขแล้ว"
    assert not audit.verify_event(first, key)
    first["signature"] = "invalid"
    assert not audit.verify_event(first, key)


def test_request_context_trusts_only_vercel_headers_in_trusted_runtime():
    spoofed = {"x-vercel-forwarded-for": "203.0.113.10", "User-Agent": "Chrome/120 Windows"}
    local = audit.request_context(trusted_vercel=False, remote_addr="127.0.0.1", headers=spoofed)
    assert local["source_ip"] == "127.0.0.1"
    trusted = audit.request_context(trusted_vercel=True, remote_addr="127.0.0.1", headers=spoofed)
    assert trusted["source_ip"] == "203.0.113.10"
    assert trusted["browser_summary"] == "Chrome บน Windows"


def test_local_immutable_storage_and_malformed_records(tmp_path):
    key = b"key"
    first = audit.sign_event(base_event(event_id="first"), key)
    second = audit.sign_event(base_event(event_id="second"), key)
    first_key = audit.object_key(first, "audit/")
    second_key = audit.object_key(second, "audit/")
    assert first_key != second_key
    audit.write_local(tmp_path, first_key, audit.serialize(first))
    audit.write_local(tmp_path, second_key, audit.serialize(second))
    malformed = tmp_path / "audit/2026/08/10/bad.json"
    malformed.write_text("not json", encoding="utf-8")
    records = audit.list_local(tmp_path, 10)
    assert {record["event_id"] for record in records} == {"first", "second"}
    assert all(audit.verify_event(record, key) for record in records)
