from __future__ import annotations

from pydantic import BaseModel, Field


class AgentReport(BaseModel):
    """Output from the TradingAgents pipeline, bridging to the sizing engine."""

    p_yes: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
