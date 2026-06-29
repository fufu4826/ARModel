# Final Production Verification

## 1. Commit hash

Egress fix commit: `12bb5bb5b642a8b5e9391eb8f0e48dd6fdcf6a83`

## 2. Summary of the egress problem

The application serves large GLB models directly from public Supabase Storage
URLs. The 41 live models total more than 1 GB, and production objects were
observed returning `Cache-Control: no-cache`. Repeated model views could
therefore consume the Supabase Free cached-egress quota quickly. Public model
URLs also remain susceptible to hotlinking.

## 3. What was changed

- Deferred assigning a GLB `src` until its model viewer approaches the
  viewport.
- Guarded the assignment so each viewer sets its source only once.
- Kept model-list and landing pages free of GLB loads.
- Added the existing loading and error-state integration to the deferred load.
- Added Meshopt decoder configuration before loading `model-viewer` for GLBs
  that use `EXT_meshopt_compression`.
- Configured future uniquely named uploads with
  `Cache-Control: max-age=31536000, immutable`.
- Added automated assertions for deferred model loading and Meshopt setup.
- Added `STORAGE_MIGRATION_PLAN.md`.
- Expanded Git ignore coverage from `.env` to `.env*`.

## 4. Test results

- Python unit tests: **53 passed**
- Python syntax compilation: passed
- `static/js/ar-viewer.js` syntax check: passed
- `static/js/admin-direct-upload.js` syntax check: passed
- `git diff --check`: passed
- Local Meshopt-compressed model verification: loaded without viewer error

## 5. Production route verification

The following production routes returned HTTP 200:

| Route | Result |
| --- | --- |
| `/` | HTTP 200 |
| `/home` | HTTP 200 |
| `/models` | HTTP 200 |
| `/models/lychee` | HTTP 200 |
| `/models/lukplakob` | HTTP 200 |

No significant browser console errors were observed on the verified routes.

## 6. GLB loading behavior before and after

Before the fix, a detail template assigned the GLB directly through the
`model-viewer` `src` attribute as soon as the element was created. Some
Meshopt-compressed files could also fail because the decoder was not enabled.

After the fix:

- `/models` observed **0 GLB assets**.
- `/models/lychee` observed exactly **1 GLB asset**.
- `/models/lukplakob` observed exactly **1 GLB asset**.
- Both detail viewers completed loading without an error state.
- Both detail pages produced no significant console errors.
- The GLB source is assigned once by the intersection-based loader.

## 7. Supabase deleted file verification

The seven approved orphan GLB paths were deleted through the Supabase Storage
API and the deletion check returned `remainingCount: 0`.

The production `/api/models` response contained 41 model records and did not
reference any of the seven deleted GLB paths.

## 8. Secret scan result

- No hardcoded JWT-like token was found.
- No `sb_secret_*` literal was found.
- References to `service_role` and `SUPABASE_SERVICE_ROLE_KEY` were variable,
  documentation, or test references; no value was committed.
- `.env` and `.env.local` are ignored through the `.env*` rule.

## 9. Remaining risks

- The live GLB set alone is larger than the Supabase Free 1 GB Storage quota.
- Existing Supabase objects still have their previous cache metadata; the new
  immutable directive applies to future uploads.
- Public Supabase model URLs can be hotlinked.
- Browser-side lazy loading reduces unnecessary requests but cannot prevent
  deliberate direct downloads.
- Supabase usage metrics may refresh with a delay.

## 10. Recommended next actions

1. Monitor Supabase Storage, Egress, and Cached Egress for at least 24 hours.
2. Rotate the `service_role` key manually during a controlled maintenance
   window. Update the server-side Vercel environment value and redeploy in the
   same operation so production is not left with an invalid key.
3. Move large GLB files to Cloudflare R2, Bunny CDN, or another object CDN,
   following `STORAGE_MIGRATION_PLAN.md`.
4. Reduce Supabase Storage below 1 GB before the new organization is evaluated
   against Free-plan limits.
5. Keep old Supabase objects during migration until each replacement URL has
   passed desktop, mobile, and AR testing.
