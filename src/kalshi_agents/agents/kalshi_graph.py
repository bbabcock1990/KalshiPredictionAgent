"""KalshiTradingGraph — TradingAgents adapted for Kalshi binary event markets.

Subclasses TradingAgentsGraph to:
  - Replace stock-specific tool nodes with Kalshi tools
  - Replace analyst factories with event-market versions
  - Replace bull/bear researchers with YES/NO researchers
  - Add probability extraction from the portfolio manager's decision
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from tradingagents.agents import (
    create_aggressive_debator,
    create_conservative_debator,
    create_msg_delete,
    create_neutral_debator,
    create_portfolio_manager,
    create_research_manager,
    create_trader,
)
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.graph.propagation import Propagator
from tradingagents.llm_clients import create_llm_client

from ..kalshi.models import Market, OrderbookSnapshot
from .base import AgentReport
from .tools import (
    clear_context,
    get_economic_data,
    get_event_market_data,
    get_event_orderbook,
    search_event_news,
    set_context,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event-market analyst factories
# ---------------------------------------------------------------------------

def _create_event_microstructure_analyst(llm):
    """Analyzes Kalshi orderbook structure, spread, volume, and price action."""

    def node(state) -> dict:
        ticker = state["company_of_interest"]

        system_message = f"""You are an event-market microstructure analyst. Analyze the current \
market structure of a Kalshi binary event contract.

Focus on:
- Current YES/NO prices and the implied probability
- Bid-ask spread quality (tight = higher confidence in pricing)
- Volume and open interest (high = more informed pricing)
- Orderbook depth and imbalance between YES and NO sides
- Time to market close and implications for pricing

IMPORTANT: This is a binary event contract, not a stock. The YES price is \
the market's implied probability that the event occurs. Focus on what the \
market structure tells you about pricing confidence and potential mispricings.

The event contract ticker is: {ticker}. Analysis date: {state['trade_date']}."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ])

        tools = [get_event_market_data, get_event_orderbook]
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state)
        return {"messages": [result], "market_report": result.content}

    return node


def _create_event_public_signal_analyst(llm):
    """Pre-fetches Kalshi market data and produces a public-signal report (no tool calls)."""

    def node(state) -> dict:
        ticker = state["company_of_interest"]
        market_data = get_event_market_data.func(ticker)
        orderbook_data = get_event_orderbook.func(ticker)

        system_message = f"""You are a public-signal analyst for event markets. Assess the consensus \
view on this binary event contract by analyzing all available signals.

<market_data>
{market_data}
</market_data>

<orderbook>
{orderbook_data}
</orderbook>

Analyze:
1. What the current market price implies about consensus probability
2. Whether volume/OI suggest informed or uninformed pricing
3. Any signals from the orderbook about directional conviction
4. What external data sources (polls, forecasts, betting markets, official data) \
might inform this question — note what you know from training and flag uncertainty
5. Overall public-signal assessment: is the market price likely efficient, \
too high, or too low?

Event contract ticker: {ticker}. Date: {state['trade_date']}."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ])
        chain = prompt | llm
        result = chain.invoke(state)
        return {"messages": [result], "sentiment_report": result.content}

    return node


def _create_event_news_analyst(llm):
    """Searches for and analyzes news relevant to the event question."""

    def node(state) -> dict:
        ticker = state["company_of_interest"]

        system_message = f"""You are a news analyst for event markets. Find and analyze recent news \
that could affect the outcome of this binary event contract.

Focus on:
- Recent developments directly related to the event question
- Policy announcements, official statements, or data releases
- Expert predictions or forecasts
- Timeline factors (when is the event expected to resolve?)
- Anything that shifts the probability of YES vs NO

Use the search_event_news tool to find relevant headlines. If the tool returns \
a placeholder, use your own training knowledge but clearly distinguish known \
facts from speculation.

Event contract ticker: {ticker}. Date: {state['trade_date']}."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ])
        tools = [search_event_news]
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state)
        return {"messages": [result], "news_report": result.content}

    return node


