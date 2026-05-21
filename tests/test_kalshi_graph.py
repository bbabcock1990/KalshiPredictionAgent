from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from kalshi_agents.agents.kalshi_graph import (
    KalshiTradingGraph,
    _create_safe_news_analyst,
    _create_safe_sentiment_analyst,
)
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


def test_safe_sentiment_analyst_handles_url_errors(monkeypatch):
    def fake_factory(_llm):
        def node(_state):
            raise ValueError(
                "URL can't contain control characters: /api/2/streams/symbol/WHO WILL TIME NAME AS PERSON OF THE DECADE?.json"
            )

        return node

    monkeypatch.setattr("tradingagents.agents.create_sentiment_analyst", fake_factory)

    state = {
        "messages": [HumanMessage(content="context")],
        "company_of_interest": "Who will TIME name as Person of the Decade?",
    }
    result = _create_safe_sentiment_analyst(None)(state)

    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][-1], AIMessage)
    assert hasattr(result["messages"][-1], "tool_calls")
    assert result["messages"][-1].tool_calls == []
    assert result["messages"][-1].content == result["sentiment_report"]
    assert "Sentiment analysis partially available." in result["sentiment_report"]
    assert "StockTwits and Reddit data could not be fetched" in result["sentiment_report"]


def test_safe_sentiment_analyst_reraises_non_url_errors(monkeypatch):
    def fake_factory(_llm):
        def node(_state):
            raise RuntimeError("llm output parse failed")

        return node

    monkeypatch.setattr("tradingagents.agents.create_sentiment_analyst", fake_factory)

    with pytest.raises(RuntimeError, match="llm output parse failed"):
        _create_safe_sentiment_analyst(None)({"messages": []})


def test_safe_news_analyst_returns_fallback_report(monkeypatch):
    def fake_factory(_llm):
        def node(_state):
            raise RuntimeError("news provider timeout")

        return node

    monkeypatch.setattr("tradingagents.agents.create_news_analyst", fake_factory)

    result = _create_safe_news_analyst(None)({"messages": [HumanMessage(content="context")]})

    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][-1], AIMessage)
    assert hasattr(result["messages"][-1], "tool_calls")
    assert result["messages"][-1].tool_calls == []
    assert result["messages"][-1].content == result["news_report"]
    assert "News analysis could not be completed." in result["news_report"]
    assert "news provider timeout" in result["news_report"]
