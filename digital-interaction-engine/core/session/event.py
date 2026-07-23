"""Interaction event definitions for navigation learning."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    """Types of interaction events."""
    SESSION_START = "session_start"
    PAGE_OBSERVED = "page_observed"
    NODE_LOCATED = "node_located"
    NAVIGATION_GUIDE = "navigation_guide"
    RISK_ALERT = "risk_alert"
    NODE_TRANSITION = "node_transition"
    UNKNOWN_PAGE = "unknown_page"
    SESSION_COMPLETE = "session_complete"
    SESSION_ERROR = "session_error"


@dataclass
class InteractionEvent:
    """A single interaction event in a navigation session."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }


@dataclass
class NavigationStep:
    """A single step in the navigation path."""
    node_id: str
    page_type: str
    guidance: str
    confidence: float
    risk_alerts: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "page_type": self.page_type,
            "guidance": self.guidance,
            "confidence": self.confidence,
            "risk_alerts": self.risk_alerts,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class InteractionFlow:
    """Complete interaction flow generated from a navigation session."""
    task: str
    app: str
    session_id: str
    started_at: datetime
    completed_at: datetime
    navigation_path: list[NavigationStep] = field(default_factory=list)
    events: list[InteractionEvent] = field(default_factory=list)
    total_steps: int = 0
    total_duration: float = 0.0
    avg_confidence: float = 0.0
    unknown_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "app": self.app,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "total_steps": self.total_steps,
            "total_duration": self.total_duration,
            "avg_confidence": self.avg_confidence,
            "unknown_nodes": self.unknown_nodes,
            "navigation_path": [s.to_dict() for s in self.navigation_path],
            "events": [e.to_dict() for e in self.events],
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
