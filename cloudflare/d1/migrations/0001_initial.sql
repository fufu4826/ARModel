CREATE TABLE IF NOT EXISTS dataset_versions (
  name TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO dataset_versions(name) VALUES
 ('projects'),('models'),('site_settings'),('slider_items'),('admin_accounts');
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, slug TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
 description TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL DEFAULT 1 CHECK(visible IN (0,1)),
 position INTEGER NOT NULL, details TEXT NOT NULL CHECK(json_valid(details))
);
CREATE UNIQUE INDEX IF NOT EXISTS projects_slug ON projects(slug) WHERE slug <> '';
CREATE TABLE IF NOT EXISTS models (
 id TEXT PRIMARY KEY, slug TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
 description TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL DEFAULT 1 CHECK(visible IN (0,1)),
 project_id TEXT REFERENCES projects(id) ON DELETE RESTRICT,
 position INTEGER NOT NULL, details TEXT NOT NULL CHECK(json_valid(details))
);
CREATE UNIQUE INDEX IF NOT EXISTS models_slug ON models(slug) WHERE slug <> '';
CREATE INDEX IF NOT EXISTS models_project ON models(project_id,visible,position);
CREATE TABLE IF NOT EXISTS slider_items (
 id TEXT PRIMARY KEY, position INTEGER NOT NULL,
 title TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 details TEXT NOT NULL CHECK(json_valid(details))
);
CREATE TABLE IF NOT EXISTS site_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_accounts (
 id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('analytics','audit','login')),
 occurred_at TEXT NOT NULL, identity TEXT NOT NULL DEFAULT '',
 payload TEXT NOT NULL CHECK(json_valid(payload))
);
CREATE INDEX IF NOT EXISTS events_kind_time ON events(kind,occurred_at DESC);
CREATE INDEX IF NOT EXISTS login_identity_time ON events(identity,occurred_at) WHERE kind='login';
CREATE TABLE IF NOT EXISTS write_guards (
 dataset TEXT PRIMARY KEY REFERENCES dataset_versions(name), expected INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS reject_stale_write BEFORE INSERT ON write_guards
 WHEN (SELECT version FROM dataset_versions WHERE name=NEW.dataset) <> NEW.expected
 BEGIN SELECT RAISE(ABORT,'STALE_REVISION'); END;
