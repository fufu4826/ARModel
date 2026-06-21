import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import uuid
import wave
import webbrowser
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import Timer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from flask import abort, flash, Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


MODEL_EXTENSIONS = {".glb"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg"}
SITE_LOGO_EXTENSIONS = IMAGE_EXTENSIONS | {".svg"}
FAVICON_EXTENSIONS = {".png", ".ico", ".svg"}
SITE_ASSET_MAX_BYTES = 5 * 1024 * 1024
NARRATION_AUDIO_MAX_BYTES = 20 * 1024 * 1024
VERCEL_UPLOAD_MESSAGE = "ระบบไม่รองรับการอัปโหลดไฟล์โดยตรงบน Vercel กรุณาระบุรูปภาพหรือไฟล์โมเดลผ่านลิงก์เว็บภายนอก (URL)"
VERCEL_EDIT_MESSAGE = "ระบบแอดมินทำงานในโหมดอ่านอย่างเดียวบน Vercel (ไม่รองรับการเขียนไฟล์บนคลาวด์) กรุณาแก้ไขไฟล์ข้อมูลภายในเครื่อง แล้ว Commit และ Deploy ใหม่ หรือกำหนดค่าเชื่อมต่อ Supabase ก่อนใช้งาน"
UNASSIGNED_PROJECT_LABEL = "ยังไม่ได้จัดอยู่ในโครงการ"
PUBLIC_SITE_URL = (
    os.environ.get("SITE_BASE_URL")
    or os.environ.get("PUBLIC_SITE_URL")
    or "https://phuphan-ar.vercel.app"
).rstrip("/")
DEFAULT_META_TITLE = "ภูพาน AR สกลนคร | ศูนย์ศึกษาการพัฒนาภูพาน"
DEFAULT_META_DESCRIPTION = (
    "สำรวจศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ จังหวัดสกลนคร "
    "ผ่านโมเดล 3D และ AR รวมวัตถุ ผลิตภัณฑ์ ภูมิปัญญา และของดีสกลนครในรูปแบบดิจิทัล"
)
DEFAULT_META_KEYWORDS = (
    "ภูพาน, พูพาน, ภูพาน สกลนคร, พูพาน สกลนคร, ศูนย์ศึกษาการพัฒนาภูพาน, "
    "ศูนย์ภูพาน, สกลนคร, สกล, ของดีสกลนคร, โมเดล 3D, AR, AR สกลนคร, "
    "Phu Phan, PhuPhan AR, Sakon Nakhon"
)
DEFAULT_META_IMAGE_PATH = "pic/og-cover.jpg"
DEFAULT_SITE_SETTINGS = {
    "landing_cover": DEFAULT_META_IMAGE_PATH,
    "landing_mobile_cover_image": "",
    "landing_headline": "ภูพาน AR สกลนคร",
    "landing_subheadline": "เรียนรู้ศูนย์ศึกษาการพัฒนาภูพานผ่านโมเดล 3D และ AR",
    "landing_description": (
        "เว็บไซต์รวบรวมวัตถุ ผลิตภัณฑ์ องค์ความรู้ และของดีสกลนครจาก"
        "ศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ บ้านนานกเค้า "
        "ตำบลห้วยยาง อำเภอเมือง จังหวัดสกลนคร ในรูปแบบโมเดลสามมิติและเทคโนโลยี AR"
    ),
    "landing_cta_text": "เข้าสู่เว็บไซต์",
    "landing_cta_url": "/home",
    "home_hero_badge": "นิทรรศการดิจิทัล 3D / AR",
    "home_hero_heading": "ศูนย์ศึกษาการพัฒนาภูพาน",
    "home_hero_subheading": "โมเดล 3D และ AR ของภูพาน สกลนคร",
    "home_hero_description": "เลือกชมโมเดล 3D หมุนดูรายละเอียด และเปิด AR บนอุปกรณ์ที่รองรับเพื่อวางโมเดลในพื้นที่จริง",
    "home_hero_primary_cta_text": "เริ่มชมโมเดล 3D",
    "home_hero_secondary_cta_text": "ดูแหล่งเรียนรู้ทั้งหมด",
    "intro_enabled": "false",
    "intro_logo_1": "",
    "intro_logo_2": "",
    "intro_logo_3": "",
    "intro_logo_duration_ms": "1400",
    "intro_display_mode": "sequence",
    "site_logo": "",
    "site_name": "PhuPhan-AR | ภูพาน AR สกลนคร",
    "site_social_image": "",
    "favicon": "favicon.ico",
    "meta_description": DEFAULT_META_DESCRIPTION,
}
DEFAULT_SLIDER_ITEMS = []
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
AUDIO_DIR = STATIC_DIR / "audio"
CATALOG_FILE = DATA_DIR / "models.json"
PROJECTS_FILE = DATA_DIR / "projects.json"
CONFIG_FILE = DATA_DIR / "config.json"
SITE_SETTINGS_FILE = DATA_DIR / "site_settings.json"
SLIDER_ITEMS_FILE = DATA_DIR / "slider_items.json"
SITE_UPLOAD_DIR = STATIC_DIR / "uploads" / "site"
SLIDER_UPLOAD_DIR = STATIC_DIR / "uploads" / "sliders"
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


def public_absolute_url(path_or_url: str | None) -> str:
    value = str(path_or_url or "").strip()
    if not value:
        return ""
    if is_external_url(value):
        return value
    if not value.startswith("/"):
        value = f"/{value}"
    return f"{PUBLIC_SITE_URL}{value}"


def public_url_for(endpoint: str, **values) -> str:
    return public_absolute_url(url_for(endpoint, **values))


def public_meta_image_url(path_or_url: str | None) -> str:
    value = str(path_or_url or "").strip()
    if not value or value.lower().startswith("data:"):
        return public_absolute_url(url_for("static", filename=DEFAULT_META_IMAGE_PATH))
    return public_absolute_url(value)


@app.context_processor
def inject_runtime_flags():
    supabase_enabled = is_supabase_enabled()
    settings = get_site_settings()
    public_settings = site_settings_with_urls(settings)
    return {
        "is_vercel": is_vercel_runtime(),
        "is_supabase": supabase_enabled,
        "uploads_disabled": is_vercel_runtime() and not supabase_enabled,
        "default_meta_title": DEFAULT_META_TITLE,
        "default_meta_description": settings["meta_description"],
        "default_meta_keywords": DEFAULT_META_KEYWORDS,
        "default_meta_image": public_settings["social_image_absolute_url"],
        "default_site_name": settings["site_name"],
        "public_site_url": PUBLIC_SITE_URL,
        "site_settings": public_settings,
    }


def public_structured_data(settings: dict) -> dict:
    place_id = f"{PUBLIC_SITE_URL}/#phu-phan-centre"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{PUBLIC_SITE_URL}/#website",
                "url": PUBLIC_SITE_URL,
                "name": settings["site_name"],
                "alternateName": ["PhuPhan AR", "ภูพาน AR สกลนคร", "พูพาน AR"],
                "description": settings["meta_description"],
                "inLanguage": "th",
                "about": {"@id": place_id},
            },
            {
                "@type": "Place",
                "@id": place_id,
                "name": "ศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ",
                "alternateName": "Phu Phan Royal Development Study Centre",
                "url": PUBLIC_SITE_URL,
                "description": (
                    "แหล่งเรียนรู้ในจังหวัดสกลนครด้านการเกษตร ทรัพยากรธรรมชาติ "
                    "ภูมิปัญญาท้องถิ่น ผลิตภัณฑ์ และการพัฒนาคุณภาพชีวิต "
                    "นำเสนอเนื้อหาที่เกี่ยวข้องผ่านโมเดล 3D และ AR"
                ),
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "314 บ้านนานกเค้า ตำบลห้วยยาง",
                    "addressLocality": "อำเภอเมืองสกลนคร",
                    "addressRegion": "สกลนคร",
                    "postalCode": "47000",
                    "addressCountry": "TH",
                },
            },
        ],
    }


