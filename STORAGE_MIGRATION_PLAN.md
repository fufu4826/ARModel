# Storage Migration Plan (Historical)

> Migration reference only. The current runtime architecture is documented in `README.md`.

## Why large GLB traffic exhausts Supabase Free

Supabase Free includes limited file storage and cached egress. A single GLB in
this project is commonly 10–40 MB. A 20 MB model downloaded 250 times consumes
about 5 GB, the full Free cached-egress allowance. Public Storage URLs can also
be hotlinked outside this application.

Current production objects return `Cache-Control: no-cache`. Browsers may
therefore revalidate or download the same large model again. The application
now assigns a GLB URL only when its viewer is near the viewport and gives future
uniquely named uploads a long-lived immutable cache directive. Existing objects
retain their current metadata until migrated or re-uploaded.

## What should stay in Supabase

- Postgres metadata: projects, models, settings, and slider records.
- Authentication data and application configuration.
- Small admin-managed images when operational simplicity matters.
- Small narration files if their traffic remains low.

## What should move to an object CDN

Move all `models/**/*.glb` objects first. Large narration audio and frequently
viewed full-resolution images can follow. Cloudflare R2 is preferred because it
is designed for object delivery and can sit behind a custom domain. Bunny CDN
is a reasonable managed alternative.

Do not migrate database records, authentication data, secrets, or private admin
configuration to a public object bucket.

## Recommended object layout

```text
public/
  models/
    <model-id>/
      <content-hash>.glb
      poster.webp
      previews/
        01.webp
  audio/
    <model-id>/
      narration.<content-hash>.mp3
```

Content-hashed or otherwise unique filenames allow:

```text
Cache-Control: public, max-age=31536000, immutable
```

## Environment variables

```text
ASSET_BASE_URL=https://assets.example.com
R2_ACCOUNT_ID=...
R2_BUCKET_NAME=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
```

Only `ASSET_BASE_URL` may be exposed to the browser. R2 credentials must remain
server-side environment variables and must never be committed.

For Bunny CDN, use equivalent server-only variables such as
`BUNNY_STORAGE_ZONE`, `BUNNY_STORAGE_API_KEY`, and public `ASSET_BASE_URL`.

## Step-by-step migration

1. Create a private-write/public-read R2 bucket and attach a custom asset
   domain.
2. Configure CORS for the production website origin and required AR clients.
3. Set long-lived immutable cache headers on GLB objects.
4. Inventory model URLs from the Supabase `models` table. Do not infer live
   objects from bucket contents alone.
5. Copy one low-risk GLB to R2 without deleting its Supabase source.
6. Validate content type (`model/gltf-binary`), content length, CORS, byte-range
   requests, and cache headers.
7. Update that model record to the new HTTPS asset URL.
8. Test desktop 3D viewing, mobile viewing, and AR launch.
9. Migrate remaining live GLBs in small batches and keep an old-to-new URL map.
10. Monitor R2/CDN requests and Supabase egress for at least 48 hours.
11. Only after observation, create an explicit reviewed list of obsolete
    Supabase objects and remove those objects through the Storage API.

## Rollback

Keep every original Supabase object during migration. Store the old URL beside
each migration record. If a model fails, restore its database row to the old
Supabase URL. Do not delete Supabase sources until supported devices pass and
the observation period is complete.

## Testing checklist

- [ ] Landing and model-list pages request no GLB files.
- [ ] A detail page requests only its selected GLB.
- [ ] Revisiting a model uses browser/CDN cache where applicable.
- [ ] Desktop rotation and zoom work.
- [ ] Android Scene Viewer/WebXR launch works.
- [ ] iOS AR fallback behavior remains acceptable.
- [ ] `Content-Type` is `model/gltf-binary`.
- [ ] CORS allows the production domain.
- [ ] Byte-range requests return correctly.
- [ ] Cache header is `public, max-age=31536000, immutable`.
- [ ] Broken model URL produces the existing recovery UI.
- [ ] Supabase egress stops increasing from GLB views.
- [ ] No R2/Bunny secret appears in source, logs, or client bundles.
