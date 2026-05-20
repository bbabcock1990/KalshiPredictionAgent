from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config as cfg
from .agents.graph import run as run_agents
from .decision.sizing import SizingEngine
from .kalshi.client import KalshiClient
from .storage.db import CalibrationStore

app = typer.Typer(help="kalshi-agents — multi-agent buy/no-buy signals for Kalshi.")
console = Console()


@app.command()
def market(ticker: str) -> None:
    """Fetch and print a Kalshi market snapshot (no agents, no LLM)."""
    c = cfg.load()
    with KalshiClient(c.kalshi) as k:
        m = k.get_market(ticker)
        ob = k.get_orderbook(ticker)
    table = Table(title=f"{m.ticker} — {m.title}")
    table.add_column("field"); table.add_column("value")
    table.add_row("status", m.status)
    table.add_row("yes_bid / yes_ask", f"{m.yes_bid:.2f} / {m.yes_ask:.2f}")
    table.add_row("spread", f"{m.spread_cents}¢")
    table.add_row("volume / OI", f"{m.volume} / {m.open_interest}")
    if m.minutes_to_close is not None:
        table.add_row("min to close", f"{m.minutes_to_close:.0f}")
    if ob.top_yes_bid:
        table.add_row("top YES bid", f"{ob.top_yes_bid.price:.2f} × {ob.top_yes_bid.quantity}")
    if ob.top_no_bid:
        table.add_row("top NO bid", f"{ob.top_no_bid.price:.2f} × {ob.top_no_bid.quantity}")
    console.print(table)


@app.command()
def signal(
    ticker: str,
    bankroll: float | None = typer.Option(None, help="Override BANKROLL_USD."),
    json_out: bool = typer.Option(False, "--json", help="Emit raw JSON."),
) -> None:
    """Run the agent panel and emit a GO / NO_GO decision with stake size."""
    c = cfg.load()
    if bankroll is not None:
        # Override at runtime
        from dataclasses import replace
        c = cfg.AppConfig(
            risk=replace(c.risk, bankroll_usd=bankroll),
            kalshi=c.kalshi,
            llm=c.llm,
            data_dir=c.data_dir,
        )

    with KalshiClient(c.kalshi) as k:
        market = k.get_market(ticker)
        orderbook = k.get_orderbook(ticker)

    report = run_agents(market, orderbook)
    engine = SizingEngine(c.risk)
    decision = engine.decide(
        ticker=ticker,
        model_prob=report.p_yes,
        confidence=report.confidence,
        market=market,
        orderbook=orderbook,
        rationale=report.rationale,
    )

    store = CalibrationStore(c.data_dir / "calibration.db")
    store.log_prediction(decision.to_dict(), extra={"analysts": [a.model_dump() for a in report.analyst_outputs]})

    if json_out:
        console.print_json(json.dumps(decision.to_dict()))
        return

    color = "green" if decision.signal == "GO" else "red"
    console.print(
        Panel.fit(
            f"[bold {color}]{decision.signal}[/]  side=[bold]{decision.side}[/]  "
            f"stake=[bold]${decision.stake_usd:,.2f}[/]  "
            f"contracts=[bold]{decision.contracts}[/]  "
            f"max_price=[bold]{decision.max_price:.2f}[/]\n"
            f"model_p={decision.model_prob:.3f}  market_p={decision.market_prob:.3f}  "
            f"edge={decision.edge:+.3f}  confidence={decision.confidence:.2f}",
            title=f"{ticker}",
        )
    )
    if decision.reasons_blocked:
        console.print("[yellow]Blocked because:[/] " + "; ".join(decision.reasons_blocked))
    console.print(f"[dim]{decision.rationale}[/]")


if __name__ == "__main__":
    app()
