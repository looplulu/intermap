#!/usr/bin/env python3
"""
Live Navigation - 独立运行版本
在终端中直接运行，不依赖 TRAE 沙盒。

使用方法：
1. 先安装依赖：
   pip3 install paddlepaddle paddleocr requests pydantic --break-system-packages

2. 打开 iPhone 镜像，确认窗口在 Mac 屏幕上可见

3. 运行（首次需要等 OCR 模型下载）：
   python3 run_live.py --app taobao --task refund --region 左上角x,左上角y,宽,高

4. 在手机上操作，系统会自动识别并语音引导

按 Ctrl+C 停止。

获取坐标方法：
- 按 Cmd+Shift+4（不按下去），鼠标移到 iPhone 镜像窗口左上角和右下角
- 左上角坐标记为 (left, top)
- 右下角坐标记为 (right, bottom)  
- 宽 = right - left, 高 = bottom - top
"""

import sys
import os
import time
import argparse
import subprocess
import tempfile
from pathlib import Path

# Add project root to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# ── Imports ──
from core.session.state import recognize_task
from core.session.event import InteractionEvent, NavigationStep, InteractionFlow
from core.hd_map.map import HDMap
from core.session.page_change import PageChangeDetector
from core.vision.ocr import extract_text_from_image
from core.vision.llm_client import DeepSeekClient


