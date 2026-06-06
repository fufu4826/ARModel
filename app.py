import json
import logging
import mimetypes
import os
import re
import secrets
import uuid
import webbrowser
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import Timer
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import abort, flash, Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


MODEL_EXTENSIONS = {".glb"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VERCEL_UPLOAD_MESSAGE = "File uploads are disabled on Vercel. Use an external URL instead."
VERCEL_EDIT_MESSAGE = "Admin editing is read-only on Vercel. Edit JSON locally, commit, and redeploy."
PLACEHOLDER_THUMBNAIL = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'>"
    "<rect width='800' height='500' fill='%23edf1ea'/>"
    "<text x='400' y='250' text-anchor='middle' dominant-baseline='middle' "
    "font-family='Arial,sans-serif' font-size='34' fill='%2366756b'>No image</text>"
    "</svg>"
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_PROJECTS = [
    {
        "id": "wellness",
        "name": "โครงการสมุนไพรและสุขภาพ",
        "description": "นิทรรศการเรียนรู้ผลิตภัณฑ์ภูมิปัญญาด้านสุขภาพของศูนย์ศึกษาการพัฒนาภูพาน",
        "department": "งานสาธารณสุข",
        "cover_image": "pic/lukplakob.JPG",
        "visible": True,
    },
    {
        "id": "garden",
        "name": "โครงการพืชสวนภูพาน",
        "description": "เรียนรู้พืชสวน ผลผลิต และความหลากหลายทางการเกษตรในพื้นที่สกลนคร",
        "department": "งานกิจกรรมพืชสวน",
        "cover_image": "pic/Lychee.jpg",
        "visible": True,
    },
    {
        "id": "rice-and-food",
        "name": "โครงการข้าวและผลิตภัณฑ์แปรรูป",
        "description": "จัดแสดงองค์ความรู้ด้านข้าวและผลิตภัณฑ์อาหารแปรรูปของศูนย์เรียนรู้",
        "department": "งานข้าวและผลิตภัณฑ์แปรรูป",
        "cover_image": "pic/ricephupan.JPG",
        "visible": True,
    },
]

DEFAULT_MODELS = [
    {
        "id": "lukplakob",
        "name": "ลูกประคบ",
        "description": "ผลิตภัณฑ์ภูมิปัญญาด้านสุขภาพสำหรับการเรียนรู้แบบสามมิติ",
        "department": "งานสาธารณสุข",
        "project_id": "wellness",
        "model": "model/lukplakob.glb",
        "image": "pic/lukplakob.JPG",
        "rotate_x": 3.141592653589793,
        "scale": 0.15,
        "visible": True,
    },
    {
        "id": "audtang",
        "name": "ธัญพืชอัดแท่ง",
        "description": "ผลิตภัณฑ์แปรรูปจากถั่วเขียวเพื่อการเรียนรู้ด้านอาหาร",
        "department": "งานผลิตภัณฑ์แปรรูป",
        "project_id": "rice-and-food",
        "model": "model/audtang.glb",
        "image": "pic/audtang.JPG",
        "rotate_x": 0,
        "scale": 0.08,
        "visible": True,
    },
    {
        "id": "lychee",
        "name": "ลิ้นจี่",
        "description": "ตัวอย่างผลผลิตพืชสวนในรูปแบบโมเดลสามมิติ",
        "department": "งานกิจกรรมพืชสวน",
        "project_id": "garden",
        "model": "model/Lychee.glb",
        "image": "pic/Lychee.jpg",
        "rotate_x": 0,
        "scale": 0.25,
        "visible": True,
    },
    {
        "id": "mond",
        "name": "ลูกหม่อน",
        "description": "พืชสวนเพื่อการเรียนรู้และการแปรรูปในท้องถิ่น",
        "department": "งานกิจกรรมพืชสวน",
        "project_id": "garden",
        "model": "model/mond.glb",
        "image": "pic/mond.JPG",
        "rotate_x": 0,
        "scale": 0.06,
        "visible": True,
    },
    {
        "id": "ricephupan",
        "name": "เมล็ดข้าวพันธุ์ภูพาน",
        "description": "โมเดลการเรียนรู้เมล็ดข้าวพันธุ์ภูพาน",
        "department": "งานข้าว",
        "project_id": "rice-and-food",
        "model": "model/ricephupan.glb",
        "image": "pic/ricephupan.JPG",
        "rotate_x": 0,
        "scale": 0.04,
        "visible": True,
    },
]


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ARMODEL_DATA_DIR", BASE_DIR))
STATIC_DIR = Path(os.environ.get("ARMODEL_STATIC_DIR", BASE_DIR / "static"))
MODEL_DIR = STATIC_DIR / "model"
PIC_DIR = STATIC_DIR / "pic"
CATALOG_FILE = DATA_DIR / "models.json"
PROJECTS_FILE = DATA_DIR / "projects.json"
CONFIG_FILE = DATA_DIR / "config.json"
_JSON_CACHE: dict[Path, tuple[float | None, object]] = {}
_DATA_READY = False

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def is_vercel_runtime() -> bool:
    return bool(os.environ.get("VERCEL"))


def is_supabase_enabled() -> bool:
    return bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        and os.environ.get("SUPABASE_STORAGE_BUCKET")
    )


@app.context_processor
def inject_runtime_flags():
    supabase_enabled = is_supabase_enabled()
    return {
        "is_vercel": is_vercel_runtime(),
        "is_supabase": supabase_enabled,
        "uploads_disabled": is_vercel_runtime() and not supabase_enabled,
    }


