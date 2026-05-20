"""Microstructure analyst — pure-logic baseline (no LLM required).

Reads Kalshi orderbook + market stats, returns a probability anchored to
market mid with adjustments for order imbalance and spread quality.
"""

from __future__ import annotations

from ...kalshi.models import Market, OrderbookSnapshot
from ..base import AnalystOutput, ProbabilityEstimate


def analyze(market: Market, orderbook: OrderbookSnapshot | None) -> AnalystOutput:
    findings: list[str] = []
    p = market.yes_mid
    confidence = 0.4
    findings.append(f"Market mid implies P(YES) = {p:.3f}.")
    findings.append(f"Spread = {market.spread_cents}¢, volume = {market.volume}.")

    if orderbook and orderbook.yes_bids and orderbook.no_bids:
        yes_qty = sum(l.quantity for l in orderbook.yes_bids[:5])
        no_qty = sum(l.quantity for l in orderbook.no_bids[:5])
        total = yes_qty + no_qty
        if total > 0:
            imbalance = (yes_qty - no_qty) / total
            findings.append(
                f"Top-5 depth imbalance YES vs NO = {imbalance:+.2f} "
                f"({yes_qty} vs {no_qty})."
            )
            # Tilt market mid toward heavier side, capped at ±0.03
            p = max(0.01, min(0.99, p + 0.03 * imbalance))
            confidence = min(0.6, 0.4 + 0.2 * abs(imbalance))

    return AnalystOutput(
        name="microstructure",
        findings=findings,
        estimate=ProbabilityEstimate(
            p_yes=p,
            confidence=confidence,
            rationale="Anchored to market mid with order-imbalance tilt.",
        ),
    )
