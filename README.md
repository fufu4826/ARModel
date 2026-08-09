# ARModel

ARModel is a Flask application for publishing community and cultural 3D models with Google model-viewer AR support. It includes public Landing/Home, project and model pages, a news slider, narration playback, and an authenticated Admin application.

## Local development

```bash
pip install -r requirements.txt
python app.py
```

Development and CI dependencies are installed with `pip install -r requirements-dev.txt`.

Open `http://127.0.0.1:5000`. Local metadata is read and written under `data/`; local uploads and runtime analytics use local files. Tests replace these paths with temporary fixtures.

## Production architecture

Vercel runs `app.py` through the Python runtime. The versioned source of truth is:

- `data/models.json`
- `data/projects.json`
- `data/site_settings.json`
- `data/slider_items.json`

When GitHub Contents credentials are configured, Production Admin writes update only these allow-listed files and create a commit on the configured branch. Without GitHub write configuration, Production mutations are blocked safely.

Cloudflare R2 stores GLB files, thumbnails, gallery and slider images, branding assets, narration audio, analytics events, and Audit Log objects. New Production analytics events are immutable objects under `analytics/events/YYYY/MM/DD/<timestamp>-<uuid>.json`; the dashboard also reads the legacy `analytics/analytics_events.json` object during transition.

## Admin security

- Prefer `ADMIN_PASSWORD_HASH`; plaintext `ADMIN_PASSWORD` remains a compatibility option.
- Admin mutations require authentication and a cryptographically random session-bound CSRF token.
- Login failures are limited to five attempts per trusted client IP within 15 minutes. Production attempts are immutable R2 objects keyed by an HMAC identity; local attempts use the system temporary directory. Storage failures fail open and are logged so an R2 outage does not lock out every administrator.
- Vercel sessions use Secure, HttpOnly, SameSite=Lax cookies. Responses include baseline content-type, referrer, permissions, framing, and HSTS protections.
- A strict CSP is not currently enforced: existing templates contain inline scripts/styles, dynamic Admin preview URLs, Google Fonts, jsDelivr, unpkg model-viewer, and administrator-configured model/image/audio origins. Enforcing a useful policy first requires nonce/hash migration and explicit asset-origin controls; a broad `unsafe-inline https:` policy was intentionally not shipped.

## Production Admin writes

Production metadata writes use the GitHub Contents API. Binary uploads use R2. Required variables are:

```text
SECRET_KEY
ADMIN_PASSWORD_HASH
GITHUB_CONTENTS_TOKEN
GITHUB_REPOSITORY
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_PUBLIC_BASE_URL
```

Optional variables include `GITHUB_BRANCH`, `GITHUB_COMMITTER_NAME`, `GITHUB_COMMITTER_EMAIL`, `SITE_BASE_URL`, `PUBLIC_SITE_URL`, `ANALYTICS_R2_OBJECT_KEY` for legacy analytics, `AUDIT_LOG_SIGNING_KEY`, `AUDIT_LOG_RETENTION_DAYS`, `R2_STORAGE_SOFT_LIMIT_GB`, and `GEMINI_API_KEY`.

Never commit environment values or credentials.

## Narration

Gemini TTS runs server-side only after an Admin requests generation. A generated draft is stored under `audio/pending/<model-id>/` and represented by a short-lived signed token bound to the model and expected current narration. Confirmation copies it to `audio/narrations/<model-id>/`, updates model metadata through the normal JSON/GitHub path, and then performs safe cleanup. Cancellation deletes only the pending object. External old narration URLs are never deleted.

Configure an R2 lifecycle rule to remove `audio/pending/` after one day.

## Audit Log

Meaningful authentication and Admin mutations create one signed immutable JSON object per event under `audit/YYYY/MM/DD/`. Events contain Thai summaries, request/session context, structured changes, recursive secret redaction, and HMAC-SHA256 tamper evidence. Authenticated Admin users can inspect and export CSV/JSON. Set a lifecycle policy for the `audit/` prefix according to the required retention period, commonly 180–365 days.

## Production rollback

A historical Git commit is a source baseline, not automatically the previous known-good Vercel deployment. Before a rollback:

1. Record the commit and deployment currently serving Production.
2. Identify and verify the previous known-good Vercel deployment in Vercel's deployment history.
3. Review newer Production Admin commits, especially changes to `data/*.json`.
4. Prefer Vercel rollback/redeploy controls for an application-only rollback, or use a reviewed Git revert/fix-forward change when source history must change.
5. Never replace newer Production content files with stale copies from an older commit.

## Validation and CI

Run the same checks used by `.github/workflows/regression.yml`:

```bash
python -m pytest
python scripts/validate_zero_supabase_data.py
node --check static/js/site-carousel.js
node --check static/js/model-narration.js
node --check static/js/admin-dashboard.js
```

The validator checks deterministic JSON, required fields, relationships, HTTPS/R2 assets, CORS, and absence of Supabase runtime URLs.

## AR and assets

Model pages use Google model-viewer. WebXR, Scene Viewer, and Quick Look depend on the browser and device. Keep large GLB assets in R2 with immutable versioned keys rather than in the Vercel filesystem.

## Historical documents

Supabase setup/schema and migration documents under `docs/`, `STORAGE_MIGRATION_PLAN.md`, and related verification reports are retained only as historical migration/audit context. They do not describe the current runtime architecture.
