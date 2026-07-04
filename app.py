import base64
import hashlib
import io
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import uuid
import wave
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import Lock, Timer
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
MAX_MODEL_FILE_SIZE_MB = 50
MAX_MODEL_FILE_SIZE_BYTES = MAX_MODEL_FILE_SIZE_MB * 1024 * 1024
VERCEL_UPLOAD_MESSAGE = "ระบบ production เป็นโหมดอ่านอย่างเดียว กรุณาอัปโหลดไฟล์ไปยัง R2 และแก้ไขไฟล์ data/*.json ผ่านขั้นตอนเผยแพร่ที่กำหนด"
VERCEL_EDIT_MESSAGE = "ระบบแอดมิน production เป็นโหมดอ่านอย่างเดียว กรุณาแก้ไขไฟล์ data/*.json ภายในเครื่อง ตรวจสอบความถูกต้อง แล้ว Commit และ Deploy ใหม่"
UNASSIGNED_PROJECT_LABEL = "ยังไม่ได้จัดอยู่ในแหล่งเรียนรู้"
PUBLIC_SITE_URL = (
    os.environ.get("SITE_BASE_URL")
    or os.environ.get("PUBLIC_SITE_URL")
    or "https://phuphan-ar.vercel.app"
).rstrip("/")
DEFAULT_META_TITLE = "ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์"
DEFAULT_META_DESCRIPTION = (
    "เรียนรู้ของดีสกลนคร แหล่งเรียนรู้ภูพาน และพิพิธภัณฑ์ท้องถิ่นผ่านโมเดล 3D และ AR "
    "ในรูปแบบออนไลน์เสมือนจริง ค้นพบผลิตภัณฑ์ท้องถิ่นสกลนคร"
)
DEFAULT_META_KEYWORDS = (
    "ภูพาน ar, ภูพาน AR สกลนคร, ภูพาน โมเดล 3D, ภูพาน 3D, ภูพาน สกลนคร AR, phuphan ar, phu phan ar, "
    "พูพาน ar, พูพาน สกลนคร, ภูพาน สกลนคร, ภูพาน 3d ar, ของดีสกลนคร 3D, ของดีสกลนคร AR, "
    "แหล่งเรียนรู้สกลนคร, พิพิธภัณฑ์ท้องถิ่นสกลนคร ออนไลน์, โมเดล 3D สกลนคร, "
    "ลูกประคบ สกลนคร 3D, ลิ้นจี่ สกลนคร 3D, ข้าวสกลนคร 3D, "
    "ศูนย์ศึกษาการพัฒนาภูพาน, ศูนย์ภูพาน, สกลนคร, สกล, ของดีสกลนคร, โมเดล 3D, AR, AR สกลนคร, "
    "Phu Phan, PhuPhan AR, Sakon Nakhon"
)
DEFAULT_META_IMAGE_PATH = "pic/og-cover.jpg"
MAX_RECOMMENDED_MODELS = 10
DEFAULT_SITE_SETTINGS = {
    "landing_cover": DEFAULT_META_IMAGE_PATH,
    "landing_mobile_cover_image": "",
    "landing_headline": "ภูพาน AR สกลนคร",
    "landing_subheadline": "โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์ ของดีสกลนคร",
    "landing_description": (
        "เว็บไซต์รวบรวมวัตถุ ผลิตภัณฑ์ องค์ความรู้ และของดีสกลนครจาก"
        "ศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ บ้านนานกเค้า "
        "ตำบลห้วยยาง อำเภอเมือง จังหวัดสกลนคร ในรูปแบบโมเดล 3D และเทคโนโลยี AR เสมือนจริง"
    ),
    "landing_text_max_width_desktop": "520",
    "landing_headline_font_size_desktop": "56",
    "landing_subheadline_font_size_desktop": "28",
    "landing_description_font_size_desktop": "18",
    "landing_badge_font_size_desktop": "14",
    "landing_button_font_size_desktop": "16",
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
    "site_name": "ภูพาน AR สกลนคร | โมเดล 3D และแหล่งเรียนรู้ท้องถิ่นออนไลน์",
    "site_social_image": "",
    "favicon": "favicon.ico",
    "meta_description": DEFAULT_META_DESCRIPTION,
    "recommended_model_ids": "",
}
LANDING_TYPOGRAPHY_SETTINGS = {
    "landing_text_max_width_desktop": (320, 900),
    "landing_headline_font_size_desktop": (28, 96),
    "landing_subheadline_font_size_desktop": (18, 56),
    "landing_description_font_size_desktop": (14, 28),
    "landing_badge_font_size_desktop": (10, 22),
    "landing_button_font_size_desktop": (12, 24),
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
        "rotate_y": 0,
        "rotate_z": 0,
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
        "rotate_y": 0,
        "rotate_z": 0,
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
        "rotate_y": 0,
        "rotate_z": 0,
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
        "rotate_y": 0,
        "rotate_z": 0,
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
        "rotate_y": 0,
        "rotate_z": 0,
        "scale": 0.04,
        "visible": True,
    },
]


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ARMODEL_DATA_DIR", BASE_DIR / "data"))
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
R2_PUBLIC_HOST = "pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev"
DASHBOARD_ASSET_CACHE_TTL_SECONDS = 300
DASHBOARD_ASSET_HEAD_TIMEOUT_SECONDS = 5
DEFAULT_R2_STORAGE_SOFT_LIMIT_GB = 10.0
_DASHBOARD_ASSET_CACHE: dict[str, tuple[float, dict]] = {}
_DASHBOARD_ASSET_CACHE_LOCK = Lock()
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
    settings = get_site_settings()
    public_settings = site_settings_with_urls(settings)
    return {
        "is_vercel": is_vercel_runtime(),
        "admin_read_only": is_vercel_runtime(),
        "uploads_disabled": is_vercel_runtime(),
        "default_meta_title": DEFAULT_META_TITLE,
        "default_meta_description": settings["meta_description"],
        "default_meta_keywords": DEFAULT_META_KEYWORDS,
        "default_meta_image": public_settings["social_image_absolute_url"],
        "default_site_name": settings["site_name"],
        "public_site_url": PUBLIC_SITE_URL,
        "site_settings": public_settings,
        "model_file_max_mb": MAX_MODEL_FILE_SIZE_MB,
        "model_file_max_bytes": MAX_MODEL_FILE_SIZE_BYTES,
    }


