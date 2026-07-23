"""Generate reviewable learned flows from completed navigation sessions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.session.event import InteractionFlow


LEARNED_FLOWS_DIR = (
    Path(__file__).parent.parent.parent / "data" / "live_training" / "learned_flows"
)


def build_learned_flow(flow: InteractionFlow) -> dict:
    """Convert a session log into a compact, reviewable map-growth candidate."""
    transitions = []
    previous = None
    for step in flow.navigation_path:
        if previous and previous != step.node_id:
            transitions.append({"from": previous, "to": step.node_id})
        previous = step.node_id

    return {
        "learned_flow_id": f"{flow.app}_{flow.task}_{flow.session_id}",
        "source_session_id": flow.session_id,
        "app": flow.app,
        "task": flow.task,
        "generated_at": datetime.now().isoformat(),
        "status": "pending_review",
        "quality": {
            "total_steps": flow.total_steps,
            "avg_confidence": round(flow.avg_confidence, 3),
            "unknown_nodes": flow.unknown_nodes,
            "total_duration": round(flow.total_duration, 2),
        },
        "nodes": [
            {
                "node_id": step.node_id,
                "page_type": step.page_type,
                "guidance": step.guidance,
                "confidence": round(step.confidence, 3),
                "duration_seconds": step.duration_seconds,
                "risk_alerts": step.risk_alerts,
            }
            for step in flow.navigation_path
        ],
        "transitions": transitions,
    }


def export_learned_flow(
    flow: InteractionFlow,
    output_dir: str | Path | None = None,
) -> Path:
    """Write a learned-flow candidate JSON file and return its path."""
    target_dir = Path(output_dir) if output_dir else LEARNED_FLOWS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{flow.session_id}_{flow.app}_{flow.task}_learned.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_learned_flow(flow), f, ensure_ascii=False, indent=2)
    return path
