"""Scheduled events and calendar data source for event markets."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.getenv("KALSHI_AGENTS_DATA", "./data")) / "events_cache"
_CACHE_TTL = timedelta(hours=6)


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _load_cache(name: str) -> list[dict[str, Any]] | None:
    path = _ensure_cache_dir() / f"{name}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s cache: %s", name, exc)
        return None

    fetched_at_raw = payload.get("fetched_at")
    if not isinstance(fetched_at_raw, str):
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw)
    except ValueError:
        return None
    if datetime.now() - fetched_at > _CACHE_TTL:
        return None

    events = payload.get("events")
    if not isinstance(events, list):
        return None
    return events


def _save_cache(name: str, events: list[dict[str, Any]]) -> None:
    path = _ensure_cache_dir() / f"{name}.json"
    payload = {"fetched_at": datetime.now().isoformat(), "events": events}
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write %s cache: %s", name, exc)


FOMC_MEETINGS = [
    {"date": "2024-01-30", "date_end": "2024-01-31", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2024-03-19", "date_end": "2024-03-20", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2024-05-01", "date_end": "2024-05-02", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2024-06-11", "date_end": "2024-06-12", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2024-07-30", "date_end": "2024-07-31", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2024-09-17", "date_end": "2024-09-18", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2024-11-06", "date_end": "2024-11-07", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2024-12-17", "date_end": "2024-12-18", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2025-01-28", "date_end": "2025-01-29", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2025-03-18", "date_end": "2025-03-19", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2025-05-06", "date_end": "2025-05-07", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2025-06-17", "date_end": "2025-06-18", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2025-07-29", "date_end": "2025-07-30", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2025-09-16", "date_end": "2025-09-17", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2025-10-28", "date_end": "2025-10-29", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2025-12-09", "date_end": "2025-12-10", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2026-01-27", "date_end": "2026-01-28", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2026-03-17", "date_end": "2026-03-18", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2026-04-28", "date_end": "2026-04-29", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2026-06-16", "date_end": "2026-06-17", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2026-07-28", "date_end": "2026-07-29", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2026-09-15", "date_end": "2026-09-16", "type": "FOMC Meeting", "statement": True, "projections": True},
    {"date": "2026-10-27", "date_end": "2026-10-28", "type": "FOMC Meeting", "statement": True, "projections": False},
    {"date": "2026-12-15", "date_end": "2026-12-16", "type": "FOMC Meeting", "statement": True, "projections": True},
]


def _get_fomc_events(days_ahead: int = 90) -> list[dict[str, Any]]:
    """Get upcoming FOMC meetings within the lookforward window."""
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    events: list[dict[str, Any]] = []
    for meeting in FOMC_MEETINGS:
        meeting_date = datetime.strptime(meeting["date"], "%Y-%m-%d")
        if now - timedelta(days=1) <= meeting_date <= cutoff:
            event = {
                "source": "Federal Reserve",
                "type": meeting["type"],
                "date": meeting["date"],
                "date_end": meeting["date_end"],
                "details": ["FOMC statement will be released at 2:00 PM ET on the second day"],
            }
            if meeting.get("projections"):
                event["details"].append("Includes Summary of Economic Projections (dot plot)")
                event["details"].append("Chair press conference at 2:30 PM ET")
            else:
                event["details"].append("No new economic projections at this meeting")
            events.append(event)

    return events


BLS_RELEASES = {
    "CPI": "Consumer Price Index — measures consumer inflation",
    "PPI": "Producer Price Index — measures wholesale/producer inflation",
    "Employment Situation": "Nonfarm payrolls, unemployment rate — released first Friday of each month",
    "JOLTS": "Job Openings and Labor Turnover Survey",
    "PCE": "Personal Consumption Expenditures price index (BEA, not BLS)",
}


def _fetch_bls_calendar(days_ahead: int = 90) -> list[dict[str, Any]]:
    """Fetch upcoming BLS economic data releases."""
    cache_key = f"bls_{days_ahead}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    events: list[dict[str, Any]] = []
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://www.bls.gov/schedule/news_release/empsit.htm",
                headers={"User-Agent": "KalshiPredictionAgent/0.1"},
            )
            if resp.status_code == 200:
                import re

                dates = re.findall(r"(\w+ \d{1,2}, \d{4})", resp.text)
                for date_str in dates[:12]:
                    try:
                        dt = datetime.strptime(date_str, "%B %d, %Y")
                    except ValueError:
                        continue
                    if now - timedelta(days=1) <= dt <= cutoff:
                        events.append(
                            {
                                "source": "Bureau of Labor Statistics",
                                "type": "Employment Situation Report",
                                "date": dt.strftime("%Y-%m-%d"),
                                "details": [
                                    "Nonfarm payrolls and unemployment rate",
                                    "Released at 8:30 AM ET",
                                ],
                            }
                        )
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("BLS calendar fetch failed: %s", exc)

    if not events:
        for month_offset in range(0, 4):
            target_month = now.month + month_offset
            target_year = now.year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1

            first_day = datetime(target_year, target_month, 1)
            days_until_friday = (4 - first_day.weekday()) % 7
            first_friday = first_day + timedelta(days=days_until_friday)

            if now - timedelta(days=1) <= first_friday <= cutoff:
                events.append(
                    {
                        "source": "Bureau of Labor Statistics (estimated)",
                        "type": "Employment Situation Report",
                        "date": first_friday.strftime("%Y-%m-%d"),
                        "details": [
                            "Nonfarm payrolls and unemployment rate",
                            "Typically released at 8:30 AM ET",
                            "Note: Date is estimated — check bls.gov for confirmed schedule",
                        ],
                    }
                )

    _save_cache(cache_key, events)
    return events


def _fetch_sports_events(sport: str = "all", team: str = "", days_ahead: int = 14) -> list[dict[str, Any]]:
    """Fetch upcoming sports events from ESPN's public API."""
    cache_team = team.lower().replace(" ", "_") or "all"
    cache_key = f"sports_{sport.lower()}_{cache_team}_{days_ahead}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    events: list[dict[str, Any]] = []
    sport_endpoints = {
        "nfl": "football/nfl",
        "nba": "basketball/nba",
        "mlb": "baseball/mlb",
        "nhl": "hockey/nhl",
        "soccer": "soccer/usa.1",
        "mma": "mma/ufc",
    }

    endpoints = sport_endpoints
    if sport.lower() in sport_endpoints:
        endpoints = {sport.lower(): sport_endpoints[sport.lower()]}

    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    for sport_key, endpoint in endpoints.items():
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/scoreboard",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for raw_event in data.get("events", []):
                    event_date_str = raw_event.get("date", "")
                    try:
                        event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        continue
                    event_date_naive = event_date.replace(tzinfo=None)
                    if not (now - timedelta(days=1) <= event_date_naive <= cutoff):
                        continue

                    name = raw_event.get("name", "Unknown event")
                    if team and team.lower() not in name.lower():
                        continue

                    competitions = raw_event.get("competitions", [{}])
                    venue = ""
                    if competitions:
                        venue_data = competitions[0].get("venue", {})
                        venue = venue_data.get("fullName", "")

                    events.append(
                        {
                            "source": f"ESPN ({sport_key.upper()})",
                            "type": f"{sport_key.upper()} Game",
                            "date": event_date_str[:10],
                            "details": [
                                name,
                                f"Venue: {venue}" if venue else "",
                                f"Status: {raw_event.get('status', {}).get('type', {}).get('description', 'Scheduled')}",
                            ],
                        }
                    )
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("ESPN %s fetch failed: %s", sport_key, exc)

    _save_cache(cache_key, events)
    return events


