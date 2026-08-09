from datetime import date, datetime, timezone

from armodel.services import analytics


def event(timestamp, visitor, **extra):
    return {
        "timestamp": timestamp,
        "visitor_id": visitor,
        "country": extra.get("country", "Thailand"),
        "referrer": extra.get("referrer", "Direct"),
        "page": extra.get("page", "Home"),
        "_occurred_at": analytics.event_datetime({"timestamp": timestamp}),
    }


def test_bangkok_boundary_and_dashboard_ranges():
    events = [
        event("2026-08-05T16:59:59+00:00", "before"),
        event("2026-08-05T17:00:00+00:00", "selected", page="Model"),
        event("2026-08-06T16:59:59+00:00", "selected", page="Model"),
        event("2026-08-06T17:00:00+00:00", "after"),
    ]
    payload = analytics.dashboard_status(
        events,
        date(2026, 8, 6),
        provider="local-json",
        today=date(2026, 8, 10),
    )
    assert payload["metrics"]["visitors_today"] == 1
    assert payload["metrics"]["pageviews_today"] == 2
    assert len(payload["trend_ranges"]["hourly_24h"]) == 24
    assert payload["trend_ranges"]["daily_7d"][-1]["label"] == "2026-08-06"
    assert payload["trend_ranges"]["daily_30d"][-1]["label"] == "2026-08-06"
    assert payload["trend_ranges"]["monthly_12m"][-1]["label"] == "2026-08"


def test_invalid_and_naive_timestamps_are_normalized_safely():
    assert analytics.event_datetime({"timestamp": "bad"}) is None
    assert analytics.event_datetime({"timestamp": ""}) is None
    parsed = analytics.event_datetime({"timestamp": "2026-08-06T00:00:00"})
    assert parsed == datetime(2026, 8, 6, tzinfo=timezone.utc)


def test_empty_dashboard_is_valid():
    payload = analytics.dashboard_status(
        [], date(2026, 8, 6), provider="local-json", today=date(2026, 8, 6)
    )
    assert payload["enabled"] is False
    assert payload["metrics"]["pageviews_today"] == 0
    assert payload["top_pages"] == []
