#!/usr/bin/env python3
"""
Live Demo: Real-time navigation using Mac screen capture of iPhone Mirroring.

Usage:
    python scripts/run_live_demo.py --app taobao --task refund

This script:
1. Captures a region of the Mac screen (where iPhone Mirroring is displayed)
2. Runs OCR on each capture
3. Matches against Golden Flow
4. Speaks guidance using Mac's built-in TTS (say command)

Press Ctrl+C to stop.
"""

import sys
import argparse
import time
import subprocess
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.session.session import NavigationSession
from core.session.event import InteractionFlow
from core.hd_map.map import HDMap
from core.vision.ocr import extract_text_from_image
from core.vision.llm_client import DeepSeekClient


def get_iphone_mirror_region() -> tuple[int, int, int, int]:
    """Get the screen region of iPhone Mirroring window.
    
    Returns (left, top, width, height) or None if not found.
    """
    # Try AppleScript first (may fail due to permissions)
    try:
        script = '''
        tell application "System Events"
            tell process "iPhone Mirroring"
                set w to first window
                set p to position of w
                set s to size of w
                return (item 1 of p) & "," & (item 2 of p) & "," & (item 1 of s) & "," & (item 2 of s)
            end tell
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except Exception:
        pass

    # Fallback: use screencapture to find dark rectangular region
    # iPhone Mirroring window has a distinct black border
    return None


def capture_screen_region(left: int, top: int, width: int, height: int, output_path: str) -> bool:
    """Capture a region of the screen using macOS screencapture."""
    try:
        subprocess.run(
            ["screencapture", "-R", f"{left},{top},{width},{height}", output_path],
            check=True, capture_output=True, timeout=5
        )
        return True
    except Exception as e:
        print(f"  [Capture Error] {e}")
        return False


def speak(text: str) -> None:
    """Use Mac's say command for voice output."""
    # Remove emojis and special chars that may confuse TTS
    clean = text.replace("🔊", "").replace("⚠️", "").strip()
    if clean:
        try:
            subprocess.Popen(
                ["say", "-v", "Ting-Ting", clean],  # Chinese voice
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Live Navigation Demo")
    parser.add_argument("--app", default="taobao", choices=["taobao", "jd"])
    parser.add_argument("--task", default="refund")
    parser.add_argument("--region", help="Screen region: left,top,width,height")
    parser.add_argument("--interval", type=float, default=2.0, help="Capture interval in seconds")
    parser.add_argument("--no-voice", action="store_true", help="Disable voice output")
    args = parser.parse_args()

    app = args.app
    task = args.task

    # ── Determine capture region ──
    region = None
    if args.region:
        parts = args.region.split(",")
        region = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    else:
        region = get_iphone_mirror_region()

    if region is None:
        print("无法自动检测 iPhone 镜像窗口位置。")
        print("请手动指定区域，例如：--region 100,200,400,800")
        print("或者先打开 iPhone 镜像，确保窗口可见。")
        sys.exit(1)

    left, top, width, height = region
    print(f"[Live] 截取区域: ({left}, {top}) {width}x{height}")

    # ── Load map & LLM ──
    hd_map = HDMap()
    llm_client = DeepSeekClient()

    # ── Setup session ──
    temp_dir = Path(tempfile.gettempdir()) / "die_live"
    temp_dir.mkdir(exist_ok=True)
    capture_path = str(temp_dir / "capture.png")

    # Frame provider: captures screen region
    def screen_provider():
        if capture_screen_region(left, top, width, height, capture_path):
            return {"image_path": capture_path, "source": "live"}
        return None

    # Vision provider: OCR on captured image
    def vision_provider(screen):
        img_path = screen.get("image_path", "") if isinstance(screen, dict) else screen
        texts = extract_text_from_image(img_path, min_confidence=0.5)
        return {
            "texts": texts,
            "app": app,
            "page_type": "live",
        }

    # Node matcher
    def node_matcher(vision_result, app_hint, task_hint):
        texts = vision_result.get("texts", [])
        node_id, confidence, _ = hd_map.match_node(texts, app_hint, task_hint)
        return node_id, confidence

    # Guidance handler with voice
    last_guidance = ""
    def guidance_handler(guidance, risk_alerts):
        nonlocal last_guidance
        # Skip if same guidance as last time
        if guidance == last_guidance:
            return
        last_guidance = guidance

        risk_str = ""
        if risk_alerts:
            risk_str = f" ⚠️ {'; '.join(risk_alerts)}"
        print(f"\n  🔊 {guidance}{risk_str}")
        if not args.no_voice:
            speak(guidance)
            if risk_alerts:
                speak("注意：" + "；".join(risk_alerts))

    # Flow exporter
    def flow_exporter(flow: InteractionFlow):
        output_path = str(
            project_root / "data" / "interaction_logs" /
            f"{flow.session_id}_{flow.app}_{flow.task}_live.json"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(flow.to_json())
        print(f"\n[Live] Interaction Flow saved: {output_path}")

    session = NavigationSession(
        screen_provider=screen_provider,
        vision_provider=vision_provider,
        node_matcher=node_matcher,
        guidance_handler=guidance_handler,
        flow_exporter=flow_exporter,
        hd_map=hd_map,
        llm_client=llm_client,
    )

    # ── Start ──
    print(f"\n{'='*60}")
    print(f"  Digital Interaction Engine - LIVE Demo")
    print(f"  App: {app} | Task: {task}")
    print(f"  Capture interval: {args.interval}s")
    print(f"  Voice: {'ON' if not args.no_voice else 'OFF'}")
    print(f"{'='*60}")
    print(f"\n👤 用户: 我要{task}")
    print(f"\n🚀 实时导航开始... (按 Ctrl+C 停止)\n")

    session.start(f"我要{task}")
    session._app = app

    # ── Live loop ──
    try:
        # Manually run the navigation loop with live capture
        session._status = __import__("core.session.state", fromlist=["SessionStatus"]).SessionStatus.NAVIGATING
        from core.session.page_change import PageChangeDetector
        detector = PageChangeDetector(text_change_threshold=0.25)

        step_count = 0
        while True:
            time.sleep(args.interval)

            # Capture
            screen = screen_provider()
            if screen is None:
                continue

            # OCR
            vision_result = vision_provider(screen)
            texts = vision_result.get("texts", [])

            # Page change detection
            snapshot = detector.snapshot(texts=texts)
            if not detector.has_changed(snapshot):
                continue
            detector.update(snapshot)

            # Locate
            node_id, confidence, _ = hd_map.match_node(texts, app, task)

            if node_id is None:
                # LLM fallback
                if llm_client and texts:
                    llm_result = llm_client.understand_page(texts, task, app)
                    if llm_result.confidence >= 0.3:
                        guidance_handler(llm_result.guidance_text, [])
                        step_count += 1
                continue

            # Navigate
            guidance, risks = hd_map.get_guidance(node_id, app, task)
            if guidance:
                guidance_handler(guidance, risks)
                step_count += 1

            # Check end
            if hd_map.is_end_node(node_id, app, task):
                print(f"\n✅ 任务完成！共 {step_count} 步")
                speak("任务已完成")
                break

    except KeyboardInterrupt:
        print(f"\n\n⏹ 用户停止")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    # Complete
    session._complete()
    flow = session._build_flow()
    print(f"\n{'='*60}")
    print(f"  导航结束")
    print(f"{'='*60}")
    print(f"  总步数: {flow.total_steps}")
    print(f"  平均置信度: {flow.avg_confidence:.0%}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
