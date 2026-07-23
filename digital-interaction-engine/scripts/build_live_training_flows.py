#!/usr/bin/env python3
"""Build reviewable Golden Flow candidates from live web training sessions."""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_DIR = PROJECT_ROOT / "data" / "live_training" / "captured_sessions"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "live_training" / "review_queue"


def redact_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[email]", text, flags=re.I)
    text = re.sub(r"1[3-9]\d{9}", "[phone]", text)
    text = re.sub(r"\b\d{8,}\b", "[number]", text)
    return text


def read_jsonl(path: Path) -> List[dict]:
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def text_counter(items: List[dict], limit: int = 40) -> List[dict]:
    counter: Counter[str] = Counter()
    for item in items or []:
        text = item.get("text") if isinstance(item, dict) else None
        if text:
            counter[redact_text(text)] += 1
    return [{"text": text, "count": count} for text, count in counter.most_common(limit)]


def build_session_candidate(events: List[dict]) -> dict:
    if not events:
        return {}

    first = events[0]
    session_id = first.get("session_id", "unknown")
    app = first.get("app", "")
    task = first.get("task", "")

    nodes: Dict[str, dict] = {}
    transitions: Counter = Counter()
    transition_details: Dict[Tuple[str, str], dict] = {}
    unresolved = []
    manual_annotations = []
    cursor_observations = []
    ocr_event_count = 0
    frame_count = 0

    for event in events:
        payload = event.get("payload") or {}
        event_type = event.get("event_type")
        frame_count = max(frame_count, int(event.get("frame_seq") or 0))

        if event_type == "ocr_observed":
            ocr_event_count += 1

        if event_type == "cursor_observed":
            hint = payload.get("cursor_hint") or {}
            target = payload.get("cursor_target") or {}
            if isinstance(hint, dict):
                cursor_observations.append(
                    {
                        "frame_seq": event.get("frame_seq"),
                        "timestamp": event.get("timestamp"),
                        "node_id": payload.get("node_id", ""),
                        "page_signature": payload.get("page_signature", ""),
                        "x_norm": hint.get("x_norm"),
                        "y_norm": hint.get("y_norm"),
                        "box_norm": hint.get("box_norm"),
                        "confidence": hint.get("confidence", 0),
                        "method": hint.get("method", ""),
                        "target": {
                            "matched_text": redact_text(target.get("matched_text", "")),
                            "relation": target.get("relation", ""),
                            "candidates": [
                                {
                                    **candidate,
                                    "text": redact_text(candidate.get("text", "")),
                                }
                                for candidate in (target.get("candidates") or [])[:8]
                                if isinstance(candidate, dict)
                            ],
                            "evidence": target.get("evidence", ""),
                        } if isinstance(target, dict) else None,
                    }
                )

        if event_type == "node_located":
            node_id = payload.get("node_id")
            if not node_id:
                continue
            node = nodes.setdefault(
                node_id,
                {
                    "node_id": node_id,
                    "node_names": Counter(),
                    "page_signatures": Counter(),
                    "confidences": [],
                    "layout_items": [],
                    "guidance_samples": Counter(),
                    "observations": 0,
                },
            )
            node["observations"] += 1
            if payload.get("node_name"):
                node["node_names"][payload["node_name"]] += 1
            if payload.get("page_signature"):
                node["page_signatures"][payload["page_signature"]] += 1
            if isinstance(payload.get("confidence"), (int, float)):
                node["confidences"].append(payload["confidence"])
            if payload.get("guidance"):
                node["guidance_samples"][payload["guidance"]] += 1
            node["layout_items"].extend(payload.get("layout_items") or [])

        elif event_type == "node_transition":
            src = payload.get("from_node_id")
            dst = payload.get("to_node_id")
            if not src or not dst:
                continue
            key = (src, dst)
            transitions[key] += 1
            detail = transition_details.setdefault(
                key,
                {
                    "from": src,
                    "to": dst,
                    "count": 0,
                    "durations": [],
                    "inferred_actions": Counter(),
                    "target_candidates": [],
                    "before_signatures": Counter(),
                    "after_signatures": Counter(),
                },
            )
            detail["count"] += 1
            if isinstance(payload.get("duration_s"), (int, float)):
                detail["durations"].append(payload["duration_s"])
            if payload.get("inferred_action"):
                detail["inferred_actions"][payload["inferred_action"]] += 1
            if payload.get("before_page_signature"):
                detail["before_signatures"][payload["before_page_signature"]] += 1
            if payload.get("after_page_signature"):
                detail["after_signatures"][payload["after_page_signature"]] += 1
            detail["target_candidates"].extend(payload.get("inferred_target_candidates") or [])
            if payload.get("before_cursor_hint"):
                detail.setdefault("cursor_hints", []).append(payload.get("before_cursor_hint"))
            if payload.get("after_cursor_hint"):
                detail.setdefault("cursor_hints", []).append(payload.get("after_cursor_hint"))
            if payload.get("before_cursor_target"):
                detail.setdefault("cursor_targets", []).append(payload.get("before_cursor_target"))
            if payload.get("after_cursor_target"):
                detail.setdefault("cursor_targets", []).append(payload.get("after_cursor_target"))

        elif event_type == "node_unresolved":
            unresolved.append(
                {
                    "frame_seq": event.get("frame_seq"),
                    "page_signature": payload.get("page_signature", ""),
                    "reason": payload.get("reason", ""),
                    "sample_texts": [redact_text(text) for text in (payload.get("sample_texts") or [])[:20]],
                    "layout_labels": text_counter(payload.get("layout_items") or [], limit=20),
                }
            )

        elif event_type == "manual_annotation":
            manual_annotations.append(
                {
                    "frame_seq": event.get("frame_seq"),
                    "timestamp": event.get("timestamp"),
                    "annotation_id": payload.get("annotation_id", ""),
                    "annotation_timing": payload.get("annotation_timing", ""),
                    "node_id": payload.get("node_id", ""),
                    "page_signature": payload.get("page_signature", ""),
                    "action_text": redact_text(payload.get("action_text", "")),
                    "target_text": redact_text(payload.get("target_text", "")),
                    "target_type": payload.get("target_type", ""),
                    "note": redact_text(payload.get("note", "")),
                    "position": payload.get("position") or None,
                    "node_path": [redact_text(item) for item in (payload.get("node_path") or [])[:12]],
                    "ocr_texts": [redact_text(text) for text in (payload.get("ocr_texts") or [])[:40]],
                    "layout_labels": text_counter(payload.get("layout_items") or [], limit=30),
                }
            )

    candidate_nodes = []
    for node in nodes.values():
        confidences = node["confidences"]
        candidate_nodes.append(
            {
                "node_id": node["node_id"],
                "name": node["node_names"].most_common(1)[0][0]
                if node["node_names"]
                else node["node_id"],
                "observations": node["observations"],
                "avg_confidence": round(mean(confidences), 3) if confidences else 0,
                "page_signatures": [
                    {"signature": sig, "count": count}
                    for sig, count in node["page_signatures"].most_common(8)
                ],
                "key_text_candidates": text_counter(node["layout_items"], limit=30),
                "guidance_samples": [
                    {"text": redact_text(text), "count": count}
                    for text, count in node["guidance_samples"].most_common(5)
                ],
            }
        )

    candidate_transitions = []
    for detail in transition_details.values():
        durations = detail["durations"]
        candidate_transitions.append(
            {
                "from": detail["from"],
                "to": detail["to"],
                "count": detail["count"],
                "avg_duration_s": round(mean(durations), 2) if durations else 0,
                "inferred_actions": [
                    {"text": redact_text(text), "count": count}
                    for text, count in detail["inferred_actions"].most_common(5)
                ],
                "target_text_candidates": text_counter(detail["target_candidates"], limit=20),
                "cursor_hints": (detail.get("cursor_hints") or [])[:10],
                "cursor_targets": [
                    {
                        "matched_text": redact_text(target.get("matched_text", "")),
                        "relation": target.get("relation", ""),
                        "candidates": [
                            {
                                **candidate,
                                "text": redact_text(candidate.get("text", "")),
                            }
                            for candidate in (target.get("candidates") or [])[:5]
                            if isinstance(candidate, dict)
                        ],
                    }
                    for target in (detail.get("cursor_targets") or [])[:10]
                    if isinstance(target, dict)
                ],
                "before_signatures": [
                    {"signature": sig, "count": count}
                    for sig, count in detail["before_signatures"].most_common(5)
                ],
                "after_signatures": [
                    {"signature": sig, "count": count}
                    for sig, count in detail["after_signatures"].most_common(5)
                ],
            }
        )

    return {
        "candidate_id": f"{session_id}_{app}_{task}",
        "source": "live_web_training",
        "status": "pending_review",
        "generated_at": datetime.now().isoformat(),
        "session_id": session_id,
        "app": app,
        "task": task,
        "quality": {
            "events": len(events),
            "frames": frame_count,
            "ocr_events": ocr_event_count,
            "located_nodes": len(candidate_nodes),
            "transitions": sum(transitions.values()),
            "unresolved_pages": len(unresolved),
            "manual_annotations": len(manual_annotations),
            "cursor_observations": len(cursor_observations),
        },
        "nodes": sorted(candidate_nodes, key=lambda n: n["node_id"]),
        "transitions": sorted(
            candidate_transitions,
            key=lambda edge: (-edge["count"], edge["from"], edge["to"]),
        ),
        "manual_annotations": manual_annotations[:200],
        "cursor_observations": cursor_observations[:200],
        "unresolved_pages": unresolved[:100],
    }


