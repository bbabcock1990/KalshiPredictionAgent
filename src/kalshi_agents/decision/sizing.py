"""Sizing engine: turns (model_prob, market, confidence) into a stake.

This is pure logic — no LLM, no network — so it's the most testable part of
the system and the foundation everything else relies on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..config import RiskConfig
from ..kalshi.models import Market, OrderbookSnapshot

Side = Literal["YES", "NO"]
Signal = Literal["GO", "NO_GO"]


@dataclass
class Decision:
    ticker: str
    signal: Signal
    side: Side
    model_prob: float          # P(YES) the agents converged on
    market_prob: float         # implied P(YES) from the market mid
    edge: float                # signed edge on the chosen side, in probability points
    confidence: float          # agents' self-rated confidence in [0,1]
    stake_usd: float
    max_price: float           # limit price (probability) you'd be willing to pay
    contracts: int             # whole-cent contracts at max_price
    rationale: str = ""
    reasons_blocked: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "signal": self.signal,
            "side": self.side,
            "model_prob": round(self.model_prob, 4),
            "market_prob": round(self.market_prob, 4),
            "edge": round(self.edge, 4),
            "confidence": round(self.confidence, 4),
            "stake_usd": round(self.stake_usd, 2),
            "max_price": round(self.max_price, 4),
            "contracts": self.contracts,
            "rationale": self.rationale,
            "reasons_blocked": self.reasons_blocked or [],
        }


def kelly_fraction(p: float, price: float) -> float:
    """Full-Kelly fraction of bankroll for a binary YES bet at `price`.

    Payoff: stake `s` at price `c` returns `s*(1-c)/c` if YES, loses `s` if NO.
    Kelly: f* = (p*(1-c) - (1-p)*c) / (1-c)
    Returns 0 when there is no edge or `price` is degenerate.
    """
    if price <= 0.0 or price >= 1.0:
        return 0.0
    edge = p * (1.0 - price) - (1.0 - p) * price
    if edge <= 0.0:
        return 0.0
    return edge / (1.0 - price)


class SizingEngine:
    def __init__(self, risk: RiskConfig):
        self.risk = risk

    def decide(
        self,
        *,
        ticker: str,
        model_prob: float,
        confidence: float,
        market: Market,
        orderbook: OrderbookSnapshot | None = None,
        rationale: str = "",
    ) -> Decision:
        market_prob = market.yes_mid
        # Pick the better side
        yes_edge = model_prob - market.yes_ask          # buy YES at ask
        no_edge = (1.0 - model_prob) - (1.0 - market.yes_bid)  # buy NO at (1-bid)
        if yes_edge >= no_edge:
            side: Side = "YES"
            edge = yes_edge
            entry_price = market.yes_ask
            p_for_kelly = model_prob
        else:
            side = "NO"
            edge = no_edge
            entry_price = 1.0 - market.yes_bid
            p_for_kelly = 1.0 - model_prob

        blocked: list[str] = []
        if edge < self.risk.min_edge:
            blocked.append(f"edge {edge:.3f} < min {self.risk.min_edge:.3f}")
        if confidence < self.risk.min_confidence:
            blocked.append(
                f"confidence {confidence:.2f} < min {self.risk.min_confidence:.2f}"
            )
        if market.spread_cents > self.risk.max_spread_cents:
            blocked.append(
                f"spread {market.spread_cents}¢ > max {self.risk.max_spread_cents}¢"
            )
        mtc = market.minutes_to_close
        if mtc is not None and mtc < self.risk.min_minutes_to_close:
            blocked.append(
                f"{mtc:.0f}min to close < min {self.risk.min_minutes_to_close}"
            )
        if market.status != "open":
            blocked.append(f"market status={market.status}")

        # Sizing
        f_full = kelly_fraction(p_for_kelly, entry_price)
        f = f_full * self.risk.kelly_fraction
        stake_pct = min(f, self.risk.max_stake_pct)
        stake_usd = max(0.0, stake_pct * self.risk.bankroll_usd)

        # Liquidity cap from top-of-book (10% of size at our price)
        if orderbook is not None:
            top = (
                orderbook.top_yes_bid if side == "YES" else orderbook.top_no_bid
            )
            if top is not None and top.quantity > 0:
                liq_cap_usd = 0.10 * top.quantity * entry_price
                if stake_usd > liq_cap_usd:
                    stake_usd = liq_cap_usd
                    blocked_note = f"capped at 10% of top-of-book ({top.quantity} @ {entry_price:.2f})"
                    rationale = (rationale + " | " + blocked_note).strip(" |")

        contracts = int(stake_usd // entry_price) if entry_price > 0 else 0
        if contracts <= 0:
            blocked.append("stake too small for ≥1 contract")

        signal: Signal = "GO" if not blocked else "NO_GO"
        if signal == "NO_GO":
            stake_usd = 0.0
            contracts = 0

        return Decision(
            ticker=ticker,
            signal=signal,
            side=side,
            model_prob=model_prob,
            market_prob=market_prob,
            edge=edge,
            confidence=confidence,
            stake_usd=stake_usd,
            max_price=entry_price,
            contracts=contracts,
            rationale=rationale,
            reasons_blocked=blocked or None,
        )
