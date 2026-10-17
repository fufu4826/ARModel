-- Admin-managed provider API keys (Gemini TTS). Additive only.
-- The key itself is stored encrypted (AES-GCM, app-side secret); only the last 4 characters are kept readable.
CREATE TABLE IF NOT EXISTS api_keys (
 id TEXT PRIMARY KEY,
 provider TEXT NOT NULL DEFAULT 'gemini',
 label TEXT NOT NULL DEFAULT '',
 fingerprint TEXT NOT NULL UNIQUE,
 hint TEXT NOT NULL,
 ciphertext TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'unknown' CHECK(status IN ('unknown','ok','invalid','quota')),
 last_error TEXT NOT NULL DEFAULT '',
 cooldown_until TEXT NOT NULL DEFAULT '',
 last_used_at TEXT NOT NULL DEFAULT '',
 last_checked_at TEXT NOT NULL DEFAULT '',
 use_count INTEGER NOT NULL DEFAULT 0,
 failure_count INTEGER NOT NULL DEFAULT 0,
 created_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS api_keys_provider ON api_keys(provider, created_at);
