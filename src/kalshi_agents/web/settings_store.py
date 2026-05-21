"""Persistent settings stored in ~/.kalshi-agents/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_DIR = Path.home() / ".kalshi-agents"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    # Kalshi
    "kalshi_env": "prod",
    "kalshi_api_key_id": "",
    "kalshi_private_key_path": "",
    # LLM
    "llm_provider": "github-copilot",
    "llm_model": "gpt-4o-mini",
    "backend_url": "http://localhost:4141/v1",
    # Data sources
    "twitter_bearer_token": "",
    "newsapi_key": "",
    "fred_api_key": "",
    "enable_social_media": True,
    "enable_speech_analysis": True,
    "enable_event_calendar": True,
    # Risk
    "bankroll_usd": 1000.0,
    "max_stake_pct": 0.05,
    "kelly_fraction": 0.25,
    "min_edge": 0.05,
    "min_confidence": 0.5,
    "max_spread_cents": 4,
    "min_minutes_to_close": 60,
}


def load() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        return {**DEFAULTS, **saved}
    return dict(DEFAULTS)


def save(settings: dict[str, Any]) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