def ensure_data_files() -> None:
    global _DATA_READY
    if _DATA_READY:
        return
    if is_vercel_runtime():
        _DATA_READY = True
        return
    for directory in (MODEL_DIR, PIC_DIR, AUDIO_DIR, SITE_UPLOAD_DIR, SLIDER_UPLOAD_DIR):
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


def normalize_preview_images(value) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("["):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                value = candidate.splitlines()
        else:
            value = candidate.splitlines()
    if not isinstance(value, (list, tuple)):
        return []

    images = []
    for item in value:
        image = str(item or "").strip()
        if image and image not in images:
            images.append(image)
    return images


def parse_preview_images_field(value: str | None) -> list[str]:
    images = normalize_preview_images(value or "")
    for image in images:
        lowered = image.lower()
        if lowered.startswith(("https://", "http://")):
            continue
        if (
            image.startswith("//")
            or lowered.startswith(("data:", "javascript:"))
            or "://" in image
        ):
            abort(400, "Preview images must use HTTP(S) URLs or local static paths")
    return images


def parse_narration_audio_field(value: str | None) -> str:
    audio = str(value or "").strip()
    if not audio:
        return ""
    lowered = audio.lower()
    if (
        audio.startswith("//")
        or lowered.startswith(("data:", "javascript:"))
        or ("://" in audio and not lowered.startswith(("https://", "http://")))
    ):
        abort(400, "Narration audio must use an HTTP(S) URL or local static path")
    path = urlsplit(audio).path if lowered.startswith(("https://", "http://")) else audio
    if Path(path).suffix.lower() not in AUDIO_EXTENSIONS:
        abort(400, "Narration audio must be MP3, M4A, WAV, or OGG")
    return audio


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
    narration_audio = str(model.get("narration_audio") or "").strip()

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
        "preview_images": normalize_preview_images(model.get("preview_images")),
        "narration_audio": narration_audio,
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
    enriched["project_name"] = project.get("name") or UNASSIGNED_PROJECT_LABEL
    enriched["project_department"] = project.get("department", "")
    enriched["has_project"] = bool(project)
    enriched["model_resolved_url"] = resolve_model_url(enriched)
    enriched["thumbnail_resolved_url"] = resolve_thumbnail_url(enriched)
    enriched["narration_audio_url"] = resolve_narration_audio_url(enriched)
    enriched["size_mb"] = model_size_mb(enriched)
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


def normalize_site_settings(settings: dict | None) -> dict:
    normalized = dict(DEFAULT_SITE_SETTINGS)
    for key in normalized:
        value = (settings or {}).get(key)
        if value is not None:
            normalized[key] = str(value).strip()
    for key, fallback in DEFAULT_SITE_SETTINGS.items():
        if not normalized[key]:
            normalized[key] = fallback
    return normalized


def load_site_settings() -> dict:
    return normalize_site_settings(read_json(SITE_SETTINGS_FILE, DEFAULT_SITE_SETTINGS))


def save_site_settings(settings: dict) -> None:
    write_json(SITE_SETTINGS_FILE, normalize_site_settings(settings))


def normalize_slider_item(item: dict) -> dict:
    try:
        sort_order = int(item.get("sort_order") or 0)
    except (TypeError, ValueError):
        sort_order = 0
    return {
        "id": str(item.get("id") or uuid.uuid4().hex),
        "title": str(item.get("title") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "image_url": str(item.get("image_url") or item.get("image") or "").strip(),
        "button_text": str(item.get("button_text") or "").strip(),
        "button_url": str(item.get("button_url") or "").strip(),
        "sort_order": sort_order,
        "active": bool(item.get("active", True)),
        "created_at": str(item.get("created_at") or "").strip(),
    }


def load_slider_items(include_inactive: bool = True) -> list[dict]:
    items = [normalize_slider_item(item) for item in read_json(SLIDER_ITEMS_FILE, DEFAULT_SLIDER_ITEMS)]
    items.sort(key=lambda item: (item["sort_order"], item["id"]))
    if include_inactive:
        return items
    return [item for item in items if item["active"]]


def save_slider_items(items: list[dict]) -> None:
    normalized = [normalize_slider_item(item) for item in items]
    normalized.sort(key=lambda item: (item["sort_order"], item["id"]))
    write_json(SLIDER_ITEMS_FILE, normalized)


class SupabaseError(RuntimeError):
    pass


class GeminiTTSError(RuntimeError):
    pass


def pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return output.getvalue()


def parse_audio_mime_type(mime_type: str | None) -> tuple[int, int, int]:
    mime = str(mime_type or "").lower()
    rate_match = re.search(r"(?:rate|samplerate)=(\d+)", mime)
    channels_match = re.search(r"channels=(\d+)", mime)
    sample_rate = int(rate_match.group(1)) if rate_match else 24000
    channels = int(channels_match.group(1)) if channels_match else 1
    return sample_rate, channels, 2


def generate_gemini_tts_audio(text: str) -> tuple[bytes, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiTTSError("GEMINI_API_KEY is not configured")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiTTSError("google-genai is not installed") from exc

    prompt = (
        "อ่านคำบรรยายต่อไปนี้เป็นภาษาไทย น้ำเสียงชัดเจน เป็นมิตร "
        "เหมาะกับนิทรรศการและแหล่งเรียนรู้ เว้นจังหวะพอดี:\n"
        f"{text.strip()}"
    )
    client = None
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-tts-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Iapetus"
                        )
                    )
                ),
            ),
        )
        part = response.candidates[0].content.parts[0]
        inline_data = part.inline_data
        audio_data = inline_data.data
        mime_type = str(inline_data.mime_type or "")
    except (AttributeError, IndexError, TypeError) as exc:
        raise GeminiTTSError("Gemini did not return audio data") from exc
    except Exception as exc:
        raise GeminiTTSError("Gemini API request failed") from exc
    finally:
        close_client = getattr(client, "close", None) if client else None
        if callable(close_client):
            try:
                close_client()
            except Exception:
                logger.warning("Unable to close Gemini client cleanly")

    if not audio_data:
        raise GeminiTTSError("Gemini returned empty audio data")
    audio_bytes = bytes(audio_data)
    if mime_type.lower().startswith(("audio/wav", "audio/x-wav")):
        return audio_bytes, ".wav"
    sample_rate, channels, sample_width = parse_audio_mime_type(mime_type)
    return pcm_to_wav(audio_bytes, sample_rate, channels, sample_width), ".wav"


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
        "preview_images": normalize_preview_images(row.get("preview_images")),
        "narration_audio": str(row.get("narration_audio") or "").strip(),
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


