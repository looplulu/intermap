"""Navigation Session - the core state machine of the Digital Interaction Engine.

Integrated features:
- Page change detection (event-driven)
- Visual position guidance (button location on screen)
- Guidance escalation (3 levels: basic -> detailed -> reset suggestion)
- Lost detection (oscillating between pages)
- Voice output with queue
- Learning module (user habit tracking)
"""

from __future__ import annotations

import uuid
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from core.session.state import SessionStatus, TaskType, recognize_task
from core.session.event import EventType, InteractionEvent, NavigationStep, InteractionFlow
from core.session.page_change import PageChangeDetector

if TYPE_CHECKING:
    from core.hd_map.map import HDMap
    from core.vision.llm_client import DeepSeekClient
    from core.voice.tts import VoiceOutput
    from core.learning.learner import UserLearner


ScreenProvider = Callable[[], Any]
VisionProvider = Callable[[Any], dict]
NodeMatcher = Callable[[dict, str, str], tuple[str | None, float]]
GuidanceHandler = Callable[[str, list[str]], None]
FlowExporter = Callable[[InteractionFlow], None]


class NavigationSession:
    """Continuous Task Navigation with guidance escalation and lost detection."""

    # Config
    STUCK_THRESHOLD = 8.0       # seconds before upgrading guidance
    LOST_WINDOW = 30.0          # seconds window for lost detection
    LOST_CYCLE_COUNT = 3        # min oscillations to be "lost"
    MAX_ESCALATION = 3          # max guidance level
    MAX_ITERATIONS = 100
    MIN_CONFIDENCE = 0.3

    def __init__(
        self,
        screen_provider: ScreenProvider,
        vision_provider: VisionProvider,
        node_matcher: NodeMatcher,
        guidance_handler: GuidanceHandler,
        flow_exporter: FlowExporter | None = None,
        hd_map: HDMap | None = None,
        llm_client: DeepSeekClient | None = None,
        voice_output: VoiceOutput | None = None,
        learner: UserLearner | None = None,
    ):
        self._screen_provider = screen_provider
        self._vision_provider = vision_provider
        self._node_matcher = node_matcher
        self._guidance_handler = guidance_handler
        self._flow_exporter = flow_exporter
        self._hd_map = hd_map
        self._llm_client = llm_client
        self._voice = voice_output
        self._learner = learner

        self.session_id: str = str(uuid.uuid4())[:8]
        self._status: SessionStatus = SessionStatus.IDLE
        self._task: TaskType | None = None
        self._app: str | None = None
        self._current_node: str | None = None
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None

        self._navigation_path: list[NavigationStep] = []
        self._events: list[InteractionEvent] = []
        self._unknown_nodes: list[str] = []

        # Guidance escalation state
        self._guidance_levels: dict[str, int] = {}      # node_id -> level (1-3)
        self._node_enter_time: float = 0.0              # when user entered current node
        self._last_step_time: float | None = None
        self._last_guidance_hash: str = ""              # dedup

        # Lost detection
        self._recent_node_history: list[tuple[float, str]] = []  # (time, node_id)

        # Page change detection
        self._page_detector = PageChangeDetector(text_change_threshold=0.25)

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def task(self) -> TaskType | None:
        return self._task

    @property
    def app(self) -> str | None:
        return self._app

    @property
    def current_node(self) -> str | None:
        return self._current_node

    # ── Lifecycle ──────────────────────────────────────────

    def start(self, user_input: str) -> None:
        if self._status != SessionStatus.IDLE:
            raise RuntimeError(f"Cannot start session in {self._status} state")

        task = recognize_task(user_input)
        if task is None:
            self._record_event(EventType.SESSION_ERROR, {
                "error": "无法识别任务类型",
                "user_input": user_input,
            })
            raise ValueError(f"无法识别任务: '{user_input}'")

        self._task = task
        self._status = SessionStatus.ACTIVE
        self._started_at = datetime.now()
        self._record_event(EventType.SESSION_START, {
            "task": task.value,
            "user_input": user_input,
        })

        if self._learner:
            self._learner.start_session(self._app or "unknown", task.value)

    def run(self) -> InteractionFlow:
        if self._status != SessionStatus.ACTIVE:
            raise RuntimeError("Call start() before run()")

        self._status = SessionStatus.NAVIGATING
        self._page_detector = PageChangeDetector(text_change_threshold=0.25)

        for _ in range(self.MAX_ITERATIONS):
            now = time.time()

            # 1. OBSERVE
            screen = self._observe()
            if screen is None:
                time.sleep(0.5)
                continue

            # 2. VISION
            vision_result = self._vision_provider(screen)
            texts = vision_result.get("texts", [])

            # 3. PAGE CHANGE DETECTION
            snapshot = self._page_detector.snapshot(texts=texts)
            page_changed = self._page_detector.has_changed(snapshot)

            if not page_changed:
                # User hasn't acted yet - check if stuck
                if self._current_node:
                    stuck_time = now - self._node_enter_time
                    if stuck_time > self.STUCK_THRESHOLD:
                        self._escalate_guidance(self._current_node, vision_result)
                        self._node_enter_time = now  # reset timer after escalation
                time.sleep(0.5)
                continue

            # Page changed!
            self._page_detector.update(snapshot)

            # 4. LOCATE
            node_id, confidence, page_type = self._locate_with_vision(vision_result)

            if node_id is None:
                self._handle_unknown_page(screen, vision_result)
                continue

            # 5. LOST DETECTION
            self._record_node_visit(now, node_id)
            if self._is_user_lost():
                lost_guidance = "你好像来回跳转好几次了，要不要返回首页重新来？"
                self._output_guidance(lost_guidance, [], node_id)
                # Don't break - let user decide

            # 6. NAVIGATE
            # Check if this is a new node or same node (shouldn't happen with page_changed)
            is_new_node = node_id != self._current_node
            if is_new_node:
                if self._current_node:
                    self._record_event(EventType.NODE_TRANSITION, {
                        "from": self._current_node,
                        "to": node_id,
                    })
                self._guidance_levels[node_id] = 1  # reset escalation
                self._node_enter_time = now

            guidance, risks = self._generate_guidance(node_id, confidence, vision_result)
            self._output_guidance(guidance, risks, node_id)

            # 7. LEARN
            self._learn(node_id, page_type, guidance, confidence, risks)
            self._current_node = node_id

            if self._learner:
                self._learner.enter_node(node_id, page_type, guidance)

            # 8. CHECK END
            if self._is_task_complete(node_id):
                break

            time.sleep(0.5)

        self._complete()
        return self._build_flow()

    # ── Internal Steps ─────────────────────────────────────

    def _observe(self) -> Any:
        self._record_event(EventType.PAGE_OBSERVED, {})
        try:
            return self._screen_provider()
        except Exception as e:
            self._record_event(EventType.SESSION_ERROR, {"error": str(e)})
            return None

    def _locate_with_vision(self, vision_result: dict) -> tuple[str | None, float, str]:
        app = self._app or "unknown"
        task = self._task.value if self._task else "unknown"
        node_id, confidence = self._node_matcher(vision_result, app, task)

        if node_id and confidence >= self.MIN_CONFIDENCE:
            self._record_event(EventType.NODE_LOCATED, {
                "node_id": node_id, "confidence": confidence,
            })
            return node_id, confidence, vision_result.get("page_type", "unknown")
        return None, 0.0, "unknown"

    def _generate_guidance(
        self, node_id: str, confidence: float, vision_result: dict
    ) -> tuple[str, list[str]]:
        """Generate guidance, optionally with position info."""
        guidance = ""
        risks = []

        if self._hd_map:
            g, risks = self._hd_map.get_guidance(
                node_id, self._app or "unknown", self._task.value if self._task else "unknown"
            )
            guidance = g

        if not guidance:
            guidance = f"当前页面: {node_id}"

        # Add position info if OCR items available
        ocr_items = vision_result.get("ocr_items", [])
        img_size = vision_result.get("image_size", (0, 0))
        if ocr_items and img_size[0] > 0:
            from core.vision.position import PositionGuider
            guider = PositionGuider(img_size[0], img_size[1])
            # Try to find the button mentioned in guidance and add its position
            # Extract button keywords from guidance (text inside quotes)
            import re
            quotes = re.findall(r"['\"](.+?)['\"]", guidance)
            if quotes:
                enhanced = guider.add_position_to_guidance(guidance, ocr_items, quotes)
                if enhanced != guidance:
                    guidance = enhanced

        return guidance, risks

    def _escalate_guidance(self, node_id: str, vision_result: dict) -> None:
        """User has been on same node too long - upgrade guidance."""
        level = self._guidance_levels.get(node_id, 1)
        if level >= self.MAX_ESCALATION:
            return  # maxed out

        level += 1
        self._guidance_levels[node_id] = level

        # Get base guidance
        guidance = ""
        if self._hd_map:
            g, _ = self._hd_map.get_guidance(
                node_id, self._app or "unknown", self._task.value if self._task else "unknown"
            )
            guidance = g

        if not guidance:
            return

        # Level 2: add more specific location
        if level == 2:
            ocr_items = vision_result.get("ocr_items", [])
            img_size = vision_result.get("image_size", (0, 0))
            if ocr_items and img_size[0] > 0:
                from core.vision.position import PositionGuider
                guider = PositionGuider(img_size[0], img_size[1])
                import re
                quotes = re.findall(r"['\"](.+?)['\"]", guidance)
                for q in quotes:
                    pos = guider.describe_button_location(ocr_items, q)
                    if pos:
                        guidance = f"{guidance}，在{pos}"
                        break
            if guidance == g:  # no position found
                guidance = f"{guidance}，仔细找一下"

        # Level 3: suggest reset
        elif level == 3:
            guidance = f"{guidance}。如果找不到，点左上角返回，回到首页重新来"

        # Dedup
        h = hash(guidance)
        if h == self._last_guidance_hash:
            return
        self._last_guidance_hash = h

        self._output_guidance(guidance, [], node_id)

        if self._learner:
            self._learner.upgrade_guidance(guidance)

    def _output_guidance(self, guidance: str, risks: list[str], node_id: str) -> None:
        """Output guidance via handler and voice."""
        self._guidance_handler(guidance, risks)
        if self._voice:
            self._voice.speak(guidance)
            for risk in risks[:1]:  # speak first risk only
                self._voice.speak(f"注意：{risk}")

        self._record_event(EventType.NAVIGATION_GUIDE, {
            "node_id": node_id, "guidance": guidance, "risks": risks,
        })

    def _record_node_visit(self, now: float, node_id: str) -> None:
        """Record node visit for lost detection."""
        self._recent_node_history.append((now, node_id))
        # Keep only recent window
        cutoff = now - self.LOST_WINDOW
        self._recent_node_history = [
            (t, n) for t, n in self._recent_node_history if t > cutoff
        ]

    def _is_user_lost(self) -> bool:
        """Detect if user is oscillating between pages (lost)."""
        if len(self._recent_node_history) < 4:
            return False

        nodes = [n for _, n in self._recent_node_history]
        # Check for A->B->A->B pattern
        for i in range(len(nodes) - 3):
            a, b, c, d = nodes[i], nodes[i+1], nodes[i+2], nodes[i+3]
            if a == c and b == d and a != b:
                return True
        return False

    def _handle_unknown_page(self, screen: Any, vision_result: dict) -> None:
        ocr_texts = vision_result.get("texts", [])
        if self._llm_client and ocr_texts:
            llm_result = self._llm_client.understand_page(
                ocr_texts=ocr_texts,
                task=self._task.value if self._task else "unknown",
                app_hint=self._app or "unknown",
            )
            if llm_result.confidence >= self.MIN_CONFIDENCE:
                guidance = llm_result.guidance_text
                self._output_guidance(guidance, [], f"llm_{llm_result.page_type}")
                self._learn(
                    f"llm_{llm_result.page_type}", llm_result.page_type,
                    guidance, llm_result.confidence, [],
                )
                self._current_node = f"llm_{llm_result.page_type}"
                return

        self._unknown_nodes.append(f"unknown_{len(self._unknown_nodes) + 1}")
        self._output_guidance("当前页面未被收录，等待页面变化...", [], "unknown")

    def _learn(self, node_id, page_type, guidance, confidence, risks):
        now = time.time()
        if self._navigation_path and self._last_step_time is not None:
            self._navigation_path[-1].duration_seconds = round(now - self._last_step_time, 2)

        step = NavigationStep(
            node_id=node_id, page_type=page_type, guidance=guidance,
            confidence=confidence, risk_alerts=risks,
        )
        self._navigation_path.append(step)
        self._last_step_time = now

    def _is_task_complete(self, node_id: str) -> bool:
        if self._hd_map:
            if self._hd_map.is_end_node(
                node_id, self._app or "unknown", self._task.value if self._task else "unknown"
            ):
                return True
        end_indicators = ["result", "complete", "success", "finish"]
        return any(indicator in node_id.lower() for indicator in end_indicators)

    def _complete(self):
        self._status = SessionStatus.COMPLETE
        self._completed_at = datetime.now()
        if self._navigation_path and self._last_step_time is not None:
            self._navigation_path[-1].duration_seconds = round(time.time() - self._last_step_time, 2)
        self._record_event(EventType.SESSION_COMPLETE, {
            "total_steps": len(self._navigation_path),
        })
        if self._learner:
            self._learner.end_session(
                completed=True, final_node=self._current_node or "",
            )

    def _build_flow(self) -> InteractionFlow:
        flow = InteractionFlow(
            task=self._task.value if self._task else "unknown",
            app=self._app or "unknown",
            session_id=self.session_id,
            started_at=self._started_at or datetime.now(),
            completed_at=self._completed_at or datetime.now(),
            navigation_path=self._navigation_path,
            events=self._events,
            total_steps=len(self._navigation_path),
            unknown_nodes=self._unknown_nodes,
        )
        if self._navigation_path:
            confidences = [s.confidence for s in self._navigation_path]
            flow.avg_confidence = sum(confidences) / len(confidences)
            flow.total_duration = sum(s.duration_seconds for s in self._navigation_path)
        if self._flow_exporter:
            self._flow_exporter(flow)
        return flow

    def _record_event(self, event_type: EventType, data: dict | None = None):
        self._events.append(InteractionEvent(event_type=event_type, data=data or {}))

    def __repr__(self):
        return f"NavigationSession(id={self.session_id}, status={self._status.value}, steps={len(self._navigation_path)})"
