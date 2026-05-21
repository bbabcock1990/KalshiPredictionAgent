from datetime import datetime, timedelta, timezone

from kalshi_agents.agents.kalshi_graph import KalshiTradingGraph
from kalshi_agents.kalshi.models import Market


def _market(
    title: str = "Will the Fed cut rates?",
    ticker: str = "KXFEDDECISION-28JAN-H0",
) -> Market:
    return Market(
        ticker=ticker,
        title=title,
        status="open",
        yes_bid=0.48,
        yes_ask=0.52,
        close_time=datetime.now(timezone.utc) + timedelta(days=2),
    )


def test_extract_topic_uses_market_title():
    market = _market(title="Will Trump mention China?")

    assert (
        KalshiTradingGraph._extract_topic(market) == "Will Trump mention China?"
    )


def test_build_market_context_keeps_kalshi_ticker_visible():
    market = _market()

    context = KalshiTradingGraph._build_market_context(market)

    assert "Question: Will the Fed cut rates?" in context
    assert "Kalshi ticker: KXFEDDECISION-28JAN-H0" in context
