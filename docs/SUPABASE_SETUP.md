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
GEMINI_API_KEY=your-gemini-api-key
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
previews/<model_id>/
projects/
site/landing/
site/branding/
site/social/
site/intro/
sliders/
```

The bucket must allow public reads if model-viewer and browsers should load assets directly from public URLs.

`GEMINI_API_KEY` is used only by the authenticated admin backend to generate Thai narration audio. It must remain a server-side Vercel Environment Variable and must never be exposed to browser JavaScript.

Keep public writes disabled. The browser must never receive the service-role key. Admin uploads are authorized by the Flask admin session, then either uploaded by the server with the service role or sent through a short-lived signed upload URL created by Flask.

The `site_settings` and `slider_items` tables are server-only resources. Flask reads and writes them with `SUPABASE_SERVICE_ROLE_KEY`; browser code does not query these tables directly. The schema enables Row Level Security without adding `anon` or `authenticated` policies, so direct client access remains blocked while the server-side service role continues to work.

Landing intro logos and `intro_display_mode` use additional keys in the existing `site_settings` table and objects under `site/intro/`. No new table or SQL schema migration is required for the intro feature. Supported display modes are `sequence` and `all_at_once`.

The social preview image uses the `site_social_image` key in the existing `site_settings` table and objects under `site/social/`. No new table or SQL schema migration is required. When unset, Open Graph and Twitter metadata fall back to the Landing cover image.

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
  preview_images jsonb not null default '[]'::jsonb,
  narration_audio text not null default '',
  file_size_mb numeric,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create or replace function armodel_catalog_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists projects_set_updated_at on projects;
create trigger projects_set_updated_at
before update on projects
for each row execute function armodel_catalog_set_updated_at();

drop trigger if exists models_set_updated_at on models;
create trigger models_set_updated_at
before update on models
for each row execute function armodel_catalog_set_updated_at();

```

The existing SQL above documents the original project/model schema. Run `docs/supabase_schema.sql` separately for Landing Page, Branding, and Slider management. That migration:

- Adds `models.preview_images` as a JSON array for model preview galleries.
- Adds `models.narration_audio` for an optional public narration audio URL.
- Runs in a transaction.
- Creates or upgrades `site_settings` and `slider_items`.
- Uses the feature-specific `armodel_site_content_set_updated_at()` trigger function.
- Adds `slider_items.updated_at`.
- Adds an index for active slider ordering.
- Inserts missing default settings without overwriting existing values.
- Enables RLS without granting browser roles direct table access.

The migration is designed to be rerunnable. It does not drop tables, truncate data, or delete rows. The application validates non-empty slider titles and supported URLs in the server layer rather than adding URL-format database constraints, because internal paths such as `/home` and external HTTPS URLs are both valid.

Run the updated `docs/supabase_schema.sql` before saving model preview galleries in production. Existing models receive an empty JSON array and continue using their thumbnail as the public gallery fallback. Until the column exists, Supabase model create/update requests that include `preview_images` will fail; public reads continue to tolerate rows where the field is absent.

Run the same migration before saving narration audio in production. Uploaded narration files use the existing public-read/private-write Storage bucket under `models/narration/`. Existing models receive an empty `narration_audio` value and continue using browser Web Speech as fallback.

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
- Landing Page, Branding, and Slider settings write to Supabase.
- Admin uploads go to Supabase Storage.
- Vercel does not write to `static/`, `models.json`, or `projects.json`.

Model `.glb` files are uploaded directly from the browser to Supabase Storage so the binary file does not pass through the Vercel serverless request. The application accepts model files up to 50 MB. In Supabase Storage Settings, set the global file size limit and the configured bucket's file size limit to at least 50 MB; the lower of those two limits takes precedence. Supabase recommends resumable uploads for files larger than 6 MB, so models should still be compressed where practical.

Before deploying the site-content feature:

1. Back up the Supabase project or confirm Point-in-Time Recovery is available.
2. Run `docs/supabase_schema.sql` in a staging project first.
3. Confirm RLS is enabled and no broad `anon`/`authenticated` write policies exist.
4. Confirm the configured Storage bucket allows public reads but rejects unauthenticated writes.
5. Run the migration in production before deploying the application code.

When Supabase is not configured:

- Public pages read local JSON files.
- Landing Page, Branding, and Slider settings read `site_settings.json` and `slider_items.json`.
- Local development can upload into `static/`.
- Vercel admin editing remains read-only.