def speak(text: str, voice: str = "Ting-Ting") -> None:
    """Mac say command for voice output."""
    clean = text.replace("'", "").replace('"', "").replace('"', "").replace('"', "").strip()
    if clean:
        subprocess.Popen(
            ["say", "-v", voice, clean],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def capture_and_crop(full_capture_path: str, region: tuple, crop_path: str) -> bool:
    """Capture full screen, then crop to region.
    
    Args:
        full_capture_path: Path to save full screenshot
        region: (left, top, width, height) in logical pixels
        crop_path: Path to save cropped image
    """
    # Capture full screen (silent)
    r = subprocess.run(
        ["screencapture", "-x", full_capture_path],
        capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
        return False

    # Use sips to crop (handles Retina scaling automatically)
    # sips -c uses center crop, -g uses extract by pixel coordinates
    # We need to first get actual pixel dimensions
    left, top, width, height = region
    
    # Get actual pixel resolution
    r = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", full_capture_path],
        capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
        return False
    
    lines = r.stdout.strip().split("\n")
    pix_w = int(lines[1].split(":")[1].strip())
    pix_h = int(lines[2].split(":")[1].strip())
    
    # Calculate scale factor (Retina)
    # macOS logical resolution
    log_w = pix_w / 2 if pix_w > 2000 else pix_w
    scale = pix_w / log_w
    
    # Convert logical coords to pixel coords
    px_left = int(left * scale)
    px_top = int(top * scale)
    px_width = int(width * scale)
    px_height = int(height * scale)
    
    # Ensure within bounds
    px_left = min(px_left, pix_w - px_width)
    px_top = min(px_top, pix_h - px_height)
    px_left = max(px_left, 0)
    px_top = max(px_top, 0)
    
    # Crop using sips (pixel coordinates)
    r = subprocess.run(
        ["sips", "-c", str(px_height), str(px_width), 
         "-s", "cropOffset", f"{px_left} {px_top}",
         "--out", crop_path, full_capture_path],
        capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
        # Fallback: use PIL
        try:
            from PIL import Image
            img = Image.open(full_capture_path)
            crop = img.crop((px_left, px_top, px_left + px_width, px_top + px_height))
            crop.save(crop_path)
            return True
        except Exception:
            return False
    
    return os.path.exists(crop_path)


def main():
    parser = argparse.ArgumentParser(
        description="Digital Interaction Engine - Live Navigation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run_live.py --app taobao --task refund --region 1856,184,652,1440
  python3 run_live.py --app jd --task refund --region 100,50,400,800 --no-voice
  python3 run_live.py --app taobao --task refund --region 1856,184,652,1440 --interval 3
        """,
    )
    parser.add_argument("--app", default="taobao", choices=["taobao", "jd"])
    parser.add_argument("--task", default="refund")
    parser.add_argument("--region", required=True, help="iPhone Mirroring 窗口区域: left,top,width,height (逻辑像素)")
    parser.add_argument("--interval", type=float, default=2.0, help="截屏间隔秒数 (默认2)")
    parser.add_argument("--no-voice", action="store_true", help="关闭语音输出")
    parser.add_argument("--output", default=None, help="Interaction Flow 输出文件路径")
    args = parser.parse_args()

    # Parse region
    parts = args.region.split(",")
    region = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    left, top, width, height = region

    print(f"""
{'='*60}
  Digital Interaction Engine - Live Navigation
{'='*60}
  App: {args.app}
  Task: {args.task}
  区域: ({left}, {top}) {width}x{height}
  间隔: {args.interval}s
  语音: {'开启' if not args.no_voice else '关闭'}
{'='*60}
""")

    # ── Init ──
    print("[初始化] 加载高精交互地图...")
    hd_map = HDMap()
    print(f"  已加载 Flow: {hd_map.list_flows()}")

    print("[初始化] 连接 DeepSeek LLM...")
    llm_client = DeepSeekClient()

    print("[初始化] 准备 OCR 引擎 (首次运行需下载模型)...")
    from core.vision.ocr import extract_text_from_image
    # Warm up OCR
    print("  OCR 引擎就绪")

    # Temp files
    tmp = Path(tempfile.gettempdir()) / "die_live"
    tmp.mkdir(exist_ok=True)
    full_path = str(tmp / "full.png")
    crop_path = str(tmp / "crop.png")

    # Page change detector
    detector = PageChangeDetector(text_change_threshold=0.25)

    # Events tracking
    events: list[InteractionEvent] = []
    navigation_path: list[NavigationStep] = []
    session_id = os.urandom(4).hex()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    step_count = 0
    current_node = None
    last_guidance_text = ""

    # ── Live Loop ──
    print(f"\n👤 用户: 我要{args.task}")
    print(f"\n🚀 实时导航开始... (按 Ctrl+C 停止)\n")

    try:
        while True:
            time.sleep(args.interval)

            # 1. CAPTURE
            if not capture_and_crop(full_path, region, crop_path):
                print("  [!] 截屏失败，跳过")
                continue

            # 2. OCR
            texts = extract_text_from_image(crop_path, min_confidence=0.5)

            # 3. PAGE CHANGE DETECTION
            snapshot = detector.snapshot(texts=texts)
            if not detector.has_changed(snapshot):
                continue
            detector.update(snapshot)

            text_preview = " | ".join(texts[:5])
            if len(texts) > 5:
                text_preview += f" ... (+{len(texts)-5})"
            print(f"  [OCR] {len(texts)} 条文字: {text_preview}")

            # 4. LOCATE - Golden Flow match
            node_id, confidence, node_data = hd_map.match_node(texts, args.app, args.task)

            if node_id is None:
                # 5. LLM FALLBACK
                if llm_client and texts:
                    llm_result = llm_client.understand_page(texts, args.task, args.app)
                    if llm_result.confidence >= 0.3:
                        guidance = llm_result.guidance_text
                        source = "LLM"
                        node_id = f"llm_{llm_result.page_type}"
                        confidence = llm_result.confidence
                    else:
                        continue
                else:
                    continue
            else:
                # Get guidance from Golden Flow
                guidance, risks = hd_map.get_guidance(node_id, args.app, args.task)
                source = "地图"
                confidence = confidence

            # Skip if same guidance
            if guidance == last_guidance_text:
                continue
            last_guidance_text = guidance

            # 6. NAVIGATE - output guidance
            risk_alerts = []
            if node_data:
                risk_alerts = [r.get("description", "") for r in node_data.get("risks", [])]

            risk_str = ""
            if risk_alerts:
                risk_str = f" ⚠️ {'; '.join(risk_alerts)}"

            print(f"\n  🔊 [{source}] ({confidence:.0%}) {guidance}{risk_str}")

            if not args.no_voice:
                speak(guidance)
                if risk_alerts:
                    time.sleep(0.5)
                    speak("注意：" + "；".join(risk_alerts[:1]))

            # 7. LEARN - record step
            step = NavigationStep(
                node_id=node_id,
                page_type=node_data.get("page_type", "unknown") if node_data else "unknown",
                guidance=guidance,
                confidence=confidence,
                risk_alerts=risk_alerts,
            )
            navigation_path.append(step)
            step_count += 1

            # Node transition
            if current_node and current_node != node_id:
                events.append(InteractionEvent(
                    event_type="node_transition",
                    data={"from": current_node, "to": node_id},
                ))
            current_node = node_id

            # 8. CHECK END
            if node_data and node_data.get("is_end"):
                print(f"\n✅ 任务完成！共 {step_count} 步")
                if not args.no_voice:
                    speak("任务已完成")
                break

    except KeyboardInterrupt:
        print(f"\n\n⏹ 用户停止导航")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    # ── Save Flow ──
    completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    flow = InteractionFlow(
        task=args.task,
        app=args.app,
        session_id=session_id,
        started_at=__import__("datetime").datetime.now(),
        completed_at=__import__("datetime").datetime.now(),
        navigation_path=navigation_path,
        events=events,
        total_steps=len(navigation_path),
    )
    if navigation_path:
        flow.avg_confidence = sum(s.confidence for s in navigation_path) / len(navigation_path)

    # Save
    output_path = args.output or str(
        SCRIPT_DIR / "data" / "interaction_logs" /
        f"{session_id}_{args.app}_{args.task}_live.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(flow.to_json())

    print(f"\n{'='*60}")
    print(f"  导航结束")
    print(f"{'='*60}")
    print(f"  步数: {flow.total_steps}")
    print(f"  平均置信度: {flow.avg_confidence:.0%}")
    print(f"  Flow 已保存: {output_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
