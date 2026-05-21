from datetime import datetime

from kalshi_agents.agents import events_calendar as ec


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2025, 1, 1, 12, 0, 0)
        if tz is not None:
            return value.replace(tzinfo=tz)
        return value


def test_get_fomc_events_returns_upcoming_meetings(monkeypatch):
    monkeypatch.setattr(ec, "datetime", FixedDatetime)

    events = ec._get_fomc_events(days_ahead=90)

    assert events
    assert events[0]["date"] == "2025-01-28"
    assert events[0]["source"] == "Federal Reserve"
    assert "FOMC statement will be released at 2:00 PM ET on the second day" in events[0]["details"]
    assert any(event["date"] == "2025-03-18" for event in events)


def test_get_upcoming_events_matches_relevant_sources(monkeypatch):
    calls: list[tuple[str, int | str]] = []

    def fake_fomc(days_ahead):
        calls.append(("fomc", days_ahead))
        return [{"source": "Fed", "type": "FOMC Meeting", "date": "2025-01-28", "details": []}]

    def fake_bls(days_ahead):
        calls.append(("bls", days_ahead))
        return [{"source": "BLS", "type": "Employment Situation Report", "date": "2025-01-10", "details": []}]

    def fake_sports(*, sport, team="", days_ahead):
        calls.append((f"sports:{sport}", days_ahead))
        return [{"source": "ESPN", "type": "MMA Game", "date": "2025-01-03", "details": [team]}]

    def fake_politics(days_ahead):
        calls.append(("politics", days_ahead))
        return [{"source": "White House", "type": "Political Event", "date": "2025-01-04", "details": []}]

    monkeypatch.setattr(ec, "datetime", FixedDatetime)
    monkeypatch.setattr(ec, "_get_fomc_events", fake_fomc)
    monkeypatch.setattr(ec, "_fetch_bls_calendar", fake_bls)
    monkeypatch.setattr(ec, "_fetch_sports_events", fake_sports)
    monkeypatch.setattr(ec, "_fetch_political_events", fake_politics)

    result = ec.get_upcoming_events("Fed inflation UFC speech", days_ahead=10)

    assert "Events found: 4" in result
    assert ("fomc", 10) in calls
    assert ("bls", 10) in calls
    assert ("sports:mma", 10) in calls
    assert ("politics", 10) in calls


def test_fetch_bls_calendar_falls_back_to_estimated_schedule(monkeypatch):
    class MidJanuaryDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2025, 1, 15, 12, 0, 0)
            if tz is not None:
                return value.replace(tzinfo=tz)
            return value

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr(ec, "datetime", MidJanuaryDatetime)
    monkeypatch.setattr(ec, "_load_cache", lambda name: None)
    monkeypatch.setattr(ec, "_save_cache", lambda name, events: None)
    monkeypatch.setattr(ec.httpx, "Client", BrokenClient)

    events = ec._fetch_bls_calendar(days_ahead=90)

    assert [event["date"] for event in events] == ["2025-02-07", "2025-03-07", "2025-04-04"]
    assert all(event["source"] == "Bureau of Labor Statistics (estimated)" for event in events)
    assert all("estimated" in event["details"][-1].lower() for event in events)


def test_get_upcoming_events_formats_sorted_output(monkeypatch):
    monkeypatch.setattr(ec, "datetime", FixedDatetime)
    monkeypatch.setattr(
        ec,
        "_get_fomc_events",
        lambda days_ahead: [
            {
                "source": "Federal Reserve",
                "type": "FOMC Meeting",
                "date": "2025-01-05",
                "date_end": "2025-01-06",
                "details": ["Chair press conference at 2:30 PM ET"],
            },
            {
                "source": "Federal Reserve",
                "type": "FOMC Meeting",
                "date": "2025-01-03",
                "details": ["FOMC statement will be released at 2:00 PM ET on the second day"],
            },
        ],
    )
    monkeypatch.setattr(ec, "_fetch_bls_calendar", lambda days_ahead: [])
    monkeypatch.setattr(ec, "_fetch_sports_events", lambda **kwargs: [])
    monkeypatch.setattr(ec, "_fetch_political_events", lambda days_ahead: [])

    result = ec.get_upcoming_events("fed rate decision", days_ahead=7)

    assert "## Upcoming Scheduled Events (next 7 days)" in result
    assert "Topic: fed rate decision" in result
    assert "Events found: 2" in result
    assert result.index("2025-01-03") < result.index("2025-01-05")
    assert "Ends: 2025-01-06" in result
    assert "**Next relevant event: FOMC Meeting in 1 day(s) (2025-01-03)**" in result
