"""Base-rate analyst — placeholder.

v1: returns a neutral prior (0.5) with low confidence and a note describing
what *would* be looked up (e.g., FRED series for econ markets). Real
implementation in phase 4.
"""

from __future__ import annotations

from ...kalshi.models import Market
from ..base import AnalystOutput, ProbabilityEstimate


def analyze(market: Market) -> AnalystOutput:
    findings = [
        f"[stub] Would look up historical base rate for: {market.title!r}.",
        "[stub] For econ markets, plan to query FRED for relevant series and"
        " compute frequency of analogous outcomes.",
    ]
    return AnalystOutput(
        name="base_rate",
        findings=findings,
        estimate=ProbabilityEstimate(
            p_yes=0.5,
            confidence=0.1,
            rationale="Stub prior; no historical data wired yet.",
        ),
    )