def fetch_supabase_site_settings() -> dict:
    rows = supabase_request("/rest/v1/site_settings?select=key,value") or []
    return normalize_site_settings({row.get("key"): row.get("value") for row in rows})


def upsert_supabase_site_settings(settings: dict) -> None:
    payload = [{"key": key, "value": value} for key, value in normalize_site_settings(settings).items()]
    supabase_request(
        "/rest/v1/site_settings?on_conflict=key",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


def fetch_supabase_slider_items(include_inactive: bool = True) -> list[dict]:
    path = "/rest/v1/slider_items?select=*&order=sort_order.asc,created_at.asc"
    if not include_inactive:
        path = "/rest/v1/slider_items?select=*&active=eq.true&order=sort_order.asc,created_at.asc"
    rows = supabase_request(path) or []
    return [normalize_slider_item(row) for row in rows]


def create_supabase_slider_item(data: dict) -> dict:
    item = normalize_slider_item(data)
    payload = {key: item[key] for key in ("id", "title", "description", "image_url", "button_text", "button_url", "sort_order", "active")}
    rows = supabase_request(
        "/rest/v1/slider_items",
        method="POST",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_slider_item(rows[0]) if rows else item


def update_supabase_slider_item(slider_id: str, data: dict) -> dict:
    item = normalize_slider_item({"id": slider_id, **data})
    payload = {key: item[key] for key in ("title", "description", "image_url", "button_text", "button_url", "sort_order", "active")}
    rows = supabase_request(
        f"/rest/v1/slider_items?id=eq.{quote(slider_id)}",
        method="PATCH",
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return normalize_slider_item(rows[0]) if rows else item


def delete_supabase_slider_item(slider_id: str) -> None:
    supabase_request(f"/rest/v1/slider_items?id=eq.{quote(slider_id)}", method="DELETE")


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


def get_site_settings() -> dict:
    if is_supabase_enabled():
        try:
            return fetch_supabase_site_settings()
        except SupabaseError as exc:
            logger.warning("Falling back to local site_settings.json because Supabase read failed: %s", exc)
    return load_site_settings()


def get_slider_items(include_inactive: bool = True) -> list[dict]:
    if is_supabase_enabled():
        try:
            return fetch_supabase_slider_items(include_inactive=include_inactive)
        except SupabaseError as exc:
            logger.warning("Falling back to local slider_items.json because Supabase read failed: %s", exc)
    return load_slider_items(include_inactive=include_inactive)


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


def upload_to_supabase_storage(
    file_storage,
    folder: str,
    allowed_extensions: set[str] | None = None,
    max_bytes: int | None = None,
) -> tuple[str, float | None]:
    if not file_storage or not file_storage.filename:
        return "", None

    allowed_extensions = allowed_extensions or (MODEL_EXTENSIONS if folder == "models" else IMAGE_EXTENSIONS)
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
    if max_bytes and len(data) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        abort(413, f"File must not exceed {max_megabytes} MB")

    supabase_request(
        f"/storage/v1/object/{quote(supabase_bucket())}/{quote(object_path, safe='/')}",
        method="PUT",
        data=data,
        content_type=content_type,
        extra_headers={"Cache-Control": "3600", "x-upsert": "false"},
    )
    return supabase_public_url(object_path), round(len(data) / (1024 * 1024), 2)


def save_generated_narration_audio(
    model_id: str,
    audio_data: bytes,
    extension: str = ".wav",
) -> str:
    extension = extension.lower()
    if extension not in AUDIO_EXTENSIONS:
        raise GeminiTTSError("Gemini returned an unsupported audio format")
    if not audio_data:
        raise GeminiTTSError("Gemini returned empty audio data")
    if len(audio_data) > NARRATION_AUDIO_MAX_BYTES:
        raise GeminiTTSError("Generated audio exceeds the 20 MB limit")

    filename = (
        f"{slugify(model_id, 'model')}-gemini-{uuid.uuid4().hex[:10]}{extension}"
    )
    if is_supabase_enabled():
        object_path = f"models/narration/{filename}"
        content_type = mimetypes.guess_type(filename)[0] or "audio/wav"
        supabase_request(
            f"/storage/v1/object/{quote(supabase_bucket())}/{quote(object_path, safe='/')}",
            method="PUT",
            data=audio_data,
            content_type=content_type,
            extra_headers={"Cache-Control": "3600", "x-upsert": "false"},
        )
        return supabase_public_url(object_path)

    if is_vercel_runtime():
        raise GeminiTTSError("Supabase must be configured to save audio on Vercel")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / filename).write_bytes(audio_data)
    return f"audio/{filename}"


def direct_upload_target(filename: str, kind: str, file_size: int | None = None) -> tuple[str, str]:
    upload_kinds = {
        "model": ("models", MODEL_EXTENSIONS),
        "model_narration_audio": ("models/narration", AUDIO_EXTENSIONS),
        "thumbnail": ("thumbnails", IMAGE_EXTENSIONS),
        "project_image": ("projects", IMAGE_EXTENSIONS),
        "landing_cover": ("site/landing", IMAGE_EXTENSIONS),
        "landing_mobile_cover_image": ("site/landing", IMAGE_EXTENSIONS),
        "site_logo": ("site/branding", SITE_LOGO_EXTENSIONS),
        "site_social_image": ("site/social", IMAGE_EXTENSIONS),
        "favicon": ("site/branding", FAVICON_EXTENSIONS),
        "intro_logo_1": ("site/intro", IMAGE_EXTENSIONS),
        "intro_logo_2": ("site/intro", IMAGE_EXTENSIONS),
        "intro_logo_3": ("site/intro", IMAGE_EXTENSIONS),
        "slider_image": ("sliders", IMAGE_EXTENSIONS),
    }
    if kind not in upload_kinds:
        abort(400, "Unsupported upload kind")

    folder, allowed_extensions = upload_kinds[kind]
    extension = Path(filename or "").suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension or '(none)'}")
    if kind in {
        "landing_cover",
        "landing_mobile_cover_image",
        "site_logo",
        "site_social_image",
        "favicon",
        "intro_logo_1",
        "intro_logo_2",
        "intro_logo_3",
        "slider_image",
    }:
        if not file_size:
            abort(400, "file_size is required for managed site uploads")
        if file_size > SITE_ASSET_MAX_BYTES:
            abort(413, "File must not exceed 5 MB")
    elif kind == "model_narration_audio":
        if not file_size:
            abort(400, "file_size is required for narration audio uploads")
        if file_size > NARRATION_AUDIO_MAX_BYTES:
            abort(413, "File must not exceed 20 MB")

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
        "preview_images": normalize_preview_images(data.get("preview_images")),
        "narration_audio": data.get("narration_audio", "").strip(),
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
        "preview_images": normalize_preview_images(data.get("preview_images")),
        "narration_audio": data.get("narration_audio", "").strip(),
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


def versioned_asset_url(url: str, version_source: str) -> str:
    if not url:
        return ""
    version = hashlib.sha256(version_source.encode("utf-8")).hexdigest()[:10]
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "v"]
    query.append(("v", version))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def site_settings_with_urls(settings: dict) -> dict:
    enriched = normalize_site_settings(settings)
    enriched["landing_cover_url"] = static_asset_url(enriched["landing_cover"]) or url_for("static", filename=DEFAULT_META_IMAGE_PATH)
    enriched["landing_mobile_cover_image_url"] = (
        static_asset_url(enriched["landing_mobile_cover_image"])
        if enriched.get("landing_mobile_cover_image")
        else enriched["landing_cover_url"]
    )
    enriched["site_logo_url"] = static_asset_url(enriched["site_logo"]) if enriched["site_logo"] else ""
    enriched["site_social_image_url"] = (
        static_asset_url(enriched["site_social_image"])
        if enriched["site_social_image"]
        else ""
    )
    social_image_fallback = (
        enriched["site_social_image_url"]
        or enriched["landing_cover_url"]
        or enriched["site_logo_url"]
        or url_for("static", filename=DEFAULT_META_IMAGE_PATH)
    )
    enriched["social_image_absolute_url"] = public_meta_image_url(
        social_image_fallback
    )
    favicon_url = static_asset_url(enriched["favicon"]) or url_for("static", filename="favicon.ico")
    enriched["favicon_version"] = hashlib.sha256(
        enriched["favicon"].encode("utf-8")
    ).hexdigest()[:10]
    enriched["favicon_url"] = versioned_asset_url(favicon_url, enriched["favicon"])
    enriched["intro_enabled_bool"] = enriched["intro_enabled"].lower() in {"1", "true", "on", "yes"}
    if enriched["intro_display_mode"] not in {"sequence", "all_at_once"}:
        enriched["intro_display_mode"] = "sequence"
    for index in range(1, 4):
        key = f"intro_logo_{index}"
        enriched[f"{key}_url"] = static_asset_url(enriched[key]) if enriched[key] else ""
    try:
        duration_ms = int(enriched["intro_logo_duration_ms"])
    except (TypeError, ValueError):
        duration_ms = int(DEFAULT_SITE_SETTINGS["intro_logo_duration_ms"])
    enriched["intro_logo_duration_ms_value"] = max(600, min(duration_ms, 1600))
    return enriched


