"""Multi-Agent Structured Contracts & Base Analyst Interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentReport(BaseModel):
    agent_name: str
    role: str
    symbol: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bias: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: List[str] = Field(default_factory=list)
    corroborating_evidence: List[str] = Field(default_factory=list)
    counter_arguments: List[str] = Field(default_factory=list)
    actionable_recommendation: str = "HOLD"


class BaseAnalyst(ABC):
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> AgentReport:
        """Process analytical context and generate auditable structured report."""
        pass

