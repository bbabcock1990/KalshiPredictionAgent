"""Kalshi-specific tool functions for the TradingAgents agent graph.

Combines:
  - Our Kalshi market/orderbook tools (pre-loaded via set_context())
  - TradingAgents' get_news / get_global_news (via yfinance Search)
  - Social media fetchers for political and behavioral markets
"""

from __future__ import annotations

from langchain_core.tools import tool

from tradingagents.agents.utils.news_data_tools import get_global_news, get_news

from ..kalshi.models import Market, OrderbookSnapshot
from .social_media import fetch_social_media_signals

# Module-level context — set before each graph run via set_context()
_context: dict = {}


def set_context(market: Market, orderbook: OrderbookSnapshot | None = None) -> None:
    _context["market"] = market
    _context["orderbook"] = orderbook


def clear_context() -> None:
    _context.clear()


def build_news_queries(market: Market) -> list[str]:
    """Generate search queries for get_global_news from the market title."""
    title = market.title or ""
    queries = [title]
    # Add focused sub-queries based on common market categories
    lower = title.lower()
    if "federal reserve" in lower or "fed" in lower:
        queries.append("Federal Reserve interest rate decision monetary policy")
        queries.append("FOMC meeting rate cut rate hike forecast")
    if "inflation" in lower or "cpi" in lower:
        queries.append("US CPI inflation consumer prices latest data")
    if "unemployment" in lower or "jobs" in lower:
        queries.append("US jobs report unemployment rate nonfarm payrolls")
    if "gdp" in lower:
        queries.append("US GDP economic growth forecast")
    # Always include a general macro query
    if len(queries) < 3:
        queries.append("US economy monetary policy outlook")
    return queries[:5]


def get_current_market_topic(fallback: str = "") -> str:
    """Return the loaded market title when available, otherwise a fallback."""
    m: Market | None = _context.get("market")
    if m and m.title:
        return m.title
    return fallback


@tool
def get_event_market_data(ticker: str) -> str:
    """Get current Kalshi event market snapshot: YES/NO prices, spread, volume, open interest, and time to close."""
    m: Market | None = _context.get("market")
    if not m:
        return "No market data loaded."
    lines = [
        f"Event Market: {m.title}",
        f"Ticker: {m.ticker}",
        f"Status: {m.status}",
        f"YES bid: {m.yes_bid:.4f}  YES ask: {m.yes_ask:.4f}",
        f"Implied P(YES) at mid: {m.yes_mid:.4f}",
        f"Spread: {m.spread_cents} cents",
        f"Volume: {m.volume}",
        f"Open Interest: {m.open_interest}",
    ]
    mtc = m.minutes_to_close
    if mtc is not None:
        if mtc > 1440:
            lines.append(f"Time to close: {mtc / 1440:.1f} days")
        else:
            lines.append(f"Time to close: {mtc:.0f} minutes")
    if m.rules_primary:
        lines.append(f"Resolution rules: {m.rules_primary}")
    return "\n".join(lines)


@tool
def get_event_orderbook(ticker: str) -> str:
    """Get current orderbook depth for a Kalshi event contract. Shows YES and NO bid levels with quantities."""
    ob: OrderbookSnapshot | None = _context.get("orderbook")
    if not ob:
        return "No orderbook data loaded."
    lines = [f"Orderbook for {ticker}:"]
    if ob.yes_bids:
        lines.append("YES bids (best first):")
        for lvl in ob.yes_bids[:10]:
            lines.append(f"  ${lvl.price:.4f} x {lvl.quantity} contracts")
    else:
        lines.append("YES bids: (empty)")
    if ob.no_bids:
        lines.append("NO bids (best first):")
        for lvl in ob.no_bids[:10]:
            lines.append(f"  ${lvl.price:.4f} x {lvl.quantity} contracts")
    else:
        lines.append("NO bids: (empty)")
    return "\n".join(lines)


@tool
def get_social_media_signals(topic: str) -> str:
    """Fetch recent Truth Social, X/Twitter, and Reddit signals relevant to a market topic."""
    return fetch_social_media_signals(get_current_market_topic(topic))


# Re-export TA's tools so they're importable from this module
__all__ = [
    "set_context",
    "clear_context",
    "build_news_queries",
    "get_current_market_topic",
    "get_event_market_data",
    "get_event_orderbook",
    "get_social_media_signals",
    "get_news",
    "get_global_news",
]
