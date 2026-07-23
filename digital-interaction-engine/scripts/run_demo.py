#!/usr/bin/env python3
"""
End-to-end Demo: Run Navigation Session against recorded video frames.

Usage:
    python scripts/run_demo.py --app taobao --task refund --frames-dir data/processed/taobao_refund_1/frames/

This script simulates a continuous navigation session by feeding
extracted video frames (as simulated OCR text) through the Session.
"""

import sys
import json
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.session.session import NavigationSession
from core.session.event import InteractionFlow
from core.hd_map.map import HDMap
from core.vision.llm_client import DeepSeekClient
from core.learning.flow_generator import export_learned_flow


# ── Simulated OCR text for each frame (from our earlier analysis) ──
# In production, this would be real PaddleOCR output.
# For demo, we provide the key indicators observed in each frame.

TAOBAO_REFUND_FRAMES = [
    {"texts": ["首页", "推荐", "搜索", "我的淘宝"], "app": "taobao"},
    {"texts": ["首页", "推荐", "搜索", "我的淘宝"], "app": "taobao"},
    {"texts": ["我的订单", "全部", "待付款", "待发货", "待收货"], "app": "taobao"},
    {"texts": ["我的订单", "全部", "待付款", "待发货", "退款/售后"], "app": "taobao"},
    {"texts": ["全部订单", "购物", "搜索订单", "全部", "交易成功"], "app": "taobao"},
    {"texts": ["全部订单", "交易成功", "退款/售后"], "app": "taobao"},
    {"texts": ["交易成功", "已签收", "申请售后", "查看物流", "实付款"], "app": "taobao"},
    {"texts": ["交易成功", "已签收", "申请售后", "7天无理由退换"], "app": "taobao"},
    {"texts": ["选择售后类型", "退货/退款", "换货", "补寄", "下一步"], "app": "taobao"},
    {"texts": ["选择售后原因", "退款", "退货退款", "买贵了", "下一步"], "app": "taobao"},
    {"texts": ["选择售后原因", "买贵了", "协商一致退款", "质量问题", "下一步"], "app": "taobao"},
    {"texts": ["提交", "确认", "退款金额", "退款说明"], "app": "taobao"},
    # LLM fallback test: a page not in golden flow (refund tracking page)
    {"texts": ["退款进度", "退款金额：129.00", "商家已同意", "退款中"], "app": "taobao"},
    {"texts": ["申请成功", "等待商家处理", "退款进度"], "app": "taobao"},
]

JD_REFUND_FRAMES = [
    {"texts": ["首页", "推荐", "搜索", "我的"], "app": "jd"},
    {"texts": ["首页", "推荐", "我的"], "app": "jd"},
    {"texts": ["我的订单", "全部", "待付款", "待收货"], "app": "jd"},
    {"texts": ["全部订单", "购物", "搜索我的订单", "待收货", "退款/售后"], "app": "jd"},
    {"texts": ["全部订单", "交易成功", "退款/售后", "确认收货"], "app": "jd"},
    {"texts": ["订单详情", "已完成", "已签收", "退款/售后", "确认收货"], "app": "jd"},
    {"texts": ["退换/售后", "售后申请", "处理中", "待评价", "申请记录"], "app": "jd"},
    {"texts": ["退换/售后", "退款/售后", "7天价保"], "app": "jd"},
    {"texts": ["选择退款售后商品", "退货", "换货", "价格保护"], "app": "jd"},
    {"texts": ["申请原因", "买多/买错/不想要", "商品质量问题", "确认"], "app": "jd"},
    {"texts": ["提交", "确认", "退款金额"], "app": "jd"},
    # LLM fallback test: refund tracking page not in golden flow
    {"texts": ["退款详情", "退款金额189.00", "原路退回", "预计1-3天到账"], "app": "jd"},
    {"texts": ["申请成功", "等待商家处理"], "app": "jd"},
]


def get_demo_frames(app: str, task: str) -> list[dict]:
    """Get simulated frame data for demo."""
    if app == "taobao" and task == "refund":
        return TAOBAO_REFUND_FRAMES
    elif app == "jd" and task == "refund":
        return JD_REFUND_FRAMES
    else:
        raise ValueError(f"No demo data for app={app}, task={task}")


def main():
    parser = argparse.ArgumentParser(description="Navigation Session Demo")
    parser.add_argument("--app", default="taobao", choices=["taobao", "jd"])
    parser.add_argument("--task", default="refund")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    app = args.app
    task = args.task

    # Load HD Map
    hd_map = HDMap()
    print(f"[Demo] Loaded flows: {hd_map.list_flows()}")

    # Init LLM client
    llm_client = DeepSeekClient()

    # Get demo frames
    frames = get_demo_frames(app, task)
    print(f"[Demo] Simulating {len(frames)} frames for {app}/{task}")

    # ── Build providers for Session ──

    frame_index = [0]  # mutable counter

    def screen_provider():
        """Provide next frame from demo data."""
        if frame_index[0] >= len(frames):
            return None
        frame = frames[frame_index[0]]
        frame_index[0] += 1
        return frame

    def vision_provider(screen):
        """Simulate vision processing (just pass through OCR text)."""
        return {
            "texts": screen.get("texts", []),
            "app": screen.get("app", "unknown"),
            "page_type": "simulated",
        }

    def node_matcher(vision_result, app_hint, task_hint):
        """Match OCR text to golden flow node."""
        texts = vision_result.get("texts", [])
        detected_app = vision_result.get("app", app_hint)
        node_id, confidence, node_data = hd_map.match_node(texts, detected_app, task_hint)
        return node_id, confidence

    def guidance_handler(guidance, risk_alerts):
        """Print guidance to console."""
        risk_str = ""
        if risk_alerts:
            risk_str = f" ⚠️ {'; '.join(risk_alerts)}"
        print(f"  🔊 {guidance}{risk_str}")

    def flow_exporter(flow: InteractionFlow):
        """Export flow to JSON file."""
        output_path = args.output or str(
            Path(project_root) / "data" / "interaction_logs" / 
            f"{flow.session_id}_{flow.app}_{flow.task}_{flow.started_at.strftime('%Y%m%d_%H%M%S')}.json"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(flow.to_json())
        print(f"\n[Demo] Interaction Flow saved to: {output_path}")
        learned_path = export_learned_flow(flow)
        print(f"[Demo] Learned Flow candidate saved to: {learned_path}")

    # ── Create and run Session ──

    session = NavigationSession(
        screen_provider=screen_provider,
        vision_provider=vision_provider,
        node_matcher=node_matcher,
        guidance_handler=guidance_handler,
        flow_exporter=flow_exporter,
        hd_map=hd_map,
        llm_client=llm_client,
    )

    # Start
    user_input = "我要退款"
    print(f"\n{'='*60}")
    print(f"  Digital Interaction Engine - Navigation Demo")
    print(f"  App: {app} | Task: {task}")
    print(f"{'='*60}")
    print(f"\n👤 用户: {user_input}")

    session.start(user_input)
    session._app = app  # Set app from context

    # Run
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
    print(f"  导航路径:")
    for i, step in enumerate(flow.navigation_path):
        print(f"    {i+1}. {step.node_id} (置信度: {step.confidence:.0%})")

    print(f"\n  生成的 Interaction Flow JSON 已保存。")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
