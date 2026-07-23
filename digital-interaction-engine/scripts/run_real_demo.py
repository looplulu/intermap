#!/usr/bin/env python3
"""
Real Recording Demo: Run Navigation Session against REAL video frames with PaddleOCR.

Usage:
    python scripts/run_real_demo.py --frames-dir data/processed/taobao_refund_1/frames/ --app taobao --task refund

This script:
1. Uses PaddleOCR to extract text from each frame
2. Matches against Golden Flow
3. Falls back to DeepSeek LLM for unknown pages
4. Outputs navigation guidance with risk alerts
5. Saves Interaction Flow JSON
"""

import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.session.session import NavigationSession
from core.session.event import InteractionFlow
from core.hd_map.map import HDMap
from core.vision.ocr import extract_text_from_image
from core.vision.llm_client import DeepSeekClient
from core.learning.flow_generator import export_learned_flow


def main():
    parser = argparse.ArgumentParser(description="Real Recording Navigation Demo")
    parser.add_argument("--frames-dir", required=True, help="Directory with frame images")
    parser.add_argument("--app", default="taobao", choices=["taobao", "jd"])
    parser.add_argument("--task", default="refund")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip OCR, use simulated data")
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    app = args.app
    task = args.task

    if not frames_dir.exists():
        print(f"Error: frames directory not found: {frames_dir}")
        sys.exit(1)

    # Collect frame images
    frame_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    print(f"[Demo] Found {len(frame_files)} frames in {frames_dir}")

    # Load HD Map
    hd_map = HDMap()
    print(f"[Demo] Loaded flows: {hd_map.list_flows()}")

    # Init LLM
    llm_client = DeepSeekClient()

    # ── OCR: Extract text from all frames ──
    frame_texts: list[list[str]] = []
    if args.skip_ocr:
        # Fallback: use empty lists (will trigger LLM for every frame)
        frame_texts = [[] for _ in frame_files]
        print("[Demo] Skipping OCR (using empty data)")
    else:
        print(f"\n[OCR] 开始提取文字...")
        for i, frame_path in enumerate(frame_files):
            texts = extract_text_from_image(frame_path, min_confidence=0.5)
            frame_texts.append(texts)
            text_preview = " | ".join(texts[:5])
            if len(texts) > 5:
                text_preview += f" ... (+{len(texts)-5} more)"
            print(f"  [{i+1:3d}/{len(frame_files)}] {frame_path.name}: {len(texts)} 条文字 - {text_preview}")
        print(f"[OCR] 完成，共处理 {len(frame_files)} 帧")

    # ── Build providers ──

    frame_index = [0]

    def screen_provider():
        if frame_index[0] >= len(frame_texts):
            return None
        data = frame_texts[frame_index[0]]
        frame_index[0] += 1
        return {"texts": data, "app": app, "source": "ocr"}

    def vision_provider(screen):
        return {
            "texts": screen.get("texts", []),
            "app": screen.get("app", "unknown"),
            "page_type": "ocr",
        }

    def node_matcher(vision_result, app_hint, task_hint):
        texts = vision_result.get("texts", [])
        detected_app = vision_result.get("app", app_hint)
        node_id, confidence, _ = hd_map.match_node(texts, detected_app, task_hint)
        return node_id, confidence

    def guidance_handler(guidance, risk_alerts):
        risk_str = ""
        if risk_alerts:
            risk_str = f" ⚠️ {'; '.join(risk_alerts)}"
        print(f"  🔊 {guidance}{risk_str}")

    def flow_exporter(flow: InteractionFlow):
        output_path = args.output or str(
            Path(project_root) / "data" / "interaction_logs" /
            f"{flow.session_id}_{flow.app}_{flow.task}_real.json"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(flow.to_json())
        print(f"\n[Demo] Interaction Flow saved to: {output_path}")
        learned_path = export_learned_flow(flow)
        print(f"[Demo] Learned Flow candidate saved to: {learned_path}")

    # ── Run Session ──

    session = NavigationSession(
        screen_provider=screen_provider,
        vision_provider=vision_provider,
        node_matcher=node_matcher,
        guidance_handler=guidance_handler,
        flow_exporter=flow_exporter,
        hd_map=hd_map,
        llm_client=llm_client,
    )

    print(f"\n{'='*60}")
    print(f"  Digital Interaction Engine - Real Recording Demo")
    print(f"  App: {app} | Task: {task} | Frames: {len(frame_files)}")
    print(f"{'='*60}")
    print(f"\n👤 用户: 我要{task}")

    session.start(f"我要{task}")
    session._app = app

    print(f"\n🚀 开始导航...\n")
    flow = session.run()

    # Results
    print(f"\n{'='*60}")
    print(f"  导航完成")
    print(f"{'='*60}")
    print(f"  Session ID: {flow.session_id}")
    print(f"  总步数: {flow.total_steps}")
    print(f"  平均置信度: {flow.avg_confidence:.0%}")
    print(f"  未知节点: {len(flow.unknown_nodes)}")
    print(f"  地图匹配: {flow.total_steps - len(flow.unknown_nodes)} 步")
    if flow.unknown_nodes:
        print(f"  LLM推理: {len(flow.unknown_nodes)} 步")
    print(f"\n  导航路径:")
    for i, step in enumerate(flow.navigation_path):
        source = "地图" if not step.node_id.startswith("llm_") else "LLM"
        print(f"    {i+1}. [{source}] {step.node_id} ({step.confidence:.0%}) - {step.guidance[:40]}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
