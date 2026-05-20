from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Market(BaseModel):
    """Normalized snapshot of a Kalshi binary market.

    Prices are stored as **probabilities in [0, 1]**, not cents.
    """

    ticker: str
    event_ticker: str | None = None
    title: str
    subtitle: str | None = None
    status: str
    yes_bid: float = Field(..., ge=0.0, le=1.0)
    yes_ask: float = Field(..., ge=0.0, le=1.0)
    last_price: float | None = None
    volume: int = 0
    open_interest: int = 0
    close_time: datetime | None = None
    rules_primary: str | None = None
    category: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @property
    def yes_mid(self) -> float:
        return (self.yes_bid + self.yes_ask) / 2.0

    @property
    def spread_cents(self) -> int:
        return round((self.yes_ask - self.yes_bid) * 100)

    @property
    def minutes_to_close(self) -> float | None:
        if self.close_time is None:
            return None
        now = datetime.now(timezone.utc)
        delta = self.close_time - now
        return delta.total_seconds() / 60.0

    @classmethod
    def from_kalshi(cls, raw: dict[str, Any]) -> "Market":
        # Kalshi returns prices in **cents** (0–100). Normalize to probability.
        def cents(v: Any) -> float:
            return (float(v) / 100.0) if v is not None else 0.0

        close = raw.get("close_time")
        close_dt = None
        if close:
            try:
                close_dt = datetime.fromisoformat(close.replace("Z", "+00:00"))
            except ValueError:
                close_dt = None

        return cls(
            ticker=raw["ticker"],
            event_ticker=raw.get("event_ticker"),
            title=raw.get("title", raw["ticker"]),
            subtitle=raw.get("subtitle"),
            status=raw.get("status", "unknown"),
            yes_bid=cents(raw.get("yes_bid")),
            yes_ask=cents(raw.get("yes_ask")) or cents(raw.get("yes_bid")),
            last_price=cents(raw.get("last_price")) if raw.get("last_price") else None,
            volume=int(raw.get("volume", 0) or 0),
            open_interest=int(raw.get("open_interest", 0) or 0),
            close_time=close_dt,
            rules_primary=raw.get("rules_primary"),
            category=raw.get("category"),
            raw=raw,
        )


class OrderbookLevel(BaseModel):
    price: float  # probability 0..1
    quantity: int


class OrderbookSnapshot(BaseModel):
    ticker: str
    yes_bids: list[OrderbookLevel] = []
    no_bids: list[OrderbookLevel] = []

    @property
    def top_yes_bid(self) -> OrderbookLevel | None:
        return self.yes_bids[0] if self.yes_bids else None

    @property
    def top_no_bid(self) -> OrderbookLevel | None:
        return self.no_bids[0] if self.no_bids else None

    @classmethod
    def from_kalshi(cls, ticker: str, raw: dict[str, Any]) -> "OrderbookSnapshot":
        ob = raw.get("orderbook", raw)

        def lvls(side: str) -> list[OrderbookLevel]:
            out = []
            for entry in ob.get(side, []) or []:
                # Kalshi: [price_cents, quantity]
                if not entry:
                    continue
                price_cents, qty = entry[0], entry[1]
                out.append(OrderbookLevel(price=price_cents / 100.0, quantity=int(qty)))
            # Best bid first (highest price)
            out.sort(key=lambda x: x.price, reverse=True)
            return out

        return cls(ticker=ticker, yes_bids=lvls("yes"), no_bids=lvls("no"))
