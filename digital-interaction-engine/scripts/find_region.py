#!/usr/bin/env python3
"""
Helper: Capture full screen and show coordinates to help find iPhone Mirroring window.

Usage:
    python scripts/find_region.py

Then:
1. Open the saved screenshot
2. Use Preview or any image viewer to find the iPhone Mirroring window
3. Note the top-left (x,y) and bottom-right (x,y) coordinates
4. Calculate: width = right_x - left_x, height = bottom_y - top_y
5. Use: --region left,top,width,height

Or the easy way on Mac:
1. Press Cmd+Shift+4
2. Move cursor to top-left corner of iPhone Mirroring window
3. Note the coordinates shown
4. Move cursor to bottom-right corner
5. Calculate width and height
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
screenshot_path = str(project_root / "data" / "fullscreen.png")

print("正在截取全屏...")
subprocess.run(["screencapture", screenshot_path], check=True)
print(f"全屏截图已保存: {screenshot_path}")
print()
print("请用 Preview 打开这张截图，找到 iPhone 镜像窗口的坐标：")
print("  左上角坐标 = (left, top)")
print("  右下角坐标 = (right, bottom)")
print("  宽 = right - left")
print("  高 = bottom - top")
print()
print("或者更简单的方法：")
print("  1. 按 Cmd+Shift+4")
print("  2. 鼠标移到 iPhone 镜像窗口左上角，记录坐标")
print("  3. 鼠标移到右下角，记录坐标")
print("  4. 计算宽和高")
print()
print("然后运行实时 Demo：")
print(f"  python scripts/run_live_demo.py --app taobao --task refund --region LEFT,TOP,WIDTH,HEIGHT")
