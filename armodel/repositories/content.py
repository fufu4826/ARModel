"""Normalization and persistence orchestration for JSON content datasets."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Callable
from pathlib import Path


Reader = Callable[[Path, object], object]
Writer = Callable[[Path, object], None]


def content_lookup(records: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for record in records:
        for key in ("id", "slug"):
            value = str(record.get(key) or "").strip()
            if value:
                lookup[value] = record
    return lookup


def normalize_project(project: dict, *, default_name: str) -> dict:
    name = str(project.get("name") or project.get("project_name") or default_name).strip()
    image_url = str(project.get("image_url") or "").strip()
    image_path = str(
        project.get("image_path") or project.get("cover_image") or project.get("image") or ""
    ).strip()
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


def normalize_model(model: dict, projects: list[dict], *, default_name: str) -> dict:
    project_ids = {project["id"] for project in projects}
    model_id = str(model.get("id") or uuid.uuid4().hex)
    project_id = str(model.get("project_id") or "").strip()
    if project_id not in project_ids:
        if model_id == "lukplakob":
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
        rotate_x = rotate_y = rotate_z = 0
        scale = 0.2
    model_url = str(model.get("model_url") or "").strip()
    model_path = str(model.get("model_path") or model.get("model") or "").strip()
    thumbnail_url = str(model.get("thumbnail_url") or "").strip()
    thumbnail_path = str(
        model.get("thumbnail_path") or model.get("image") or model.get("thumbnail") or ""
    ).strip()
    size_mb = model.get("file_size_mb")
    try:
        size_mb = float(size_mb) if size_mb is not None else None
    except (TypeError, ValueError):
        size_mb = None
    return {
        "id": model_id,
        "slug": str(model.get("slug") or "").strip(),
        "name": str(model.get("name") or default_name).strip(),
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
        "narration_audio": str(model.get("narration_audio") or "").strip(),
        "file_size_mb": size_mb,
        "rotate_x": rotate_x,
        "rotate_y": rotate_y,
        "rotate_z": rotate_z,
        "scale": scale,
        "visible": bool(model.get("visible", True)),
        "created_at": str(model.get("created_at") or "").strip(),
        "updated_at": str(model.get("updated_at") or "").strip(),
    }


def normalize_landing_typography_value(key: str, value, defaults: dict, limits: dict) -> str:
    minimum, maximum = limits[key]
    try:
        numeric_value = float(str(value).strip())
        if not math.isfinite(numeric_value):
            raise ValueError
        parsed_value = int(round(numeric_value))
    except (TypeError, ValueError):
        parsed_value = int(defaults[key])
    return str(max(minimum, min(parsed_value, maximum)))


def normalize_site_settings(settings: dict | None, defaults: dict, typography_limits: dict) -> dict:
    normalized = dict(defaults)
    for key in normalized:
        value = (settings or {}).get(key)
        if value is not None:
            normalized[key] = str(value).strip()
    for key, fallback in defaults.items():
        if not normalized[key]:
            normalized[key] = fallback
    for key in typography_limits:
        normalized[key] = normalize_landing_typography_value(
            key, normalized[key], defaults, typography_limits
        )
    return normalized


def normalize_slider_item(item: dict) -> dict:
    try:
        sort_order = int(item.get("sort_order") or 0)
    except (TypeError, ValueError):
        sort_order = 0
    created_at = str(item.get("created_at") or "").strip()
    return {
        "id": str(item.get("id") or uuid.uuid4().hex),
        "title": str(item.get("title") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "image_url": str(item.get("image_url") or item.get("image") or "").strip(),
        "button_text": str(item.get("button_text") or "").strip(),
        "button_url": str(item.get("button_url") or "").strip(),
        "sort_order": sort_order,
        "active": bool(item.get("active", True)),
        "created_at": created_at,
        "updated_at": str(item.get("updated_at") or created_at).strip(),
    }


def load_normalized(path: Path, defaults, reader: Reader, normalizer: Callable, *, visible_key: str | None = None, include_hidden: bool = True) -> list[dict]:
    items = [normalizer(item) for item in reader(path, defaults)]
    if not items:
        items = [normalizer(item) for item in defaults]
    if visible_key and not include_hidden:
        return [item for item in items if item.get(visible_key, True)]
    return items


def save_normalized(path: Path, items, writer: Writer, normalizer: Callable, *, sort_key=None) -> None:
    normalized = [normalizer(item) for item in items]
    if sort_key:
        normalized.sort(key=sort_key)
    writer(path, normalized)