def _create_event_base_rate_analyst(llm):
    """Analyzes historical base rates and economic fundamentals for the event."""

    def node(state) -> dict:
        ticker = state["company_of_interest"]

        system_message = f"""You are a base-rate and fundamentals analyst for event markets. Your job \
is to ground the probability estimate in historical data and structural analysis.

Focus on:
- Historical frequency of similar outcomes (base rate)
- For economic events: relevant macro data (rates, inflation, employment, GDP)
- For policy events: institutional behavior patterns and stated positions
- Structural factors that constrain the range of outcomes
- How the current situation compares to historical precedents

Use the get_economic_data tool to retrieve FRED series if relevant \
(e.g., FEDFUNDS for Fed rate markets, CPIAUCSL for inflation). If the \
tool returns a placeholder, use your training knowledge.

Event contract ticker: {ticker}. Date: {state['trade_date']}."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ])
        tools = [get_economic_data]
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state)
        return {"messages": [result], "fundamentals_report": result.content}

    return node


# ---------------------------------------------------------------------------
# YES / NO researchers (adapted from bull/bear)
# ---------------------------------------------------------------------------

def _create_yes_researcher(llm):
    """Argues the event WILL happen (YES outcome)."""

    def node(state) -> dict:
        ids = state["investment_debate_state"]
        history = ids.get("history", "")
        bull_history = ids.get("bull_history", "")
        current_response = ids.get("current_response", "")

        prompt = f"""You are a YES Analyst arguing that this event WILL occur. Build a strong, \
evidence-based case for the YES outcome.

Key points:
- Evidence supporting the event occurring (data, precedent, expert opinion)
- Why current conditions favor the YES outcome
- Counter the NO analyst's arguments with specific evidence
- Engage directly with the opposing arguments — debate, don't just list facts

Resources:
Market microstructure report: {state['market_report']}
Public signal report: {state['sentiment_report']}
News report: {state['news_report']}
Base rate / fundamentals report: {state['fundamentals_report']}
Debate history: {history}
Last NO argument: {current_response}

Deliver a compelling case for YES. Be specific and data-driven."""

        response = llm.invoke(prompt)
        # Prefix with "Bull Analyst:" for compatibility with TA's debate routing
        argument = f"Bull Analyst: {response.content}"
        return {
            "investment_debate_state": {
                "history": history + "\n" + argument,
                "bull_history": bull_history + "\n" + argument,
                "bear_history": ids.get("bear_history", ""),
                "current_response": argument,
                "count": ids["count"] + 1,
            }
        }

    return node


def _create_no_researcher(llm):
    """Argues the event will NOT happen (NO outcome)."""

    def node(state) -> dict:
        ids = state["investment_debate_state"]
        history = ids.get("history", "")
        bear_history = ids.get("bear_history", "")
        current_response = ids.get("current_response", "")

        prompt = f"""You are a NO Analyst arguing that this event will NOT occur. Build a strong, \
evidence-based case for the NO outcome.

Key points:
- Evidence against the event occurring (data, precedent, expert opinion)
- Why current conditions favor the NO outcome
- Counter the YES analyst's arguments with specific evidence
- Engage directly with the opposing arguments — debate, don't just list facts

Resources:
Market microstructure report: {state['market_report']}
Public signal report: {state['sentiment_report']}
News report: {state['news_report']}
Base rate / fundamentals report: {state['fundamentals_report']}
Debate history: {history}
Last YES argument: {current_response}