def build_aggregate(candidates: List[dict]) -> List[dict]:
    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for candidate in candidates:
        if candidate:
            grouped[(candidate.get("app", ""), candidate.get("task", ""))].append(candidate)

    aggregates = []
    for (app, task), group in grouped.items():
        node_counts: Counter[str] = Counter()
        transition_counts: Counter[tuple[str, str]] = Counter()
        unresolved_count = 0
        annotation_count = 0
        cursor_count = 0
        for candidate in group:
            for node in candidate.get("nodes", []):
                node_counts[node["node_id"]] += node.get("observations", 0)
            for edge in candidate.get("transitions", []):
                transition_counts[(edge["from"], edge["to"])] += edge.get("count", 0)
            unresolved_count += len(candidate.get("unresolved_pages", []))
            annotation_count += len(candidate.get("manual_annotations", []))
            cursor_count += len(candidate.get("cursor_observations", []))

        aggregates.append(
            {
                "candidate_id": f"{app}_{task}_aggregate",
                "source": "live_web_training",
                "status": "pending_review",
                "generated_at": datetime.now().isoformat(),
                "app": app,
                "task": task,
                "session_count": len(group),
                "nodes": [
                    {"node_id": node_id, "observations": count}
                    for node_id, count in node_counts.most_common()
                ],
                "transitions": [
                    {"from": src, "to": dst, "count": count}
                    for (src, dst), count in transition_counts.most_common()
                ],
                "unresolved_pages": unresolved_count,
                "manual_annotations": annotation_count,
                "cursor_observations": cursor_count,
                "source_sessions": [c["session_id"] for c in group],
            }
        )
    return aggregates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session_files = sorted(args.sessions_dir.glob("*/events.jsonl"))
    candidates = []

    for events_path in session_files:
        events = read_jsonl(events_path)
        candidate = build_session_candidate(events)
        if not candidate:
            continue
        out_path = args.output_dir / f"{candidate['candidate_id']}.json"
        out_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
        candidates.append(candidate)
        print(f"wrote {out_path}")

    for aggregate in build_aggregate(candidates):
        out_path = args.output_dir / f"{aggregate['candidate_id']}.json"
        out_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out_path}")

    print(f"processed {len(candidates)} live training sessions")


if __name__ == "__main__":
    main()
