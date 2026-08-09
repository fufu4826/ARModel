from pathlib import Path

from armodel.repositories import content


def test_project_and_model_normalization_preserves_relationships_and_assets():
    projects = [content.normalize_project({"id": "garden", "slug": "สวน", "name": "สวน", "visible": False}, default_name="แหล่งเรียนรู้")]
    model = content.normalize_model(
        {
            "id": "fruit",
            "slug": "fruit-slug",
            "project_id": "garden",
            "model": "model/fruit.glb",
            "image": "pic/fruit.webp",
            "preview_images": ["pic/one.webp", "pic/one.webp"],
            "narration_audio": "audio/fruit.mp3",
            "visible": False,
        },
        projects,
        default_name="โมเดล",
    )

    assert model["project_id"] == "garden"
    assert model["model_path"] == "model/fruit.glb"
    assert model["thumbnail_path"] == "pic/fruit.webp"
    assert model["preview_images"] == ["pic/one.webp"]
    assert model["narration_audio"] == "audio/fruit.mp3"
    assert model["visible"] is False


def test_legacy_model_defaults_match_existing_rules():
    projects = [{"id": "rice-and-food"}, {"id": "garden"}, {"id": "wellness"}]
    assert content.normalize_model({"id": "lychee"}, projects, default_name="โมเดล")["project_id"] == "garden"
    normalized = content.normalize_model({"id": "other", "scale": "bad"}, projects, default_name="โมเดล")
    assert normalized["project_id"] == "rice-and-food"
    assert normalized["scale"] == 0.2


def test_content_lookup_supports_id_and_slug():
    record = {"id": "model-id", "slug": "model-slug"}
    lookup = content.content_lookup([record])
    assert lookup["model-id"] is record
    assert lookup["model-slug"] is record


def test_load_normalized_filters_visibility_and_falls_back_to_defaults():
    defaults = [{"id": "default", "visible": True}]
    reader = lambda _path, _defaults: [
        {"id": "shown", "visible": True},
        {"id": "hidden", "visible": False},
    ]
    normalizer = lambda item: dict(item)
    visible = content.load_normalized(
        Path("models.json"), defaults, reader, normalizer,
        visible_key="visible", include_hidden=False,
    )
    assert [item["id"] for item in visible] == ["shown"]
    fallback = content.load_normalized(
        Path("models.json"), defaults, lambda *_: [], normalizer
    )
    assert fallback == defaults


def test_slider_and_settings_normalization_and_writer_delegation():
    defaults = {"site_name": "ARModel", "size": "20"}
    settings = content.normalize_site_settings(
        {"site_name": "  ภูพาน AR  ", "size": "999"},
        defaults,
        {"size": (10, 40)},
    )
    assert settings == {"site_name": "ภูพาน AR", "size": "40"}

    written = []
    content.save_normalized(
        Path("slider_items.json"),
        [{"id": "b", "sort_order": 2}, {"id": "a", "sort_order": 1}],
        lambda path, value: written.append((path, value)),
        content.normalize_slider_item,
        sort_key=lambda item: (item["sort_order"], item["id"]),
    )
    assert [item["id"] for item in written[0][1]] == ["a", "b"]
