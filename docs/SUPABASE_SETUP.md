# Supabase Setup

## Overview

ARModel can use Supabase as the production backend on Vercel:

- Supabase Storage stores uploaded `.glb` files and images.
- Supabase Postgres stores project and model metadata.
- Local JSON files remain as the fallback when Supabase environment variables are missing.

## Environment Variables

Set these in Vercel Project Settings:

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=your-bucket-name
SECRET_KEY=your-flask-secret
ADMIN_PASSWORD_HASH=your-werkzeug-password-hash
```

Never expose `SUPABASE_SERVICE_ROLE_KEY` in frontend JavaScript.

## Storage Bucket

Create a bucket using the value from `SUPABASE_STORAGE_BUCKET`.

The app uploads objects into these folders:

```text
models/
thumbnails/
projects/
```

The bucket must allow public reads if model-viewer and browsers should load assets directly from public URLs.

## SQL Schema

Run this SQL in the Supabase SQL editor:

```sql
create table if not exists projects (
  id text primary key,
  slug text unique not null,
  name text not null,
  description text,
  image_url text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists models (
  id text primary key,
  project_id text references projects(id) on delete set null,
  slug text unique not null,
  name text not null,
  description text,
  model_url text,
  thumbnail_url text,
  file_size_mb numeric,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists projects_set_updated_at on projects;
create trigger projects_set_updated_at
before update on projects
for each row execute function set_updated_at();

drop trigger if exists models_set_updated_at on models;
create trigger models_set_updated_at
before update on models
for each row execute function set_updated_at();
```

## Migration From JSON

From the project root:

```bash
set SUPABASE_URL=https://your-project.supabase.co
set SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
set SUPABASE_STORAGE_BUCKET=your-bucket-name
python scripts/migrate_json_to_supabase.py --upload-assets
```

Use `--upload-assets` to upload local files from `static/model/` and `static/pic/` into Supabase Storage. Without this flag, the script inserts metadata and preserves existing external URLs, but local-only asset paths are not usable on Supabase records.

To validate your local JSON metadata and preview exactly what files and database records would be migrated without modifying any remote data, run the migration with the `--dry-run` flag (which does not require the environment variables to be set):

```bash
python scripts/migrate_json_to_supabase.py --dry-run
# Or to preview with local static asset checks:
python scripts/migrate_json_to_supabase.py --dry-run --upload-assets
```

## Production Behavior

When all Supabase environment variables are configured:

- Public pages read projects and models from Supabase.
- Admin create/edit/delete writes to Supabase.
- Admin uploads go to Supabase Storage.
- Vercel does not write to `static/`, `models.json`, or `projects.json`.

When Supabase is not configured:

- Public pages read local JSON files.
- Local development can upload into `static/`.
- Vercel admin editing remains read-only.
