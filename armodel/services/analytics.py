"""Pure analytics normalization and dashboard aggregation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


def event_datetime(event: dict) -> datetime | None:
    raw_value = str(event.get("timestamp") or "")
    if not raw_value:
        return None
    try:
        value = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def unique_visitors(items: list[dict]) -> int:
    return len({str(item.get("visitor_id") or "") for item in items if item.get("visitor_id")})


def top_counts(events: list[dict], key: str, limit: int = 5) -> list[dict]:
    counts: dict[str, int] = {}
    for event in events:
        label = str(event.get(key) or "Unknown").strip() or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    return [
        {"label": label, "value": value}
        for label, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def day_bounds(selected_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(selected_date, datetime.min.time(), tzinfo=BANGKOK_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def date_label(selected_date: date) -> str:
    thai_months = (
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    )
    return f"{selected_date.day} {thai_months[selected_date.month - 1]} {selected_date.year + 543}"


def events_between(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [event for event in events if start <= event["_occurred_at"] < end]


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    return value.replace(year=value.year + month_index // 12, month=month_index % 12 + 1)


def _bucket(label: str, start: datetime, end: datetime, events: list[dict]) -> dict:
    bucket_events = events_between(events, start, end)
    return {
        "label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "visitors": unique_visitors(bucket_events),
        "pageviews": len(bucket_events),
    }


def trend_ranges(selected_date: date, events: list[dict]) -> dict:
    selected_start, _ = day_bounds(selected_date)
    selected_local_start = selected_start.astimezone(BANGKOK_TZ)
    hourly = []
    for hour in range(24):
        start_local = selected_local_start + timedelta(hours=hour)
        start = start_local.astimezone(timezone.utc)
        hourly.append(_bucket(start_local.strftime("%H:00"), start, start + timedelta(hours=1), events))
    daily_7d = []
    for offset in range(6, -1, -1):
        day = selected_date - timedelta(days=offset)
        start, end = day_bounds(day)
        daily_7d.append(_bucket(day.isoformat(), start, end, events))
    daily_30d = []
    for offset in range(29, -1, -1):
        day = selected_date - timedelta(days=offset)
        start, end = day_bounds(day)
        daily_30d.append(_bucket(day.isoformat(), start, end, events))
    current_month = _month_start(selected_local_start)
    monthly_12 = []
    for offset in range(11, -1, -1):
        start = _shift_months(current_month, -offset)
        end = _shift_months(start, 1)
        monthly_12.append(_bucket(start.strftime("%Y-%m"), start, end, events))
    return {
        "hourly_24h": hourly,
        "daily_7d": daily_7d,
        "daily_30d": daily_30d,
        "monthly_12m": monthly_12,
        "default_range": "daily_7d",
    }


def dashboard_status(events: list[dict], selected_date: date, *, provider: str | None, today: date) -> dict:
    selected_start, selected_end = day_bounds(selected_date)
    seven_start, _ = day_bounds(selected_date - timedelta(days=6))
    thirty_start, _ = day_bounds(selected_date - timedelta(days=29))
    selected_events = events_between(events, selected_start, selected_end)
    events_7d = events_between(events, seven_start, selected_end)
    events_30d = events_between(events, thirty_start, selected_end)
    daily_counts = []
    for offset in range(29, -1, -1):
        day = selected_date - timedelta(days=offset)
        start, end = day_bounds(day)
        day_events = events_between(events, start, end)
        daily_counts.append({"date": day.isoformat(), "visitors": unique_visitors(day_events), "pageviews": len(day_events)})
    enabled = bool(events)
    return {
        "enabled": enabled,
        "provider": provider,
        "message": "Analytics is collecting visitor data." if enabled else "Analytics is ready. Visit public pages to collect data.",
        "metrics": {
            "visitors_today": unique_visitors(selected_events),
            "pageviews_today": len(selected_events),
            "visitors_7d": unique_visitors(events_7d),
            "visitors_30d": unique_visitors(events_30d),
            "total_events": len(events),
        },
        "selected_date": selected_date.isoformat(),
        "selected_date_label": date_label(selected_date),
        "is_today": selected_date == today,
        "trend": daily_counts,
        "trend_ranges": trend_ranges(selected_date, events),
        "top_countries": top_counts(selected_events, "country"),
        "top_referrers": top_counts(selected_events, "referrer"),
        "top_pages": top_counts(selected_events, "page"),
    }
