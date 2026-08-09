import base64
import hmac
import hashlib
import io
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import tempfile
import uuid
import wave
import csv
import xml.etree.ElementTree as ET
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from threading import Lock, Timer
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from flask import abort, flash, Flask, jsonify, redirect, render_template, request, session, url_for, send_file, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from armodel.services import analytics as analytics_service
from armodel.services import audit as audit_service
from armodel.services import github_storage, r2_storage
from armodel.services import narration as narration_service
from armodel.repositories import content as content_repository


def load_local_env() -> None:
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


MODEL_EXTENSIONS = {".glb"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg"}
SITE_LOGO_EXTENSIONS = IMAGE_EXTENSIONS | {".svg"}
FAVICON_EXTENSIONS = {".png", ".ico", ".svg"}
SITE_ASSET_MAX_BYTES = 5 * 1024 * 1024
NARRATION_AUDIO_MAX_BYTES = 20 * 1024 * 1024
NARRATION_DRAFT_MAX_AGE_SECONDS = 30 * 60
NARRATION_PENDING_PREFIX = "audio/pending/"
NARRATION_PERMANENT_PREFIX = "audio/narrations/"
LOCAL_NARRATION_DRAFT_DIR = Path(tempfile.gettempdir()) / "armodel-narration-drafts"
LOCAL_AUDIT_LOG_DIR = Path(tempfile.gettempdir()) / "armodel-audit-logs"
LOCAL_LOGIN_RATE_LIMIT_DIR = Path(tempfile.gettempdir()) / "armodel-login-rate-limit"
AUDIT_PREFIX = "audit/"
LOGIN_FAILURE_PREFIX = "auth/login-failures/"
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
AUDIT_PAGE_SIZE = 50
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
ANALYTICS_FILE = DATA_DIR / "analytics_events.json"
SITE_UPLOAD_DIR = STATIC_DIR / "uploads" / "site"
SLIDER_UPLOAD_DIR = STATIC_DIR / "uploads" / "sliders"
_JSON_CACHE: dict[Path, tuple[float | None, object]] = {}
_PRODUCTION_JSON_CACHE: dict[str, tuple[float, object]] = {}
PRODUCTION_JSON_CACHE_TTL_SECONDS = 30
R2_PUBLIC_HOST = "pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev"
DASHBOARD_ASSET_CACHE_TTL_SECONDS = 300
DASHBOARD_ASSET_HEAD_TIMEOUT_SECONDS = 5
DEFAULT_R2_STORAGE_SOFT_LIMIT_GB = 10.0
_DASHBOARD_ASSET_CACHE: dict[str, tuple[float, dict]] = {}
_DASHBOARD_ASSET_CACHE_LOCK = Lock()
_ANALYTICS_LOCK = Lock()
ANALYTICS_MAX_EVENTS = 10000
ANALYTICS_R2_OBJECT_KEY = os.environ.get(
    "ANALYTICS_R2_OBJECT_KEY",
    "analytics/analytics_events.json",
).strip("/")
ANALYTICS_EVENT_PREFIX = "analytics/events/"
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
_DATA_READY = False
PRODUCTION_DATA_FILES = {
    "models.json",
    "projects.json",
    "site_settings.json",
    "slider_items.json",
}

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))


