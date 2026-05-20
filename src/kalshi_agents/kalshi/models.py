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
        # Kalshi historically returned integer cents (yes_bid=54). Newer responses
        # use string-decimal "_dollars" fields (yes_bid_dollars="0.5400"). Support both.
        def to_prob(raw_dict: dict, base: str) -> float:
            dollars = raw_dict.get(f"{base}_dollars")
            if dollars not in (None, ""):
                try:
                    return float(dollars)
                except (TypeError, ValueError):
                    pass
            cents = raw_dict.get(base)
            if cents in (None, ""):
                return 0.0
            try:
                return float(cents) / 100.0
            except (TypeError, ValueError):
                return 0.0

        close = raw.get("close_time")
        close_dt = None
        if close:
            try:
                close_dt = datetime.fromisoformat(close.replace("Z", "+00:00"))
            except ValueError:
                close_dt = None

        yes_bid = to_prob(raw, "yes_bid")
        yes_ask = to_prob(raw, "yes_ask") or yes_bid
        last_price = to_prob(raw, "last_price") or None

        def to_int(d: dict, *keys: str) -> int:
            for k in keys:
                v = d.get(k)
                if v not in (None, ""):
                    try:
                        return int(float(v))
                    except (TypeError, ValueError):
                        continue
            return 0

        return cls(
            ticker=raw["ticker"],
            event_ticker=raw.get("event_ticker"),
            title=raw.get("title", raw["ticker"]),
            subtitle=raw.get("subtitle") or raw.get("yes_sub_title"),
            status=raw.get("status", "unknown"),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            last_price=last_price,
            volume=to_int(raw, "volume", "volume_fp"),
            open_interest=to_int(raw, "open_interest", "open_interest_fp"),
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
                if not entry:
                    continue
                # Two formats: legacy [price_cents:int, qty:int]
                # newer:        [price_dollars:str|float, qty:int]
                raw_price, qty = entry[0], entry[1]
                if isinstance(raw_price, str):
                    price = float(raw_price)
                elif isinstance(raw_price, (int,)) and raw_price > 1:
                    # cents
                    price = raw_price / 100.0
                else:
                    price = float(raw_price)
                    if price > 1.0:
                        price = price / 100.0
                out.append(OrderbookLevel(price=price, quantity=int(qty)))
            out.sort(key=lambda x: x.price, reverse=True)
            return out

        return cls(ticker=ticker, yes_bids=lvls("yes"), no_bids=lvls("no"))
