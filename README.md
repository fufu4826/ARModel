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
3. Add `SECRET_KEY` in the Vercel project environment variables.
4. Add `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD` in Vercel if admin access is needed after deployment. `ADMIN_PASSWORD_HASH` is preferred.
5. Deploy with the Python runtime.
6. If this project is inside a larger repository, set the Vercel root directory to `ARModel`.

## Adding Models

- Put `.glb` files in `static/model/`.
- Put thumbnails in `static/pic/`.
- Match the thumbnail filename with the model filename when possible, for example `rice.glb` and `rice.jpg`.
- Update `models.json` when metadata such as name, description, project, visibility, or thumbnail path is required.

## AR Usage

Open a model page on a supported mobile device and tap the AR button in the viewer. WebXR, Scene Viewer, and Quick Look support depends on the device, operating system, and browser.

## Large File Warning

`.glb` files can be large. If Vercel deployment fails due to size limits, move model assets to external storage such as Cloudflare R2, Supabase Storage, Firebase Storage, or Cloudinary, then store the external model URLs in `models.json`.

## Admin

The existing admin system is preserved. On local development, visit `/admin/login` and create an admin password if one is not already configured. On Vercel, configure `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD` as an environment variable because serverless file writes are not durable.