Deliver a compelling case for NO. Be specific and data-driven."""

        response = llm.invoke(prompt)
        argument = f"Bear Analyst: {response.content}"
        return {
            "investment_debate_state": {
                "history": history + "\n" + argument,
                "bear_history": bear_history + "\n" + argument,
                "bull_history": ids.get("bull_history", ""),
                "current_response": argument,
                "count": ids["count"] + 1,
            }
        }

    return node


# ---------------------------------------------------------------------------
# Graph setup override
# ---------------------------------------------------------------------------

class KalshiGraphSetup(GraphSetup):
    """GraphSetup with event-market analyst and researcher factories."""

    def setup_graph(self, selected_analysts=None):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]

        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.analyst_concurrency_limit,
        )

        analyst_factories = {
            "market": lambda: _create_event_microstructure_analyst(self.quick_thinking_llm),
            "social": lambda: _create_event_public_signal_analyst(self.quick_thinking_llm),
            "news": lambda: _create_event_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: _create_event_base_rate_analyst(self.quick_thinking_llm),
        }

        # YES/NO researchers (adapted from bull/bear)
        bull_researcher_node = _create_yes_researcher(self.quick_thinking_llm)
        bear_researcher_node = _create_no_researcher(self.quick_thinking_llm)

        # Reuse TradingAgents' research manager, trader, risk debate, and PM
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # Build the workflow (same graph structure as TradingAgents)
        workflow = StateGraph(AgentState)

        for spec in plan.specs:
            workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
            workflow.add_node(spec.clear_node, create_msg_delete())
            workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Edges: analysts in sequence
        workflow.add_edge(START, plan.specs[0].agent_node)
        for i, spec in enumerate(plan.specs):
            workflow.add_conditional_edges(
                spec.agent_node,
                getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                [spec.tool_node, spec.clear_node],
            )
            workflow.add_edge(spec.tool_node, spec.agent_node)
            if i < len(plan.specs) - 1:
                workflow.add_edge(spec.clear_node, plan.specs[i + 1].agent_node)
            else:
                workflow.add_edge(spec.clear_node, "Bull Researcher")

        # Debate
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )

        # Post-debate
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")

        # Risk discussion
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_edge("Portfolio Manager", END)

        return workflow


# ---------------------------------------------------------------------------
# Probability extraction
# ---------------------------------------------------------------------------

class EventProbability(BaseModel):
    """Structured probability estimate extracted from the agent debate."""
    p_yes: float = Field(ge=0.0, le=1.0, description="Probability the outcome is YES")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the estimate (0=guess, 1=certain)")
    rationale: str = Field(description="Brief rationale for the probability estimate")


def extract_probability(
    llm, final_decision: str, market: Market
) -> EventProbability:
    """Ask the LLM to distill the full debate into a P(YES) estimate."""
    prompt = f"""You analyzed a Kalshi binary event market through a multi-agent debate. \
Now distill the analysis into a single probability estimate.

Market question: {market.title}
Ticker: {market.ticker}
Current market YES price: {market.yes_mid:.4f}
Rules: {market.rules_primary or "N/A"}

Full analysis and final decision:
{final_decision}

Based on ALL the analysis above, what is your best estimate of P(YES) — the \
probability that the event outcome is YES?

Respond with ONLY a JSON object (no markdown, no explanation outside the JSON):
{{"p_yes": 0.XX, "confidence": 0.XX, "rationale": "brief summary"}}

