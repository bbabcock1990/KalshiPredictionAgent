from kalshi_agents.kalshi.models import Market, OrderbookSnapshot


def test_market_from_kalshi_normalizes_cents_to_probability():
    m = Market.from_kalshi(
        {
            "ticker": "X",
            "title": "Test",
            "status": "open",
            "yes_bid": 54,
            "yes_ask": 57,
            "volume": 1234,
            "open_interest": 500,
            "close_time": "2030-01-01T00:00:00Z",
        }
    )
    assert m.yes_bid == 0.54
    assert m.yes_ask == 0.57
    assert m.spread_cents == 3
    assert abs(m.yes_mid - 0.555) < 1e-9


def test_market_from_kalshi_accepts_dollars_format():
    """Newer Kalshi payloads use *_dollars string fields and *_fp volumes."""
    m = Market.from_kalshi(
        {
            "ticker": "KXFEDDECISION-28JAN-H0",
            "title": "Will the Fed hike 0bps?",
            "status": "active",
            "yes_bid_dollars": "0.6700",
            "yes_ask_dollars": "0.7000",
            "last_price_dollars": "0.6800",
            "volume_fp": "1343.00",
            "open_interest_fp": "374.00",
            "close_time": "2030-01-01T00:00:00Z",
        }
    )
    assert m.yes_bid == 0.67
    assert m.yes_ask == 0.70
    assert m.last_price == 0.68
    assert m.volume == 1343
    assert m.open_interest == 374
    assert m.spread_cents == 3


def test_orderbook_from_kalshi_sorts_levels():
    raw = {
        "orderbook": {
            "yes": [[40, 100], [45, 50], [42, 75]],
            "no":  [[55, 200], [58, 100]],
        }
    }
    ob = OrderbookSnapshot.from_kalshi("X", raw)
    assert [l.price for l in ob.yes_bids] == [0.45, 0.42, 0.40]
    assert ob.top_yes_bid.quantity == 50
    assert ob.top_no_bid.price == 0.58