def csrf_token() -> str:
    """Return the per-session token used by authenticated Admin mutations."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.before_request
def protect_admin_mutations_with_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if not request.path.startswith("/admin/") or request.path == "/admin/login":
        return None
    if not session.get("admin"):
        return None
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        abort(400, "Invalid CSRF token")


def is_vercel_runtime() -> bool:
    return bool(os.environ.get("VERCEL"))


def env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def github_content_configured() -> bool:
    return bool(
        env_value("GITHUB_CONTENTS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
        and env_value("GITHUB_REPOSITORY", "GITHUB_REPO")
    )


def r2_upload_configured() -> bool:
    return bool(
        env_value("R2_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
        and env_value("R2_ACCESS_KEY_ID")
        and env_value("R2_SECRET_ACCESS_KEY")
        and env_value("R2_BUCKET")
        and env_value("R2_PUBLIC_BASE_URL")
    )


def production_admin_writes_enabled() -> bool:
    return (not is_vercel_runtime()) or github_content_configured()


def production_uploads_enabled() -> bool:
    return (not is_vercel_runtime()) or r2_upload_configured()


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
        "admin_read_only": is_vercel_runtime() and not production_admin_writes_enabled(),
        "uploads_disabled": is_vercel_runtime() and not production_uploads_enabled(),
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
    if is_vercel_runtime() and github_content_configured():
        relative_path = production_data_relative_path(path)
        if relative_path:
            cached = _PRODUCTION_JSON_CACHE.get(relative_path)
            if cached and monotonic() - cached[0] < PRODUCTION_JSON_CACHE_TTL_SECONDS:
                return deepcopy(cached[1])
            try:
                branch = env_value("GITHUB_BRANCH", "GIT_BRANCH") or "main"
                current = github_api_request(
                    "GET",
                    f"/repos/{env_value('GITHUB_REPOSITORY', 'GITHUB_REPO')}/contents/{quote(relative_path, safe='/')}?ref={quote(branch, safe='')}",
                )
                raw_content = base64.b64decode(current.get("content", "")).decode("utf-8")
                value = json.loads(raw_content)
                if isinstance(value, type(default)):
                    _PRODUCTION_JSON_CACHE[relative_path] = (monotonic(), deepcopy(value))
                    return deepcopy(value)
                logger.warning("Unexpected production JSON shape for %s", relative_path)
            except Exception as exc:
                logger.warning("Unable to read production JSON from GitHub for %s: %s", relative_path, exc)

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


def production_data_relative_path(path: Path) -> str | None:
    try:
        relative_path = path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        return None
    if relative_path.name not in PRODUCTION_DATA_FILES or len(relative_path.parts) != 1:
        return None
    return f"data/{relative_path.name}"


def github_api_request(method: str, api_path: str, payload: dict | None = None) -> dict:
    token = env_value("GITHUB_CONTENTS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
    if not token:
        abort(500, "GITHUB_CONTENTS_TOKEN is not configured")
    try:
        return github_storage.request_json(method, api_path, token, payload, opener=urlopen)
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace").strip()
        logger.warning("GitHub content API failed: HTTP %s %s", exc.code, detail)
        abort(502, f"GitHub content update failed: HTTP {exc.code}")
    except (URLError, OSError, TimeoutError) as exc:
        logger.warning("GitHub content API connection failed: %s", exc)
        abort(502, "GitHub content update failed")


def github_commit_json(relative_path: str, value) -> None:
    repo = env_value("GITHUB_REPOSITORY", "GITHUB_REPO")
    branch = env_value("GITHUB_BRANCH", "GIT_BRANCH") or "main"
    if not repo:
        abort(500, "GITHUB_REPOSITORY is not configured")
    committer_name = env_value("GITHUB_COMMITTER_NAME")
    committer_email = env_value("GITHUB_COMMITTER_EMAIL")
    github_storage.commit_json(
        relative_path,
        value,
        repository=repo,
        branch=branch,
        requester=lambda method, path, payload=None: github_api_request(method, path, payload),
        committer_name=committer_name,
        committer_email=committer_email,
    )


def write_json(path: Path, value) -> None:
    if is_vercel_runtime():
        relative_path = production_data_relative_path(path)
        if relative_path and github_content_configured():
            github_commit_json(relative_path, value)
            _JSON_CACHE.pop(path.resolve(), None)
            _PRODUCTION_JSON_CACHE.pop(relative_path, None)
            return
        logger.warning("Blocked JSON write on Vercel runtime: %s", path)
        abort(403, VERCEL_EDIT_MESSAGE)

    path = path.resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
        _JSON_CACHE.pop(path, None)
    except OSError as exc:
        logger.exception("Unable to write JSON file %s", path)
        abort(500, f"Unable to save data: {exc}")


def analytics_tracking_enabled() -> bool:
    if os.environ.get("ARMODEL_ANALYTICS_ENABLED", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    return (not is_vercel_runtime()) or r2_upload_configured()


def analytics_provider_name() -> str | None:
    if not analytics_tracking_enabled():
        return None
    return "cloudflare-r2-json" if is_vercel_runtime() else "local-json"


def analytics_should_track(response) -> bool:
    if not analytics_tracking_enabled() or response.status_code >= 400:
        return False
    if request.method != "GET":
        return False
    endpoint = request.endpoint or ""
    if endpoint == "static" or endpoint.startswith("admin") or endpoint.startswith("api_"):
        return False
    if request.path.startswith(("/admin", "/api", "/static")):
        return False
    content_type = response.headers.get("Content-Type", "")
    return "text/html" in content_type


def analytics_visitor_id() -> tuple[str, bool]:
    value = request.cookies.get("armodel_visitor_id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{16,80}", value):
        return value, False
    seed = "|".join(
        [
            request.headers.get("User-Agent", ""),
            request.headers.get("Accept-Language", ""),
            request.remote_addr or "",
            secrets.token_urlsafe(16),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32], True


def analytics_country_label() -> str:
    value = (
        request.headers.get("CF-IPCountry")
        or request.headers.get("X-Vercel-IP-Country")
        or request.headers.get("X-Country-Code")
        or ""
    ).strip().upper()
    if len(value) == 2 and value != "XX":
        return value
    if request.remote_addr in {"127.0.0.1", "::1"}:
        return "LOCAL"
    return "Unknown"


def analytics_referrer_label() -> str:
    raw_referrer = request.headers.get("Referer", "").strip()
    if not raw_referrer:
        return "Direct"
    host = (urlsplit(raw_referrer).hostname or "").lower()
    if not host:
        return "Direct"
    current_host = (request.host or "").split(":", 1)[0].lower()
    public_host = (urlsplit(PUBLIC_SITE_URL).hostname or "").lower()
    if host in {current_host, public_host}:
        return "Internal"
    return host.removeprefix("www.")


def content_lookup(records: list[dict]) -> dict[str, dict]:
    return content_repository.content_lookup(records)


def analytics_page_label(
    path: str,
    *,
    project_lookup: dict[str, dict] | None = None,
    model_lookup: dict[str, dict] | None = None,
) -> str:
    path = urlsplit(path).path.rstrip("/") or "/"
    if path == "/":
        return "Landing"
    if path == "/home":
        return "Home"
    if path == "/models":
        return "Models"
    if path.startswith("/models/"):
        model_id = path.rsplit("/", 1)[-1]
        if model_lookup is None:
            model_lookup = content_lookup(get_models(include_hidden=True))
        model = model_lookup.get(model_id)
        if model is None:
            return "โมเดลที่ไม่พบ"
        return f"Model: {model.get('name') or 'โมเดลที่ไม่พบ'}"
    if path.startswith("/projects/"):
        project_id = path.rsplit("/", 1)[-1]
        if project_lookup is None:
            project_lookup = content_lookup(get_projects(include_hidden=True))
        project = project_lookup.get(project_id)
        if project is None:
            return "โครงการที่ไม่พบ"
        return f"Project: {project.get('name') or 'โครงการที่ไม่พบ'}"
    return path


def read_analytics_events() -> list[dict]:
    if is_vercel_runtime():
        if not r2_upload_configured():
            return []
        events: list[dict] = []
        try:
            value = json.loads(r2_get_bytes(ANALYTICS_R2_OBJECT_KEY).decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 404:
                logger.warning("Unable to read analytics R2 object: HTTP %s", exc.code)
            value = []
        except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read analytics R2 object: %s", exc)
            value = []
        if isinstance(value, list):
            events.extend(event for event in value if isinstance(event, dict))

        continuation = ""
        keys: list[str] = []
        try:
            while len(keys) < ANALYTICS_MAX_EVENTS:
                page, continuation = r2_list_object_keys(
                    ANALYTICS_EVENT_PREFIX,
                    max_keys=min(1000, ANALYTICS_MAX_EVENTS - len(keys)),
                    continuation_token=continuation,
                )
                keys.extend(page)
                if not continuation:
                    break
        except Exception as exc:
            logger.warning("Unable to list immutable analytics events: %s", exc)
            return events[-ANALYTICS_MAX_EVENTS:]

        for key in keys:
            try:
                event = json.loads(r2_get_bytes(key).decode("utf-8"))
            except Exception as exc:
                logger.warning("Skipping unreadable analytics event %s: %s", key, exc)
                continue
            if isinstance(event, dict):
                events.append(event)
        return events[-ANALYTICS_MAX_EVENTS:]

    events = read_json(ANALYTICS_FILE, [])
    return [event for event in events if isinstance(event, dict)]


def append_analytics_event(event: dict) -> None:
    if is_vercel_runtime():
        if not r2_upload_configured():
            return
        stored_event = dict(event)
        stored_event.setdefault("event_id", uuid.uuid4().hex)
        occurred_at = _analytics_event_datetime(stored_event) or datetime.now(timezone.utc)
        key = (
            f"{ANALYTICS_EVENT_PREFIX}{occurred_at:%Y/%m/%d}/"
            f"{occurred_at:%Y%m%dT%H%M%S.%fZ}-{stored_event['event_id']}.json"
        )
        payload = json.dumps(stored_event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        r2_upload_bytes(
            payload,
            key,
            "application/json; charset=utf-8",
            cache_control="no-store, max-age=0",
        )
        return

    with _ANALYTICS_LOCK:
        events = read_analytics_events()
        events.append(event)
        if len(events) > ANALYTICS_MAX_EVENTS:
            events = events[-ANALYTICS_MAX_EVENTS:]
        write_json(ANALYTICS_FILE, events)


@app.after_request
def record_local_analytics(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(self)")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if is_vercel_runtime() or request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if (
        session.get("admin")
        and request.path.startswith("/admin")
        and response.mimetype == "text/html"
        and response.status_code < 400
    ):
        token = csrf_token()
        html = response.get_data(as_text=True)
        html = re.sub(
            r"(<form\\b[^>]*method=[\"']post[\"'][^>]*>)",
            lambda match: match.group(1) + f'<input type="hidden" name="csrf_token" value="{token}">',
            html,
            flags=re.IGNORECASE,
        )
        response.set_data(html)
    if not analytics_should_track(response):
        return response
    visitor_id, needs_cookie = analytics_visitor_id()
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "visitor_id": visitor_id,
        "path": request.path,
        "page": analytics_page_label(request.path),
        "referrer": analytics_referrer_label(),
        "country": analytics_country_label(),
        "user_agent_hash": hashlib.sha256(
            request.headers.get("User-Agent", "").encode("utf-8")
        ).hexdigest()[:16],
    }
    try:
        append_analytics_event(event)
        if needs_cookie:
            response.set_cookie(
                "armodel_visitor_id",
                visitor_id,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Lax",
            )
    except Exception as exc:
        logger.warning("Unable to record local analytics event: %s", exc)
    return response


def _analytics_event_datetime(event: dict) -> datetime | None:
    return analytics_service.event_datetime(event)


def dashboard_analytics_status(selected_date: date | None = None) -> dict:
    selected_date = selected_date or datetime.now(BANGKOK_TZ).date()
    project_lookup = content_lookup(get_projects(include_hidden=True))
    model_lookup = content_lookup(get_models(include_hidden=True))
    events = []
    for event in read_analytics_events():
        occurred_at = _analytics_event_datetime(event)
        if occurred_at is None:
            continue
        normalized = dict(event)
        path = str(event.get("path") or "").strip()
        if path:
            normalized["page"] = analytics_page_label(
                path,
                project_lookup=project_lookup,
                model_lookup=model_lookup,
            )
        normalized["_occurred_at"] = occurred_at
        events.append(normalized)

    return analytics_service.dashboard_status(
        events,
        selected_date,
        provider=analytics_provider_name(),
        today=datetime.now(BANGKOK_TZ).date(),
    )


def save_projects(projects: list[dict]) -> None:
    write_json(PROJECTS_FILE, projects)


def save_models(models: list[dict]) -> None:
    write_json(CATALOG_FILE, models)


def normalize_project(project: dict) -> dict:
    return content_repository.normalize_project(project, default_name="แหล่งเรียนรู้")


def load_projects(include_hidden: bool = True) -> list[dict]:
    ensure_data_files()
    return content_repository.load_normalized(
        PROJECTS_FILE,
        DEFAULT_PROJECTS,
        read_json,
        normalize_project,
        visible_key="visible",
        include_hidden=include_hidden,
    )


def normalize_preview_images(value) -> list[str]:
    return content_repository.normalize_preview_images(value)


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
    return content_repository.normalize_model(model, projects, default_name="โมเดล")


def load_models(include_hidden: bool = True) -> list[dict]:
    ensure_data_files()
    projects = load_projects(include_hidden=True)
    return content_repository.load_normalized(
        CATALOG_FILE,
        DEFAULT_MODELS,
        read_json,
        lambda model: normalize_model(model, projects),
        visible_key="visible",
        include_hidden=include_hidden,
    )


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
    return content_lookup(get_projects(include_hidden=include_hidden)).get(project_id)


def find_model(model_id: str, include_hidden: bool = False) -> dict | None:
    return content_lookup(get_models(include_hidden=include_hidden)).get(model_id)


def load_config() -> dict:
    return read_json(CONFIG_FILE, {})


def save_config(config: dict) -> None:
    write_json(CONFIG_FILE, config)


def normalize_site_settings(settings: dict | None) -> dict:
    return content_repository.normalize_site_settings(
        settings, DEFAULT_SITE_SETTINGS, LANDING_TYPOGRAPHY_SETTINGS
    )


def normalize_landing_typography_value(key: str, value) -> str:
    return content_repository.normalize_landing_typography_value(
        key, value, DEFAULT_SITE_SETTINGS, LANDING_TYPOGRAPHY_SETTINGS
    )


def load_site_settings() -> dict:
    return normalize_site_settings(read_json(SITE_SETTINGS_FILE, DEFAULT_SITE_SETTINGS))


def save_site_settings(settings: dict) -> None:
    write_json(SITE_SETTINGS_FILE, normalize_site_settings(settings))


def normalize_slider_item(item: dict) -> dict:
    return content_repository.normalize_slider_item(item)


def load_slider_items(include_inactive: bool = True) -> list[dict]:
    items = content_repository.load_normalized(
        SLIDER_ITEMS_FILE, DEFAULT_SLIDER_ITEMS, read_json, normalize_slider_item
    )
    items.sort(key=lambda item: (item["sort_order"], item["id"]))
    if include_inactive:
        return items
    return [item for item in items if item["active"]]


def save_slider_items(items: list[dict]) -> None:
    content_repository.save_normalized(
        SLIDER_ITEMS_FILE,
        items,
        write_json,
        normalize_slider_item,
        sort_key=lambda item: (item["sort_order"], item["id"]),
    )


def slider_save_flash_message(action: str) -> str:
    if is_vercel_runtime() and production_admin_writes_enabled():
        return f"{action} saved. Production may take up to {PRODUCTION_JSON_CACHE_TTL_SECONDS} seconds to show the latest data."
    return f"{action} saved."


GeminiTTSError = narration_service.GeminiTTSError


def pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    return narration_service.pcm_to_wav(pcm_data, sample_rate, channels, sample_width)


def parse_audio_mime_type(mime_type: str | None) -> tuple[int, int, int]:
    return narration_service.parse_audio_mime_type(mime_type)


def convert_to_wav(audio_data: bytes, mime_type: str | None) -> tuple[bytes, str]:
    return narration_service.convert_to_wav(audio_data, mime_type)


def generate_gemini_tts_audio(text: str) -> tuple[bytes, str]:
    return narration_service.generate_gemini_tts_audio(
        text, os.environ.get("GEMINI_API_KEY", "").strip(), opener=urlopen
    )


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


def dashboard_analytics_status_disabled_placeholder() -> dict:
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


def build_admin_dashboard_summary(selected_date: date | None = None) -> dict:
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
            "admin_mode": (
                "writable"
                if is_vercel_runtime() and production_admin_writes_enabled()
                else ("read-only" if is_vercel_runtime() else "local development")
            ),
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
                "score": 100,
                "status": (
                    "writable"
                    if is_vercel_runtime() and production_admin_writes_enabled()
                    else ("protected" if is_vercel_runtime() else "local")
                ),
                "details": {
                    "production_read_only": is_vercel_runtime() and not production_admin_writes_enabled(),
                    "production_rule_enabled": True,
                },
            },
            "public_runtime_status": {
                "score": integrity_score,
                "status": "operational" if integrity_score == 100 else "degraded",
                "details": {"source": "JSON"},
            },
        },
        "analytics": dashboard_analytics_status(selected_date),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def r2_public_base_url() -> str:
    return env_value("R2_PUBLIC_BASE_URL").rstrip("/")


def r2_object_folder(relative_folder: str) -> str:
    mapping = {
        "model": "models",
        "pic": "images",
        "audio": "audio",
        "uploads/sliders": "sliders",
        "uploads/site": "site",
        "uploads/site/intro": "site/intro",
        "uploads/site/social": "site/social",
    }
    return mapping.get(relative_folder.strip("/"), relative_folder.strip("/"))


def r2_signed_request(
    method: str,
    object_key: str,
    payload_hash: str,
    extra_headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 120,
    query_params: dict[str, str] | None = None,
):
    account_id = env_value("R2_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
    access_key = env_value("R2_ACCESS_KEY_ID")
    secret_key = env_value("R2_SECRET_ACCESS_KEY")
    bucket = env_value("R2_BUCKET")
    if not all((account_id, access_key, secret_key, bucket)):
        abort(500, "R2 environment variables are not configured")

    return r2_storage.signed_request(
        method,
        object_key,
        payload_hash,
        account_id=account_id,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        extra_headers=extra_headers,
        data=data,
        timeout=timeout,
        query_params=query_params,
        opener=urlopen,
    )

def r2_get_bytes(object_key: str) -> bytes:
    try:
        status, body = r2_storage.get_bytes(r2_signed_request, object_key)
        if status != 200:
            abort(502, f"R2 read failed: HTTP {status}")
        return body
    except HTTPError:
        raise
    except (URLError, OSError, TimeoutError) as exc:
        logger.warning("R2 read connection failed: %s", exc)
        abort(502, "R2 read failed")


def r2_list_object_keys(
    prefix: str,
    max_keys: int = AUDIT_PAGE_SIZE,
    continuation_token: str = "",
) -> tuple[list[str], str]:
    """List a bounded page of private R2 object keys using S3 ListObjectsV2."""
    try:
        status, keys, next_token = r2_storage.list_object_keys(
            r2_signed_request,
            prefix,
            max_keys=max_keys,
            continuation_token=continuation_token,
        )
        if status != 200:
            abort(502, f"R2 list failed: HTTP {status}")
    except ET.ParseError as exc:
        logger.warning("R2 list returned invalid XML: %s", exc)
        abort(502, "R2 list returned invalid data")
    except HTTPError as exc:
        logger.warning("R2 list failed: HTTP %s", exc.code)
        abort(502, f"R2 list failed: HTTP {exc.code}")
    except (URLError, OSError, TimeoutError) as exc:
        logger.warning("R2 list connection failed: %s", exc)
        abort(502, "R2 list failed")

    return keys, next_token


def r2_upload_bytes(
    data: bytes,
    object_key: str,
    content_type: str,
    cache_control: str = "public, max-age=31536000, immutable",
) -> str:
    public_base = r2_public_base_url()
    if not public_base:
        abort(500, "R2_PUBLIC_BASE_URL is not configured")

    try:
        status = r2_storage.put_bytes(
            r2_signed_request,
            data,
            object_key,
            content_type,
            cache_control=cache_control,
        )
        if status not in {200, 201}:
            abort(502, f"R2 upload failed: HTTP {status}")
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace").strip()
        logger.warning("R2 upload failed: HTTP %s %s", exc.code, detail)
        abort(502, f"R2 upload failed: HTTP {exc.code}")
    except (URLError, OSError, TimeoutError) as exc:
        logger.warning("R2 upload connection failed: %s", exc)
        abort(502, "R2 upload failed")
    return f"{public_base}/{quote(object_key, safe='/-_.~')}"


def audit_signing_key() -> bytes:
    return (os.environ.get("AUDIT_LOG_SIGNING_KEY") or app.secret_key or "local-audit-key").encode("utf-8")


def redact_audit_value(value):
    return audit_service.redact(value)


def audit_request_context() -> dict:
    return audit_service.request_context(
        trusted_vercel=bool(os.environ.get("VERCEL")),
        remote_addr=request.remote_addr or "",
        headers=request.headers,
    )


def login_rate_limit_identity() -> str:
    context = audit_request_context()
    material = str(context["source_ip"]).encode("utf-8")
    return hmac.new(audit_signing_key(), material, hashlib.sha256).hexdigest()


def record_login_attempt(identity: str, outcome: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    event = {"timestamp": now.isoformat(), "identity": identity, "outcome": outcome}
    key = f"{LOGIN_FAILURE_PREFIX}{identity}/{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%S.%fZ}-{uuid.uuid4().hex}.json"
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")
    try:
        if is_vercel_runtime():
            r2_upload_bytes(payload, key, "application/json", "private, max-age=0")
        else:
            target = LOCAL_LOGIN_RATE_LIMIT_DIR / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        return True
    except Exception:
        logger.exception("Unable to write login rate-limit event")
        return False


def recent_login_attempts(identity: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    earliest = now - LOGIN_FAILURE_WINDOW
    records: list[dict] = []
    try:
        days = {now.date(), earliest.date()}
        if is_vercel_runtime():
            sources = ((key, r2_get_bytes(key)) for day in days for key in r2_list_object_keys(f"{LOGIN_FAILURE_PREFIX}{identity}/{day:%Y/%m/%d}/", max_keys=1000)[0])
        else:
            sources = ((str(path), path.read_bytes()) for day in days for path in (LOCAL_LOGIN_RATE_LIMIT_DIR / f"{LOGIN_FAILURE_PREFIX}{identity}/{day:%Y/%m/%d}").glob("*.json"))
        for _, payload in sources:
            try:
                event = json.loads(payload)
                timestamp = datetime.fromisoformat(str(event.get("timestamp") or "").replace("Z", "+00:00"))
                if event.get("identity") == identity and earliest <= timestamp <= now:
                    records.append(event)
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    except Exception:
        logger.exception("Unable to read login rate-limit events")
        return []
    return sorted(records, key=lambda event: event["timestamp"])


def login_is_rate_limited(identity: str, now: datetime | None = None) -> bool:
    attempts = recent_login_attempts(identity, now)
    last_success = max((index for index, event in enumerate(attempts) if event.get("outcome") == "success"), default=-1)
    return sum(event.get("outcome") == "failure" for event in attempts[last_success + 1 :]) >= LOGIN_FAILURE_LIMIT


def browser_summary(user_agent: str) -> str:
    return audit_service.browser_summary(user_agent)


def audit_changes(before: dict, after: dict, labels: dict[str, str] | None = None) -> list[dict]:
    return audit_service.changes(before, after, labels)


def write_audit_event(category: str, action: str, outcome: str, summary_th: str, *, resource_type="", resource_id="", resource_name="", changes=None, metadata=None, severity="info") -> dict | None:
    try:
        now = datetime.now(timezone.utc)
        event = audit_service.build_event(
            category, action, outcome, summary_th,
            context=audit_request_context(),
            admin_session_id=session.get("admin_session_id", ""),
            request_id=request.headers.get("x-vercel-id", uuid.uuid4().hex),
            request_method=request.method,
            request_path=request.path,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            changes_value=changes,
            metadata=metadata,
            severity=severity,
            now=now,
        )
        event = audit_service.sign_event(event, audit_signing_key())
        key = audit_service.object_key(event, AUDIT_PREFIX)
        data = audit_service.serialize(event)
        if is_vercel_runtime():
            r2_upload_bytes(data, key, "application/json", "private, max-age=0")
        else:
            audit_service.write_local(LOCAL_AUDIT_LOG_DIR, key, data)
        return event
    except Exception:
        logger.exception("Unable to write audit event")
        if session.get("admin") and request.path.startswith("/admin"):
            flash("บันทึกข้อมูลสำเร็จ แต่ไม่สามารถเขียนบันทึกการใช้งานได้", "warning")
        return None


def verify_audit_event(event: dict) -> bool:
    return audit_service.verify_event(event, audit_signing_key())


def list_audit_events(limit: int = AUDIT_PAGE_SIZE) -> list[dict]:
    """Read a bounded recent page of immutable audit events from local storage or R2."""
    events: list[dict] = []
    if is_vercel_runtime():
        # Object listings are lexicographic, so use daily prefixes from newest to oldest.
        # This keeps normal Admin views bounded instead of scanning the entire audit archive.
        keys: list[str] = []
        today = datetime.now(timezone.utc).date()
        for days_ago in range(31):
            prefix_date = today - timedelta(days=days_ago)
            day_keys, _ = r2_list_object_keys(
                f"{AUDIT_PREFIX}{prefix_date:%Y/%m/%d}/", max_keys=1000
            )
            keys.extend(day_keys)
            if len(keys) >= limit:
                break
        keys = sorted(keys, reverse=True)[:limit]
        if keys:
            with ThreadPoolExecutor(max_workers=min(10, len(keys))) as executor:
                futures = {executor.submit(r2_get_bytes, key): key for key in keys}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        events.append(json.loads(future.result().decode("utf-8")))
                    except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                        logger.warning("Skipping unreadable audit event %s: %s", key, exc)
    else:
        events.extend(audit_service.list_local(LOCAL_AUDIT_LOG_DIR, limit))
    events.sort(key=lambda event: event.get("timestamp_utc", ""), reverse=True)
    for event in events:
        event["signature_valid"] = verify_audit_event(event)
    return events


def save_r2_upload(
    file_storage,
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
    object_key = f"{r2_object_folder(relative_folder)}/{asset_name}"
    content_type = (
        file_storage.mimetype
        or mimetypes.guess_type(file_storage.filename)[0]
        or "application/octet-stream"
    )
    return r2_upload_bytes(data, object_key, content_type)


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
        if not r2_upload_configured():
            raise GeminiTTSError("R2 upload environment variables are not configured")
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return r2_upload_bytes(audio_data, f"audio/{filename}", content_type)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / filename).write_bytes(audio_data)
    return f"audio/{filename}"


NarrationDraftError = narration_service.NarrationDraftError


def narration_draft_serializer() -> URLSafeTimedSerializer:
    return narration_service.serializer(app.secret_key)


def narration_draft_token(payload: dict) -> str:
    return narration_draft_serializer().dumps(payload)


def load_narration_draft_token(token: str) -> dict:
    return narration_service.load_token(
        token, app.secret_key, NARRATION_DRAFT_MAX_AGE_SECONDS, NARRATION_PENDING_PREFIX
    )


def local_narration_draft_path(key: str) -> Path:
    return narration_service.local_draft_path(LOCAL_NARRATION_DRAFT_DIR, key)


def r2_delete_object(object_key: str) -> None:
    try:
        with r2_signed_request("DELETE", object_key, hashlib.sha256(b"").hexdigest(), timeout=45) as response:
            if response.status not in {200, 204}:
                raise NarrationDraftError(f"ลบไฟล์เสียงไม่สำเร็จ (HTTP {response.status})")
    except HTTPError as exc:
        if exc.code != 404:
            raise NarrationDraftError(f"ลบไฟล์เสียงไม่สำเร็จ (HTTP {exc.code})") from exc


def save_pending_narration_audio(model_id: str, audio_data: bytes, extension: str) -> str:
    extension = extension.lower()
    if extension not in AUDIO_EXTENSIONS or not audio_data or len(audio_data) > NARRATION_AUDIO_MAX_BYTES:
        raise NarrationDraftError("ไฟล์เสียงรอตรวจสอบไม่ถูกต้อง")
    filename = f"{uuid.uuid4().hex}{extension}"
    if is_vercel_runtime():
        if not r2_upload_configured():
            raise NarrationDraftError("ยังไม่ได้ตั้งค่า R2 สำหรับจัดเก็บเสียง")
        key = f"{NARRATION_PENDING_PREFIX}{slugify(model_id, 'model')}/{filename}"
        r2_upload_bytes(audio_data, key, mimetypes.guess_type(filename)[0] or "audio/wav")
        return key
    key = f"local-pending/{slugify(model_id, 'model')}/{filename}"
    target = local_narration_draft_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio_data)
    return key


def read_pending_narration_audio(key: str) -> bytes:
    if key.startswith(NARRATION_PENDING_PREFIX):
        return r2_get_bytes(key)
    target = local_narration_draft_path(key)
    if not target.is_file():
        raise NarrationDraftError("ไม่พบไฟล์เสียงรอตรวจสอบ")
    return target.read_bytes()


def delete_pending_narration_audio(key: str) -> None:
    if key.startswith(NARRATION_PENDING_PREFIX):
        r2_delete_object(key)
        return
    target = local_narration_draft_path(key)
    if target.exists():
        target.unlink()


def owned_r2_narration_key(audio_url: str) -> str:
    return narration_service.owned_r2_key(
        audio_url, r2_public_base_url(), NARRATION_PERMANENT_PREFIX
    )


def admin_write_blocked_on_vercel() -> bool:
    if not is_vercel_runtime():
        return False
    if github_content_configured():
        return False
    abort(403, VERCEL_EDIT_MESSAGE)


def upload_attempted(*field_names: str) -> bool:
    for field_name in field_names:
        file_storage = request.files.get(field_name)
        if file_storage and file_storage.filename:
            return True
    return False


def reject_vercel_upload_if_needed(*field_names: str) -> bool:
    if is_vercel_runtime() and upload_attempted(*field_names) and not r2_upload_configured():
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


def url_and_path(value: str | None) -> tuple[str, str]:
    candidate = str(value or "").strip()
    if is_external_url(candidate):
        return candidate, ""
    return "", candidate


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
    if is_vercel_runtime():
        max_bytes = (
            MAX_MODEL_FILE_SIZE_BYTES
            if MODEL_EXTENSIONS & allowed_extensions
            else SITE_ASSET_MAX_BYTES
        )
        return save_r2_upload(file_storage, relative_folder, allowed_extensions, max_bytes)
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
    if is_vercel_runtime():
        return save_r2_upload(file_storage, relative_folder, allowed_extensions, max_bytes)
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
    if is_vercel_runtime():
        return save_r2_upload(file_storage, relative_folder, allowed_extensions, SITE_ASSET_MAX_BYTES)
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
    now = datetime.now(timezone.utc).isoformat()
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
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
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
        landing_slider_collapsible=True,
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
        landing_slider_collapsible=False,
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
        if model.get("project_id") == project.get("id")
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
    projects = get_projects(include_hidden=False)
    visible_project_ids = {project.get("id") for project in projects}
    models = [
        model
        for model in get_models(include_hidden=False)
        if model.get("project_id") in visible_project_ids
    ]
    return jsonify([api_model_payload(model, projects) for model in models])


@app.get("/api/projects")
def api_projects():
    projects = get_projects(include_hidden=False)
    visible_project_ids = {project.get("id") for project in projects}
    models = [
        model
        for model in get_models(include_hidden=False)
        if model.get("project_id") in visible_project_ids
    ]
    return jsonify(
        [
            project_with_urls(project, models)
            for project in projects
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
    return render_template(
        "admin_dashboard.html",
        analytics_today=datetime.now(BANGKOK_TZ).date().isoformat(),
    )


@app.get("/admin/audit-logs")
@admin_required
def admin_audit_logs():
    events = list_audit_events()
    query = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip()
    outcome = request.args.get("outcome", "").strip()
    if query:
        events = [event for event in events if query in " ".join(str(event.get(key, "")) for key in ("summary_th", "resource_name", "source_ip")).lower()]
    if category: events = [event for event in events if event.get("category") == category]
    if outcome: events = [event for event in events if event.get("outcome") == outcome]
    counts = {"today": sum(event["timestamp_utc"][:10] == datetime.now(timezone.utc).date().isoformat() for event in events), "login_success": sum(event.get("event_type") == "auth.login" and event.get("outcome") == "success" for event in events), "login_failure": sum(event.get("event_type") == "auth.login" and event.get("outcome") == "failure" for event in events), "changes": sum(event.get("category") in {"model", "project", "slider", "settings", "narration"} for event in events), "errors": sum(event.get("outcome") in {"failure", "conflict", "rejected"} for event in events)}
    return render_template("admin_audit_logs.html", events=events, counts=counts)


@app.get("/admin/audit-logs/export/<format>")
@admin_required
def export_audit_logs(format: str):
    events = list_audit_events(500)
    if format == "json": return Response(json.dumps(events, ensure_ascii=False, indent=2), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=audit-logs.json"})
    if format == "csv":
        output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=["timestamp_local", "category", "action", "outcome", "summary_th", "source_ip", "resource_type", "resource_name"]); writer.writeheader(); writer.writerows([{key: event.get(key, "") for key in writer.fieldnames} for event in events])
        return Response(output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=audit-logs.csv"})
    abort(404)


@app.get("/admin/api/dashboard/summary")
@admin_required
def admin_dashboard_summary():
    raw_date = request.args.get("date", "").strip()
    selected_date = datetime.now(BANGKOK_TZ).date()
    if raw_date:
        try:
            selected_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify({"error": "รูปแบบวันที่ไม่ถูกต้อง กรุณาใช้ YYYY-MM-DD"}), 400
        if selected_date > datetime.now(BANGKOK_TZ).date():
            return jsonify({"error": "ไม่สามารถเลือกวันที่ในอนาคตได้"}), 400
    try:
        return jsonify(build_admin_dashboard_summary(selected_date))
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


@app.get("/admin/narrations")
@admin_required
def admin_narrations():
    projects = get_projects(include_hidden=True)
    models = [model_with_project(model, projects) for model in get_models(include_hidden=True)]
    draft = None
    token = request.args.get("draft", "").strip()
    if token:
        try:
            payload = load_narration_draft_token(token)
            draft_model = next((item for item in models if item["id"] == payload["model_id"]), None)
            if draft_model and str(draft_model.get("narration_audio") or "") == str(payload.get("expected_audio") or ""):
                draft = {"token": token, "model_id": payload["model_id"], "text": payload.get("text", "")}
            else:
                flash("เสียงรอตรวจสอบไม่ตรงกับข้อมูลโมเดลปัจจุบัน", "error")
        except NarrationDraftError as exc:
            flash(str(exc), "error")
    return render_template(
        "admin_narrations.html",
        models=models,
        projects=projects,
        draft=draft,
        narration_counts={
            "total": len(models),
            "with_audio": sum(bool(item.get("narration_audio_url")) for item in models),
            "without_audio": sum(not item.get("narration_audio_url") for item in models),
        },
        focus_model_id=request.args.get("focus", "").strip(),
    )


@app.post("/admin/narrations/<model_id>/draft")
@admin_required
def generate_narration_draft(model_id: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin_narrations", focus=model_id))
    model = next((item for item in get_models(include_hidden=True) if item["id"] == model_id), None)
    if model is None:
        abort(404)
    narration_text = ". ".join(part for part in (str(model.get("name") or "").strip(), str(model.get("description") or "").strip()) if part)
    if not narration_text:
        flash("โมเดลนี้ยังไม่มีข้อความสำหรับสร้างเสียงบรรยาย", "error")
        return redirect(url_for("admin_narrations", focus=model_id))
    try:
        if os.environ.get("NARRATION_PREVIEW_MOCK", "").strip() == "1":
            audio_data, extension = pcm_to_wav(b"\x00\x00" * 1200), ".wav"
        else:
            audio_data, extension = generate_gemini_tts_audio(narration_text)
        pending_key = save_pending_narration_audio(model_id, audio_data, extension)
        token = narration_draft_token({
            "model_id": model_id,
            "pending_key": pending_key,
            "expected_audio": str(model.get("narration_audio") or ""),
            "text": narration_text,
            "extension": extension,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except (GeminiTTSError, NarrationDraftError, OSError) as exc:
        logger.exception("Unable to create narration draft for %s", model_id)
        write_audit_event("narration", "draft", "failure", f'สร้างเสียงบรรยายฉบับทดลองสำหรับ “{model.get("name", "โมเดล")}” ไม่สำเร็จ', resource_type="model", resource_id=model_id, resource_name=model.get("name", ""), severity="warning")
        flash(f"สร้างเสียงรอตรวจสอบไม่สำเร็จ: {exc}", "error")
        return redirect(url_for("admin_narrations", focus=model_id))
    write_audit_event("narration", "draft", "success", f'สร้างเสียงบรรยายฉบับทดลองสำหรับ “{model.get("name", "โมเดล")}” สำเร็จ', resource_type="model", resource_id=model_id, resource_name=model.get("name", ""))
    return redirect(url_for("admin_narrations", draft=token, focus=model_id))


@app.get("/admin/narrations/drafts/<token>/audio")
@admin_required
def admin_narration_draft_audio(token: str):
    try:
        payload = load_narration_draft_token(token)
        data = read_pending_narration_audio(payload["pending_key"])
    except NarrationDraftError as exc:
        write_audit_event("narration", "confirm", "conflict", "ยืนยันเสียงบรรยายใหม่ไม่สำเร็จเนื่องจากข้อมูลขัดแย้ง", severity="warning")
        abort(404, str(exc))
    extension = str(payload.get("extension") or ".wav")
    return send_file(io.BytesIO(data), mimetype=mimetypes.guess_type(f"draft{extension}")[0] or "audio/wav", conditional=True)


@app.post("/admin/narrations/drafts/<token>/confirm")
@admin_required
def confirm_narration_draft(token: str):
    if admin_write_blocked_on_vercel():
        return redirect(url_for("admin_narrations"))
    try:
        payload = load_narration_draft_token(token)
        models = load_models(include_hidden=True)
        model = next((item for item in models if item["id"] == payload["model_id"]), None)
        if model is None:
            abort(404)
        if str(model.get("narration_audio") or "") != str(payload.get("expected_audio") or ""):
            raise NarrationDraftError("เสียงปัจจุบันถูกเปลี่ยนแล้ว กรุณาสร้างเสียงใหม่อีกครั้ง")
        audio_data = read_pending_narration_audio(payload["pending_key"])
        extension = str(payload.get("extension") or ".wav")
        filename = f"{uuid.uuid4().hex}{extension}"
        if is_vercel_runtime():
            permanent_key = f"{NARRATION_PERMANENT_PREFIX}{slugify(model['id'], 'model')}/{filename}"
            narration_audio = r2_upload_bytes(audio_data, permanent_key, mimetypes.guess_type(filename)[0] or "audio/wav")
        else:
            narration_audio = save_generated_narration_audio(model["id"], audio_data, extension)
        old_audio = str(model.get("narration_audio") or "")
        model["narration_audio"] = narration_audio
        try:
            save_models(models)
        except Exception:
            model["narration_audio"] = old_audio
            raise
        delete_pending_narration_audio(payload["pending_key"])
        old_key = owned_r2_narration_key(old_audio)
        if old_key:
            r2_delete_object(old_key)
    except NarrationDraftError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_narrations"))
    except Exception:
        logger.exception("Unable to confirm narration draft")
        write_audit_event("narration", "confirm", "failure", "ยืนยันเสียงบรรยายใหม่ไม่สำเร็จ", severity="warning")
        flash("ยืนยันเสียงบรรยายไม่สำเร็จ ข้อมูลเดิมยังไม่ถูกแทนที่", "error")
        return redirect(url_for("admin_narrations"))
    write_audit_event("narration", "confirm", "success", f'ยืนยันใช้เสียงบรรยายใหม่สำหรับ “{model.get("name", "โมเดล")}”', resource_type="model", resource_id=payload["model_id"], resource_name=model.get("name", ""))
    flash("ยืนยันและบันทึกเสียงบรรยายแล้ว", "success")
    return redirect(url_for("admin_narrations", focus=payload["model_id"]))


@app.post("/admin/narrations/drafts/<token>/cancel")
@admin_required
def cancel_narration_draft(token: str):
    try:
        payload = load_narration_draft_token(token)
        delete_pending_narration_audio(payload["pending_key"])
    except NarrationDraftError as exc:
        flash(str(exc), "error")
    else:
        write_audit_event("narration", "cancel", "success", "ยกเลิกเสียงบรรยายฉบับทดลอง", resource_type="model", resource_id=payload.get("model_id", ""))
        flash("ยกเลิกเสียงรอตรวจสอบแล้ว", "success")
    return redirect(url_for("admin_narrations"))


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
    before = dict(settings)
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
    write_audit_event(
        "settings", "edit", "success", "บันทึกการตั้งค่า Intro สำเร็จ",
        resource_type="site_settings",
        changes=audit_changes(before, settings),
        metadata={"section": "intro"},
    )
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
        write_audit_event("slider", "create", "success", f'เพิ่มสไลด์ “{data["title"]}” สำเร็จ', resource_type="slider", resource_id=data["id"], resource_name=data["title"])
        flash(slider_save_flash_message("Slider"), "success")
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
        write_audit_event("slider", "edit", "success", f'แก้ไขสไลด์ “{data["title"]}” สำเร็จ', resource_type="slider", resource_id=slider_id, resource_name=data["title"], changes=audit_changes(slider, data, {"active":"สถานะเปิดใช้งาน","title":"หัวข้อสไลด์"}))
        flash(slider_save_flash_message("Slider"), "success")
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
    deleted_slider = next(item for item in sliders if item["id"] == slider_id)
    save_slider_items([item for item in sliders if item["id"] != slider_id])
    write_audit_event("slider", "delete", "success", f'ลบสไลด์ “{deleted_slider.get("title", "")}” สำเร็จ', resource_type="slider", resource_id=slider_id, resource_name=deleted_slider.get("title", ""))
    if request.method == "DELETE":
        return "", 204
    flash(slider_save_flash_message("Slider"), "success")
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

        previous_ids = settings.get("recommended_model_ids", "")
        settings["recommended_model_ids"] = ",".join(sorted_ids)

        save_site_settings(settings)
        write_audit_event("settings", "edit", "success", "บันทึกโมเดลแนะนำสำเร็จ", resource_type="site_settings", changes=[{"field":"recommended_model_ids","label_th":"โมเดลแนะนำ","before":previous_ids,"after":settings["recommended_model_ids"]}], metadata={"section":"recommended_models"})

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
    before = dict(settings)
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
    section_label = "Landing" if section == "landing" else "Branding และ SEO"
    write_audit_event(
        "settings", "edit", "success", f"บันทึกการตั้งค่า {section_label} สำเร็จ",
        resource_type="site_settings",
        changes=audit_changes(before, settings),
        metadata={"section": section},
    )
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
        identity = login_rate_limit_identity()
        if not first_run and login_is_rate_limited(identity):
            write_audit_event(
                "auth", "login", "rejected",
                "มีความพยายามเข้าสู่ระบบเกินจำนวนที่กำหนด",
                severity="warning",
                metadata={"reason": "rate_limited"},
            )
            flash("ไม่สามารถเข้าสู่ระบบได้ในขณะนี้ โปรดลองใหม่ภายหลัง", "error")
            return render_template("login.html", first_run=first_run), 429
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
                session["admin_session_id"] = uuid.uuid4().hex
                write_audit_event("auth", "login", "success", "ผู้ดูแลตั้งค่ารหัสผ่านและเข้าสู่ระบบสำเร็จ")
                flash("ตั้งค่ารหัสผ่านผู้ดูแลแล้ว", "success")
                return redirect(next_url)
        elif verify_admin_password(password):
            record_login_attempt(identity, "success")
            session["admin"] = True
            session["admin_session_id"] = uuid.uuid4().hex
            write_audit_event("auth", "login", "success", f"ผู้ดูแลเข้าสู่ระบบสำเร็จจาก IP {audit_request_context()['source_ip']} ผ่าน {audit_request_context()['browser_summary']}")
            return redirect(next_url)
        else:
            record_login_attempt(identity, "failure")
            write_audit_event("auth", "login", "failure", f"มีความพยายามเข้าสู่ระบบไม่สำเร็จจาก IP {audit_request_context()['source_ip']}", severity="warning")
            flash("รหัสผ่านไม่ถูกต้อง", "error")

    return render_template("login.html", first_run=first_run)


@app.post("/admin/logout")
def admin_logout():
    if session.get("admin"):
        write_audit_event("auth", "logout", "success", "ผู้ดูแลออกจากระบบ")
    session.pop("admin", None)
    session.pop("admin_session_id", None)
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
    stored_image_url, stored_image_path = url_and_path(cover_image)
    projects = load_projects(include_hidden=True)
    projects.append(
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": request.form.get("description", "").strip(),
            "department": request.form.get("department", "").strip(),
            "cover_image": cover_image,
            "image_url": stored_image_url,
            "image_path": stored_image_path,
            "visible": form_visible(),
        }
    )
    save_projects(projects)
    write_audit_event("project", "create", "success", f'เพิ่มโครงการ “{name}” สำเร็จ', resource_type="project", resource_id=projects[-1]["id"], resource_name=name)
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

        before = dict(project); old_cover = project.get("cover_image")
        image_url = request.form.get("image_url", "").strip()
        new_cover = image_url or save_upload(request.files.get("cover_image"), PIC_DIR, "pic", IMAGE_EXTENSIONS)
        final_cover = new_cover or old_cover
        stored_image_url, stored_image_path = url_and_path(final_cover)
        project.update(
            {
                "name": request.form.get("name", "").strip() or project["name"],
                "description": request.form.get("description", "").strip(),
                "department": request.form.get("department", "").strip(),
                "cover_image": final_cover,
                "image_url": stored_image_url,
                "image_path": "" if stored_image_url else (stored_image_path or project.get("image_path", "")),
                "visible": form_visible(),
            }
        )
        if new_cover and old_cover and not image_url:
            delete_static_file(old_cover)
        save_projects(projects)
        write_audit_event("project", "edit", "success", f'แก้ไขโครงการ “{project["name"]}” สำเร็จ', resource_type="project", resource_id=project_id, resource_name=project["name"], changes=audit_changes(before, project, {"name":"ชื่อโครงการ","description":"คำอธิบาย","visible":"การเผยแพร่","cover_image":"รูปปก"}))
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
    write_audit_event("project", "delete", "success", f'ลบโครงการ “{project.get("name", "")}” สำเร็จ', resource_type="project", resource_id=project_id, resource_name=project.get("name", ""), metadata={"deleted_models": len(linked_models)})
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
    stored_model_url, stored_model_path = url_and_path(model_path)
    stored_thumbnail_url, stored_thumbnail_path = url_and_path(image_path)

    models = load_models(include_hidden=True)
    models.append(
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": request.form.get("description", "").strip(),
            "department": request.form.get("department", "").strip(),
            "project_id": project_id,
            "model": model_path,
            "model_url": stored_model_url,
            "model_path": stored_model_path,
            "image": image_path,
            "thumbnail_url": stored_thumbnail_url,
            "thumbnail_path": stored_thumbnail_path,
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
    write_audit_event("model", "create", "success", f'เพิ่มโมเดล “{name}” สำเร็จ', resource_type="model", resource_id=models[-1]["id"], resource_name=name)
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

        before = dict(model); project_id = request.form.get("project_id", "").strip()
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
        final_model = new_model or manual_model_path or old_model
        final_image = new_image or manual_image_path or old_image
        stored_model_url, stored_model_path = url_and_path(final_model)
        stored_thumbnail_url, stored_thumbnail_path = url_and_path(final_image)

        model.update(
            {
                "name": request.form.get("name", "").strip() or model["name"],
                "description": request.form.get("description", "").strip(),
                "department": request.form.get("department", "").strip(),
                "project_id": project_id,
                "model": final_model,
                "model_url": stored_model_url,
                "model_path": "" if stored_model_url else (stored_model_path or model.get("model_path", "")),
                "image": final_image,
                "thumbnail_url": stored_thumbnail_url,
                "thumbnail_path": "" if stored_thumbnail_url else (stored_thumbnail_path or model.get("thumbnail_path", "")),
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
        write_audit_event("model", "edit", "success", f'แก้ไขโมเดล “{model["name"]}” สำเร็จ', resource_type="model", resource_id=model_id, resource_name=model["name"], changes=audit_changes(before, model, {"name":"ชื่อโมเดล","description":"คำอธิบาย","project_id":"โครงการ","visible":"การเผยแพร่","narration_audio":"เสียงบรรยาย"}))
        flash("บันทึกข้อมูลโมเดลแล้ว", "success")
        return redirect(url_for("admin"))

    return render_template("edit_model.html", model=model_with_project(model, projects), projects=projects)


@app.post("/admin/models/<model_id>/generate-narration")
@admin_required
def generate_model_narration(model_id: str):
    # Kept as a safe compatibility endpoint for old bookmarks and forms.
    if is_vercel_runtime():
        admin_write_blocked_on_vercel()
    return redirect(url_for("admin_narrations", focus=model_id))

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
    write_audit_event("model", "delete", "success", f'ลบโมเดล “{deleted.get("name", "")}” สำเร็จ', resource_type="model", resource_id=model_id, resource_name=deleted.get("name", ""))
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
