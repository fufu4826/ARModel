"""Validate production-equivalent JSON data for the zero-Supabase runtime."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ORIGIN = "https://phuphan-ar.vercel.app"
R2_PREFIX = "https://pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev/"
EXPECTED_COUNTS = {
    "models.json": 41,
    "projects.json": 10,
    "site_settings.json": 31,
    "slider_items.json": 2,
}


def fail(message: str) -> None:
    raise ValueError(message)


def load_pretty_json(filename: str):
    path = DATA_DIR / filename
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    canonical = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if raw != canonical:
        fail(f"{filename} is not deterministic pretty-formatted JSON")
    if "supabase.co" in raw.lower() or "storage/v1/object/public" in raw.lower():
        fail(f"{filename} still contains a Supabase URL")
    if len(value) != EXPECTED_COUNTS[filename]:
        fail(
            f"{filename} count is {len(value)}, "
            f"expected {EXPECTED_COUNTS[filename]}"
        )
    return value


def require_fields(record: dict, fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        fail(f"{label} is missing fields: {', '.join(missing)}")
    empty = [
        field
        for field in fields
        if field
        not in {
            "description",
            "narration_audio",
            "file_size_mb",
            "button_text",
            "button_url",
        }
        and record.get(field) in (None, "")
    ]
    if empty:
        fail(f"{label} has empty required fields: {', '.join(empty)}")


def require_unique(records: list[dict], field: str, label: str) -> None:
    values = [str(record.get(field) or "").strip() for record in records]
    if any(not value for value in values):
        fail(f"{label} contains an empty {field}")
    if len(values) != len(set(values)):
        fail(f"{label} contains duplicate {field} values")


def walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)
    else:
        yield value


def standalone_urls(datasets) -> set[str]:
    urls: set[str] = set()
    for dataset in datasets:
        for value in walk_values(dataset):
            if not isinstance(value, str):
                continue
            candidate = value.strip()
            if candidate.startswith(("http://", "https://")):
                if not candidate.startswith("https://"):
                    fail(f"Non-HTTPS URL value found: {candidate}")
                urls.add(candidate)
    return urls


def verify_r2_url(url: str) -> tuple[str, str | None]:
    request = Request(
        url,
        method="HEAD",
        headers={
            "Origin": ORIGIN,
            "User-Agent": "ARModel-Phase-D-Validator/1.0",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                return url, f"HTTP {response.status}"
            allow_origin = response.headers.get("Access-Control-Allow-Origin", "")
            if allow_origin != ORIGIN:
                return url, f"unexpected Access-Control-Allow-Origin: {allow_origin!r}"
            if not response.headers.get("Content-Length"):
                return url, "missing Content-Length"
    except HTTPError as exc:
        return url, f"HTTP {exc.code}"
    except (URLError, OSError) as exc:
        return url, str(exc.reason if isinstance(exc, URLError) else exc)
    return url, None


def main() -> int:
    models = load_pretty_json("models.json")
    projects = load_pretty_json("projects.json")
    settings = load_pretty_json("site_settings.json")
    sliders = load_pretty_json("slider_items.json")

    if models != sorted(models, key=lambda item: str(item["id"])):
        fail("models.json is not deterministically sorted by id")
    if projects != sorted(projects, key=lambda item: str(item["id"])):
        fail("projects.json is not deterministically sorted by id")
    if list(settings) != sorted(settings):
        fail("site_settings.json keys are not deterministically sorted")
    if sliders != sorted(
        sliders,
        key=lambda item: (int(item.get("sort_order") or 0), str(item["id"])),
    ):
        fail("slider_items.json is not deterministically sorted")

    require_unique(models, "id", "models")
    require_unique(models, "slug", "models")
    require_unique(projects, "id", "projects")
    require_unique(projects, "slug", "projects")

    project_ids = {str(project["id"]) for project in projects}
    for model in models:
        label = f"model {model.get('id')!r}"
        require_fields(
            model,
            (
                "id",
                "slug",
                "name",
                "description",
                "project_id",
                "model_url",
                "thumbnail_url",
                "preview_images",
                "narration_audio",
                "file_size_mb",
                "rotate_x",
                "rotate_y",
                "rotate_z",
                "scale",
                "visible",
                "created_at",
                "updated_at",
            ),
            label,
        )
        if str(model["project_id"]) not in project_ids:
            fail(f"{label} references unknown project_id {model['project_id']!r}")
        if not model["model_url"].startswith(R2_PREFIX):
            fail(f"{label} model_url is not an R2 URL")
        if not model["thumbnail_url"].startswith(R2_PREFIX):
            fail(f"{label} thumbnail_url is not an R2 URL")
        if not isinstance(model["preview_images"], list):
            fail(f"{label} preview_images is not a list")

    for project in projects:
        label = f"project {project.get('id')!r}"
        require_fields(
            project,
            (
                "id",
                "slug",
                "name",
                "description",
                "image_url",
                "created_at",
                "updated_at",
            ),
            label,
        )
        if not project["image_url"].startswith(R2_PREFIX):
            fail(f"{label} image_url is not an R2 URL")

    required_settings = {
        "landing_cover",
        "intro_logo_1",
        "intro_logo_2",
        "intro_logo_3",
        "site_logo",
        "site_social_image",
        "favicon",
        "recommended_model_ids",
    }
    missing_settings = required_settings - set(settings)
    if missing_settings:
        fail(f"site_settings.json is missing keys: {sorted(missing_settings)}")

    for slider in sliders:
        label = f"slider {slider.get('id')!r}"
        require_fields(
            slider,
            (
                "id",
                "title",
                "description",
                "image_url",
                "button_text",
                "button_url",
                "sort_order",
                "active",
                "created_at",
                "updated_at",
            ),
            label,
        )
        if not slider["image_url"].startswith(R2_PREFIX):
            fail(f"{label} image_url is not an R2 URL")

    urls = standalone_urls((models, projects, settings, sliders))
    r2_urls = sorted(url for url in urls if url.startswith(R2_PREFIX))
    if not r2_urls:
        fail("No Cloudflare R2 asset URLs were found in production data")

    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(verify_r2_url, url) for url in r2_urls]
        for future in as_completed(futures):
            url, error = future.result()
            if error:
                failures.append((url, error))
    if failures:
        details = "\n".join(f"- {url}: {error}" for url, error in failures)
        fail(f"R2 network/CORS validation failed:\n{details}")

    print("PASS counts models=41 projects=10 site_settings=31 slider_items=2")
    print("PASS unique IDs/slugs and model project foreign keys")
    print("PASS required public fields and HTTPS URL values")
    print("PASS zero Supabase URLs")
    print(f"PASS R2 HTTP/CORS URLs={len(r2_urls)} origin={ORIGIN}")
    print("PASS deterministic pretty-formatted JSON")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
