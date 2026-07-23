#!/usr/bin/env python3
"""Batch OCR for all frames - processes at intervals and saves progress."""
import sys, json, time, os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from core.vision.ocr import extract_text_from_image

frames_dir = Path("data/processed/new_recording_1/frames")
files = sorted(frames_dir.glob("*.jpg"))
out_path = Path("data/processed/new_recording_1/ocr_results.json")

results = {}
for i, f in enumerate(files):
    t = i + 1
    try:
        texts = extract_text_from_image(f, min_confidence=0.5)
    except Exception as e:
        texts = [f"ERROR: {e}"]
    results[t] = {"frame": f.name, "texts": texts, "count": len(texts)}
    preview = " | ".join(texts[:6])
    print(f"  [{t:3d}/{len(files)}] {len(texts):2d}t: {preview}", flush=True)
    # Save incremental
    if t % 10 == 0:
        with open(out_path, "w") as fp:
            json.dump(results, fp, ensure_ascii=False)

with open(out_path, "w") as fp:
    json.dump(results, fp, ensure_ascii=False)
print(f"\nDone! Saved to {out_path}")