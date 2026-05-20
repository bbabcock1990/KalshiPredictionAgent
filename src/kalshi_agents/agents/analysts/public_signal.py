"""Public-signal analyst — placeholder.

For econ markets, this will pull CME FedWatch implied probabilities,
consensus economist surveys, and competing prediction-market venues.
"""

from __future__ import annotations

from ...kalshi.models import Market
from ..base import AnalystOutput


def analyze(market: Market) -> AnalystOutput:
    return AnalystOutput(
        name="public_signal",
        findings=[
            f"[stub] Would pull external consensus signals for: {market.title!r}."
        ],
        estimate=None,
    )
