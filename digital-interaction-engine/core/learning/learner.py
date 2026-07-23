"""Learning module - records user behavior and habits to optimize guidance."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any


@dataclass
class NodeInteraction:
    """Record of a single node visit."""
    node_id: str
    page_type: str
    entered_at: float  # timestamp
    left_at: float | None = None
    guidance_given: str = ""
    guidance_level: int = 1  # 1=first, 2=upgraded, 3=upgraded again
    user_followed: bool | None = None  # True if user did what we said

    @property
    def duration(self) -> float:
        if self.left_at:
            return self.left_at - self.entered_at
        return time.time() - self.entered_at


@dataclass
class SessionRecord:
    """Record of one navigation session."""
    session_id: str
    app: str
    task: str
    started_at: str
    completed: bool = False
    total_steps: int = 0
    nodes: list[NodeInteraction] = field(default_factory=list)
    stuck_nodes: list[str] = field(default_factory=list)  # nodes where user got stuck
    repeated_guidance: list[str] = field(default_factory=list)  # nodes needing upgrade
    final_node: str = ""


class UserLearner:
    """Learns from user navigation patterns.
    
    Tracks:
    - Which nodes the user frequently gets stuck on
    - Average time spent on each node
    - Which guidance levels work best
    - User's common mistake patterns
    """

    def __init__(self, user_id: str = "default", data_dir: str | None = None):
        self.user_id = user_id
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent.parent / "data" / "user_profiles"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.sessions: list[SessionRecord] = []
        self._current_session: SessionRecord | None = None
        self._current_node: NodeInteraction | None = None
        
        self._load_profile()

    def _profile_path(self) -> Path:
        return self.data_dir / f"{self.user_id}.json"

    def _load_profile(self):
        path = self._profile_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # TODO: deserialize sessions
            except Exception:
                pass

    def save_profile(self):
        path = self._profile_path()
        data = {
            "user_id": self.user_id,
            "updated_at": datetime.now().isoformat(),
            "total_sessions": len(self.sessions),
            "weak_nodes": self.get_weak_nodes(),
            "average_times": self.get_average_node_times(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def start_session(self, app: str, task: str) -> str:
        session_id = f"{self.user_id}_{int(time.time())}"
        self._current_session = SessionRecord(
            session_id=session_id,
            app=app,
            task=task,
            started_at=datetime.now().isoformat(),
        )
        return session_id

    def enter_node(self, node_id: str, page_type: str, guidance: str = ""):
        if self._current_node:
            self._current_node.left_at = time.time()
        
        self._current_node = NodeInteraction(
            node_id=node_id,
            page_type=page_type,
            entered_at=time.time(),
            guidance_given=guidance,
        )
        if self._current_session:
            self._current_session.nodes.append(self._current_node)

    def upgrade_guidance(self, new_guidance: str):
        """Record that guidance was upgraded (user didn't act on first attempt)."""
        if self._current_node:
            self._current_node.guidance_level += 1
            self._current_node.guidance_given = new_guidance
            if self._current_session:
                self._current_session.repeated_guidance.append(self._current_node.node_id)

    def end_session(self, completed: bool, final_node: str = ""):
        if self._current_session:
            self._current_session.completed = completed
            self._current_session.final_node = final_node
            self._current_session.total_steps = len(self._current_session.nodes)
            self.sessions.append(self._current_session)
            self.save_profile()
        self._current_node = None
        self._current_session = None

    def get_weak_nodes(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Return nodes where user most often gets stuck, with count."""
        stuck_counts: dict[str, int] = {}
        for session in self.sessions:
            for node_id in session.repeated_guidance:
                stuck_counts[node_id] = stuck_counts.get(node_id, 0) + 1
        return sorted(stuck_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def get_average_node_times(self) -> dict[str, float]:
        """Return average time spent on each node type."""
        times: dict[str, list[float]] = {}
        for session in self.sessions:
            for node in session.nodes:
                pt = node.page_type
                if pt not in times:
                    times[pt] = []
                times[pt].append(node.duration)
        return {k: sum(v) / len(v) for k, v in times.items() if v}

    def is_stuck_prone(self, node_id: str) -> bool:
        """Check if user has historically gotten stuck on this node."""
        weak = self.get_weak_nodes(top_n=10)
        return any(nid == node_id for nid, _ in weak)

    def get_suggested_guidance_level(self, node_id: str) -> int:
        """Suggest initial guidance level based on user's history."""
        if self.is_stuck_prone(node_id):
            return 2  # Start with more detailed guidance
        return 1
