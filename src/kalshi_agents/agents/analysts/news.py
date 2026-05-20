"""News analyst — placeholder."""

from __future__ import annotations

from ...kalshi.models import Market
from ..base import AnalystOutput


def analyze(market: Market) -> AnalystOutput:
    return AnalystOutput(
        name="news",
        findings=[f"[stub] Would search recent news for: {market.title!r}."],
        estimate=None,
    )
