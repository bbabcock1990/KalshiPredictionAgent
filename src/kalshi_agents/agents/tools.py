"""Kalshi-specific tool functions for the TradingAgents agent graph.

These are LangChain @tool functions that the analyst nodes call.
Market/orderbook data is pre-loaded via set_context() before each run.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ..kalshi.models import Market, OrderbookSnapshot

# Module-level context — set before each graph run via set_context()
_context: dict = {}


def set_context(market: Market, orderbook: OrderbookSnapshot | None = None) -> None:
    _context["market"] = market
    _context["orderbook"] = orderbook


def clear_context() -> None:
    _context.clear()


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
def search_event_news(query: str) -> str:
    """Search for recent news relevant to an event market question. Returns headlines and summaries."""
    return (
        "[News API not yet configured. Rely on your training knowledge of recent "
        "events relevant to this market question. State clearly what you know vs. "
        "what you are uncertain about.]"
    )


@tool
def get_economic_data(series_id: str) -> str:
    """Retrieve economic data from FRED for a given series ID (e.g., FEDFUNDS, CPIAUCSL, UNRATE)."""
    return (
        f"[FRED API not yet configured for series '{series_id}'. "
        "Use your training knowledge of recent economic data. "
        "State the most recent values you are aware of and note your knowledge cutoff.]"
    )