def slider_with_url(item: dict) -> dict:
    enriched = normalize_slider_item(item)
    enriched["resolved_image_url"] = static_asset_url(enriched["image_url"]) if enriched["image_url"] else ""
    return enriched


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


def resolve_narration_audio_url(model: dict) -> str:
    value = str(model.get("narration_audio") or "").strip()
    if is_external_url(value):
        return value
    return local_static_url_if_exists(value)


def resolve_model_preview_images(model: dict) -> list[str]:
    resolved_images = []
    for image in normalize_preview_images(model.get("preview_images")):
        if str(image).lower().startswith(("https://", "http://")):
            resolved = image
        else:
            resolved = local_static_url_if_exists(image)
        if resolved and resolved not in resolved_images:
            resolved_images.append(resolved)

    if resolved_images:
        return resolved_images

    thumbnail_url = resolve_thumbnail_url(model)
    if thumbnail_url and thumbnail_url != PLACEHOLDER_THUMBNAIL:
        return [thumbnail_url]
    return []


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
        "preview_images": resolve_model_preview_images(enriched),
        "narration_audio": enriched.get("narration_audio", ""),
        "narration_audio_url": resolve_narration_audio_url(enriched),
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


def save_limited_upload(
    file_storage,
    directory: Path,
    relative_folder: str,
    allowed_extensions: set[str],
    max_bytes: int,
) -> str:
    if not file_storage or not file_storage.filename:
        return ""
    extension = Path(file_storage.filename).suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension}")
    data = file_storage.read(max_bytes + 1)
    file_storage.seek(0)
    if not data:
        abort(400, "Uploaded file is empty")
    if len(data) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        abort(413, f"File must not exceed {max_megabytes} MB")
    asset_name = unique_asset_name(file_storage.filename, allowed_extensions)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / asset_name).write_bytes(data)
    except OSError as exc:
        logger.exception("Unable to save uploaded file %s", asset_name)
        abort(500, f"Unable to save uploaded file: {exc}")
    return f"{relative_folder}/{asset_name}"


def save_site_upload(file_storage, directory: Path, relative_folder: str, allowed_extensions: set[str]) -> str:
    if not file_storage or not file_storage.filename:
        return ""
    extension = Path(file_storage.filename).suffix.lower()
    if extension not in allowed_extensions:
        abort(400, f"Unsupported file type: {extension}")
    data = file_storage.read(SITE_ASSET_MAX_BYTES + 1)
    file_storage.seek(0)
    if not data:
        abort(400, "Uploaded file is empty")
    if len(data) > SITE_ASSET_MAX_BYTES:
        abort(413, "File must not exceed 5 MB")
    asset_name = unique_asset_name(file_storage.filename, allowed_extensions)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / asset_name).write_bytes(data)
    except OSError as exc:
        logger.exception("Unable to save site asset %s", asset_name)
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


def validated_content_url(value: str | None, field_name: str, default: str = "") -> str:
    candidate = str(value or "").strip() or default
    if not candidate:
        return ""
    lowered = candidate.lower()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    if candidate.startswith("#"):
        return candidate
    if lowered.startswith(("https://", "http://")):
        return candidate
    abort(400, f"{field_name} must be an internal path, anchor, or HTTP(S) URL")


def setting_asset_from_request(
    settings: dict,
    key: str,
    file_field: str,
    folder: str,
    directory: Path,
    relative_folder: str,
    allowed_extensions: set[str],
) -> str:
    submitted_url = request.form.get(key, "").strip()
    file_storage = request.files.get(file_field)
    if is_supabase_enabled():
        uploaded_url, _ = upload_to_supabase_storage(
            file_storage,
            folder,
            allowed_extensions=allowed_extensions,
            max_bytes=SITE_ASSET_MAX_BYTES,
        )
        return uploaded_url or submitted_url or settings.get(key, "")
    uploaded_path = save_site_upload(file_storage, directory, relative_folder, allowed_extensions)
    return uploaded_path or submitted_url or settings.get(key, "")


def slider_data_from_request(existing: dict | None = None) -> dict:
    existing = existing or {}
    image_url = request.form.get("image_url", "").strip()
    file_storage = request.files.get("image_file")
    if is_supabase_enabled():
        uploaded_url, _ = upload_to_supabase_storage(
            file_storage,
            "sliders",
            allowed_extensions=IMAGE_EXTENSIONS,
            max_bytes=SITE_ASSET_MAX_BYTES,
        )
        image_url = uploaded_url or image_url or existing.get("image_url", "")
    else:
        uploaded_path = save_site_upload(file_storage, SLIDER_UPLOAD_DIR, "uploads/sliders", IMAGE_EXTENSIONS)
        image_url = uploaded_path or image_url or existing.get("image_url", "")
    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        abort(400, "ลำดับการแสดงผล (sort_order) ต้องเป็นจำนวนเต็ม")
    button_text = request.form.get("button_text", "").strip()
    button_url = validated_content_url(request.form.get("button_url"), "button_url")
    if bool(button_text) != bool(button_url):
        abort(400, "ต้องระบุทั้งข้อความปุ่ม (button_text) และลิงก์ปุ่ม (button_url) คู่กัน")
    return {
        "id": existing.get("id") or uuid.uuid4().hex,
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "image_url": image_url,
        "button_text": button_text,
        "button_url": button_url,
        "sort_order": sort_order,
        "active": form_visible(),
        "created_at": existing.get("created_at", ""),
    }


