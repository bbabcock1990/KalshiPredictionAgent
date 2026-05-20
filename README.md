# kalshi-agents

A multi-agent **buy / no-buy signal generator** for [Kalshi](https://kalshi.com)
event-contract markets, inspired by
[TradingAgents](https://github.com/bbabcock1990/TradingAgents).

You give it a Kalshi market ticker; a panel of LLM agents (analysts +
researchers + decision agent) debates the question; the system outputs:

```json
{
  "ticker": "FED-25JUL-T3.75",
  "signal": "GO",
  "side": "YES",
  "model_prob": 0.62,
  "market_prob": 0.54,
  "edge": 0.08,
  "confidence": 0.7,
  "stake_usd": 124.50,
  "max_price": 0.57,
  "rationale": "..."
}
```

> ⚠️ **Research / paper-trading only.** v1 does not place live orders. See
> `plan.md` and the disclaimers in this README. Not financial advice.

## Status

v0.1.0 — scaffolding. Kalshi read-only client, sizing engine, calibration log,
and stub agent graph in place. Real LLM analysts wired incrementally.

## Why this works for event markets (vs. stocks)

TradingAgents's value is the multi-agent **debate architecture**, not the stock
data. Kalshi markets are binary, resolve on a fixed date, and have a built-in
benchmark (the market price ≈ implied probability). That makes them an
arguably better fit for the framework than equities. See `plan.md` for the
full mapping of analyst roles.

## v1 Category: economics

First-class support for econ markets (Fed, CPI, unemployment, GDP). Other
categories (politics, sports, weather) are routed but currently fall back to
the generic prompt set.

## Install (dev)

```powershell
cd kalshi-agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,agents]"
copy .env.example .env   # fill in keys
```

## Quickstart

```powershell
# Read-only — no API key needed for public market data
kalshi-agents market FED-25JUL-T3.75

# Full agent run (requires LLM key)
kalshi-agents signal FED-25JUL-T3.75 --bankroll 5000
```

## Architecture

See `plan.md`. Briefly:

```
CLI → KalshiClient → CategoryRouter → AgentGraph (analysts → debate → decision)
    → SizingEngine (fractional Kelly) → CalibrationLogger → JSON output
```

## Disclaimer

This software is for research and education. It does not constitute financial,
investment, or trading advice. You are solely responsible for any positions
you take based on its output. The authors accept no liability.