def ensure_data_files() -> None:
    global _DATA_READY
    if _DATA_READY:
        return
    if is_vercel_runtime():
        _DATA_READY = True
        return
    for directory in (MODEL_DIR, PIC_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Static directory is not writable or cannot be created: %s (%s)", directory, exc)
    _DATA_READY = True


def read_json(path: Path, default):
    path = path.resolve()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        logger.warning("JSON file is missing or unreadable, using defaults: %s", path)
        return deepcopy(default)

    cached = _JSON_CACHE.get(path)
    if cached and cached[0] == mtime:
        return deepcopy(cached[1])

    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in %s, using defaults: %s", path, exc)
        return deepcopy(default)
    except OSError as exc:
        logger.warning("Unable to read JSON file %s, using defaults: %s", path, exc)
        return deepcopy(default)

    if not isinstance(value, type(default)):
        logger.warning("Unexpected JSON shape in %s, using defaults", path)
        return deepcopy(default)

    _JSON_CACHE[path] = (mtime, deepcopy(value))
    return deepcopy(value)


def write_json(path: Path, value) -> None:
    if is_vercel_runtime():
        logger.warning("Blocked JSON write on Vercel runtime: %s", path)
        abort(400, VERCEL_EDIT_MESSAGE)

    path = path.resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
        _JSON_CACHE.pop(path, None)
    except OSError as exc:
        logger.exception("Unable to write JSON file %s", path)
        abort(500, f"Unable to save data: {exc}")


def save_projects(projects: list[dict]) -> None:
    write_json(PROJECTS_FILE, projects)


def save_models(models: list[dict]) -> None:
    write_json(CATALOG_FILE, models)


def normalize_project(project: dict) -> dict:
    name = str(project.get("name") or project.get("project_name") or "โครงการ").strip()
    image_url = str(project.get("image_url") or "").strip()
    image_path = str(project.get("image_path") or project.get("cover_image") or project.get("image") or "").strip()
    return {
        "id": str(project.get("id") or uuid.uuid4().hex),
        "name": name,
        "description": str(project.get("description") or "").strip(),
        "department": str(project.get("department") or project.get("unit") or "").strip(),
        "cover_image": image_url or image_path,
        "image_url": image_url,
        "image_path": image_path,
        "visible": bool(project.get("visible", True)),
    }


def load_projects(include_hidden: bool = True) -> list[dict]:
    ensure_data_files()
    projects = [normalize_project(project) for project in read_json(PROJECTS_FILE, DEFAULT_PROJECTS)]
    if not projects:
        projects = [normalize_project(project) for project in DEFAULT_PROJECTS]
    if include_hidden:
        return projects
    return [project for project in projects if project.get("visible", True)]


def normalize_model(model: dict, projects: list[dict]) -> dict:
    project_ids = {project["id"] for project in projects}
    model_id = str(model.get("id") or uuid.uuid4().hex)
    project_id = str(model.get("project_id") or "").strip()
    if project_id not in project_ids:
        if model_id in {"lukplakob"}:
            project_id = "wellness"
        elif model_id in {"lychee", "mond"}:
            project_id = "garden"
        else:
            project_id = "rice-and-food" if "rice-and-food" in project_ids else (projects[0]["id"] if projects else "")

    try:
        rotate_x = float(model.get("rotate_x") or 0)
        scale = float(model.get("scale") or 0.2)
    except (TypeError, ValueError):
        rotate_x = 0
        scale = 0.2

    model_url = str(model.get("model_url") or "").strip()
    model_path = str(model.get("model_path") or model.get("model") or "").strip()
    thumbnail_url = str(model.get("thumbnail_url") or "").strip()
    thumbnail_path = str(model.get("thumbnail_path") or model.get("image") or model.get("thumbnail") or "").strip()

    return {
        "id": model_id,
        "name": str(model.get("name") or "โมเดล").strip(),
        "description": str(model.get("description") or model.get("info") or "").strip(),
        "department": str(model.get("department") or model.get("unit") or "").strip(),
        "project_id": project_id,
        "model": model_url or model_path,
        "model_url": model_url,
        "model_path": model_path,
        "image": thumbnail_url or thumbnail_path,
        "thumbnail_url": thumbnail_url,
        "thumbnail_path": thumbnail_path,
        "rotate_x": rotate_x,
        "scale": scale,
        "visible": bool(model.get("visible", True)),
    }


def load_models(include_hidden: bool = True) -> list[dict]:
    ensure_data_files()
    projects = load_projects(include_hidden=True)
    models = [normalize_model(model, projects) for model in read_json(CATALOG_FILE, DEFAULT_MODELS)]
    if include_hidden:
        return models
    return [model for model in models if model.get("visible", True)]


def model_with_project(model: dict, projects: list[dict]) -> dict:
    project_map = {project["id"]: project for project in projects}
    project = project_map.get(model.get("project_id"), {})
    enriched = dict(model)
    enriched["project"] = project
    enriched["project_name"] = project.get("name", "-")
    enriched["project_department"] = project.get("department", "")
    enriched["model_resolved_url"] = resolve_model_url(enriched)
    enriched["thumbnail_resolved_url"] = resolve_thumbnail_url(enriched)
    return enriched


def project_with_urls(project: dict, models: list[dict] | None = None) -> dict:
    enriched = dict(project)
    enriched["cover_image_url"] = resolve_project_image_url(enriched, models)
    return enriched


def project_model_counts(projects: list[dict], models: list[dict]) -> dict[str, int]:
    counts = {project["id"]: 0 for project in projects}
    for model in models:
        counts[model.get("project_id")] = counts.get(model.get("project_id"), 0) + 1
    return counts


def find_project(project_id: str, include_hidden: bool = False) -> dict | None:
    for project in get_projects(include_hidden=include_hidden):
        if project.get("id") == project_id:
            return project
    return None


def find_model(model_id: str, include_hidden: bool = False) -> dict | None:
    for model in get_models(include_hidden=include_hidden):
        if model.get("id") == model_id:
            return model
    return None


def load_config() -> dict:
    return read_json(CONFIG_FILE, {})


def save_config(config: dict) -> None:
    write_json(CONFIG_FILE, config)


class SupabaseError(RuntimeError):
    pass


def supabase_base_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def supabase_service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def supabase_bucket() -> str:
    return os.environ.get("SUPABASE_STORAGE_BUCKET", "")


def supabase_headers(content_type: str | None = "application/json") -> dict[str, str]:
    headers = {
        "apikey": supabase_service_key(),
        "Authorization": f"Bearer {supabase_service_key()}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def supabase_request(
    path: str,
    method: str = "GET",
    payload: dict | list | None = None,
    data: bytes | None = None,
    content_type: str | None = "application/json",
    extra_headers: dict[str, str] | None = None,
):
    if not is_supabase_enabled():
        raise SupabaseError("Supabase is not configured.")

    body = data
    headers = supabase_headers(content_type)
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request_obj = Request(f"{supabase_base_url()}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request_obj, timeout=45) as response:
            response_body = response.read()
            if not response_body:
                return None
            content = response_body.decode("utf-8")
            return json.loads(content) if content else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(f"Supabase {method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise SupabaseError(f"Supabase {method} {path} failed: {exc.reason}") from exc
    except OSError as exc:
        raise SupabaseError(f"Supabase {method} {path} failed: {exc}") from exc


def slugify(value: str, fallback: str | None = None) -> str:
    raw = secure_filename(value or "") or (fallback or "")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-_").lower()
    return slug or uuid.uuid4().hex


def normalize_supabase_project(row: dict) -> dict:
    image_url = str(row.get("image_url") or "").strip()
    return {
        "id": str(row.get("id") or uuid.uuid4().hex),
        "slug": str(row.get("slug") or "").strip(),
        "name": str(row.get("name") or "Project").strip(),
        "description": str(row.get("description") or "").strip(),
        "department": "",
        "cover_image": image_url,
        "image_url": image_url,
        "image_path": "",
        "visible": True,
    }


def normalize_supabase_model(row: dict) -> dict:
    model_url = str(row.get("model_url") or "").strip()
    thumbnail_url = str(row.get("thumbnail_url") or "").strip()
    size_mb = row.get("file_size_mb")
    try:
        size_mb = float(size_mb) if size_mb is not None else None
    except (TypeError, ValueError):
        size_mb = None
    return {
        "id": str(row.get("id") or uuid.uuid4().hex),
        "slug": str(row.get("slug") or "").strip(),
        "name": str(row.get("name") or "Model").strip(),
        "description": str(row.get("description") or "").strip(),
        "department": "",
        "project_id": str(row.get("project_id") or "").strip(),
        "model": model_url,
        "model_url": model_url,
        "model_path": "",
        "image": thumbnail_url,
        "thumbnail_url": thumbnail_url,
        "thumbnail_path": "",
        "file_size_mb": size_mb,
        "rotate_x": 0,
        "scale": 0.2,
        "visible": True,
    }


def fetch_supabase_projects() -> list[dict]:
    rows = supabase_request("/rest/v1/projects?select=*&order=created_at.asc") or []
    return [normalize_supabase_project(row) for row in rows]


def fetch_supabase_models() -> list[dict]:
    rows = supabase_request("/rest/v1/models?select=*&order=created_at.asc") or []
    return [normalize_supabase_model(row) for row in rows]


def get_projects(include_hidden: bool = True) -> list[dict]:
    if is_supabase_enabled():
        try:
            return fetch_supabase_projects()
        except SupabaseError as exc:
            logger.warning("Falling back to local projects.json because Supabase read failed: %s", exc)
    return load_projects(include_hidden=include_hidden)


def get_models(include_hidden: bool = True) -> list[dict]:
    if is_supabase_enabled():
        try:
            return fetch_supabase_models()
        except SupabaseError as exc:
            logger.warning("Falling back to local models.json because Supabase read failed: %s", exc)
    return load_models(include_hidden=include_hidden)


def supabase_public_url(object_path: str) -> str:
    return f"{supabase_base_url()}/storage/v1/object/public/{quote(supabase_bucket())}/{quote(object_path, safe='/')}"


def supabase_signed_upload_url(object_path: str) -> str:
    response = supabase_request(
        f"/storage/v1/object/upload/sign/{quote(supabase_bucket())}/{quote(object_path, safe='/')}",
        method="POST",
        payload={},
    )
    upload_url = str((response or {}).get("url") or "").strip()
    if not upload_url:
        raise SupabaseError("Supabase did not return a signed upload URL.")
    if upload_url.startswith("/"):
        return f"{supabase_base_url()}/storage/v1{upload_url}"
    return upload_url


def upload_to_supabase_storage(file_storage, folder: str) -> tuple[str, float | None]:
    if not file_storage or not file_storage.filename:
        return "", None

    allowed_extensions = MODEL_EXTENSIONS if folder == "models" else IMAGE_EXTENSIONS
    extension = Path(file_storage.filename).suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension}")

    filename = unique_asset_name(file_storage.filename, allowed_extensions)
    object_path = f"{folder.strip('/')}/{filename}"
    content_type = file_storage.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    data = file_storage.read()
    file_storage.seek(0)
    if not data:
        abort(400, "Uploaded file is empty")

    supabase_request(
        f"/storage/v1/object/{quote(supabase_bucket())}/{quote(object_path, safe='/')}",
        method="PUT",
        data=data,
        content_type=content_type,
        extra_headers={"Cache-Control": "3600", "x-upsert": "false"},
    )
    return supabase_public_url(object_path), round(len(data) / (1024 * 1024), 2)


def direct_upload_target(filename: str, kind: str) -> tuple[str, str]:
    upload_kinds = {
        "model": ("models", MODEL_EXTENSIONS),
        "thumbnail": ("thumbnails", IMAGE_EXTENSIONS),
        "project_image": ("projects", IMAGE_EXTENSIONS),
    }
    if kind not in upload_kinds:
        abort(400, "Unsupported upload kind")

    folder, allowed_extensions = upload_kinds[kind]
    extension = Path(filename or "").suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension or '(none)'}")

    object_path = f"{folder}/{uuid.uuid4().hex}{extension}"
    return object_path, supabase_public_url(object_path)


def create_project(data: dict) -> dict:
    project_id = data.get("id") or uuid.uuid4().hex
    payload = {
        "id": project_id,
        "slug": data.get("slug") or slugify(data.get("name", ""), project_id),
        "name": data.get("name", "").strip(),
        "description": data.get("description", "").strip(),
        "image_url": data.get("image_url", "").strip(),
    }
    rows = supabase_request(
        "/rest/v1/projects",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_supabase_project(rows[0]) if rows else normalize_supabase_project(payload)


def update_project(project_id: str, data: dict) -> dict:
    payload = {
        "name": data.get("name", "").strip(),
        "description": data.get("description", "").strip(),
        "image_url": data.get("image_url", "").strip(),
    }
    rows = supabase_request(
        f"/rest/v1/projects?id=eq.{quote(project_id)}",
        method="PATCH",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_supabase_project(rows[0]) if rows else normalize_supabase_project({"id": project_id, **payload})


def delete_project(project_id: str) -> None:
    supabase_request(f"/rest/v1/projects?id=eq.{quote(project_id)}", method="DELETE")


def create_model(data: dict) -> dict:
    model_id = data.get("id") or uuid.uuid4().hex
    payload = {
        "id": model_id,
        "project_id": data.get("project_id") or None,
        "slug": data.get("slug") or slugify(data.get("name", ""), model_id),
        "name": data.get("name", "").strip(),
        "description": data.get("description", "").strip(),
        "model_url": data.get("model_url", "").strip(),
        "thumbnail_url": data.get("thumbnail_url", "").strip(),
        "file_size_mb": data.get("file_size_mb"),
    }
    rows = supabase_request(
        "/rest/v1/models",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_supabase_model(rows[0]) if rows else normalize_supabase_model(payload)


def update_model(model_id: str, data: dict) -> dict:
    payload = {
        "project_id": data.get("project_id") or None,
        "name": data.get("name", "").strip(),
        "description": data.get("description", "").strip(),
        "model_url": data.get("model_url", "").strip(),
        "thumbnail_url": data.get("thumbnail_url", "").strip(),
        "file_size_mb": data.get("file_size_mb"),
    }
    rows = supabase_request(
        f"/rest/v1/models?id=eq.{quote(model_id)}",
        method="PATCH",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_supabase_model(rows[0]) if rows else normalize_supabase_model({"id": model_id, **payload})


def delete_model(model_id: str) -> None:
    supabase_request(f"/rest/v1/models?id=eq.{quote(model_id)}", method="DELETE")


def admin_write_blocked_on_vercel() -> bool:
    if not is_vercel_runtime() or is_supabase_enabled():
        return False
    flash(VERCEL_EDIT_MESSAGE, "error")
    return True


def upload_attempted(*field_names: str) -> bool:
    for field_name in field_names:
        file_storage = request.files.get(field_name)
        if file_storage and file_storage.filename:
            return True
    return False


def reject_vercel_upload_if_needed(*field_names: str) -> bool:
    if is_vercel_runtime() and not is_supabase_enabled() and upload_attempted(*field_names):
        flash(VERCEL_UPLOAD_MESSAGE, "error")
        return True
    return False


def ensure_secret_key() -> str:
    env_secret = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
    if env_secret:
        return env_secret

    config = load_config()
    secret_key = str(config.get("secret_key") or "").strip()
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        logger.warning("No SECRET_KEY configured; using an ephemeral runtime secret.")
    return secret_key


def strip_static_prefix(path_value: str | None) -> str:
    value = str(path_value or "").strip().replace("\\", "/")
    if value.startswith("/static/"):
        return value.removeprefix("/static/")
    if value.startswith("static/"):
        return value.removeprefix("static/")
    return value


def is_external_url(path_value: str | None) -> bool:
    value = str(path_value or "").strip().lower()
    return value.startswith(("http://", "https://", "http//", "https//", "data:"))


def static_asset_url(path_value: str | None) -> str:
    value = str(path_value or "").strip()
    if not value:
        return ""
    if is_external_url(value):
        return value
    return url_for("static", filename=strip_static_prefix(value))


def local_static_url_if_exists(path_value: str | None) -> str:
    value = strip_static_prefix(path_value)
    if not value:
        return ""
    target = static_asset_path(value)
    if not target or not target.exists() or not target.is_file():
        logger.warning("Missing static asset referenced by metadata: %s", path_value)
        return ""
    return url_for("static", filename=value)


def resolve_model_url(model: dict) -> str:
    for key in ("model_url", "model"):
        value = str(model.get(key) or "").strip()
        if is_external_url(value):
            return value
    return local_static_url_if_exists(model.get("model_path") or model.get("model"))


def resolve_thumbnail_url(model: dict) -> str:
    for key in ("thumbnail_url", "image"):
        value = str(model.get(key) or "").strip()
        if is_external_url(value):
            return value
    resolved = local_static_url_if_exists(
        model.get("thumbnail_path") or model.get("image") or find_thumbnail_for_model(model.get("model_path") or model.get("model"))
    )
    return resolved or PLACEHOLDER_THUMBNAIL


def resolve_project_image_url(project: dict, models: list[dict] | None = None) -> str:
    for key in ("image_url", "cover_image"):
        value = str(project.get(key) or "").strip()
        if is_external_url(value):
            return value
    resolved = local_static_url_if_exists(project.get("image_path") or project.get("cover_image"))
    if resolved:
        return resolved
    for model in models or []:
        if model.get("project_id") == project.get("id"):
            thumbnail_url = resolve_thumbnail_url(model)
            if thumbnail_url:
                return thumbnail_url
            break
    return resolved or PLACEHOLDER_THUMBNAIL


def static_asset_path(path_value: str | None) -> Path | None:
    value = strip_static_prefix(path_value)
    if not value or is_external_url(value):
        return None
    target = (STATIC_DIR / value).resolve()
    static_root = STATIC_DIR.resolve()
    if target == static_root or static_root not in target.parents:
        return None
    return target


def file_size_mb(path_value: str | None) -> float | None:
    if is_external_url(path_value):
        return None
    target = static_asset_path(path_value)
    if not target or not target.exists() or not target.is_file():
        logger.info("Model file is missing or external; size unavailable: %s", path_value)
        return None
    return round(target.stat().st_size / (1024 * 1024), 2)


def model_size_mb(model: dict) -> float | None:
    if model.get("file_size_mb") is not None:
        try:
            return round(float(model.get("file_size_mb")), 2)
        except (TypeError, ValueError):
            return None
    return file_size_mb(model.get("model_path") or model.get("model"))


def find_thumbnail_for_model(model_path: str | None) -> str:
    if not model_path:
        return ""
    model_stem = Path(strip_static_prefix(model_path)).stem.lower()
    if not model_stem or not PIC_DIR.exists():
        return ""
    try:
        images = PIC_DIR.iterdir()
    except OSError as exc:
        logger.warning("Unable to scan thumbnail directory %s: %s", PIC_DIR, exc)
        return ""
    for image in images:
        if image.is_file() and image.suffix.lower() in IMAGE_EXTENSIONS and image.stem.lower() == model_stem:
            return f"pic/{image.name}"
    return ""


def models_from_filesystem(projects: list[dict]) -> list[dict]:
    if not MODEL_DIR.exists():
        return []
    project_id = projects[0]["id"] if projects else ""
    models = []
    try:
        model_files = sorted(MODEL_DIR.iterdir())
    except OSError as exc:
        logger.warning("Unable to scan model directory %s: %s", MODEL_DIR, exc)
        return []
    for model_file in model_files:
        if not model_file.is_file() or model_file.suffix.lower() not in MODEL_EXTENSIONS:
            continue
        model_path = f"model/{model_file.name}"
        models.append(
            {
                "id": model_file.stem,
                "name": model_file.stem.replace("-", " ").replace("_", " ").title(),
                "description": "",
                "department": "",
                "project_id": project_id,
                "model": model_path,
                "image": find_thumbnail_for_model(model_path),
                "rotate_x": 0,
                "scale": 0.2,
                "visible": True,
            }
        )
    return models


def api_model_payload(model: dict, projects: list[dict]) -> dict:
    enriched = model_with_project(model, projects)
    return {
        "id": enriched.get("id", ""),
        "name": enriched.get("name", ""),
        "description": enriched.get("description", ""),
        "model_url": resolve_model_url(enriched),
        "thumbnail_url": resolve_thumbnail_url(enriched),
        "project_id": enriched.get("project_id", ""),
        "project_name": enriched.get("project_name", ""),
        "size_mb": model_size_mb(enriched),
    }


app.secret_key = ensure_secret_key()


def admin_password_configured() -> bool:
    config = load_config()
    return bool(
        os.environ.get("ADMIN_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD_HASH")
        or config.get("admin_password_hash")
    )


def verify_admin_password(password: str) -> bool:
    config = load_config()
    env_password = os.environ.get("ADMIN_PASSWORD")
    if env_password is not None:
        return secrets.compare_digest(password, env_password)

    password_hash = os.environ.get("ADMIN_PASSWORD_HASH") or config.get("admin_password_hash")
    return bool(password_hash and check_password_hash(password_hash, password))


def save_admin_password(password: str) -> None:
    if is_vercel_runtime():
        abort(400, VERCEL_EDIT_MESSAGE)
    config = load_config()
    config["admin_password_hash"] = generate_password_hash(password)
    save_config(config)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def safe_redirect_target(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("admin")
    return target


def unique_asset_name(original_name: str, allowed_extensions: set[str]) -> str:
    extension = Path(original_name).suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension}")
    stem = secure_filename(Path(original_name).stem) or "asset"
    return f"{stem}-{uuid.uuid4().hex[:8]}{extension}"


def delete_static_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    if is_external_url(relative_path):
        return

    target = static_asset_path(relative_path)
    static_root = STATIC_DIR.resolve()
    if target is None or static_root not in target.parents:
        abort(400, "Invalid file path")
    try:
        if target.exists() and target.is_file():
            target.unlink()
    except OSError as exc:
        logger.exception("Unable to delete static file %s", target)
        abort(500, f"Unable to delete file: {exc}")


def save_upload(file_storage, directory: Path, relative_folder: str, allowed_extensions: set[str]) -> str:
    if not file_storage or not file_storage.filename:
        return ""
    asset_name = unique_asset_name(file_storage.filename, allowed_extensions)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_storage.save(directory / asset_name)
    except OSError as exc:
        logger.exception("Unable to save uploaded file %s", asset_name)
        abort(500, f"Unable to save uploaded file: {exc}")
    return f"{relative_folder}/{asset_name}"


def form_visible() -> bool:
    if "visible" not in request.form:
        return False
    return request.form.get("visible") in {"1", "true", "on", "yes"}


def parse_float(name: str, default: float) -> float:
    try:
        return float(request.form.get(name) or default)
    except ValueError:
        abort(400, f"{name} must be a number")


@app.route("/")
def index():
    models = get_models(include_hidden=False)
    projects = [project_with_urls(project, models) for project in get_projects(include_hidden=False)]
    counts = project_model_counts(projects, models)
    return render_template("index.html", projects=projects, model_counts=counts)


@app.route("/projects/<project_id>")
def project_detail(project_id: str):
    project = find_project(project_id)
    if project is None:
        abort(404)
    projects = get_projects(include_hidden=False)
    models = [
        model_with_project(model, projects)
        for model in get_models(include_hidden=False)
        if model.get("project_id") == project_id
    ]
    project = project_with_urls(project, models)
    return render_template("project.html", project=project, models=models)


@app.route("/models/<model_id>")
def model_detail(model_id: str):
    model = find_model(model_id)
    if model is None:
        abort(404)
    projects = get_projects(include_hidden=False)
    model = model_with_project(model, projects)
    related_models = []
    for item in get_models(include_hidden=False):
        if item.get("project_id") != model.get("project_id") or item.get("id") == model.get("id"):
            continue
        related = model_with_project(item, projects)
        related["model_url"] = resolve_model_url(related)
        related["thumbnail_url"] = resolve_thumbnail_url(related)
        related["size_mb"] = model_size_mb(related)
        related_models.append(related)
        if len(related_models) >= 4:
            break
    return render_template(
        "model_view.html",
        model=model,
        model_url=resolve_model_url(model),
        thumbnail_url=resolve_thumbnail_url(model),
        model_name=model.get("name", ""),
        size_mb=model_size_mb(model),
        related_models=related_models,
        mode=request.args.get("mode", "3d"),
    )


@app.get("/api/models")
def api_models():
    projects = get_projects(include_hidden=True)
    models = get_models(include_hidden=True)
    known_paths = {strip_static_prefix(model.get("model")).lower() for model in models if model.get("model")}
    if not is_supabase_enabled():
        for filesystem_model in models_from_filesystem(projects):
            if strip_static_prefix(filesystem_model.get("model")).lower() not in known_paths:
                models.append(normalize_model(filesystem_model, projects))
    return jsonify([api_model_payload(model, projects) for model in models])


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/admin")
@admin_required
def admin():
    raw_projects = get_projects(include_hidden=True)
    raw_models = get_models(include_hidden=True)
    projects = [project_with_urls(project, raw_models) for project in raw_projects]
    models = [model_with_project(model, projects) for model in raw_models]
    counts = project_model_counts(projects, models)
    return render_template("admin.html", projects=projects, models=models, model_counts=counts)


@app.post("/admin/api/create-upload-url")
@admin_required
def create_admin_upload_url():
    if not is_supabase_enabled():
        abort(400, "Supabase is not configured.")
    if admin_write_blocked_on_vercel():
        abort(403, "Admin uploads are disabled.")

    payload = request.get_json(silent=True) or {}
    filename = str(payload.get("filename") or "").strip()
    kind = str(payload.get("kind") or "").strip()
    if not filename:
        abort(400, "filename is required")

    object_path, public_url = direct_upload_target(filename, kind)
    try:
        upload_url = supabase_signed_upload_url(object_path)
    except SupabaseError as exc:
        logger.exception("Unable to create Supabase signed upload URL")
        abort(502, f"Unable to create upload URL: {exc}")

    return jsonify(
        {
            "upload_url": upload_url,
            "public_url": public_url,
            "path": object_path,
        }
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    first_run = not admin_password_configured()
    next_url = safe_redirect_target(request.args.get("next"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if first_run:
            if len(password) < 8:
                flash("รหัสผ่านผู้ดูแลต้องมีอย่างน้อย 8 ตัวอักษร", "error")
            elif password != confirm:
                flash("รหัสผ่านยืนยันไม่ตรงกัน", "error")
            elif is_vercel_runtime():
                flash(VERCEL_EDIT_MESSAGE, "error")
            else:
                save_admin_password(password)
                session["admin"] = True
                flash("ตั้งค่ารหัสผ่านผู้ดูแลแล้ว", "success")
                return redirect(next_url)
        elif verify_admin_password(password):
            session["admin"] = True
            return redirect(next_url)
        else:
            flash("รหัสผ่านไม่ถูกต้อง", "error")

    return render_template("login.html", first_run=first_run)


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("ออกจากระบบผู้ดูแลแล้ว", "success")
    return redirect(url_for("index"))


@app.post("/admin/projects")
@admin_required
def add_project():
    if reject_vercel_upload_if_needed("cover_image") or admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    name = request.form.get("name", "").strip()
    if not name:
        abort(400, "Project name is required")

    image_url = request.form.get("image_url", "").strip()
    if is_supabase_enabled():
        try:
            uploaded_image_url, _ = upload_to_supabase_storage(request.files.get("cover_image"), "projects")
            create_project(
                {
                    "name": name,
                    "description": request.form.get("description", "").strip(),
                    "image_url": uploaded_image_url or image_url,
                }
            )
            flash(f'เพิ่มโครงการ "{name}" แล้ว', "success")
        except SupabaseError as exc:
            logger.exception("Unable to create project in Supabase")
            flash(f"Unable to save project to Supabase: {exc}", "error")
        return redirect(url_for("admin"))

    cover_image = image_url or save_upload(request.files.get("cover_image"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
    projects = load_projects(include_hidden=True)
    projects.append(
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": request.form.get("description", "").strip(),
            "department": request.form.get("department", "").strip(),
            "cover_image": cover_image,
            "image_url": image_url,
            "image_path": "" if image_url else cover_image,
            "visible": form_visible(),
        }
    )
    save_projects(projects)
    flash(f'เพิ่มโครงการ "{name}" แล้ว', "success")
    return redirect(url_for("admin"))


@app.route("/admin/projects/<project_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_project(project_id: str):
    projects = get_projects(include_hidden=True)
    project = next((item for item in projects if item["id"] == project_id), None)
    if project is None:
        abort(404)

    if request.method == "POST":
        if reject_vercel_upload_if_needed("cover_image") or admin_write_blocked_on_vercel():
            return redirect(url_for("edit_project", project_id=project_id))

        if is_supabase_enabled():
            try:
                uploaded_image_url, _ = upload_to_supabase_storage(request.files.get("cover_image"), "projects")
                image_url = uploaded_image_url or request.form.get("image_url", "").strip() or project.get("image_url", "")
                update_project(
                    project_id,
                    {
                        "name": request.form.get("name", "").strip() or project["name"],
                        "description": request.form.get("description", "").strip(),
                        "image_url": image_url,
                    },
                )
                flash("บันทึกข้อมูลโครงการแล้ว", "success")
                return redirect(url_for("admin"))
            except SupabaseError as exc:
                logger.exception("Unable to update project in Supabase")
                flash(f"Unable to save project to Supabase: {exc}", "error")
                return redirect(url_for("edit_project", project_id=project_id))

        old_cover = project.get("cover_image")
        image_url = request.form.get("image_url", "").strip()
        new_cover = image_url or save_upload(request.files.get("cover_image"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
        project.update(
            {
                "name": request.form.get("name", "").strip() or project["name"],
                "description": request.form.get("description", "").strip(),
                "department": request.form.get("department", "").strip(),
                "cover_image": new_cover or old_cover,
                "image_url": image_url,
                "image_path": "" if image_url else (new_cover or project.get("image_path") or old_cover),
                "visible": form_visible(),
            }
        )
        if new_cover and old_cover and not image_url:
            delete_static_file(old_cover)
        save_projects(projects)
        flash("บันทึกข้อมูลโครงการแล้ว", "success")
        return redirect(url_for("admin"))

    return render_template("edit_project.html", project=project_with_urls(project))


@app.post("/admin/projects/<project_id>/delete", endpoint="delete_project")
@admin_required
def delete_project_route(project_id: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    if is_supabase_enabled():
        try:
            delete_project(project_id)
            flash("ลบโครงการแล้ว", "success")
        except SupabaseError as exc:
            logger.exception("Unable to delete project in Supabase")
            flash(f"Unable to delete project from Supabase: {exc}", "error")
        return redirect(url_for("admin"))

    projects = load_projects(include_hidden=True)
    project = next((item for item in projects if item["id"] == project_id), None)
    if project is None:
        abort(404)

    models = load_models(include_hidden=True)
    linked_models = [model for model in models if model.get("project_id") == project_id]
    for model in linked_models:
        delete_static_file(model.get("model"))
        delete_static_file(model.get("image"))
    models = [model for model in models if model.get("project_id") != project_id]
    projects = [item for item in projects if item["id"] != project_id]
    delete_static_file(project.get("cover_image"))
    save_models(models)
    save_projects(projects)
    flash(f'ลบโครงการ "{project.get("name", "")}" และโมเดลในโครงการแล้ว', "success")
    return redirect(url_for("admin"))


@app.post("/admin/models")
@admin_required
def add_model():
    if reject_vercel_upload_if_needed("model_file", "image_file") or admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    name = request.form.get("name", "").strip()
    project_id = request.form.get("project_id", "").strip()
    if not name:
        abort(400, "Model name is required")
    if find_project(project_id, include_hidden=True) is None:
        abort(400, "Project is required")

    model_url = request.form.get("model_url", "").strip()
    thumbnail_url = request.form.get("thumbnail_url", "").strip()

    if is_supabase_enabled():
        try:
            uploaded_model_url, model_size_mb = upload_to_supabase_storage(request.files.get("model_file"), "models")
            uploaded_thumbnail_url, _ = upload_to_supabase_storage(request.files.get("image_file"), "thumbnails")
            final_model_url = uploaded_model_url or model_url
            final_thumbnail_url = uploaded_thumbnail_url or thumbnail_url
            if not final_model_url:
                abort(400, "A .glb file or external model URL is required")
            create_model(
                {
                    "name": name,
                    "description": request.form.get("description", "").strip(),
                    "project_id": project_id,
                    "model_url": final_model_url,
                    "thumbnail_url": final_thumbnail_url,
                    "file_size_mb": model_size_mb,
                }
            )
            flash(f'เพิ่มโมเดล "{name}" แล้ว', "success")
        except SupabaseError as exc:
            logger.exception("Unable to create model in Supabase")
            flash(f"Unable to save model to Supabase: {exc}", "error")
        return redirect(url_for("admin"))

    model_path = model_url or request.form.get("model_path", "").strip()
    uploaded_model = save_upload(request.files.get("model_file"), MODEL_DIR, "model", MODEL_EXTENSIONS)
    if uploaded_model:
        model_path = uploaded_model
    if not model_path:
        abort(400, "A .glb/.gltf file or model path is required")

    image_path = thumbnail_url or request.form.get("image_path", "").strip()
    uploaded_image = save_upload(request.files.get("image_file"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
    if uploaded_image:
        image_path = uploaded_image

    models = load_models(include_hidden=True)
    models.append(
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": request.form.get("description", "").strip(),
            "department": request.form.get("department", "").strip(),
            "project_id": project_id,
            "model": model_path,
            "model_url": model_url,
            "model_path": "" if model_url else model_path,
            "image": image_path,
            "thumbnail_url": thumbnail_url,
            "thumbnail_path": "" if thumbnail_url else image_path,
            "rotate_x": parse_float("rotate_x", 0),
            "scale": parse_float("scale", 0.2),
            "visible": form_visible(),
        }
    )
    save_models(models)
    flash(f'เพิ่มโมเดล "{name}" แล้ว', "success")
    return redirect(url_for("admin"))


@app.route("/admin/models/<model_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_model(model_id: str):
    projects = get_projects(include_hidden=True)
    models = get_models(include_hidden=True)
    model = next((item for item in models if item["id"] == model_id), None)
    if model is None:
        abort(404)

    if request.method == "POST":
        if reject_vercel_upload_if_needed("model_file", "image_file") or admin_write_blocked_on_vercel():
            return redirect(url_for("edit_model", model_id=model_id))

        project_id = request.form.get("project_id", "").strip()
        if find_project(project_id, include_hidden=True) is None:
            abort(400, "Project is required")

        if is_supabase_enabled():
            try:
                uploaded_model_url, uploaded_size_mb = upload_to_supabase_storage(request.files.get("model_file"), "models")
                uploaded_thumbnail_url, _ = upload_to_supabase_storage(request.files.get("image_file"), "thumbnails")
                final_model_url = uploaded_model_url or request.form.get("model_url", "").strip() or model.get("model_url", "")
                final_thumbnail_url = (
                    uploaded_thumbnail_url
                    or request.form.get("thumbnail_url", "").strip()
                    or model.get("thumbnail_url", "")
                )
                if not final_model_url:
                    abort(400, "A .glb file or external model URL is required")
                update_model(
                    model_id,
                    {
                        "name": request.form.get("name", "").strip() or model["name"],
                        "description": request.form.get("description", "").strip(),
                        "project_id": project_id,
                        "model_url": final_model_url,
                        "thumbnail_url": final_thumbnail_url,
                        "file_size_mb": uploaded_size_mb if uploaded_size_mb is not None else model.get("file_size_mb"),
                    },
                )
                flash("บันทึกข้อมูลโมเดลแล้ว", "success")
                return redirect(url_for("admin"))
            except SupabaseError as exc:
                logger.exception("Unable to update model in Supabase")
                flash(f"Unable to save model to Supabase: {exc}", "error")
                return redirect(url_for("edit_model", model_id=model_id))

        old_model = model.get("model")
        old_image = model.get("image")
        new_model = save_upload(request.files.get("model_file"), MODEL_DIR, "model", MODEL_EXTENSIONS)
        new_image = save_upload(request.files.get("image_file"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
        model_url = request.form.get("model_url", "").strip()
        thumbnail_url = request.form.get("thumbnail_url", "").strip()
        manual_model_path = model_url or request.form.get("model_path", "").strip()
        manual_image_path = thumbnail_url or request.form.get("image_path", "").strip()

        model.update(
            {
                "name": request.form.get("name", "").strip() or model["name"],
                "description": request.form.get("description", "").strip(),
                "department": request.form.get("department", "").strip(),
                "project_id": project_id,
                "model": new_model or manual_model_path or old_model,
                "model_url": model_url,
                "model_path": "" if model_url else (new_model or manual_model_path or model.get("model_path") or old_model),
                "image": new_image or manual_image_path or old_image,
                "thumbnail_url": thumbnail_url,
                "thumbnail_path": "" if thumbnail_url else (new_image or manual_image_path or model.get("thumbnail_path") or old_image),
                "rotate_x": parse_float("rotate_x", 0),
                "scale": parse_float("scale", 0.2),
                "visible": form_visible(),
            }
        )
        if new_model and old_model:
            delete_static_file(old_model)
        if new_image and old_image:
            delete_static_file(old_image)
        save_models(models)
        flash("บันทึกข้อมูลโมเดลแล้ว", "success")
        return redirect(url_for("admin"))

    return render_template("edit_model.html", model=model_with_project(model, projects), projects=projects)


@app.post("/admin/models/<model_id>/delete", endpoint="delete_model")
@admin_required
def delete_model_route(model_id: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    if is_supabase_enabled():
        try:
            delete_model(model_id)
            flash("ลบโมเดลแล้ว", "success")
        except SupabaseError as exc:
            logger.exception("Unable to delete model in Supabase")
            flash(f"Unable to delete model from Supabase: {exc}", "error")
        return redirect(url_for("admin"))

    models = load_models(include_hidden=True)
    deleted = next((item for item in models if item["id"] == model_id), None)
    if deleted is None:
        abort(404)

    delete_static_file(deleted.get("model"))
    delete_static_file(deleted.get("image"))
    save_models([model for model in models if model["id"] != model_id])
    flash(f'ลบโมเดล "{deleted.get("name", "")}" แล้ว', "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    ensure_data_files()
    logger.info("Runtime data: %s", DATA_DIR)
    logger.info("Static folder: %s", STATIC_DIR)
    port = int(os.environ.get("PORT", "5000"))
    if not os.environ.get("WERKZEUG_RUN_MAIN") and not os.environ.get("NO_BROWSER"):
        Timer(1.0, webbrowser.open_new, args=(f"http://127.0.0.1:{port}",)).start()
    app.run(host="0.0.0.0", port=port, debug=False)
