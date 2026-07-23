#!/usr/bin/env python3
"""Quick scan all frames to understand the video content."""
import sys, os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from core.vision.ocr import extract_text_from_image

frames_dir = Path("data/processed/new_recording_1/frames")
files = sorted(frames_dir.glob("*.jpg"))
print(f"Total frames: {len(files)}")

# Scan every 5th frame + key transition frames
for i, f in enumerate(files):
    texts = extract_text_from_image(f, min_confidence=0.5)
    preview = " | ".join(texts[:6])
    if len(texts) > 6:
        preview += f" ... (+{len(texts)-6})"
    print(f"  [{i+1:3d}s] {len(texts):3d} texts: {preview}")