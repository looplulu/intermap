#!/usr/bin/env python3
"""Analyze timing of guidance vs page changes."""
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read()) if len(sys.argv) > 1 else \
    json.loads(Path("/Users/assum/projects/intermap/digital-interaction-engine/data/guidance_scripts/taobao_refund_guidance.json").read_text())

print(f"App: {data['app']} | Task: {data['task']} | 共 {len(data['steps'])} 步")
print()

# Core verification: is guidance BEFORE page change?
print("=" * 80)
print("时序分析：引导语是否在屏幕变化之前输出？")
print("=" * 80)
print()

# The key insight: when we see frame N, the user has ALREADY operated.
# The guidance for frame N tells the user what to do to GET to frame N+1.
# So guidance should be: "do X to proceed" — this is FORWARD guidance.
# But our current system is BACKWARD: it tells you what you SHOULD HAVE done
# to get to this page, not what to do NEXT.

# Actually, re-thinking: 
# Frame 1 = home page → guidance says "click 我的淘宝" → user clicks
# Frame 3 = mine page → guidance says "click 我的订单" → user clicks
# The guidance on frame N tells the user what to do to reach frame N+1

# Let's verify this pattern
print(f"{'步骤':>4s}  {'时间':>6s}  {'帧':>6s}  {'节点':30s}  {'来源':10s}  {'引导语'}")
print("-" * 120)

issues = []
for step in data["steps"]:
    time_str = f"{step['time_seconds']:.0f}s"
    frame_str = f"#{step['frame_num']:02d}"
    trans = "→" if step["is_transition"] else "·"
    node = step["node_id"]
    source = step["source"]
    guidance = step["guidance"]
    
    print(f"{step['step']:4d}  {time_str:>6s}  {trans}{frame_str:>5s}  {node:30s}  {source:10s}  {guidance}")

    # Check: is this guidance telling user what to do NEXT (forward) 
    # or what they already did (backward)?
    forward_keywords = ["请点击", "请选择", "请找到", "请确认", "请输入", "请返回"]
    backward_keywords = []
    
    is_forward = any(k in guidance for k in forward_keywords)
    if not is_forward:
        issues.append(f"  ⚠️ 步骤{step['step']}: 引导语可能不是前瞻性的: {guidance}")

print()
print("=" * 80)
print("问题分析")
print("=" * 80)

if issues:
    print(f"\n发现 {len(issues)} 个潜在问题:")
    for issue in issues:
        print(issue)
else:
    print("\n所有引导语都是前瞻性的（告诉用户下一步做什么）。✓")

print()
print("=" * 80)
print("页面转换时序验证")
print("=" * 80)

transitions = [s for s in data["steps"] if s["is_transition"]]
print(f"\n共 {len(transitions)} 次页面转换:")
for t in transitions:
    print(f"  @{t['time_seconds']:.0f}s: {t['prev_node']} → {t['node_id']}")

print()
print("=" * 80)
print("关键验证：引导语 → 用户操作 → 页面变化")
print("=" * 80)
print("""
当前系统的行为模式:
  1. 用户看到 Frame N（某个页面）
  2. 系统识别到 Frame N，输出引导语："请点击XXX"
  3. 用户听到引导语，点击
  4. 页面变化到 Frame N+1
  5. 系统识别到 Frame N+1，输出新的引导语

这意味着引导语确实是"在屏幕变化之前"输出的。
引导语告诉用户当前页面应该做什么操作，用户操作后页面才变化。

但存在一个问题：页面变化检测后输出引导语，存在延迟。
理想情况是：用户操作 → 页面变化 → 系统立刻输出下一步引导语。
延迟 = OCR时间 + 匹配时间
""")