def public_structured_data(settings: dict) -> dict:
    place_id = f"{PUBLIC_SITE_URL}/#phu-phan-centre"
    org_id = f"{PUBLIC_SITE_URL}/#organization"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{PUBLIC_SITE_URL}/#website",
                "url": PUBLIC_SITE_URL,
                "name": settings["site_name"],
                "alternateName": ["PhuPhan AR", "ภูพาน AR", "พูพาน AR", "ภูพาน สกลนคร"],
                "description": settings["meta_description"],
                "inLanguage": "th",
                "about": {"@id": place_id},
            },
            {
                "@type": "EducationalOrganization",
                "@id": org_id,
                "name": "โครงการเพิ่มศักยภาพแหล่งเรียนรู้และพิพิธภัณฑ์ท้องถิ่นจังหวัดสกลนคร",
                "url": PUBLIC_SITE_URL,
                "description": "โครงการเสริมสร้างศักยภาพของแหล่งเรียนรู้และพิพิธภัณฑ์ท้องถิ่นในจังหวัดสกลนครผ่านนวัตกรรมดิจิทัล 3D และ AR",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "เมืองสกลนคร",
                    "addressRegion": "สกลนคร",
                    "addressCountry": "TH"
                }
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


def public_models_structured_data(settings: dict, models: list) -> dict:
    base = public_structured_data(settings)
    item_list_elements = []
    for i, m in enumerate(models):
        item_list_elements.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"{PUBLIC_SITE_URL}/models/{m['id']}",
            "name": m.get("name", "")
        })
    item_list = {
        "@type": "ItemList",
        "@id": f"{PUBLIC_SITE_URL}/models#item-list",
        "name": "รายการโมเดล 3D และ AR แหล่งเรียนรู้ภูพาน สกลนคร",
        "description": "คลังโมเดล 3D และวัตถุเสมือนจริง (AR) ของดีเมืองสกลนคร",
        "itemListElement": item_list_elements
    }
    base["@graph"].append(item_list)
    return base


def public_model_detail_structured_data(settings: dict, model: dict) -> dict:
    base = public_structured_data(settings)
    model_url = f"{PUBLIC_SITE_URL}/models/{model['id']}"
    creative_work = {
        "@type": "CreativeWork",
        "@id": f"{model_url}#creativework",
        "name": model.get("name", ""),
        "description": model.get("description") or f"โมเดล 3D และ AR ของ {model.get('name', '')} แหล่งเรียนรู้ภูพาน สกลนคร",
        "url": model_url,
        "provider": {
            "@id": f"{PUBLIC_SITE_URL}/#organization"
        }
    }
    thumbnail = model.get("thumbnail_url") or model.get("thumbnail_resolved_url")
    if thumbnail:
        from urllib.parse import urljoin
        creative_work["image"] = urljoin(PUBLIC_SITE_URL, thumbnail)
    base["@graph"].append(creative_work)
    return base