def landing_preload_image_urls(
    settings: dict,
    sliders: list[dict],
    projects: list[dict],
    models: list[dict],
    limit: int = 50,
) -> list[str]:
    candidates = [
        settings.get("landing_cover_url"),
        settings.get("landing_mobile_cover_image_url"),
        settings.get("site_logo_url"),
        settings.get("intro_logo_1_url"),
        settings.get("intro_logo_2_url"),
        settings.get("intro_logo_3_url"),
    ]
    candidates.extend(item.get("resolved_image_url") for item in sliders)
    candidates.extend(project.get("cover_image_url") for project in projects)
    for model in models:
        candidates.append(resolve_thumbnail_url(model))
        candidates.extend(resolve_model_preview_images(model))

    urls = []
    for candidate in candidates:
        url = str(candidate or "").strip()
        if not url or url.lower().startswith("data:") or url in urls:
            continue
        if url.lower().endswith(".glb"):
            continue
        if not (url.startswith("/") or url.lower().startswith(("https://", "http://"))):
            continue
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


@app.route("/")
def index():
    settings = get_site_settings()
    public_settings = site_settings_with_urls(settings)
    sliders = [slider_with_url(item) for item in get_slider_items(include_inactive=False)]
    models = get_models(include_hidden=False)
    projects = [
        project_with_urls(project, models)
        for project in get_projects(include_hidden=False)
    ]
    return render_template(
        "landing.html",
        landing_image_url=public_settings["landing_cover_url"],
        sliders=sliders,
        intro_logos=[
            public_settings[f"intro_logo_{index}_url"]
            for index in range(1, 4)
            if public_settings[f"intro_logo_{index}_url"]
        ],
        preload_image_urls=landing_preload_image_urls(
            public_settings,
            sliders,
            projects,
            models,
        ),
        structured_data=public_structured_data(settings),
        page_title=settings["site_name"],
        page_description=settings["meta_description"],
        page_image=public_settings["social_image_absolute_url"],
        page_url=public_url_for("index"),
    )


@app.route("/home")
def home():
    settings = get_site_settings()
    public_settings = site_settings_with_urls(settings)
    models = get_models(include_hidden=False)
    projects = [project_with_urls(project, models) for project in get_projects(include_hidden=False)]
    counts = project_model_counts(projects, models)
    all_models = [model_with_project(model, projects) for model in models]
    featured_models = all_models[:6]
    sliders = [slider_with_url(item) for item in get_slider_items(include_inactive=False)]
    return render_template(
        "index.html",
        projects=projects,
        model_counts=counts,
        featured_models=featured_models,
        total_project_count=len(projects),
        total_model_count=len(all_models),
        uses_online_data=is_supabase_enabled(),
        sliders=sliders,
        structured_data=public_structured_data(settings),
        page_title=settings["site_name"],
        page_description=settings["meta_description"],
        page_image=public_settings["social_image_absolute_url"],
        page_url=public_url_for("home"),
    )


@app.route("/models")
def models_index():
    settings = get_site_settings()
    models = get_models(include_hidden=False)
    projects = [project_with_urls(project, models) for project in get_projects(include_hidden=False)]
    all_models = [model_with_project(model, projects) for model in models]
    project_filters = []
    seen_projects = set()
    for model in all_models:
        project_name = model.get("project_name") or UNASSIGNED_PROJECT_LABEL
        if project_name in seen_projects:
            continue
        seen_projects.add(project_name)
        project_filters.append(project_name)
    return render_template(
        "models.html",
        models=all_models,
        project_filters=project_filters,
        page_title="โมเดล 3D ภูพาน | ของดีสกลนครในรูปแบบ AR",
        page_description=settings["meta_description"],
        page_url=public_url_for("models_index"),
    )


@app.route("/projects/<project_id>")
def project_detail(project_id: str):
    settings = get_site_settings()
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
    return render_template(
        "project.html",
        project=project,
        models=models,
        page_title=f"{project.get('name', '')} | ภูพาน สกลนคร",
        page_description=(
            f"{project.get('description')} เรียนรู้ผ่านโมเดล 3D และ AR ของศูนย์ศึกษาการพัฒนาภูพาน จังหวัดสกลนคร"
            if project.get("description")
            else settings["meta_description"]
        ),
        page_image=public_meta_image_url(project.get("cover_image_url")),
        page_url=public_url_for("project_detail", project_id=project_id),
    )


@app.route("/models/<model_id>")
def model_detail(model_id: str):
    settings = get_site_settings()
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
        preview_images=resolve_model_preview_images(model),
        narration_audio_url=resolve_narration_audio_url(model),
        model_name=model.get("name", ""),
        size_mb=model_size_mb(model),
        related_models=related_models,
        mode=request.args.get("mode", "3d"),
        page_title=f"{model.get('name', '')} | โมเดล 3D ภูพาน AR",
        page_description=(
            f"{model.get('description')} ชมโมเดล 3D และ AR จากเนื้อหาภูพาน สกลนคร"
            if model.get("description")
            else settings["meta_description"]
        ),
        page_image=public_meta_image_url(resolve_thumbnail_url(model)),
        page_url=public_url_for("model_detail", model_id=model_id),
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


@app.get("/api/settings")
def api_settings():
    return jsonify(site_settings_with_urls(get_site_settings()))


@app.get("/api/sliders")
def api_sliders():
    return jsonify([slider_with_url(item) for item in get_slider_items(include_inactive=False)])


@app.get("/sitemap.xml")
def sitemap():
    projects = get_projects(include_hidden=False)
    models = get_models(include_hidden=False)
    urls = [
        {"loc": public_url_for("index"), "priority": "1.0"},
        {"loc": public_url_for("home"), "priority": "0.9"},
        {"loc": public_url_for("models_index"), "priority": "0.9"},
    ]
    urls.extend(
        {"loc": public_url_for("project_detail", project_id=project["id"]), "priority": "0.8"}
        for project in projects
    )
    urls.extend(
        {"loc": public_url_for("model_detail", model_id=model["id"]), "priority": "0.7"}
        for model in models
    )
    xml_body = render_template("sitemap.xml", urls=urls).lstrip("\ufeff \t\r\n")
    xml_document = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
    return xml_document, 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.get("/robots.txt")
def robots():
    return render_template("robots.txt", sitemap_url=public_url_for("sitemap")), 200, {
        "Content-Type": "text/plain; charset=utf-8"
    }


@app.get("/googleaf10e1de09a9b1b8.html")
def google_site_verification():
    return "google-site-verification: googleaf10e1de09a9b1b8.html", 200, {
        "Content-Type": "text/html; charset=utf-8"
    }


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


@app.route("/admin/landing")
@admin_required
def admin_landing():
    return render_template("admin_landing.html", settings=site_settings_with_urls(get_site_settings()))


@app.route("/admin/branding")
@admin_required
def admin_branding():
    return render_template("admin_branding.html", settings=site_settings_with_urls(get_site_settings()))