Guidelines:
- p_yes should be between 0.0 and 1.0
- confidence: 0.0 = pure guess, 0.5 = moderate, 0.8+ = high confidence
- If the analysis strongly supports YES → p_yes > market price
- If the analysis strongly supports NO → p_yes < market price
- If inconclusive → p_yes near market price, low confidence"""

    response = llm.invoke(prompt)
    text = response.content.strip()

    # Parse JSON from response
    json_match = re.search(r"\{[^}]+\}", text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return EventProbability(**data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: use rating heuristic
    lower = final_decision.lower()
    if "buy" in lower:
        p = 0.70
    elif "overweight" in lower:
        p = 0.60
    elif "underweight" in lower:
        p = 0.40
    elif "sell" in lower:
        p = 0.30
    else:
        p = market.yes_mid

    return EventProbability(
        p_yes=p,
        confidence=0.3,
        rationale="Fallback: extracted from rating heuristic, LLM probability parse failed.",
    )


# ---------------------------------------------------------------------------
# Main graph class
# ---------------------------------------------------------------------------

class KalshiTradingGraph:
    """TradingAgents adapted for Kalshi binary event markets.

    Uses TradingAgents' LLM client factory, debate machinery, risk discussion,
    and portfolio manager — but with event-market-specific analysts, tools,
    and YES/NO researchers.
    """

    def __init__(self, config: Dict[str, Any] | None = None, debug: bool = False):
        self.debug = debug
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Create LLMs via TradingAgents' provider factory
        llm_kwargs = self._get_llm_kwargs()
        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        # Tool nodes
        tool_nodes = {
            "market": ToolNode([get_event_market_data, get_event_orderbook]),
            "social": ToolNode([search_event_news]),
            "news": ToolNode([search_event_news]),
            "fundamentals": ToolNode([get_economic_data]),
        }

        # Build graph with event-market factories
        conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        graph_setup = KalshiGraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            tool_nodes,
            conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
        )
        selected = ["market", "social", "news", "fundamentals"]
        self.workflow = graph_setup.setup_graph(selected)
        self.graph = self.workflow.compile()

    def _get_llm_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        provider = self.config.get("llm_provider", "").lower()
        if provider == "google":
            v = self.config.get("google_thinking_level")
            if v:
                kwargs["thinking_level"] = v
        elif provider == "openai":
            v = self.config.get("openai_reasoning_effort")
            if v:
                kwargs["reasoning_effort"] = v
        elif provider == "anthropic":
            v = self.config.get("anthropic_effort")
            if v:
                kwargs["effort"] = v
        return kwargs

    def analyze_event(
        self,
        market: Market,
        orderbook: OrderbookSnapshot | None = None,
    ) -> AgentReport:
        """Run the full TradingAgents pipeline on a Kalshi event market.

        Returns an AgentReport with p_yes, confidence, and rationale.
        """
        set_context(market, orderbook)
        trade_date = datetime.now().strftime("%Y-%m-%d")

        # Build initial state matching TradingAgents' AgentState
        market_context = self._build_market_context(market)
        init_state = {
            "messages": [("human", market_context)],
            "company_of_interest": market.ticker,
            "asset_type": "event",
            "trade_date": trade_date,
            "past_context": "",
            "investment_debate_state": InvestDebateState({
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            }),
            "risk_debate_state": RiskDebateState({
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "latest_speaker": "",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            }),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

        logger.info("Running TradingAgents on %s (%s)", market.ticker, market.title)

        if self.debug:
            trace = []
            for chunk in self.graph.stream(
                init_state,
                stream_mode="values",
                config={"recursion_limit": self.config.get("max_recur_limit", 100)},
            ):
                if chunk.get("messages"):
                    chunk["messages"][-1].pretty_print()
                trace.append(chunk)
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(
                init_state,
                stream_mode="values",
                config={"recursion_limit": self.config.get("max_recur_limit", 100)},
            )

        final_decision = final_state.get("final_trade_decision", "")
        logger.info("TA decision text: %s", final_decision[:200])

        # Extract probability from the full decision
        prob = extract_probability(
            self.quick_thinking_llm, final_decision, market
        )

        clear_context()

        return AgentReport(
            p_yes=prob.p_yes,
            confidence=prob.confidence,
            rationale=prob.rationale,
        )

    @staticmethod
    def _build_market_context(market: Market) -> str:
        lines = [
            "Analyze this Kalshi binary event market:",
            f"",
            f"Question: {market.title}",
            f"Ticker: {market.ticker}",
            f"Current YES price (implied probability): {market.yes_mid:.4f}",
            f"YES bid/ask: {market.yes_bid:.4f} / {market.yes_ask:.4f}",
            f"Spread: {market.spread_cents} cents",
            f"Volume: {market.volume}  Open Interest: {market.open_interest}",
        ]
        if market.rules_primary:
            lines.append(f"Resolution rules: {market.rules_primary}")
        mtc = market.minutes_to_close
        if mtc is not None:
            if mtc > 1440:
                lines.append(f"Closes in: {mtc / 1440:.1f} days")
            else:
                lines.append(f"Closes in: {mtc:.0f} minutes")
        lines.append("")
        lines.append(
            "Your job: determine whether the market price is correct, too high, "
            "or too low. What is the TRUE probability of YES?"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def run_kalshi_agents(
    market: Market,
    orderbook: OrderbookSnapshot | None,
    config: Dict[str, Any] | None = None,
    debug: bool = False,
) -> AgentReport:
    """Top-level entry point: run TradingAgents on a Kalshi market.

    Creates the graph, runs the full pipeline, extracts a probability estimate.
    """
    graph = KalshiTradingGraph(config=config, debug=debug)
    return graph.analyze_event(market, orderbook)