def public_project_detail_structured_data(settings: dict, project: dict, models: list) -> dict:
    base = public_structured_data(settings)
    project_url = f"{PUBLIC_SITE_URL}/projects/{project['id']}"
    creative_work = {
        "@type": "CreativeWork",
        "@id": f"{project_url}#project",
        "name": project.get("name", ""),
        "description": project.get("description") or f"แหล่งเรียนรู้ {project.get('name', '')} ของดีสกลนคร",
        "url": project_url,
        "provider": {
            "@id": f"{PUBLIC_SITE_URL}/#organization"
        }
    }
    if project.get("cover_image_url"):
        from urllib.parse import urljoin
        creative_work["image"] = urljoin(PUBLIC_SITE_URL, project["cover_image_url"])
    base["@graph"].append(creative_work)
    return base



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
    name = str(project.get("name") or project.get("project_name") or "แหล่งเรียนรู้").strip()
    image_url = str(project.get("image_url") or "").strip()
    image_path = str(project.get("image_path") or project.get("cover_image") or project.get("image") or "").strip()
    return {
        "id": str(project.get("id") or uuid.uuid4().hex),
        "slug": str(project.get("slug") or "").strip(),
        "name": name,
        "description": str(project.get("description") or "").strip(),
        "department": str(project.get("department") or project.get("unit") or "").strip(),
        "cover_image": image_url or image_path,
        "image_url": image_url,
        "image_path": image_path,
        "visible": bool(project.get("visible", True)),
        "created_at": str(project.get("created_at") or "").strip(),
        "updated_at": str(project.get("updated_at") or "").strip(),
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
        rotate_y = float(model.get("rotate_y") or 0)
        rotate_z = float(model.get("rotate_z") or 0)
        scale = float(model.get("scale") or 0.2)
    except (TypeError, ValueError):
        rotate_x = 0
        rotate_y = 0
        rotate_z = 0
        scale = 0.2

    model_url = str(model.get("model_url") or "").strip()
    model_path = str(model.get("model_path") or model.get("model") or "").strip()
    thumbnail_url = str(model.get("thumbnail_url") or "").strip()
    thumbnail_path = str(model.get("thumbnail_path") or model.get("image") or model.get("thumbnail") or "").strip()
    narration_audio = str(model.get("narration_audio") or "").strip()
    size_mb = model.get("file_size_mb")
    try:
        size_mb = float(size_mb) if size_mb is not None else None
    except (TypeError, ValueError):
        size_mb = None

    return {
        "id": model_id,
        "slug": str(model.get("slug") or "").strip(),
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
        "file_size_mb": size_mb,
        "rotate_x": rotate_x,
        "rotate_y": rotate_y,
        "rotate_z": rotate_z,
        "scale": scale,
        "visible": bool(model.get("visible", True)),
        "created_at": str(model.get("created_at") or "").strip(),
        "updated_at": str(model.get("updated_at") or "").strip(),
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
    for key in LANDING_TYPOGRAPHY_SETTINGS:
        normalized[key] = normalize_landing_typography_value(key, normalized[key])
    return normalized


def normalize_landing_typography_value(key: str, value) -> str:
    minimum, maximum = LANDING_TYPOGRAPHY_SETTINGS[key]
    try:
        numeric_value = float(str(value).strip())
        if not math.isfinite(numeric_value):
            raise ValueError
        parsed_value = int(round(numeric_value))
    except (TypeError, ValueError):
        parsed_value = int(DEFAULT_SITE_SETTINGS[key])
    return str(max(minimum, min(parsed_value, maximum)))


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


def convert_to_wav(audio_data: bytes, mime_type: str | None) -> tuple[bytes, str]:
    mime = str(mime_type or "").lower()
    if mime.startswith(("audio/wav", "audio/x-wav")):
        return audio_data, ".wav"
    if mime.startswith(("audio/mpeg", "audio/mp3")):
        return audio_data, ".mp3"
    if mime.startswith(("audio/ogg", "application/ogg")):
        return audio_data, ".ogg"
    if mime.startswith(("audio/mp4", "audio/x-m4a")):
        return audio_data, ".m4a"
    sample_rate, channels, sample_width = parse_audio_mime_type(mime)
    return pcm_to_wav(audio_data, sample_rate, channels, sample_width), ".wav"


def generate_gemini_tts_audio(text: str) -> tuple[bytes, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiTTSError("GEMINI_API_KEY is not configured")

    prompt = (
        "อ่านคำบรรยายต่อไปนี้เป็นภาษาไทย น้ำเสียงชัดเจน เป็นมิตร "
        "เหมาะกับนิทรรศการและแหล่งเรียนรู้ เว้นจังหวะพอดี:\n"
        f"{text.strip()}"
    )
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.1-flash-tts-preview:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": "Iapetus"}
                }
            },
        },
    }
    request_obj = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(request_obj, timeout=90) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace").strip()
        raise GeminiTTSError(
            f"Gemini API returned HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except URLError as exc:
        raise GeminiTTSError(f"Gemini API connection failed: {exc.reason}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GeminiTTSError("Gemini API returned an invalid response") from exc

    try:
        inline_data = response_data["candidates"][0]["content"]["parts"][0][
            "inlineData"
        ]
        encoded_audio = inline_data["data"]
        mime_type = str(inline_data.get("mimeType") or "")
        audio_bytes = base64.b64decode(encoded_audio, validate=True)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiTTSError("Gemini did not return audio data") from exc
    if not audio_bytes:
        raise GeminiTTSError("Gemini did not return audio data")
    return convert_to_wav(audio_bytes, mime_type)


def slugify(value: str, fallback: str | None = None) -> str:
    raw = secure_filename(value or "") or (fallback or "")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-_").lower()
    return slug or uuid.uuid4().hex


def get_projects(include_hidden: bool = True) -> list[dict]:
    return load_projects(include_hidden=include_hidden)


def get_models(include_hidden: bool = True) -> list[dict]:
    return load_models(include_hidden=include_hidden)


def get_site_settings() -> dict:
    return load_site_settings()


def get_slider_items(include_inactive: bool = True) -> list[dict]:
    return load_slider_items(include_inactive=include_inactive)


def _dashboard_walk_urls(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _dashboard_walk_urls(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _dashboard_walk_urls(child)
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("https://", "http://")):
            yield candidate


def _dashboard_add_asset(assets: dict[str, str], value, category: str) -> None:
    values = value if isinstance(value, list) else [value]
    for candidate in values:
        if not isinstance(candidate, str):
            continue
        url = candidate.strip()
        if url.startswith(("https://", "http://")):
            assets.setdefault(url, category)


def dashboard_assets_from_sources(
    models: list[dict],
    projects: list[dict],
    settings: dict,
    sliders: list[dict],
) -> dict[str, str]:
    assets: dict[str, str] = {}
    for model in models:
        _dashboard_add_asset(assets, model.get("model_url"), "glb_models")
        _dashboard_add_asset(assets, model.get("thumbnail_url"), "thumbnails")
        _dashboard_add_asset(assets, model.get("preview_images"), "thumbnails")
        _dashboard_add_asset(assets, model.get("narration_audio"), "narration_audio")
    for project in projects:
        _dashboard_add_asset(assets, project.get("image_url"), "project_images")
    for value in settings.values():
        _dashboard_add_asset(assets, value, "site_settings_images")
    for slider in sliders:
        _dashboard_add_asset(assets, slider.get("image_url"), "slider_images")

    for url in _dashboard_walk_urls((models, projects, settings, sliders)):
        assets.setdefault(url, "other")
    return assets


def dashboard_asset_head(url: str) -> dict:
    cached_at = 0.0
    cached_result = None
    with _DASHBOARD_ASSET_CACHE_LOCK:
        cached = _DASHBOARD_ASSET_CACHE.get(url)
        if cached:
            cached_at, cached_result = cached
    if cached_result is not None and monotonic() - cached_at < DASHBOARD_ASSET_CACHE_TTL_SECONDS:
        return deepcopy(cached_result)

    result = {
        "reachable": False,
        "size_bytes": None,
        "status_code": None,
        "error": "Unknown asset response",
    }
    if urlsplit(url).hostname != R2_PUBLIC_HOST:
        result["error"] = "Asset is not hosted on the configured public R2 hostname"
        return result

    request_obj = Request(
        url,
        method="HEAD",
        headers={"User-Agent": "ARModel-Admin-Dashboard/1.0"},
    )
    try:
        with urlopen(request_obj, timeout=DASHBOARD_ASSET_HEAD_TIMEOUT_SECONDS) as response:
            status_code = int(response.status)
            raw_size = response.headers.get("Content-Length")
            size_bytes = int(raw_size) if raw_size and raw_size.isdigit() else None
            result = {
                "reachable": status_code == 200,
                "size_bytes": size_bytes,
                "status_code": status_code,
                "error": None if status_code == 200 else f"HTTP {status_code}",
            }
    except HTTPError as exc:
        result["status_code"] = int(exc.code)
        result["error"] = f"HTTP {exc.code}"
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        result["error"] = type(exc).__name__

    with _DASHBOARD_ASSET_CACHE_LOCK:
        _DASHBOARD_ASSET_CACHE[url] = (monotonic(), deepcopy(result))
    return result


def dashboard_storage_soft_limit() -> tuple[float, str]:
    raw_value = os.environ.get("R2_STORAGE_SOFT_LIMIT_GB", "").strip()
    if raw_value:
        try:
            value = float(raw_value)
            if math.isfinite(value) and value > 0:
                return value, "environment"
        except ValueError:
            pass
        logger.warning("Ignoring invalid R2_STORAGE_SOFT_LIMIT_GB value")
    return DEFAULT_R2_STORAGE_SOFT_LIMIT_GB, "default"


def dashboard_analytics_status() -> dict:
    """Provider adapter boundary for future real analytics integrations."""
    return {
        "enabled": False,
        "provider": None,
        "message": "ยังไม่ได้ตั้งค่าระบบวิเคราะห์ผู้เข้าชม",
        "metrics": None,
        "trend": [],
        "top_countries": [],
        "top_referrers": [],
        "top_pages": [],
    }


def dashboard_source_data() -> tuple[dict, list[str]]:
    specs = (
        ("models", CATALOG_FILE, list),
        ("projects", PROJECTS_FILE, list),
        ("site_settings", SITE_SETTINGS_FILE, dict),
        ("sliders", SLIDER_ITEMS_FILE, list),
    )
    sources = {}
    errors = []
    for name, path, expected_type in specs:
        try:
            with path.open("r", encoding="utf-8") as source_file:
                value = json.load(source_file)
            if not isinstance(value, expected_type):
                raise ValueError(f"expected {expected_type.__name__}")
            sources[name] = value
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            sources[name] = expected_type()
            errors.append(f"{name}: {type(exc).__name__}")

    project_ids = {
        str(project.get("id"))
        for project in sources["projects"]
        if isinstance(project, dict) and project.get("id") is not None
    }
    if any(
        not isinstance(model, dict) or str(model.get("project_id")) not in project_ids
        for model in sources["models"]
    ):
        errors.append("models: invalid project relationship")
    return sources, errors


def build_admin_dashboard_summary() -> dict:
    sources, data_errors = dashboard_source_data()
    assets = dashboard_assets_from_sources(
        sources["models"],
        sources["projects"],
        sources["site_settings"],
        sources["sliders"],
    )
    r2_assets = {
        url: category
        for url, category in assets.items()
        if urlsplit(url).hostname == R2_PUBLIC_HOST
    }
    supabase_count = sum(
        1
        for url in assets
        if "supabase.co" in (urlsplit(url).hostname or "").lower()
    )

    checks: dict[str, dict] = {}
    if r2_assets:
        with ThreadPoolExecutor(max_workers=min(10, len(r2_assets))) as executor:
            future_map = {
                executor.submit(dashboard_asset_head, url): url for url in r2_assets
            }
            for future in as_completed(future_map):
                url = future_map[future]
                try:
                    checks[url] = future.result()
                except Exception as exc:  # Keep one failed check from breaking the summary.
                    logger.warning("Dashboard asset check failed for %s: %s", url, exc)
                    checks[url] = {
                        "reachable": False,
                        "size_bytes": None,
                        "status_code": None,
                        "error": type(exc).__name__,
                    }

    categories = (
        "glb_models",
        "thumbnails",
        "narration_audio",
        "project_images",
        "site_settings_images",
        "slider_images",
        "other",
    )
    breakdown = []
    for category in categories:
        urls = [url for url, item_category in r2_assets.items() if item_category == category]
        known_sizes = [
            checks[url]["size_bytes"]
            for url in urls
            if checks.get(url, {}).get("size_bytes") is not None
        ]
        breakdown.append(
            {
                "category": category,
                "asset_count": len(urls),
                "known_size_count": len(known_sizes),
                "unknown_size_count": len(urls) - len(known_sizes),
                "size_bytes": sum(known_sizes),
            }
        )

    known_size_bytes = sum(item["size_bytes"] for item in breakdown)
    reachable_count = sum(1 for result in checks.values() if result["reachable"])
    unknown_size_count = sum(item["unknown_size_count"] for item in breakdown)
    soft_limit_gb, soft_limit_source = dashboard_storage_soft_limit()
    soft_limit_bytes = int(soft_limit_gb * 1024**3)
    remaining_bytes = max(0, soft_limit_bytes - known_size_bytes)
    usage_percent = (
        min(100.0, known_size_bytes / soft_limit_bytes * 100)
        if soft_limit_bytes
        else 0.0
    )
    reachability_score = (
        round(reachable_count / len(r2_assets) * 100) if r2_assets else 100
    )
    integrity_score = 100 if not data_errors else 0

    asset_counts = {item["category"]: item["asset_count"] for item in breakdown}
    asset_counts.update(
        {
            "tracked_urls": len(assets),
            "r2_urls": len(r2_assets),
            "supabase_urls": supabase_count,
        }
    )
    return {
        "runtime": {
            "source": "JSON",
            "asset_storage": "Cloudflare R2",
            "production": is_vercel_runtime(),
            "admin_mode": "read-only" if is_vercel_runtime() else "local development",
            "full_bucket_inventory": False,
        },
        "content": {
            "models": len(sources["models"]),
            "projects": len(sources["projects"]),
            "site_settings": len(sources["site_settings"]),
            "sliders": len(sources["sliders"]),
        },
        "assets": asset_counts,
        "storage": {
            "label": "พื้นที่ของไฟล์ public ที่ระบบติดตาม",
            "known_size_bytes": known_size_bytes,
            "unknown_size_count": unknown_size_count,
            "reachable_count": reachable_count,
            "failed_count": len(r2_assets) - reachable_count,
            "checked_count": len(r2_assets),
            "soft_limit_gb": soft_limit_gb,
            "soft_limit_bytes": soft_limit_bytes,
            "soft_limit_source": soft_limit_source,
            "remaining_bytes": remaining_bytes,
            "usage_percent": round(usage_percent, 2),
            "is_complete_bucket_inventory": False,
            "breakdown": breakdown,
        },
        "health": {
            "json_data_integrity": {
                "score": integrity_score,
                "status": "healthy" if integrity_score == 100 else "error",
                "details": data_errors,
            },
            "r2_asset_reachability": {
                "score": reachability_score,
                "status": "healthy" if reachability_score == 100 else "warning",
                "details": {
                    "reachable": reachable_count,
                    "checked": len(r2_assets),
                },
            },
            "supabase_url_cleanliness": {
                "score": 100 if supabase_count == 0 else 0,
                "status": "healthy" if supabase_count == 0 else "error",
                "details": {"supabase_urls": supabase_count},
            },
            "admin_read_only_protection": {
                "score": 100 if is_vercel_runtime() else 100,
                "status": "protected" if is_vercel_runtime() else "local",
                "details": {
                    "production_read_only": is_vercel_runtime(),
                    "production_rule_enabled": True,
                },
            },
            "public_runtime_status": {
                "score": integrity_score,
                "status": "operational" if integrity_score == 100 else "degraded",
                "details": {"source": "JSON"},
            },
        },
        "analytics": dashboard_analytics_status(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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
    if is_vercel_runtime():
        raise GeminiTTSError("Narration persistence is disabled in production read-only mode")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / filename).write_bytes(audio_data)
    return f"audio/{filename}"


def admin_write_blocked_on_vercel() -> bool:
    if not is_vercel_runtime():
        return False
    abort(403, VERCEL_EDIT_MESSAGE)


def upload_attempted(*field_names: str) -> bool:
    for field_name in field_names:
        file_storage = request.files.get(field_name)
        if file_storage and file_storage.filename:
            return True
    return False


def reject_vercel_upload_if_needed(*field_names: str) -> bool:
    if is_vercel_runtime() and upload_attempted(*field_names):
        abort(403, VERCEL_UPLOAD_MESSAGE)
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
    uploaded_path = save_site_upload(file_storage, directory, relative_folder, allowed_extensions)
    return uploaded_path or submitted_url or settings.get(key, "")


def slider_data_from_request(existing: dict | None = None) -> dict:
    existing = existing or {}
    image_url = request.form.get("image_url", "").strip()
    file_storage = request.files.get("image_file")
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

    # Select featured models
    rec_ids_str = settings.get("recommended_model_ids", "")
    recommended_ids = [r.strip() for r in rec_ids_str.split(",") if r.strip()]
    is_custom_recommended = False

    if recommended_ids:
        model_map = {m["id"]: m for m in all_models}
        featured_models = []
        for mid in recommended_ids:
            if mid in model_map and model_map[mid] not in featured_models:
                featured_models.append(model_map[mid])
        featured_models = featured_models[:MAX_RECOMMENDED_MODELS]
        if featured_models:
            is_custom_recommended = True
        else:
            featured_models = all_models[:MAX_RECOMMENDED_MODELS]
    else:
        featured_models = all_models[:MAX_RECOMMENDED_MODELS]

    sliders = [slider_with_url(item) for item in get_slider_items(include_inactive=False)]
    return render_template(
        "index.html",
        projects=projects,
        model_counts=counts,
        featured_models=featured_models,
        is_custom_recommended=is_custom_recommended,
        total_project_count=len(projects),
        total_model_count=len(all_models),
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
        page_title="โมเดล 3D ภูพาน AR สกลนคร | ของดีสกลนครและแหล่งเรียนรู้ท้องถิ่นออนไลน์",
        page_description="สำรวจและค้นหาโมเดล 3D และ AR ของดีสกลนคร เช่น ลูกประคบ ลิ้นจี่ ข้าวสกลนคร และแหล่งเรียนรู้ภูพานในพิพิธภัณฑ์ออนไลน์เสมือนจริง",
        structured_data=public_models_structured_data(settings, all_models),
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
        page_title=f"{project.get('name', '')} | แหล่งเรียนรู้สกลนคร ภูพาน โมเดล 3D AR ของดีสกลนคร",
        page_description=(
            f"{project.get('description')} เรียนรู้ผ่านโมเดล 3D และ AR ของศูนย์ศึกษาการพัฒนาภูพาน จังหวัดสกลนคร"
            if project.get("description")
            else f"ร่วมเรียนรู้และอนุรักษ์ {project.get('name', '')} ของดีสกลนคร ภูพาน ในรูปแบบออนไลน์ 3D AR"
        ),
        structured_data=public_project_detail_structured_data(settings, project, models),
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
        page_title=f"{model.get('name', '')} | โมเดล 3D AR ภูพาน สกลนคร ของดีสกลนคร",
        page_description=(
            f"โมเดล 3D และ AR {model.get('name', '')} ของดีสกลนคร: {model.get('description', '')[:120]} เรียนรู้ภูพาน สกลนคร ในพิพิธภัณฑ์ออนไลน์"
            if model.get("description")
            else f"ชมโมเดล 3D และ AR {model.get('name', '')} แหล่งเรียนรู้ภูพาน สกลนคร และของดีสกลนครแบบเสมือนจริง"
        ),
        structured_data=public_model_detail_structured_data(settings, model),
        page_image=public_meta_image_url(resolve_thumbnail_url(model)),
        page_url=public_url_for("model_detail", model_id=model_id),
    )


@app.get("/api/models")
def api_models():
    projects = get_projects(include_hidden=True)
    models = get_models(include_hidden=True)
    return jsonify([api_model_payload(model, projects) for model in models])


@app.get("/api/projects")
def api_projects():
    models = get_models(include_hidden=True)
    return jsonify(
        [
            project_with_urls(project, models)
            for project in get_projects(include_hidden=True)
        ]
    )


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


@app.get("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


@app.get("/admin/api/dashboard/summary")
@admin_required
def admin_dashboard_summary():
    try:
        return jsonify(build_admin_dashboard_summary())
    except Exception:
        logger.exception("Unable to build admin dashboard summary")
        return jsonify(
            {
                "error": "ไม่สามารถโหลดข้อมูลสรุปของแดชบอร์ดได้ในขณะนี้",
                "analytics": dashboard_analytics_status(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        ), 503


@app.route("/admin/landing")
@admin_required
def admin_landing():
    return render_template("admin_landing.html", settings=site_settings_with_urls(get_site_settings()))


@app.route("/admin/landing/preview")
@admin_required
def admin_landing_preview():
    return render_template(
        "admin_landing_preview.html",
        settings=site_settings_with_urls(get_site_settings()),
    )


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
        save_slider_items([data if item["id"] == slider_id else item for item in sliders])
        flash("บันทึกสไลด์แล้ว", "success")
        return redirect(url_for("admin_sliders"))
    return render_template("edit_slider.html", slider=slider_with_url(slider))


@app.route("/admin/sliders/<slider_id>", methods=["POST", "DELETE"])
@admin_required
def delete_slider(slider_id: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin_sliders"))
    sliders = load_slider_items(include_inactive=True)
    if not any(item["id"] == slider_id for item in sliders):
        abort(404)
    save_slider_items([item for item in sliders if item["id"] != slider_id])
    if request.method == "DELETE":
        return "", 204
    flash("ลบสไลด์แล้ว", "success")
    return redirect(url_for("admin_sliders"))


@app.route("/admin/recommended-models", methods=["GET", "POST"])
@admin_required
def admin_recommended_models():
    settings = get_site_settings()
    if request.method == "POST":
        if admin_write_blocked_on_vercel():
            return redirect(url_for("admin_recommended_models"))

        selected_ids = request.form.getlist("recommended_ids")

        id_order_pairs = []
        for mid in selected_ids:
            try:
                order_val = int(request.form.get(f"sort_order_{mid}", "0") or 0)
            except (TypeError, ValueError):
                order_val = 0
            id_order_pairs.append((mid, order_val))

        id_order_pairs.sort(key=lambda x: x[1])
        sorted_ids = [pair[0] for pair in id_order_pairs][:MAX_RECOMMENDED_MODELS]

        settings["recommended_model_ids"] = ",".join(sorted_ids)

        save_site_settings(settings)

        flash("บันทึกรายชื่อโมเดลแนะนำแล้ว", "success")
        return redirect(url_for("admin_recommended_models"))

    models = get_models(include_hidden=False)
    projects = get_projects(include_hidden=False)
    all_models = [model_with_project(model, projects) for model in models]

    rec_ids_str = settings.get("recommended_model_ids", "")
    recommended_ids = [r.strip() for r in rec_ids_str.split(",") if r.strip()]
    rec_order_map = {mid: i + 1 for i, mid in enumerate(recommended_ids)}

    for m in all_models:
        m["is_recommended"] = m["id"] in rec_order_map
        m["recommend_order"] = rec_order_map.get(m["id"], "")

    return render_template("admin_recommended_models.html", models=all_models)


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
                **{
                    key: normalize_landing_typography_value(
                        key,
                        request.form.get(key) or DEFAULT_SITE_SETTINGS[key],
                    )
                    for key in LANDING_TYPOGRAPHY_SETTINGS
                },
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
    save_site_settings(settings)
    flash("บันทึกการตั้งค่าแล้ว", "success")
    return redirect(request.form.get("return_to") or url_for("admin"))


@app.post("/admin/api/create-upload-url")
@admin_required
def create_admin_upload_url():
    abort(403, VERCEL_UPLOAD_MESSAGE)


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
        abort(400, "จำเป็นต้องกรอกชื่อแหล่งเรียนรู้ (Project Name)")

    image_url = request.form.get("image_url", "").strip()
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
    flash(f'เพิ่มแหล่งเรียนรู้ "{name}" แล้ว', "success")
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
        flash("บันทึกข้อมูลแหล่งเรียนรู้แล้ว", "success")
        return redirect(url_for("admin"))

    return render_template("edit_project.html", project=project_with_urls(project))


@app.post("/admin/projects/<project_id>/delete", endpoint="delete_project")
@admin_required
def delete_project_route(project_id: str):
    if admin_write_blocked_on_vercel():
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
    flash(f'ลบแหล่งเรียนรู้ "{project.get("name", "")}" และโมเดลในแหล่งเรียนรู้แล้ว', "success")
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
        abort(400, "จำเป็นต้องเลือกแหล่งเรียนรู้ (Project)")

    model_url = request.form.get("model_url", "").strip()
    thumbnail_url = request.form.get("thumbnail_url", "").strip()
    preview_images = parse_preview_images_field(request.form.get("preview_images"))
    narration_audio = parse_narration_audio_field(request.form.get("narration_audio"))

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
            "rotate_y": parse_float("rotate_y", 0),
            "rotate_z": parse_float("rotate_z", 0),
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
            abort(400, "จำเป็นต้องเลือกแหล่งเรียนรู้ (Project)")
        preview_images = parse_preview_images_field(request.form.get("preview_images"))
        remove_narration_audio = request.form.get("narration_audio_remove") in {"1", "true", "on", "yes"}

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
                "rotate_y": parse_float("rotate_y", 0),
                "rotate_z": parse_float("rotate_z", 0),
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
    except (GeminiTTSError, OSError) as exc:
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
