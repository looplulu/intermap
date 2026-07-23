#!/usr/bin/env python3
"""
Generate complete guidance script from recorded frames.

Supports multiple tasks from the same recording:
  --task refund    -> "我要退款"
  --task find_order -> "查订单"
  --task contact_customer_service -> "联系客服"

Usage:
    python3 scripts/generate_guidance.py --frames-dir data/processed/taobao_refund_1/frames/ --app taobao --task refund
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.hd_map.map import HDMap
from core.session.page_change import PageChangeDetector
from core.vision.ocr import extract_text_with_position
from core.vision.position import PositionGuider
from core.vision.llm_client import DeepSeekClient


def generate_guidance(frames_dir, app, task, interval=1.0):
    frames_dir = Path(frames_dir)
    frame_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))

    hd_map = HDMap()
    llm_client = DeepSeekClient()
    detector = PageChangeDetector(text_change_threshold=0.25)

    script = {
        "app": app,
        "task": task,
        "generated_at": datetime.now().isoformat(),
        "total_frames": len(frame_files),
        "interval_seconds": interval,
        "steps": [],
    }

    cumulative_time = 0.0
    prev_node_id = None

    for i, frame_path in enumerate(frame_files):
        frame_num = i + 1
        cumulative_time += interval

        # OCR with position
        ocr_items, img_size = extract_text_with_position(frame_path, min_confidence=0.5)
        texts = [item.text for item in ocr_items]

        # Page change detection
        snapshot = detector.snapshot(texts=texts)
        page_changed = detector.has_changed(snapshot)
        detector.update(snapshot)

        # Node matching
        node_id, confidence, node_data = hd_map.match_node(texts, app, task)

        # Determine guidance
        guidance = ""
        source = "none"
        risks = []
        page_type = "unknown"

        if node_id:
            guidance, risks = hd_map.get_guidance(node_id, app, task)
            source = "golden_flow"
            if node_data:
                page_type = node_data.get("page_type", "unknown")
            # Add position info
            if ocr_items and img_size[0] > 0:
                guider = PositionGuider(img_size[0], img_size[1])
                import re
                quotes = re.findall(r"['\"](.+?)['\"]", guidance)
                if quotes:
                    enhanced = guider.add_position_to_guidance(guidance, ocr_items, quotes)
                    if enhanced != guidance:
                        guidance = enhanced
        elif texts:
            llm_result = llm_client.understand_page(texts, task, app)
            if llm_result.confidence >= 0.3:
                guidance = llm_result.guidance_text
                node_id = f"llm_{llm_result.page_type}"
                confidence = llm_result.confidence
                source = "llm"
                page_type = llm_result.page_type

        # Detect transitions
        is_transition = False
        if node_id and node_id != prev_node_id:
            is_transition = True

        if is_transition and guidance:
            step = {
                "step": len(script["steps"]) + 1,
                "time_seconds": round(cumulative_time, 1),
                "frame": frame_path.name,
                "frame_num": frame_num,
                "node_id": node_id,
                "page_type": page_type,
                "source": source,
                "confidence": round(confidence, 2) if confidence else 0,
                "is_transition": is_transition,
                "prev_node": prev_node_id,
                "guidance": guidance,
                "risks": risks,
                "ocr_texts_count": len(texts),
            }
            script["steps"].append(step)

            arrow = "→" if is_transition else "·"
            print(f"  [{arrow}] {step['step']:2d}. @{step['time_seconds']:5.1f}s "
                  f"[{source:10s}] {node_id:30s} ({confidence:.0%})")
            print(f"       🔊 {guidance}")
            if risks:
                print(f"       ⚠️  {risks[0]}")

        prev_node_id = node_id

    return script


def main():
    parser = argparse.ArgumentParser(description="Generate guidance script from recording")
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--app", default="taobao")
    parser.add_argument("--task", default="refund")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    print(f"[Guide] App={args.app}, Task={args.task}, Frames dir={args.frames_dir}")

    script = generate_guidance(args.frames_dir, args.app, args.task, args.interval)

    output_path = str(
        project_root / "data" / "guidance_scripts" /
        f"{args.app}_{args.task}_guidance.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    print(f"\n[Guide] 共 {len(script['steps'])} 步引导")
    print(f"[Guide] 已保存: {output_path}")


if __name__ == "__main__":
    main()
