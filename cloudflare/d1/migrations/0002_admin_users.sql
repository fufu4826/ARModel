-- Multiple administrators with roles; one owner issues one-time invite/reset links.
-- Additive only: the legacy admin_accounts table is kept untouched.
CREATE TABLE IF NOT EXISTS admin_users (
 id TEXT PRIMARY KEY,
 username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 display_name TEXT NOT NULL DEFAULT '',
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('owner','admin','editor','reviewer')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 session_version INTEGER NOT NULL DEFAULT 1,
 invited_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_single_owner ON admin_users(role) WHERE role='owner';
CREATE TABLE IF NOT EXISTS admin_invites (
 token_hash TEXT PRIMARY KEY,
 kind TEXT NOT NULL DEFAULT 'invite' CHECK(kind IN ('invite','reset')),
 role TEXT NOT NULL DEFAULT '' CHECK(role IN ('','admin','editor','reviewer')),
 user_id TEXT NOT NULL DEFAULT '',
 note TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 used_at TEXT,
 used_by TEXT,
 revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS admin_invites_open ON admin_invites(kind, used_at, revoked_at, expires_at);
-- The existing single account becomes the owner, only while no admin user exists yet.
INSERT OR IGNORE INTO admin_users(id,username,display_name,password_hash,role,active,session_version,invited_by,created_at,updated_at)
 SELECT 'legacy-owner', username, username, password_hash, 'owner', 1, 1, '', strftime('%Y-%m-%dT%H:%M:%SZ','now'), strftime('%Y-%m-%dT%H:%M:%SZ','now')
 FROM admin_accounts WHERE NOT EXISTS (SELECT 1 FROM admin_users);
