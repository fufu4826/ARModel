# ARModel

Flask web application for viewing cultural and community 3D models with Google model-viewer AR support.

## Local Development

```bash
cd ARModel
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For production, set a `SECRET_KEY` environment variable. Local development can run without it, but sessions will reset when the process restarts.

## Vercel Deployment

1. Push `ARModel` to GitHub.
2. Import the repository in Vercel.
3. Add `SECRET_KEY` and `ADMIN_PASSWORD_HASH` in the Vercel project environment variables.
4. For production admin uploads, add `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET`.
5. Deploy with the Python runtime.
6. If this project is inside a larger repository, set the Vercel root directory to `ARModel`.

## Vercel Runtime Limitation

Vercel serverless functions use a read-only project filesystem at runtime. Uploading files into `static/`, editing `models.json`, or editing `projects.json` through the admin UI works only in local development.

On Vercel:

- If Supabase is configured, public pages and admin writes use Supabase Database and Supabase Storage.
- If Supabase is not configured, public pages, `/api/models`, and the AR viewer read committed JSON/static assets.
- If Supabase is not configured, admin editing is read-only and file uploads are disabled.
- Use external image/model URLs in Supabase or JSON for production assets that are not committed to the repository.

To add files permanently:

1. Add `.glb` files and images locally.
2. Update `models.json` or `projects.json`.
3. Commit and push to GitHub.
4. Redeploy on Vercel.

For production admin uploads, configure Supabase Storage and Supabase Database. See `docs/SUPABASE_SETUP.md`.

## Supabase Production Uploads

Supabase is optional. When these environment variables are present, the app reads and writes projects and models through Supabase:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET
SECRET_KEY
ADMIN_PASSWORD_HASH
```

Uploaded model files are stored under `models/`, model thumbnails under `thumbnails/`, and project images under `projects/` in the configured Supabase Storage bucket. Metadata is stored in the `projects` and `models` Postgres tables.

To migrate local JSON/static data into Supabase:

```bash
python scripts/migrate_json_to_supabase.py --upload-assets
```

Omit `--upload-assets` to insert metadata only. The full schema and setup workflow are documented in `docs/SUPABASE_SETUP.md`.

## Adding Models

- Put `.glb` files in `static/model/`.
- Put thumbnails in `static/pic/`.
- Match the thumbnail filename with the model filename when possible, for example `rice.glb` and `rice.jpg`.
- Update `models.json` when metadata such as name, description, project, visibility, or thumbnail path is required.
- For externally hosted assets, set `model_url` and `thumbnail_url` in `models.json`.
- For externally hosted project images, set `image_url` in `projects.json`.

## AR Usage

Open a model page on a supported mobile device and tap the AR button in the viewer. WebXR, Scene Viewer, and Quick Look support depends on the device, operating system, and browser.

## Large File Warning

`.glb` files can be large. If Vercel deployment fails due to size limits, move model assets to external storage such as Cloudflare R2, Supabase Storage, Firebase Storage, or Cloudinary, then store the external model URLs in `models.json`.

## Admin

The existing admin system is preserved. On local development, visit `/admin/login` and create an admin password if one is not already configured. On Vercel, configure `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD` as an environment variable because serverless file writes are not durable.
