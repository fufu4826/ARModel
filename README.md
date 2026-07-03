# ARModel

Flask web application for viewing cultural and community 3D models with Google model-viewer AR support.

The admin panel also manages the public Landing Page, site branding, and homepage slider content.

## Local Development

```bash
cd ARModel
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For production, set a `SECRET_KEY` environment variable. Local development can run without it, but sessions will reset when the process restarts.

Public canonical URLs and sitemap entries default to `https://phuphan-ar.vercel.app`. Set `SITE_BASE_URL` in the deployment environment to override the public base URL; `PUBLIC_SITE_URL` remains supported for backward compatibility.

## Vercel Deployment

1. Push `ARModel` to GitHub.
2. Import the repository in Vercel.
3. Add `SECRET_KEY` and `ADMIN_PASSWORD_HASH` in the Vercel project environment variables.
4. Deploy with the Python runtime.
5. If this project is inside a larger repository, set the Vercel root directory to `ARModel`.

## Vercel Runtime Limitation

Vercel serverless functions use a read-only project filesystem at runtime. Production metadata is loaded from versioned files under `data/`, and binary assets are served by Cloudflare R2.

On Vercel:

- Public pages and APIs always read committed `data/*.json`.
- Admin mutation and upload endpoints are read-only and return HTTP 403.
- Model, image, slider, site, and narration assets use Cloudflare R2 URLs.
- Production does not require Supabase environment variables.

To publish content:

1. Upload immutable, versioned assets to the R2 bucket.
2. Update `data/models.json`, `data/projects.json`, `data/site_settings.json`, or `data/slider_items.json`.
3. Run `python scripts/validate_zero_supabase_data.py`.
4. Run `python -m pytest`.
5. Review the diff.
6. Commit, push, and deploy only after approval.

Local development may still edit JSON/local static files, but those changes are not durable on Vercel.

## Versioned production data

The production-equivalent datasets are:

- `data/models.json`
- `data/projects.json`
- `data/site_settings.json`
- `data/slider_items.json`

Validate counts, relationships, URLs, HTTP responses, and R2 CORS with:

```bash
python scripts/validate_zero_supabase_data.py
```

Historical Supabase setup and migration documents remain under `docs/` for rollback/audit context; they are not part of the runtime architecture.

## Adding Models

For production:

1. Upload the GLB and thumbnail to Cloudflare R2.
2. Add the verified HTTPS URLs to `data/models.json`.
3. Run the validator and test suite.
4. Commit and push to GitHub after approval.

For local-only development, static files under `static/model/` and `static/pic/` remain supported through the local JSON editing paths.

## AR Usage

Open a model page on a supported mobile device and tap the AR button in the viewer. WebXR, Scene Viewer, and Quick Look support depends on the device, operating system, and browser.

## Large File Warning

`.glb` files can be large. Keep production model assets in Cloudflare R2 and store their public URLs in `data/models.json`.

## Admin

On local development, visit `/admin/login` and create an admin password if one is not already configured. Production admin pages are viewers only; all content mutation, upload, generation, and delete endpoints are blocked. Configure `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD` on Vercel if read-only admin access is required.