def _fetch_political_events(days_ahead: int = 30) -> list[dict[str, Any]]:
    """Fetch upcoming political events from public sources."""
    cache_key = f"politics_{days_ahead}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    events: list[dict[str, Any]] = []
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(
                "https://www.whitehouse.gov/wp-json/wp/v2/posts",
                params={
                    "categories": "6",
                    "per_page": 20,
                    "orderby": "date",
                    "order": "desc",
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                for post in resp.json():
                    title = post.get("title", {}).get("rendered", "")
                    date_str = post.get("date", "")[:10]
                    lower_title = title.lower()
                    if not any(
                        kw in lower_title
                        for kw in ["schedule", "travel", "press conference", "briefing", "remarks", "speech"]
                    ):
                        continue
                    try:
                        event_date = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        continue
                    if not (now - timedelta(days=1) <= event_date <= cutoff):
                        continue
                    events.append(
                        {
                            "source": "White House",
                            "type": "Political Event",
                            "date": date_str,
                            "details": [title],
                        }
                    )
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("White House schedule fetch failed: %s", exc)

    _save_cache(cache_key, events)
    return events


def _topic_has_term(topic: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", topic) is not None



def _topic_has_any(topic: str, terms: list[str]) -> bool:
    return any(_topic_has_term(topic, term) for term in terms)



def get_upcoming_events(topic: str, days_ahead: int = 30) -> str:
    """Get upcoming scheduled events relevant to a market topic."""
    topic_lower = topic.lower()
    events: list[dict[str, Any]] = []

    fomc_terms = ["fed", "fomc", "federal reserve", "interest rate", "monetary policy", "rate cut", "rate hike"]
    if _topic_has_any(topic_lower, fomc_terms):
        events.extend(_get_fomc_events(days_ahead))

    economic_terms = ["inflation", "cpi", "employment", "jobs", "unemployment", "payroll", "ppi", "gdp", "economic"]
    if _topic_has_any(topic_lower, economic_terms):
        events.extend(_fetch_bls_calendar(days_ahead))

    sport_aliases = {
        "nfl": "nfl",
        "football": "nfl",
        "nba": "nba",
        "basketball": "nba",
        "mlb": "mlb",
        "baseball": "mlb",
        "nhl": "nhl",
        "hockey": "nhl",
        "soccer": "soccer",
        "mma": "mma",
        "ufc": "mma",
        "fight": "mma",
        "game": "all",
        "match": "all",
    }
    if _topic_has_any(topic_lower, list(sport_aliases)):
        sport = "all"
        for keyword, mapped_sport in sport_aliases.items():
            if _topic_has_term(topic_lower, keyword):
                sport = mapped_sport
                break
        events.extend(_fetch_sports_events(sport=sport, days_ahead=min(days_ahead, 14)))

    political_terms = ["trump", "biden", "president", "white house", "congress", "speech", "press conference"]
    if _topic_has_any(topic_lower, political_terms):
        events.extend(_fetch_political_events(days_ahead))

    if not events:
        events.extend(_get_fomc_events(days_ahead))
        events.extend(_fetch_bls_calendar(days_ahead))

    if not events:
        return (
            f"No upcoming scheduled events found for topic: '{topic}'\n"
            f"(Searched {days_ahead} days ahead)\n"
            "Note: Some event sources may be temporarily unavailable."
        )

    events.sort(key=lambda event: event.get("date", "9999-12-31"))
    lines = [
        f"## Upcoming Scheduled Events (next {days_ahead} days)",
        f"Topic: {topic}",
        f"Events found: {len(events)}",
        "",
    ]

    for index, event in enumerate(events, start=1):
        lines.append(f"### {index}. {event['type']} — {event['date']}")
        lines.append(f"Source: {event['source']}")
        for detail in event.get("details", []):
            if detail:
                lines.append(f"  • {detail}")
        if event.get("date_end"):
            lines.append(f"  Ends: {event['date_end']}")
        lines.append("")

    next_event = events[0]
    try:
        next_date = datetime.strptime(str(next_event["date"]), "%Y-%m-%d")
        days_until = (next_date - datetime.now()).days
        lines.append(f"**Next relevant event: {next_event['type']} in {days_until} day(s) ({next_event['date']})**")
    except (TypeError, ValueError):
        pass

    return "\n".join(lines)
