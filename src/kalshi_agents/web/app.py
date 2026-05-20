"""Kalshi Agents — Streamlit Dashboard.

Launch with:  streamlit run src/kalshi_agents/web/app.py
"""

from __future__ import annotations

import httpx
import streamlit as st

st.set_page_config(
    page_title="Kalshi Agents",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from kalshi_agents.web import settings_store  # noqa: E402

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "settings" not in st.session_state:
    st.session_state.settings = settings_store.load()
if "signals_history" not in st.session_state:
    st.session_state.signals_history = []


def s() -> dict:
    return st.session_state.settings


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 Kalshi Agents")
    page = st.radio(
        "Navigate",
        ["🏠 Dashboard", "⚙️ Settings", "📜 History"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"Bankroll: **${s()['bankroll_usd']:,.0f}**")
    st.caption(f"LLM: **{s()['llm_provider']}** / {s()['llm_model']}")
    st.caption(f"Kalshi: **{s()['kalshi_env']}**")

    # copilot-api health check
    try:
        r = httpx.get(f"{s()['backend_url'].rstrip('/v1')}/v1/models", timeout=2)
        st.success("LLM proxy ✓", icon="🟢")
    except Exception:
        st.error("LLM proxy offline", icon="🔴")


# ===================================================================
# SETTINGS PAGE
# ===================================================================
if page == "⚙️ Settings":
    st.header("⚙️ Settings")
    st.caption("Saved to `~/.kalshi-agents/settings.json`")

    settings = dict(s())

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Kalshi API")
        settings["kalshi_env"] = st.selectbox(
            "Environment", ["prod", "demo"], index=0 if settings["kalshi_env"] == "prod" else 1
        )
        settings["kalshi_api_key_id"] = st.text_input(
            "API Key ID (optional for read-only)", value=settings["kalshi_api_key_id"], type="password"
        )
        settings["kalshi_private_key_path"] = st.text_input(
            "Private Key Path", value=settings["kalshi_private_key_path"],
            help="Path to your RSA private key PEM file. Only needed for placing orders."
        )

        st.subheader("LLM Provider")
        providers = ["github-copilot", "openai", "anthropic", "google", "deepseek"]
        idx = providers.index(settings["llm_provider"]) if settings["llm_provider"] in providers else 0
        settings["llm_provider"] = st.selectbox("Provider", providers, index=idx)
        settings["llm_model"] = st.text_input("Model", value=settings["llm_model"])
        settings["backend_url"] = st.text_input(
            "Backend URL",
            value=settings["backend_url"],
            help="For github-copilot: http://localhost:4141/v1",
        )

    with col2:
        st.subheader("Risk Parameters")
        settings["bankroll_usd"] = st.number_input(
            "Bankroll (USD)", value=float(settings["bankroll_usd"]), min_value=0.0, step=100.0
        )
        settings["max_stake_pct"] = st.slider(
            "Max Stake %", 0.01, 0.25, float(settings["max_stake_pct"]), 0.01,
            format="%.0f%%", help="Max % of bankroll per market"
        )
        settings["kelly_fraction"] = st.slider(
            "Kelly Fraction", 0.05, 1.0, float(settings["kelly_fraction"]), 0.05,
            help="1.0 = full Kelly (aggressive), 0.25 = quarter Kelly (conservative)"
        )
        settings["min_edge"] = st.slider(
            "Min Edge (cents)", 1, 20, int(float(settings["min_edge"]) * 100), 1,
            help="Minimum probability edge to GO"
        ) / 100.0
        settings["min_confidence"] = st.slider(
            "Min Confidence", 0.0, 1.0, float(settings["min_confidence"]), 0.05,
        )
        settings["max_spread_cents"] = st.slider(
            "Max Spread (cents)", 1, 20, int(settings["max_spread_cents"]), 1,
        )
        settings["min_minutes_to_close"] = st.number_input(
            "Min Minutes to Close", value=int(settings["min_minutes_to_close"]), min_value=0, step=10,
        )

    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        settings_store.save(settings)
        st.session_state.settings = settings
        st.success("Settings saved!")
        st.rerun()


# ===================================================================
# DASHBOARD PAGE
# ===================================================================
elif page == "🏠 Dashboard":
    st.header("🏠 Signal Dashboard")

    # --- Market lookup ---
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        ticker = st.text_input(
            "Kalshi Ticker",
            placeholder="e.g. KXFEDDECISION-28JAN-H0",
            label_visibility="collapsed",
        )
    with col_btn:
        fetch_clicked = st.button("🔍 Fetch Market", use_container_width=True)

    # --- Market browser ---
    with st.expander("📋 Browse Markets by Series", expanded=not ticker):
        series_col, market_col = st.columns([1, 2])
        with series_col:
            series_input = st.text_input(
                "Series ticker",
                value="KXFEDDECISION",
                help="Try: KXFEDDECISION, KXTEMPNYCH, KXCPI, KXUNEMPLOYMENT",
            )
            browse_clicked = st.button("Browse", use_container_width=True)

        if browse_clicked and series_input:
            base = (
                "https://api.elections.kalshi.com/trade-api/v2"
                if s()["kalshi_env"] == "prod"
                else "https://demo-api.kalshi.co/trade-api/v2"
            )
            try:
                r = httpx.get(
                    f"{base}/markets",
                    params={"series_ticker": series_input, "status": "open", "limit": 50},
                    timeout=10,
                )
                markets = r.json().get("markets", [])
                with market_col:
                    if not markets:
                        st.warning("No open markets in this series.")
                    else:
                        for m in markets[:20]:
                            bid = m.get("yes_bid_dollars") or "0"
                            ask = m.get("yes_ask_dollars") or "0"
                            vol = m.get("volume_fp") or "0"
                            label = f"**{m['ticker']}** — {(m.get('title') or '')[:80]}"
                            detail = f"bid={bid} ask={ask} vol={vol}"
                            if st.button(
                                f"{label}\n{detail}",
                                key=m["ticker"],
                                use_container_width=True,
                            ):
                                st.session_state["selected_ticker"] = m["ticker"]
                                st.rerun()
            except Exception as e:
                with market_col:
                    st.error(f"Error: {e}")

    # Use selected ticker from browser if available
    if not ticker and "selected_ticker" in st.session_state:
        ticker = st.session_state.pop("selected_ticker")

    if not ticker:
        st.info("Enter a Kalshi ticker above or browse by series to get started.")
        st.stop()

    # --- Fetch market data ---
    from kalshi_agents.config import KalshiConfig
    from kalshi_agents.kalshi.client import KalshiClient
    from kalshi_agents.kalshi.models import Market

    kalshi_cfg = KalshiConfig(
        env=s()["kalshi_env"],
        api_key_id=s()["kalshi_api_key_id"] or None,
        private_key_path=s()["kalshi_private_key_path"] or None,
    )

    try:
        with KalshiClient(kalshi_cfg) as client:
            market = client.get_market(ticker)
            orderbook = client.get_orderbook(ticker)
    except Exception as e:
        st.error(f"Failed to fetch market: {e}")
        st.stop()

    # --- Market info card ---
    st.subheader(f"📈 {market.title}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("YES Mid", f"{market.yes_mid:.2f}")
    m2.metric("Spread", f"{market.spread_cents}¢")
    m3.metric("Volume", f"{market.volume:,}")
    m4.metric("Open Interest", f"{market.open_interest:,}")
    mtc = market.minutes_to_close
    if mtc is not None:
        if mtc > 1440:
            m5.metric("Closes In", f"{mtc / 1440:.0f} days")
        else:
            m5.metric("Closes In", f"{mtc:.0f} min")
    else:
        m5.metric("Closes In", "—")

    bid_ask_col, ob_col = st.columns(2)
    with bid_ask_col:
        st.caption(f"YES bid: **{market.yes_bid:.4f}** / ask: **{market.yes_ask:.4f}**")
        st.caption(f"Status: **{market.status}** | Ticker: `{market.ticker}`")
    with ob_col:
        if orderbook.yes_bids:
            ob_data = [
                {"side": "YES", "price": f"${l.price:.4f}", "qty": l.quantity}
                for l in orderbook.yes_bids[:5]
            ] + [
                {"side": "NO", "price": f"${l.price:.4f}", "qty": l.quantity}
                for l in orderbook.no_bids[:5]
            ]
            st.dataframe(ob_data, use_container_width=True, hide_index=True)

    st.divider()

    # --- Run signal ---
    run_col, info_col = st.columns([1, 2])
    with run_col:
        run_clicked = st.button(
            "🚀 Run Agent Signal",
            type="primary",
            use_container_width=True,
            help="Runs the TradingAgents debate pipeline (1-3 min)",
        )
        bankroll_override = st.number_input(
            "Bankroll override",
            value=float(s()["bankroll_usd"]),
            min_value=0.0,
            step=100.0,
        )

    if run_clicked:
        with st.spinner("🤖 Running TradingAgents debate... (1-3 minutes)"):
            try:
                from tradingagents.default_config import DEFAULT_CONFIG

                from kalshi_agents.agents.kalshi_graph import run_kalshi_agents
                from kalshi_agents.config import RiskConfig
                from kalshi_agents.decision.sizing import SizingEngine
                from kalshi_agents.storage.db import CalibrationStore

                ta_config = {**DEFAULT_CONFIG}
                ta_config["llm_provider"] = s()["llm_provider"]
                ta_config["backend_url"] = s()["backend_url"]
                ta_config["deep_think_llm"] = s()["llm_model"]
                ta_config["quick_think_llm"] = s()["llm_model"]
                ta_config["max_debate_rounds"] = 1
                ta_config["max_risk_discuss_rounds"] = 1

                report = run_kalshi_agents(market, orderbook, config=ta_config)

                risk = RiskConfig(
                    bankroll_usd=bankroll_override,
                    max_stake_pct=s()["max_stake_pct"],
                    kelly_fraction=s()["kelly_fraction"],
                    min_edge=s()["min_edge"],
                    min_confidence=s()["min_confidence"],
                    max_spread_cents=s()["max_spread_cents"],
                    min_minutes_to_close=s()["min_minutes_to_close"],
                )
                engine = SizingEngine(risk)
                decision = engine.decide(
                    ticker=ticker,
                    model_prob=report.p_yes,
                    confidence=report.confidence,
                    market=market,
                    orderbook=orderbook,
                    rationale=report.rationale,
                )

                # Log to calibration DB
                data_dir = settings_store.SETTINGS_DIR / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                store = CalibrationStore(data_dir / "calibration.db")
                store.log_prediction(decision.to_dict())

                # Save to session history
                st.session_state.signals_history.insert(0, decision.to_dict())

                # Display result
                st.divider()
                if decision.signal == "GO":
                    st.success(f"## ✅ GO — {decision.side}", icon="🟢")
                else:
                    st.warning(f"## ⛔ NO GO", icon="🔴")

                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Model P(YES)", f"{decision.model_prob:.3f}")
                r2.metric("Market P(YES)", f"{decision.market_prob:.3f}")
                r3.metric("Edge", f"{decision.edge:+.3f}")
                r4.metric("Confidence", f"{decision.confidence:.2f}")

                s1, s2, s3 = st.columns(3)
                s1.metric("Side", decision.side)
                s2.metric("Stake", f"${decision.stake_usd:,.2f}")
                s3.metric("Contracts", decision.contracts)

                if decision.reasons_blocked:
                    st.warning("**Blocked:** " + " · ".join(decision.reasons_blocked))

                with st.expander("📝 Agent Rationale", expanded=True):
                    st.write(decision.rationale)

            except Exception as e:
                st.error(f"Pipeline error: {e}")
                import traceback
                st.code(traceback.format_exc())


# ===================================================================
# HISTORY PAGE
# ===================================================================
elif page == "📜 History":
    st.header("📜 Signal History")

    # Load from calibration DB
    import sqlite3

    db_path = settings_store.SETTINGS_DIR / "data" / "calibration.db"
    if not db_path.exists():
        st.info("No signals recorded yet. Run a signal from the Dashboard first.")
        st.stop()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT ts, ticker, side, signal, model_prob, market_prob,
                      edge, confidence, stake_usd, contracts, rationale
               FROM predictions ORDER BY ts DESC LIMIT 100"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        st.info("No signals recorded yet.")
        st.stop()

    import pandas as pd

    df = pd.DataFrame(
        rows,
        columns=[
            "Timestamp", "Ticker", "Side", "Signal", "Model P",
            "Market P", "Edge", "Confidence", "Stake ($)", "Contracts", "Rationale",
        ],
    )

    # Color the Signal column
    def style_signal(val):
        if val == "GO":
            return "background-color: #22c55e20; color: #22c55e"
        return "background-color: #ef444420; color: #ef4444"

    display_cols = ["Timestamp", "Ticker", "Signal", "Side", "Model P", "Market P", "Edge", "Confidence", "Stake ($)", "Contracts"]
    styled = df[display_cols].style.map(style_signal, subset=["Signal"]).format(
        {"Model P": "{:.3f}", "Market P": "{:.3f}", "Edge": "{:+.3f}", "Confidence": "{:.2f}", "Stake ($)": "${:,.2f}"}
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Calibration score
    from kalshi_agents.storage.db import CalibrationStore

    store = CalibrationStore(db_path)
    brier = store.brier_score()
    if brier is not None:
        st.metric("Brier Score (lower is better)", f"{brier:.4f}")
    else:
        st.caption("Brier score available once market outcomes are recorded.")

    # Detail expander
    for _, row in df.iterrows():
        with st.expander(f"{row['Timestamp'][:19]} — {row['Ticker']} — {row['Signal']}"):
            st.write(row["Rationale"])
