import argparse
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MODEL_EXTENSIONS = {".glb"}


class SupabaseError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


SUPABASE_URL = require_env("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = require_env("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = require_env("SUPABASE_STORAGE_BUCKET")


def headers(content_type: str | None = "application/json") -> dict[str, str]:
    result = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if content_type:
        result["Content-Type"] = content_type
    return result


def supabase_request(
    path: str,
    method: str = "GET",
    payload: dict | list | None = None,
    data: bytes | None = None,
    content_type: str | None = "application/json",
    extra_headers: dict[str, str] | None = None,
):
    body = data
    request_headers = headers(content_type)
    if extra_headers:
        request_headers.update(extra_headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request_obj = Request(f"{SUPABASE_URL}{path}", data=body, headers=request_headers, method=method)
    try:
        with urlopen(request_obj, timeout=60) as response:
            response_body = response.read()
            if not response_body:
                return None
            return json.loads(response_body.decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise SupabaseError(f"{method} {path} failed: {exc.reason}") from exc


def slugify(value: str, fallback: str) -> str:
    raw = secure_filename(value or "") or fallback
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-_").lower()
    return slug or fallback


def strip_static_prefix(path_value: str | None) -> str:
    value = str(path_value or "").strip().replace("\\", "/")
    if value.startswith("/static/"):
        return value.removeprefix("/static/")
    if value.startswith("static/"):
        return value.removeprefix("static/")
    return value


def is_external_url(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(("http://", "https://"))


def public_url(object_path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_STORAGE_BUCKET)}/{quote(object_path, safe='/')}"


def upload_file(relative_path: str, folder: str, allowed_extensions: set[str]) -> tuple[str, float | None]:
    if is_external_url(relative_path):
        return relative_path, None

    relative_path = strip_static_prefix(relative_path)
    source = STATIC_DIR / relative_path
    if not source.exists() or not source.is_file():
        print(f"Skipping missing asset: {relative_path}")
        return "", None

    extension = source.suffix.lower()
    if extension not in allowed_extensions:
        print(f"Skipping unsupported asset: {relative_path}")
        return "", None

    safe_stem = secure_filename(source.stem) or "asset"
    object_path = f"{folder}/{safe_stem}-{uuid.uuid4().hex[:8]}{extension}"
    data = source.read_bytes()
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    supabase_request(
        f"/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET)}/{quote(object_path, safe='/')}",
        method="PUT",
        data=data,
        content_type=content_type,
        extra_headers={"Cache-Control": "3600", "x-upsert": "false"},
    )
    return public_url(object_path), round(len(data) / (1024 * 1024), 2)


def upsert_project(project: dict, upload_assets: bool) -> None:
    project_id = str(project.get("id") or uuid.uuid4().hex)
    image_value = str(project.get("image_url") or project.get("cover_image") or project.get("image") or "").strip()
    image_url = image_value
    if upload_assets and image_value and not is_external_url(image_value):
        image_url, _ = upload_file(image_value, "projects", IMAGE_EXTENSIONS)

    payload = {
        "id": project_id,
        "slug": str(project.get("slug") or slugify(project.get("name", ""), project_id)),
        "name": str(project.get("name") or "Project").strip(),
        "description": str(project.get("description") or "").strip(),
        "image_url": image_url if is_external_url(image_url) else "",
    }
    supabase_request(
        "/rest/v1/projects",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )
    print(f"Upserted project: {payload['name']}")


def upsert_model(model: dict, upload_assets: bool) -> None:
    model_id = str(model.get("id") or uuid.uuid4().hex)
    model_value = str(model.get("model_url") or model.get("model") or model.get("model_path") or "").strip()
    thumb_value = str(model.get("thumbnail_url") or model.get("image") or model.get("thumbnail") or "").strip()

    model_url = model_value
    file_size_mb = None
    if upload_assets and model_value and not is_external_url(model_value):
        model_url, file_size_mb = upload_file(model_value, "models", MODEL_EXTENSIONS)

    thumbnail_url = thumb_value
    if upload_assets and thumb_value and not is_external_url(thumb_value):
        thumbnail_url, _ = upload_file(thumb_value, "thumbnails", IMAGE_EXTENSIONS)

    payload = {
        "id": model_id,
        "project_id": str(model.get("project_id") or "").strip() or None,
        "slug": str(model.get("slug") or slugify(model.get("name", ""), model_id)),
        "name": str(model.get("name") or "Model").strip(),
        "description": str(model.get("description") or "").strip(),
        "model_url": model_url if is_external_url(model_url) else "",
        "thumbnail_url": thumbnail_url if is_external_url(thumbnail_url) else "",
        "file_size_mb": file_size_mb,
    }
    supabase_request(
        "/rest/v1/models",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )
    print(f"Upserted model: {payload['name']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate ARModel JSON metadata to Supabase.")
    parser.add_argument("--upload-assets", action="store_true", help="Upload local static assets to Supabase Storage.")
    args = parser.parse_args()

    projects = json.loads((BASE_DIR / "projects.json").read_text(encoding="utf-8"))
    models = json.loads((BASE_DIR / "models.json").read_text(encoding="utf-8"))

    for project in projects:
        upsert_project(project, args.upload_assets)
    for model in models:
        upsert_model(model, args.upload_assets)

    print("Migration complete.")


if __name__ == "__main__":
    main()
