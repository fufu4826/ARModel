# ARModel

Flask application for Thai community learning resources, 3D models, AR, narration,
and an authenticated administrator interface.

## Persistence Architecture

- **Cloudflare D1**: projects, models, sliders, site settings, administrator account
  hashes, analytics, signed audit events, and login rate-limit events.
- **Cloudflare R2**: GLB files, thumbnails, gallery/slider/branding images, narration
  audio, and temporary narration audio files.
- **Flask**: rendering, authorization, CSRF protection, validation, and AR pages.
- **D1 connection**: direct Cloudflare REST API or a private Worker gateway.
  Both use bound SQL batches. The browser never receives credentials.

GitHub is source control only. Admin saves no longer create GitHub commits.
Runtime reads/writes no content JSON files. Existing `data/*.json` are retained
only as migration snapshots and validation fixtures, not a database fallback.
Gallery/media metadata and event details can use structured JSON columns inside
D1; this is not file-based persistence.

## Cloud D1 Review (Prepared October 16, 2026)

The separate `armodel-production` D1 database has the complete review snapshot:
10 projects, 41 models, 31 settings, and 2 slides. Every original field was
verified against the source. The live site's JSON system has NOT been switched.

On the Windows account holding the encrypted D1 credential:

```powershell
python scripts/verify_cloud_d1_readonly.py   # SELECT-only field/type/order/FK comparison
python scripts/run_cloud_d1_review.py         # analytics disabled for this preview
```

`validate_cloud_d1.py` additionally runs deliberately failing write transactions;
run it only with explicit approval.

For UI review without any cloud access, `python scripts/run_snapshot_review.py`
serves http://127.0.0.1:5018 from a throwaway SQLite copy of the snapshot. R2 CORS
allows only the production origin, so 3D models cannot load from localhost.

Open http://127.0.0.1:5017/home. This is loopback Flask with real cloud D1,
not Wrangler emulation. The launcher decrypts the token in memory using Windows
DPAPI and reads non-secret target IDs from `~/.armodel-secrets/d1-target.toml`.
Neither the token nor a plaintext environment file is saved in this repository.
Do not repeat snapshot import: existing nonempty targets are rejected.

See [verified cloud migration](docs/D1_CLOUD_VERIFICATION.md) for exact scope,
fingerprints, remaining R2 upload/account checks, and the approval boundary.

## Local Review With Real D1 Emulation

Install Python dependencies in the project root:

```powershell
python -m pip install -r requirements-dev.txt
```

In `cloudflare/d1`:

```powershell
npm ci
npm run migrate:local
npm run dev
```

The Worker listens on loopback port 8787 and uses Wrangler's local D1 runtime.
The all-zero database ID is a local placeholder, not a production database.
Do not add `--remote` or deploy this configuration during local review.

In the project root, import the snapshot **once into an empty database**, then run:

```powershell
python scripts/migrate_to_d1.py --gateway http://127.0.0.1:8787
python scripts/run_d1_review.py
```

Review http://127.0.0.1:5016/home and http://127.0.0.1:5016/admin/login.
The migration preserves original files and refuses to overwrite a nonempty D1.
It verifies every original field and reports source SHA-256 fingerprints.
Do not rerun an import to refresh existing content; use the Admin interface.

The Python repository also has an isolated SQLite adapter for fast tests.
Flask only enables it in TESTING mode. A normal runtime without a D1 gateway
fails instead of creating a local database or falling back after gateway failure.

## Security and Concurrent Changes

Admin accounts live in D1 and use Werkzeug password hashes. Legacy
`ADMIN_PASSWORD`, `ADMIN_PASSWORD_HASH`, and private JSON configuration are not
read by runtime authentication. Preserve and import an existing hash before a
production cutover; no password needs to be printed or changed.
Browser first-run setup exists only in isolated tests: every real runtime (local
review, cloud review, production) shows that no account exists and refuses web setup.
Import an existing hash with `python scripts/import_admin_to_d1.py --cloud --username <name>
--source <private config>` (refuses to replace an existing account; never prints the hash).
The login form is CSRF-protected. Server deployment requires a stable `SECRET_KEY`.

Normal Admin forms carry dataset revisions. Stale saves return HTTP 409 rather
than overwrite newer data. Each collection write and linked project/model
deletion uses one D1 transaction, with foreign keys and unique IDs/slugs.
D1 failure returns HTTP 503; stale JSON is never served as a fallback.
Authentication rate-limit storage failures fail closed.

The gateway requires a shared server-side token over HTTPS. The local auth
bypass is limited to explicit local development on loopback. Browser-origin
requests and unsupported SQL/table access are rejected.

## Configuration For A Reviewed Cloud Deployment

These names describe future configuration; this branch does not change actual
environment variables, credentials, or production deployment settings.

Flask: either `D1_ACCOUNT_ID`, `D1_DATABASE_ID`, `D1_API_TOKEN` for direct API,
or `D1_GATEWAY_URL`, `D1_GATEWAY_TOKEN` for a Worker (not both).
Also required: stable `SECRET_KEY`, and existing R2
credentials (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_BUCKET`, `R2_PUBLIC_BASE_URL`). Worker: a D1 binding named `DB` and
`GATEWAY_TOKEN` matching Flask's gateway token. Gemini narration still uses the
existing server-side `GEMINI_API_KEY` when requested.

See [D1/R2 migration and acceptance](docs/D1_R2_MIGRATION.md) before any cutover.
Do not delete historical JSON or R2 event archives until the migration has been
validated and explicitly approved.

## Validation

```powershell
python -m pytest
python scripts/validate_zero_supabase_data.py
python scripts/validate_d1_review.py
node --check static/js/site-carousel.js
node --check static/js/ar-viewer.js
node --check static/js/admin-dashboard.js
```

Worker authentication/validation tests: `npm test` in `cloudflare/d1`.
The local D1 integration script tests Flask CRUD, a mocked R2 upload, conflict
rejection, foreign-key rollback, and restoration of original content IDs.
Cloud D1 source parity and transaction checks have passed. Real R2 writes,
actual administrator credentials, live cutover, and physical-device AR still
require separate acceptance.

Earlier production documents describe the retired JSON/GitHub storage design.
They are historical evidence, not deployment instructions for this branch.
