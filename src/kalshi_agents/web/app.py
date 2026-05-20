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
        check_url = s()["backend_url"]
        if not check_url.endswith("/models"):
            check_url = check_url.rstrip("/") + "/models"
        r = httpx.get(check_url, timeout=2)
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

    # --- Live/Demo banner ---
    if s()["kalshi_env"] == "prod":
        st.info(
            "🔴 **LIVE MARKETS** — You are viewing real Kalshi markets with real money. "
            "This tool is **read-only** — it analyzes markets and recommends bets but "
            "never places orders on your behalf.",
            icon="📡",
        )
    else:
        st.warning(
            "🟡 **DEMO MODE** — You are viewing Kalshi's demo/sandbox environment. "
            "Markets use play money. Switch to **prod** in Settings for real markets.",
            icon="🧪",
        )

    # --- Market lookup ---
    # If a market was selected from the browser, set it in widget state
    if "selected_ticker" in st.session_state:
        st.session_state["ticker_input"] = st.session_state.pop("selected_ticker")
        st.session_state["auto_fetch"] = True

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        ticker = st.text_input(
            "Kalshi Ticker",
            placeholder="e.g. KXFEDDECISION-28JAN-H0",
            label_visibility="collapsed",
            key="ticker_input",
        )
    with col_btn:
        fetch_clicked = st.button("🔍 Fetch Market", use_container_width=True)

    # Auto-fetch when a market was selected from the browser
    if st.session_state.pop("auto_fetch", False):
        fetch_clicked = True

    # --- Market browser ---
    CATEGORIES = [
        "All", "Sports", "Politics", "Economics", "Elections",
        "Entertainment", "Financials", "Climate and Weather",
        "Crypto", "Science and Technology", "World", "Companies",
        "Health", "Commodities",
    ]

    base_url = (
        "https://api.elections.kalshi.com/trade-api/v2"
        if s()["kalshi_env"] == "prod"
        else "https://demo-api.kalshi.co/trade-api/v2"
    )

    with st.expander("📋 Browse & Filter Markets", expanded=not ticker):
        filter_col, results_col = st.columns([1, 2])

        with filter_col:
            st.markdown("**Filter by category**")
            selected_cat = st.selectbox(
                "Category", CATEGORIES, label_visibility="collapsed"
            )
            search_text = st.text_input(
                "Search by keyword",
                placeholder="e.g. Fed, NBA, Trump, Bitcoin",
            )
            series_input = st.text_input(
                "Or enter series ticker directly",
                placeholder="e.g. KXFEDDECISION",
                help="Series group related markets (e.g., all Fed rate meetings).",
            )
            browse_clicked = st.button("🔎 Search Markets", use_container_width=True)

        if browse_clicked:
            with results_col:
                try:
                    if series_input:
                        # Search by series ticker
                        r = httpx.get(
                            f"{base_url}/markets",
                            params={"series_ticker": series_input.strip(), "status": "open", "limit": 50},
                            timeout=15,
                        )
                        found = r.json().get("markets", [])
                    else:
                        # Search by events (supports category/keyword)
                        params = {"status": "open", "limit": 100}
                        r = httpx.get(f"{base_url}/events", params=params, timeout=15)
                        events = r.json().get("events", [])

                        # Filter by category
                        if selected_cat != "All":
                            events = [
                                e for e in events
                                if (e.get("category") or "").lower() == selected_cat.lower()
                            ]

                        # Filter by keyword
                        if search_text:
                            kw = search_text.lower()
                            events = [
                                e for e in events
                                if kw in (e.get("title") or "").lower()
                                or kw in (e.get("event_ticker") or "").lower()
                            ]

                        # Fetch markets for matching events
                        found = []
                        for ev in events[:15]:
                            et = ev.get("event_ticker")
                            if not et:
                                continue
                            mr = httpx.get(
                                f"{base_url}/markets",
                                params={"event_ticker": et, "status": "open", "limit": 10},
                                timeout=10,
                            )
                            found.extend(mr.json().get("markets", []))
                            if len(found) >= 30:
                                break

                    if not found:
                        st.warning("No open markets found. Try a different filter.")
                    else:
                        st.markdown(f"**{len(found)} market(s) found**")
                        for m in found[:30]:
                            bid = m.get("yes_bid_dollars") or "—"
                            ask = m.get("yes_ask_dollars") or "—"
                            vol = m.get("volume_fp") or "0"
                            title = (m.get("title") or m["ticker"])[:90]
                            cat = m.get("category") or ""
                            cat_badge = f" `{cat}`" if cat else ""

                            if st.button(
                                f"**{title}**{cat_badge}\n"
                                f"`{m['ticker']}` · YES {bid}/{ask} · vol {vol}",
                                key=f"browse_{m['ticker']}",
                                use_container_width=True,
                            ):
                                st.session_state["selected_ticker"] = m["ticker"]
                                st.rerun()
                except Exception as e:
                    st.error(f"Error searching: {e}")

    ticker = ticker.strip() if ticker else ""

    if not ticker:
        st.info("Enter a Kalshi ticker above or browse markets to get started.")
        st.stop()

    if not fetch_clicked and "current_market" not in st.session_state:
        st.info("Enter a ticker and click **🔍 Fetch Market** to load it.")
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

    if fetch_clicked or st.session_state.get("current_ticker") != ticker:
        try:
            with KalshiClient(kalshi_cfg) as client:
                market = client.get_market(ticker)
                orderbook = client.get_orderbook(ticker)
            st.session_state["current_market"] = market
            st.session_state["current_orderbook"] = orderbook
            st.session_state["current_ticker"] = ticker
        except Exception as e:
            st.error(f"Failed to fetch market: {e}")
            st.stop()
    else:
        market = st.session_state.get("current_market")
        orderbook = st.session_state.get("current_orderbook")
        if not market:
            st.info("Click **🔍 Fetch Market** to load market data.")
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
        # --- Node-to-stage mapping for progress bar ---
        NODE_INFO = {
            "Market Analyst":        ("📊 Analyzing market microstructure...", 0.07),
            "tools_market":          ("📊 Fetching orderbook data...", 0.10),
            "Msg Clear Market":      ("✅ Market analysis complete", 0.13),
            "Sentiment Analyst":     ("📡 Assessing public signals & consensus...", 0.20),
            "tools_social":          ("📡 Fetching signal data...", 0.22),
            "Msg Clear Sentiment":   ("✅ Public signal analysis complete", 0.25),
            "News Analyst":          ("📰 Searching for relevant news...", 0.33),
            "tools_news":            ("📰 Fetching news articles...", 0.37),
            "Msg Clear News":        ("✅ News analysis complete", 0.40),
            "Fundamentals Analyst":  ("📈 Analyzing base rates & fundamentals...", 0.47),
            "tools_fundamentals":    ("📈 Fetching economic data...", 0.50),
            "Msg Clear Fundamentals":("✅ Base rate analysis complete", 0.53),
            "Bull Researcher":       ("🟢 YES Researcher making the case for YES...", 0.60),
            "Bear Researcher":       ("🔴 NO Researcher making the case for NO...", 0.67),
            "Research Manager":      ("🧠 Research Manager synthesizing the debate...", 0.73),
            "Trader":                ("💼 Trader forming a position proposal...", 0.78),
            "Aggressive Analyst":    ("⚡ Risk team: Aggressive analyst...", 0.82),
            "Conservative Analyst":  ("🛡️ Risk team: Conservative analyst...", 0.86),
            "Neutral Analyst":       ("⚖️ Risk team: Neutral analyst...", 0.90),
            "Portfolio Manager":     ("👔 Portfolio Manager making final decision...", 0.95),
            "__extracting_probability__": ("🎯 Extracting probability estimate...", 0.98),
        }

        # Report keys that contain the readable agent output
        REPORT_KEYS = [
            "market_report", "sentiment_report", "news_report",
            "fundamentals_report", "investment_plan",
            "trader_investment_plan", "final_trade_decision",
        ]

        progress_bar = st.progress(0, text="Starting AI agents...")
        console = st.status("🤖 Agent Console — click to expand", expanded=False)

        def on_progress(node_name, node_output):
            label, pct = NODE_INFO.get(node_name, (node_name, None))
            if pct:
                progress_bar.progress(pct, text=label)
            console.write(f"**{label}**")
            # Show report content if available
            for key in REPORT_KEYS:
                val = node_output.get(key, "")
                if val and isinstance(val, str) and len(val) > 20:
                    preview = val[:500].replace("\n", " ")
                    console.caption(f"_{preview}{'...' if len(val) > 500 else ''}_")

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

            report = run_kalshi_agents(
                market, orderbook, config=ta_config,
                progress_callback=on_progress,
            )

            progress_bar.progress(1.0, text="✅ Analysis complete!")
            console.update(label="🤖 Agent Console — complete", state="complete")

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
                st.success(f"## ✅ GO — Bet {decision.side}")
                st.markdown(
                    f"**Our AI agents found an edge.** They think the market is mispriced "
                    f"and recommend betting **{decision.side}** with "
                    f"**${decision.stake_usd:,.2f}** ({decision.contracts} contracts)."
                )
            else:
                st.error(f"## ⛔ NO GO — Don't Bet")
                st.markdown(
                    "**No good bet here.** Our AI agents didn't find enough of an edge "
                    "over the market price to justify a bet."
                )

            st.markdown("---")
            st.markdown("### 📊 What the AI Found")

            r1, r2 = st.columns(2)
            with r1:
                pct_model = decision.model_prob * 100
                st.metric("🤖 AI's Probability", f"{pct_model:.0f}%")
                st.caption("What our AI agents think the chance of YES is, after debating the evidence.")

            with r2:
                pct_market = decision.market_prob * 100
                st.metric("📈 Market's Probability", f"{pct_market:.0f}%")
                st.caption("What other traders think — the current YES price on Kalshi.")

            e1, e2 = st.columns(2)
            with e1:
                edge_pct = decision.edge * 100
                edge_color = "🟢" if edge_pct > 0 else "🔴"
                st.metric(f"{edge_color} Edge", f"{edge_pct:+.1f}%")
                st.caption(
                    "The gap between our AI's estimate and the market price. "
                    "Positive = we think the market is wrong in our favor. "
                    "Needs to be ≥5% for a GO signal."
                )

            with e2:
                conf_pct = decision.confidence * 100
                st.metric("🎯 Confidence", f"{conf_pct:.0f}%")
                st.caption(
                    "How sure our AI agents are about their probability estimate. "
                    "Higher = more agreement between analysts. Needs ≥50% for a GO."
                )

            st.markdown("### 💰 Recommended Bet")
            if decision.signal == "GO":
                b1, b2, b3 = st.columns(3)
                with b1:
                    side_emoji = "👍" if decision.side == "YES" else "👎"
                    st.metric(f"{side_emoji} Side", decision.side)
                    st.caption(
                        "Which side to bet on. **YES** = you think the event will happen. "
                        "**NO** = you think it won't."
                    )
                with b2:
                    st.metric("💵 Stake", f"${decision.stake_usd:,.2f}")
                    st.caption(
                        f"How much to bet, based on your ${bankroll_override:,.0f} bankroll "
                        "and conservative Kelly sizing (protects against overconfidence)."
                    )
                with b3:
                    st.metric("📦 Contracts", decision.contracts)
                    st.caption(
                        "Number of contracts to buy at the current price. "
                        "Each contract pays $1 if your side wins."
                    )
            else:
                st.info(
                    "🚫 **No bet recommended.** The system didn't find a large enough "
                    "edge to justify risking money. See the reasons below."
                )

            if decision.reasons_blocked:
                st.markdown("### ⚠️ Why NO GO")
                for reason in decision.reasons_blocked:
                    if "edge" in reason:
                        st.warning(
                            f"📉 **Not enough edge**\n\n"
                            f"Our AI's probability ({decision.model_prob*100:.0f}%) is too close "
                            f"to the market price ({decision.market_prob*100:.0f}%). The gap "
                            f"({decision.edge*100:+.1f}%) needs to be at least "
                            f"{s()['min_edge']*100:.0f}% to justify a bet. When the AI agrees "
                            f"with the market, there's no money to be made."
                        )
                    elif "confidence" in reason:
                        st.warning(
                            f"🤷 **Too uncertain**\n\n"
                            f"Our AI agents only have {decision.confidence*100:.0f}% confidence "
                            f"in their estimate. This means the analysts disagreed with each "
                            f"other or the evidence was weak. We need at least "
                            f"{s()['min_confidence']*100:.0f}% confidence to risk real money."
                        )
                    elif "spread" in reason:
                        st.warning(
                            f"💸 **Market too thin (wide spread)**\n\n"
                            f"The spread is {market.spread_cents}¢ — that's the gap between "
                            f"what buyers are willing to pay and what sellers are asking. "
                            f"A wide spread means fewer people are trading this market, so "
                            f"you'd lose money just entering and exiting the position. "
                            f"We need the spread to be {s()['max_spread_cents']}¢ or less."
                        )
                    elif "close" in reason or "min" in reason.lower():
                        st.warning(
                            f"⏰ **Too close to closing**\n\n"
                            f"This market closes soon. Near-expiry markets can be volatile "
                            f"and hard to exit. We require at least "
                            f"{s()['min_minutes_to_close']} minutes before close."
                        )
                    elif "stake" in reason:
                        st.warning(
                            f"📦 **Bet too small**\n\n"
                            f"After applying our risk limits, the recommended bet size is "
                            f"less than the cost of a single contract. This usually happens "
                            f"when the edge is tiny or the bankroll is small relative to the "
                            f"contract price."
                        )
                    elif "status" in reason:
                        st.warning(
                            f"🔒 **Market not open**\n\n"
                            f"This market's status is '{market.status}' — it may be closed, "
                            f"settled, or not yet open for trading."
                        )
                    else:
                        st.warning(f"⚠️ {reason}")

            with st.expander("📝 AI Agent Rationale (detailed)", expanded=False):
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
