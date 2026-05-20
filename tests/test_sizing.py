from datetime import datetime, timedelta, timezone

import pytest

from kalshi_agents.config import RiskConfig
from kalshi_agents.decision.sizing import SizingEngine, kelly_fraction
from kalshi_agents.kalshi.models import Market


def _market(yes_bid=0.50, yes_ask=0.52, status="open", mtc_minutes=240) -> Market:
    return Market(
        ticker="TEST",
        title="Test market",
        status=status,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        close_time=datetime.now(timezone.utc) + timedelta(minutes=mtc_minutes),
    )


def _risk(**overrides) -> RiskConfig:
    base = dict(
        bankroll_usd=1000.0,
        max_stake_pct=0.05,
        kelly_fraction=0.25,
        min_edge=0.05,
        min_confidence=0.5,
        max_spread_cents=4,
        min_minutes_to_close=60,
    )
    base.update(overrides)
    return RiskConfig(**base)


def test_kelly_zero_when_no_edge():
    assert kelly_fraction(0.5, 0.5) == 0.0
    assert kelly_fraction(0.4, 0.5) == 0.0


def test_kelly_positive_with_edge():
    f = kelly_fraction(0.6, 0.5)
    assert f == pytest.approx(0.2, rel=1e-6)  # (0.6*0.5 - 0.4*0.5)/0.5 = 0.2


def test_go_signal_strong_edge():
    eng = SizingEngine(_risk())
    m = _market(yes_bid=0.50, yes_ask=0.52)
    d = eng.decide(ticker="T", model_prob=0.70, confidence=0.8, market=m)
    assert d.signal == "GO"
    assert d.side == "YES"
    assert d.stake_usd > 0
    assert d.contracts >= 1
    # Quarter-Kelly capped by max_stake_pct (5% of 1000 = $50)
    assert d.stake_usd <= 50.0 + 1e-6


def test_no_go_when_edge_below_threshold():
    eng = SizingEngine(_risk())
    m = _market(yes_bid=0.50, yes_ask=0.52)
    d = eng.decide(ticker="T", model_prob=0.54, confidence=0.8, market=m)
    assert d.signal == "NO_GO"
    assert d.stake_usd == 0.0


def test_no_go_when_low_confidence():
    eng = SizingEngine(_risk())
    m = _market()
    d = eng.decide(ticker="T", model_prob=0.7, confidence=0.3, market=m)
    assert d.signal == "NO_GO"
    assert any("confidence" in r for r in d.reasons_blocked)


def test_no_go_when_spread_too_wide():
    eng = SizingEngine(_risk())
    m = _market(yes_bid=0.45, yes_ask=0.55)  # 10¢
    d = eng.decide(ticker="T", model_prob=0.7, confidence=0.8, market=m)
    assert d.signal == "NO_GO"
    assert any("spread" in r for r in d.reasons_blocked)


def test_no_go_when_market_closing_soon():
    eng = SizingEngine(_risk())
    m = _market(mtc_minutes=10)
    d = eng.decide(ticker="T", model_prob=0.7, confidence=0.8, market=m)
    assert d.signal == "NO_GO"


def test_no_side_chosen_when_model_prob_low():
    eng = SizingEngine(_risk())
    m = _market(yes_bid=0.50, yes_ask=0.52)
    # Model thinks NO is much more likely
    d = eng.decide(ticker="T", model_prob=0.30, confidence=0.8, market=m)
    assert d.side == "NO"
    assert d.signal == "GO"
    assert d.max_price == pytest.approx(1 - 0.50)  # buy NO at (1 - yes_bid)
