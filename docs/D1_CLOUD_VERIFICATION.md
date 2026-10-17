# Verified D1 Migration - 2026-10-16

Workspace: `C:\Users\fufu\ARModel-review-20261016`

Branch: `review/phuphan-content-admin-login`

## Cloud Target

- Database: `armodel-production`
- Database ID: `c9fc6704-2f9a-403d-a81a-62999457d21f`
- The database is separate from the existing live site's JSON persistence.
- No Worker, website, or production environment configuration was deployed.
- Direct Flask-to-D1 REST access uses server-side credentials and bound parameters.
- Token is encrypted with Windows CurrentUser DPAPI outside the repository.
- No plaintext credential or token value is included in this report.

## Source Coverage

All four content JSON datasets in the review clone were imported together.
The root `config.json` is empty; no real administrator credential exists there.
No analytics, audit, or login JSON archive exists in the clone's data directory.
Production-only historical records have not been retrieved or claimed migrated.

| Snapshot | Rows/Keys | SHA-256 |
| --- | ---: | --- |
| projects.json | 10 | 9bb655aa20fcb015488cf9604f2e87bad5023d279b2eba15d0af336bca3657bf |
| models.json | 41 | d401239b6c30bb9720888a03048edbc7b22bb7c96c912f85ff4f29295d4a72c4 |
| site_settings.json | 31 | 92bee1eab37ea2bf8eae66e2e09cc77a6a8a388caac4a5139ee8f88e64357246 |
| slider_items.json | 2 | 32645eb455f2115e0a74d9cf9f1f67e1f919e51daf9d408a83a4dd3b3398c5ec |

Every original field was compared after reading it back from cloud D1, including
IDs, order, Thai text, URLs, image lists, narration references, visibility,
model scale, and rotation. Original snapshots were not deleted or overwritten.
The model snapshot includes the earlier approved-for-review description edits;
it is not a freshly downloaded snapshot of the live site.

## Runtime Persistence

- D1: content, settings, account hashes, analytics, audit events, login attempts.
- R2: uploaded models, images, audio, temporary narration audio.
- Removed unused local JSON audit writer and reader.
- JSON HTTP payloads, audit downloads, and structured SQL columns remain valid
  serialization formats; they are not a JSON file database.
- Legacy Path-shaped dataset identifiers in Flask are table selectors only,
  retained for compatibility with existing test fixtures; no file is opened.
- SQLite/filesystem adapters are test-only. Failure never falls back to JSON.

## Verification

- Python: 135 tests passed, 79 subtests passed.
- Worker: 5 tests passed.
- JavaScript: `node --check static/js/site-carousel.js` passed.
- Snapshot/HTTPS/CORS validation: 121 R2 asset URLs passed.
- Actual cloud D1: all original fields match; foreign-key check passed.
- Actual cloud D1: a deliberate FK failure rolled the complete batch back.
- Actual cloud D1: a stale revision rejected the batch and left no probe row.
- Flask `/`, `/home`, `/models`, `/admin/login`, `/health`, one model detail,
  and one project detail returned 200 while all JSON/JSONL file access was blocked.
- Cloud D1 REST boolean parameters are explicitly converted to SQLite integers.
  The first failed import rolled back; there was no partial content import.

Review: http://127.0.0.1:5017/home

Screenshot: `review-screenshots/cloud-d1-home-5017.png`

## Remaining Release Gates

1. Obtain existing R2 upload credentials or authorize a narrowly scoped new token.
   Public R2 reads passed; real R2 writes have NOT been verified here.
2. Import an existing administrator hash securely or let the owner create an
   account. No default password or production account has been invented.
3. Retrieve a final current live snapshot and any historical records during an
   agreed edit freeze. Import only into a reviewed empty release target or use
   a separately reviewed reconciliation; never overwrite this populated target.
4. Preserve the existing audit signing key and stable Flask session secret.
5. Owner reviews the preview, then separately approves cutover/deployment.

No commit, push, merge, website deployment, R2 deletion, or live-site switch.
