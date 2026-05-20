from __future__ import annotations

from pydantic import BaseModel, Field


class ProbabilityEstimate(BaseModel):
    p_yes: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    rationale: str = ""


class AnalystOutput(BaseModel):
    name: str
    findings: list[str] = []
    estimate: ProbabilityEstimate | None = None  # not all analysts produce a probability


class DebateOutput(BaseModel):
    yes_argument: str
    no_argument: str
    rebuttals: list[str] = []


class AgentReport(BaseModel):
    """Final aggregated report fed to the sizing engine."""

    p_yes: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    analyst_outputs: list[AnalystOutput] = []
    debate: DebateOutput | None = None
