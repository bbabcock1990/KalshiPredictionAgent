"""Agent graph orchestration.

v0.1: synchronous, no LangGraph yet — runs analysts sequentially and combines
their probability estimates with confidence-weighted average. The LangGraph
debate loop is wired in phase 5.
"""

from __future__ import annotations

from ..kalshi.models import Market, OrderbookSnapshot
from .analysts import base_rate, microstructure, news, public_signal
from .base import AgentReport, AnalystOutput


def _combine(estimates: list[AnalystOutput]) -> tuple[float, float, str]:
    weighted = [
        (a.estimate.p_yes, a.estimate.confidence, a.name)
        for a in estimates
        if a.estimate is not None and a.estimate.confidence > 0
    ]
    if not weighted:
        return 0.5, 0.0, "no analyst produced a probability"
    total_w = sum(w for _, w, _ in weighted)
    p = sum(p * w for p, w, _ in weighted) / total_w
    # Aggregate confidence: average, slightly penalized when analysts disagree.
    avg_conf = total_w / len(weighted)
    if len(weighted) > 1:
        spread = max(p_ for p_, _, _ in weighted) - min(p_ for p_, _, _ in weighted)
        avg_conf = max(0.0, avg_conf - 0.5 * spread)
    rationale = "Combined estimate from: " + ", ".join(
        f"{name}(p={p_:.2f},c={c:.2f})" for p_, c, name in weighted
    )
    return p, avg_conf, rationale


def run(market: Market, orderbook: OrderbookSnapshot | None = None) -> AgentReport:
    outputs = [
        microstructure.analyze(market, orderbook),
        base_rate.analyze(market),
        news.analyze(market),
        public_signal.analyze(market),
    ]
    p, conf, rationale = _combine(outputs)
    return AgentReport(
        p_yes=p,
        confidence=conf,
        rationale=rationale,
        analyst_outputs=outputs,
        debate=None,
    )