@app.route("/admin/intro", methods=["GET", "POST"])
@admin_required
def admin_intro():
    if request.method == "GET":
        return render_template(
            "admin_intro.html",
            settings=site_settings_with_urls(get_site_settings()),
        )

    file_fields = tuple(f"intro_logo_{index}_file" for index in range(1, 4))
    if reject_vercel_upload_if_needed(*file_fields) or admin_write_blocked_on_vercel():
        return redirect(url_for("admin_intro"))

    settings = get_site_settings()
    settings["intro_enabled"] = (
        "true" if request.form.get("intro_enabled") in {"1", "true", "on", "yes"} else "false"
    )
    intro_display_mode = request.form.get("intro_display_mode", "sequence").strip()
    settings["intro_display_mode"] = (
        intro_display_mode
        if intro_display_mode in {"sequence", "all_at_once"}
        else "sequence"
    )
    try:
        duration_ms = int(request.form.get("intro_logo_duration_ms") or 1400)
    except ValueError:
        abort(400, "ระยะเวลาแสดงโลโก้ต้องเป็นจำนวนเต็ม")
    settings["intro_logo_duration_ms"] = str(max(600, min(duration_ms, 1600)))

    for index in range(1, 4):
        key = f"intro_logo_{index}"
        if request.form.get(f"{key}_remove") in {"1", "true", "on", "yes"}:
            settings[key] = ""
        else:
            settings[key] = setting_asset_from_request(
                settings,
                key,
                f"{key}_file",
                "site/intro",
                SITE_UPLOAD_DIR / "intro",
                "uploads/site/intro",
                IMAGE_EXTENSIONS,
            )

    if is_supabase_enabled():
        try:
            upsert_supabase_site_settings(settings)
        except SupabaseError as exc:
            logger.exception("Unable to save intro settings in Supabase")
            flash(f"ไม่สามารถบันทึกการตั้งค่าอินโทรไปยัง Supabase ได้: {exc}", "error")
            return redirect(url_for("admin_intro"))
    else:
        save_site_settings(settings)
    flash("บันทึกการตั้งค่าอินโทรแล้ว", "success")
    return redirect(url_for("admin_intro"))


@app.route("/admin/sliders", methods=["GET", "POST"])
@admin_required
def admin_sliders():
    if request.method == "POST":
        if reject_vercel_upload_if_needed("image_file") or admin_write_blocked_on_vercel():
            return redirect(url_for("admin_sliders"))
        data = slider_data_from_request()
        if not data["title"]:
            abort(400, "จำเป็นต้องกรอกชื่อสไลด์เดอร์ (Slider Title)")
        if not data["image_url"]:
            abort(400, "จำเป็นต้องระบุรูปภาพสไลด์เดอร์")
        if is_supabase_enabled():
            try:
                create_supabase_slider_item(data)
            except SupabaseError as exc:
                logger.exception("Unable to create slider in Supabase")
                flash(f"ไม่สามารถบันทึกสไลด์เดอร์ไปยัง Supabase ได้: {exc}", "error")
                return redirect(url_for("admin_sliders"))
        else:
            items = load_slider_items(include_inactive=True)
            items.append(data)
            save_slider_items(items)
        flash("เพิ่มสไลด์แล้ว", "success")
        return redirect(url_for("admin_sliders"))
    sliders = [slider_with_url(item) for item in get_slider_items(include_inactive=True)]
    return render_template("admin_sliders.html", sliders=sliders)


