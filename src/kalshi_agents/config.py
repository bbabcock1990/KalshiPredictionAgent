from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _i(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class RiskConfig:
    bankroll_usd: float = _f("BANKROLL_USD", 1000.0)
    max_stake_pct: float = _f("MAX_STAKE_PCT", 0.05)
    kelly_fraction: float = _f("KELLY_FRACTION", 0.25)
    min_edge: float = _f("MIN_EDGE", 0.05)
    min_confidence: float = _f("MIN_CONFIDENCE", 0.5)
    max_spread_cents: int = _i("MAX_SPREAD_CENTS", 4)
    min_minutes_to_close: int = _i("MIN_MINUTES_TO_CLOSE", 60)


@dataclass(frozen=True)
class KalshiConfig:
    env: str = os.getenv("KALSHI_ENV", "demo")
    api_key_id: str | None = os.getenv("KALSHI_API_KEY_ID") or None
    private_key_path: str | None = os.getenv("KALSHI_PRIVATE_KEY_PATH") or None

    @property
    def base_url(self) -> str:
        if self.env == "prod":
            return "https://api.elections.kalshi.com/trade-api/v2"
        return "https://demo-api.kalshi.co/trade-api/v2"


@dataclass(frozen=True)
class LLMConfig:
    model: str = os.getenv("LLM_MODEL", "gpt-5-mini")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None


@dataclass(frozen=True)
class AppConfig:
    risk: RiskConfig
    kalshi: KalshiConfig
    llm: LLMConfig
    data_dir: Path = Path(os.getenv("KALSHI_AGENTS_DATA", "./data"))


def load() -> AppConfig:
    cfg = AppConfig(risk=RiskConfig(), kalshi=KalshiConfig(), llm=LLMConfig())
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
