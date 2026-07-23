"""HD Interaction Map - loads Golden Flows and matches nodes."""

from __future__ import annotations

import json
import os
from pathlib import Path

GOLDEN_FLOWS_DIR = Path(__file__).parent.parent.parent / "data" / "golden_flows"


class GoldenFlow:
    """A pre-built interaction flow serving as ground truth."""

    def __init__(self, data: dict):
        self.flow_id = data["flow_id"]
        self.app = data["app"]
        self.task = data["task"]
        self.description = data.get("description", "")
        self.nodes = {n["node_id"]: n for n in data["nodes"]}
        self.node_order = [n["node_id"] for n in data["nodes"]]
        self.edges = data.get("edges", [])

    @property
    def start_node(self) -> str | None:
        for nid, node in self.nodes.items():
            if node.get("is_start"):
                return nid
        return self.node_order[0] if self.node_order else None

    @property
    def end_nodes(self) -> list[str]:
        return [nid for nid, n in self.nodes.items() if n.get("is_end")]

    def get_next_node(self, current_node_id: str) -> str | None:
        """Get the expected next node in the flow."""
        if current_node_id not in self.node_order:
            return None
        idx = self.node_order.index(current_node_id)
        if idx + 1 < len(self.node_order):
            return self.node_order[idx + 1]
        return None

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def is_end_node(self, node_id: str) -> bool:
        return node_id in self.end_nodes


class HDMap:
    """High-level interface to the HD Interaction Map.
    
    Loads Golden Flows from JSON files and provides node matching.
    """

    def __init__(self, flows_dir: str | Path | None = None):
        self._flows_dir = Path(flows_dir) if flows_dir else GOLDEN_FLOWS_DIR
        self._flows: dict[str, GoldenFlow] = {}  # key: "app_task"
        self._load_flows()

    def _load_flows(self) -> None:
        """Load all Golden Flow JSON files from the flows directory."""
        if not self._flows_dir.exists():
            return
        for f in self._flows_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                flow = GoldenFlow(data)
                key = f"{flow.app}_{flow.task}"
                existing = self._flows.get(key)
                if existing and f.stem.endswith("_web"):
                    continue
                self._flows[key] = flow
            except Exception as e:
                print(f"[HDMap] Failed to load {f}: {e}")

    def get_flow(self, app: str, task: str) -> GoldenFlow | None:
        """Get a Golden Flow by app and task."""
        return self._flows.get(f"{app}_{task}")

    def match_node(
        self, ocr_texts: list[str], app: str, task: str
    ) -> tuple[str | None, float, dict | None]:
        """Match OCR text to a node in the golden flow.
        
        Uses keyword matching. Returns (node_id, confidence, node_data).
        
        Args:
            ocr_texts: List of text strings from OCR
            app: App identifier (e.g. "taobao")
            task: Task identifier (e.g. "refund")
        
        Returns:
            (node_id, confidence, node_data) or (None, 0.0, None)
        """
        flow = self.get_flow(app, task)
        if flow is None:
            return None, 0.0, None

        # Combine all OCR texts into one string for matching
        full_text = " ".join(ocr_texts).lower()
        text_set = set(ocr_texts)

        best_node_id = None
        best_score = 0.0
        best_node_data = None

        for node_id, node in flow.nodes.items():
            indicators = node.get("key_indicators", [])
            if not indicators:
                continue

            # Score: how many key indicators appear in OCR text
            matched = sum(1 for ind in indicators if ind.lower() in full_text)
            # Penalize if we expect strong indicators that are absent
            strong_indicators = [ind for ind in indicators if len(ind) >= 3]
            matched_strong = sum(1 for ind in strong_indicators if ind.lower() in full_text)

            if matched_strong == 0:
                continue

            score = matched / len(indicators)
            # Bonus for matching more strong indicators
            if strong_indicators:
                score = 0.6 * (matched_strong / len(strong_indicators)) + 0.4 * score

            if score > best_score:
                best_score = score
                best_node_id = node_id
                best_node_data = node

        if best_node_id and best_score >= 0.3:
            return best_node_id, best_score, best_node_data

        return None, 0.0, None

    def get_guidance(self, node_id: str, app: str, task: str) -> tuple[str, list[str]]:
        """Get guidance text and risk alerts for a node."""
        flow = self.get_flow(app, task)
        if flow is None:
            return "未知页面", []

        node = flow.get_node(node_id)
        if node is None:
            return "未知页面", []

        guidance = node.get("guidance", {})
        action_text = guidance.get("action", "")
        risks = node.get("risks", [])
        risk_texts = [r.get("description", "") for r in risks]

        return action_text, risk_texts

    def is_end_node(self, node_id: str, app: str, task: str) -> bool:
        """Check if a node is the end of the task."""
        flow = self.get_flow(app, task)
        if flow is None:
            return False
        return flow.is_end_node(node_id)

    def list_flows(self) -> list[str]:
        """List all loaded flow keys."""
        return list(self._flows.keys())