@app.route("/admin/sliders/<slider_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_slider(slider_id: str):
    sliders = get_slider_items(include_inactive=True)
    slider = next((item for item in sliders if item["id"] == slider_id), None)
    if slider is None:
        abort(404)
    if request.method == "POST":
        if reject_vercel_upload_if_needed("image_file") or admin_write_blocked_on_vercel():
            return redirect(url_for("edit_slider", slider_id=slider_id))
        data = slider_data_from_request(slider)
        if not data["title"]:
            abort(400, "จำเป็นต้องกรอกชื่อสไลด์เดอร์ (Slider Title)")
        if is_supabase_enabled():
            try:
                update_supabase_slider_item(slider_id, data)
            except SupabaseError as exc:
                logger.exception("Unable to update slider in Supabase")
                flash(f"ไม่สามารถบันทึกสไลด์เดอร์ไปยัง Supabase ได้: {exc}", "error")
                return redirect(url_for("edit_slider", slider_id=slider_id))
        else:
            save_slider_items([data if item["id"] == slider_id else item for item in sliders])
        flash("บันทึกสไลด์แล้ว", "success")
        return redirect(url_for("admin_sliders"))
    return render_template("edit_slider.html", slider=slider_with_url(slider))


@app.route("/admin/sliders/<slider_id>", methods=["POST", "DELETE"])
@admin_required
def delete_slider(slider_id: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin_sliders"))
    if is_supabase_enabled():
        try:
            delete_supabase_slider_item(slider_id)
        except SupabaseError as exc:
            logger.exception("Unable to delete slider in Supabase")
            if request.method == "DELETE":
                return jsonify({"error": str(exc)}), 502
            flash(f"ไม่สามารถลบสไลด์เดอร์ออกจาก Supabase ได้: {exc}", "error")
            return redirect(url_for("admin_sliders"))
    else:
        sliders = load_slider_items(include_inactive=True)
        if not any(item["id"] == slider_id for item in sliders):
            abort(404)
        save_slider_items([item for item in sliders if item["id"] != slider_id])
    if request.method == "DELETE":
        return "", 204
    flash("ลบสไลด์แล้ว", "success")
    return redirect(url_for("admin_sliders"))


@app.post("/admin/settings")
@admin_required
def update_admin_settings():
    if reject_vercel_upload_if_needed(
        "landing_cover_file",
        "landing_mobile_cover_image_file",
        "site_logo_file",
        "site_social_image_file",
        "favicon_file",
    ) or admin_write_blocked_on_vercel():
        return redirect(request.form.get("return_to") or url_for("admin"))
    settings = get_site_settings()
    section = request.form.get("section", "").strip()
    if section == "landing":
        settings.update(
            {
                "landing_headline": request.form.get("landing_headline", "").strip() or DEFAULT_SITE_SETTINGS["landing_headline"],
                "landing_subheadline": request.form.get("landing_subheadline", "").strip() or DEFAULT_SITE_SETTINGS["landing_subheadline"],
                "landing_description": request.form.get("landing_description", "").strip() or DEFAULT_SITE_SETTINGS["landing_description"],
                "landing_cta_text": request.form.get("landing_cta_text", "").strip() or DEFAULT_SITE_SETTINGS["landing_cta_text"],
                "landing_cta_url": validated_content_url(
                    request.form.get("landing_cta_url"),
                    "landing_cta_url",
                    DEFAULT_SITE_SETTINGS["landing_cta_url"],
                ),
                "home_hero_badge": request.form.get("home_hero_badge", "").strip()
                or DEFAULT_SITE_SETTINGS["home_hero_badge"],
                "home_hero_heading": request.form.get("home_hero_heading", "").strip()
                or DEFAULT_SITE_SETTINGS["home_hero_heading"],
                "home_hero_subheading": request.form.get("home_hero_subheading", "").strip()
                or DEFAULT_SITE_SETTINGS["home_hero_subheading"],
                "home_hero_description": request.form.get("home_hero_description", "").strip()
                or DEFAULT_SITE_SETTINGS["home_hero_description"],
                "home_hero_primary_cta_text": request.form.get(
                    "home_hero_primary_cta_text", ""
                ).strip()
                or DEFAULT_SITE_SETTINGS["home_hero_primary_cta_text"],
                "home_hero_secondary_cta_text": request.form.get(
                    "home_hero_secondary_cta_text", ""
                ).strip()
                or DEFAULT_SITE_SETTINGS["home_hero_secondary_cta_text"],
            }
        )
        settings["landing_cover"] = setting_asset_from_request(
            settings,
            "landing_cover",
            "landing_cover_file",
            "site/landing",
            SITE_UPLOAD_DIR,
            "uploads/site",
            IMAGE_EXTENSIONS,
        )
        if request.form.get("landing_mobile_cover_image_remove") in {"1", "true", "on", "yes"}:
            settings["landing_mobile_cover_image"] = ""
        else:
            settings["landing_mobile_cover_image"] = setting_asset_from_request(
                settings,
                "landing_mobile_cover_image",
                "landing_mobile_cover_image_file",
                "site/landing",
                SITE_UPLOAD_DIR,
                "uploads/site",
                IMAGE_EXTENSIONS,
            )
    elif section == "branding":
        settings["site_name"] = request.form.get("site_name", "").strip() or DEFAULT_SITE_SETTINGS["site_name"]
        settings["meta_description"] = request.form.get("meta_description", "").strip() or DEFAULT_SITE_SETTINGS["meta_description"]
        settings["site_logo"] = setting_asset_from_request(
            settings,
            "site_logo",
            "site_logo_file",
            "site/branding",
            SITE_UPLOAD_DIR,
            "uploads/site",
            SITE_LOGO_EXTENSIONS,
        )
        if request.form.get("site_social_image_remove") in {"1", "true", "on", "yes"}:
            settings["site_social_image"] = ""
        else:
            settings["site_social_image"] = setting_asset_from_request(
                settings,
                "site_social_image",
                "site_social_image_file",
                "site/social",
                SITE_UPLOAD_DIR / "social",
                "uploads/site/social",
                IMAGE_EXTENSIONS,
            )
        settings["favicon"] = setting_asset_from_request(
            settings,
            "favicon",
            "favicon_file",
            "site/branding",
            SITE_UPLOAD_DIR,
            "uploads/site",
            FAVICON_EXTENSIONS,
        )
    else:
        abort(400, "Unsupported settings section")
    if is_supabase_enabled():
        try:
            upsert_supabase_site_settings(settings)
        except SupabaseError as exc:
            logger.exception("Unable to save site settings in Supabase")
            flash(f"ไม่สามารถบันทึกการตั้งค่าระบบไปยัง Supabase ได้: {exc}", "error")
            return redirect(request.form.get("return_to") or url_for("admin"))
    else:
        save_site_settings(settings)
    flash("บันทึกการตั้งค่าแล้ว", "success")
    return redirect(request.form.get("return_to") or url_for("admin"))


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
    try:
        file_size = int(payload.get("file_size") or 0)
    except (TypeError, ValueError):
        abort(400, "file_size must be an integer")
    if not filename:
        abort(400, "filename is required")

    object_path, public_url = direct_upload_target(filename, kind, file_size=file_size)
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
    return redirect(url_for("home"))


@app.post("/admin/projects")
@admin_required
def add_project():
    if reject_vercel_upload_if_needed("cover_image") or admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    name = request.form.get("name", "").strip()
    if not name:
        abort(400, "จำเป็นต้องกรอกชื่อโครงการ (Project Name)")

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
            flash(f"ไม่สามารถบันทึกโครงการไปยัง Supabase ได้: {exc}", "error")
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
                flash(f"ไม่สามารถบันทึกข้อมูลโครงการไปยัง Supabase ได้: {exc}", "error")
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
            flash(f"ไม่สามารถลบโครงการออกจาก Supabase ได้: {exc}", "error")
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
        delete_static_file(model.get("narration_audio"))
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
    if reject_vercel_upload_if_needed("model_file", "image_file", "narration_audio_file") or admin_write_blocked_on_vercel():
        return redirect(url_for("admin"))

    name = request.form.get("name", "").strip()
    project_id = request.form.get("project_id", "").strip()
    if not name:
        abort(400, "จำเป็นต้องกรอกชื่อโมเดล (Model Name)")
    if find_project(project_id, include_hidden=True) is None:
        abort(400, "จำเป็นต้องเลือกโครงการ (Project)")

    model_url = request.form.get("model_url", "").strip()
    thumbnail_url = request.form.get("thumbnail_url", "").strip()
    preview_images = parse_preview_images_field(request.form.get("preview_images"))
    narration_audio = parse_narration_audio_field(request.form.get("narration_audio"))

    if is_supabase_enabled():
        try:
            uploaded_model_url, model_size_mb = upload_to_supabase_storage(request.files.get("model_file"), "models")
            uploaded_thumbnail_url, _ = upload_to_supabase_storage(request.files.get("image_file"), "thumbnails")
            uploaded_narration_audio, _ = upload_to_supabase_storage(
                request.files.get("narration_audio_file"),
                "models/narration",
                AUDIO_EXTENSIONS,
                NARRATION_AUDIO_MAX_BYTES,
            )
            final_model_url = uploaded_model_url or model_url
            final_thumbnail_url = uploaded_thumbnail_url or thumbnail_url
            if not final_model_url:
                abort(400, "จำเป็นต้องอัปโหลดไฟล์โมเดล .glb หรือระบุลิงก์ภายนอก")
            create_model(
                {
                    "name": name,
                    "description": request.form.get("description", "").strip(),
                    "project_id": project_id,
                    "model_url": final_model_url,
                    "thumbnail_url": final_thumbnail_url,
                    "preview_images": preview_images,
                    "narration_audio": uploaded_narration_audio or narration_audio,
                    "file_size_mb": model_size_mb,
                }
            )
            flash(f'เพิ่มโมเดล "{name}" แล้ว', "success")
        except SupabaseError as exc:
            logger.exception("Unable to create model in Supabase")
            flash(f"ไม่สามารถบันทึกโมเดลไปยัง Supabase ได้: {exc}", "error")
        return redirect(url_for("admin"))

    model_path = model_url or request.form.get("model_path", "").strip()
    uploaded_model = save_upload(request.files.get("model_file"), MODEL_DIR, "model", MODEL_EXTENSIONS)
    if uploaded_model:
        model_path = uploaded_model
    if not model_path:
        abort(400, "จำเป็นต้องอัปโหลดไฟล์โมเดล .glb/.gltf หรือระบุ Path ของโมเดล")

    image_path = thumbnail_url or request.form.get("image_path", "").strip()
    uploaded_image = save_upload(request.files.get("image_file"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
    if uploaded_image:
        image_path = uploaded_image
    uploaded_narration_audio = save_limited_upload(
        request.files.get("narration_audio_file"),
        AUDIO_DIR,
        "audio",
        AUDIO_EXTENSIONS,
        NARRATION_AUDIO_MAX_BYTES,
    )

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
            "preview_images": preview_images,
            "narration_audio": uploaded_narration_audio or narration_audio,
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
        if reject_vercel_upload_if_needed("model_file", "image_file", "narration_audio_file") or admin_write_blocked_on_vercel():
            return redirect(url_for("edit_model", model_id=model_id))

        project_id = request.form.get("project_id", "").strip()
        if find_project(project_id, include_hidden=True) is None:
            abort(400, "จำเป็นต้องเลือกโครงการ (Project)")
        preview_images = parse_preview_images_field(request.form.get("preview_images"))
        remove_narration_audio = request.form.get("narration_audio_remove") in {"1", "true", "on", "yes"}

        if is_supabase_enabled():
            try:
                uploaded_model_url, uploaded_size_mb = upload_to_supabase_storage(request.files.get("model_file"), "models")
                uploaded_thumbnail_url, _ = upload_to_supabase_storage(request.files.get("image_file"), "thumbnails")
                uploaded_narration_audio, _ = upload_to_supabase_storage(
                    request.files.get("narration_audio_file"),
                    "models/narration",
                    AUDIO_EXTENSIONS,
                    NARRATION_AUDIO_MAX_BYTES,
                )
                final_model_url = uploaded_model_url or request.form.get("model_url", "").strip() or model.get("model_url", "")
                final_thumbnail_url = (
                    uploaded_thumbnail_url
                    or request.form.get("thumbnail_url", "").strip()
                    or model.get("thumbnail_url", "")
                )
                if not final_model_url:
                    abort(400, "จำเป็นต้องอัปโหลดไฟล์โมเดล .glb หรือระบุลิงก์ภายนอก")
                final_narration_audio = (
                    ""
                    if remove_narration_audio
                    else uploaded_narration_audio
                    or parse_narration_audio_field(request.form.get("narration_audio"))
                    or model.get("narration_audio", "")
                )
                update_model(
                    model_id,
                    {
                        "name": request.form.get("name", "").strip() or model["name"],
                        "description": request.form.get("description", "").strip(),
                        "project_id": project_id,
                        "model_url": final_model_url,
                        "thumbnail_url": final_thumbnail_url,
                        "preview_images": preview_images,
                        "narration_audio": final_narration_audio,
                        "file_size_mb": uploaded_size_mb if uploaded_size_mb is not None else model.get("file_size_mb"),
                    },
                )
                flash("บันทึกข้อมูลโมเดลแล้ว", "success")
                return redirect(url_for("admin"))
            except SupabaseError as exc:
                logger.exception("Unable to update model in Supabase")
                flash(f"ไม่สามารถบันทึกข้อมูลโมเดลไปยัง Supabase ได้: {exc}", "error")
                return redirect(url_for("edit_model", model_id=model_id))

        old_model = model.get("model")
        old_image = model.get("image")
        new_model = save_upload(request.files.get("model_file"), MODEL_DIR, "model", MODEL_EXTENSIONS)
        new_image = save_upload(request.files.get("image_file"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
        new_narration_audio = save_limited_upload(
            request.files.get("narration_audio_file"),
            AUDIO_DIR,
            "audio",
            AUDIO_EXTENSIONS,
            NARRATION_AUDIO_MAX_BYTES,
        )
        model_url = request.form.get("model_url", "").strip()
        thumbnail_url = request.form.get("thumbnail_url", "").strip()
        manual_model_path = model_url or request.form.get("model_path", "").strip()
        manual_image_path = thumbnail_url or request.form.get("image_path", "").strip()
        old_narration_audio = model.get("narration_audio", "")
        narration_audio = (
            ""
            if remove_narration_audio
            else new_narration_audio
            or parse_narration_audio_field(request.form.get("narration_audio"))
            or old_narration_audio
        )

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
                "preview_images": preview_images,
                "narration_audio": narration_audio,
                "rotate_x": parse_float("rotate_x", 0),
                "scale": parse_float("scale", 0.2),
                "visible": form_visible(),
            }
        )
        if new_model and old_model:
            delete_static_file(old_model)
        if new_image and old_image:
            delete_static_file(old_image)
        if (new_narration_audio or remove_narration_audio) and old_narration_audio:
            delete_static_file(old_narration_audio)
        save_models(models)
        flash("บันทึกข้อมูลโมเดลแล้ว", "success")
        return redirect(url_for("admin"))

    return render_template("edit_model.html", model=model_with_project(model, projects), projects=projects)


@app.post("/admin/models/<model_id>/generate-narration")
@admin_required
def generate_model_narration(model_id: str):
    model = next(
        (item for item in get_models(include_hidden=True) if item["id"] == model_id),
        None,
    )
    if model is None:
        abort(404)

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        flash(
            "ยังไม่ได้ตั้งค่า GEMINI_API_KEY ใน Vercel Environment Variables",
            "error",
        )
        return redirect(url_for("edit_model", model_id=model_id))
    if admin_write_blocked_on_vercel():
        return redirect(url_for("edit_model", model_id=model_id))

    name = str(model.get("name") or "โมเดล").strip()
    description = str(model.get("description") or "").strip()
    narration_text = ". ".join(part for part in (name, description) if part)
    old_narration_audio = str(model.get("narration_audio") or "").strip()

    try:
        audio_data, extension = generate_gemini_tts_audio(narration_text)
        narration_audio = save_generated_narration_audio(
            model_id,
            audio_data,
            extension,
        )

        if is_supabase_enabled():
            update_model(
                model_id,
                {
                    "name": name,
                    "description": description,
                    "project_id": model.get("project_id", ""),
                    "model_url": model.get("model_url", ""),
                    "thumbnail_url": model.get("thumbnail_url", ""),
                    "preview_images": model.get("preview_images", []),
                    "narration_audio": narration_audio,
                    "file_size_mb": model.get("file_size_mb"),
                },
            )
        else:
            models = load_models(include_hidden=True)
            stored_model = next(
                (item for item in models if item["id"] == model_id),
                None,
            )
            if stored_model is None:
                abort(404)
            stored_model["narration_audio"] = narration_audio
            save_models(models)
            if old_narration_audio and old_narration_audio != narration_audio:
                delete_static_file(old_narration_audio)
    except (GeminiTTSError, SupabaseError, OSError) as exc:
        logger.exception("Unable to generate Gemini narration for model %s", model_id)
        flash(f"สร้างเสียงคำบรรยายไม่สำเร็จ: {exc}", "error")
        return redirect(url_for("edit_model", model_id=model_id))
    except Exception:
        logger.exception("Unexpected Gemini narration failure for model %s", model_id)
        flash("สร้างเสียงคำบรรยายไม่สำเร็จ: ระบบสร้างเสียงเกิดข้อผิดพลาด", "error")
        return redirect(url_for("edit_model", model_id=model_id))

    flash("สร้างไฟล์เสียงคำบรรยายเรียบร้อยแล้ว", "success")
    return redirect(url_for("edit_model", model_id=model_id))


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
            flash(f"ไม่สามารถลบโมเดลออกจาก Supabase ได้: {exc}", "error")
        return redirect(url_for("admin"))

    models = load_models(include_hidden=True)
    deleted = next((item for item in models if item["id"] == model_id), None)
    if deleted is None:
        abort(404)

    delete_static_file(deleted.get("model"))
    delete_static_file(deleted.get("image"))
    delete_static_file(deleted.get("narration_audio"))
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
