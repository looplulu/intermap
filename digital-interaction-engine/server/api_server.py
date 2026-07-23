"""Backend OCR API for Digital Interaction Engine.

Real-time OCR + Golden Flow matching.
No prediction. Only detect CURRENT page and guide based on that.
"""

from __future__ import annotations

import os
import json
import base64
import io
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, APIRouter, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

# Suppress Paddle logs
logging.getLogger("ppocr").setLevel(logging.WARNING)
logging.getLogger("paddlenlp").setLevel(logging.WARNING)
os.environ["PPOCR_DEBUG"] = "0"
os.environ["QUICK_SETUP"] = "1"

app = FastAPI(title="Digital Interaction Engine - OCR API")

# CORS - allow frontend from same domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Router with /api prefix
api_router = APIRouter(prefix="/api")

# ═══════════════════════════════════════════════════════════
# OCR Engine (lazy init)
# ═══════════════════════════════════════════════════════════
_ocr_engine = None
_ocr_version = None


def get_ocr_engine():
    global _ocr_engine, _ocr_version
    if _ocr_engine is not None:
        return _ocr_engine, _ocr_version
    from paddleocr import PaddleOCR
    _ocr_engine = PaddleOCR(
        use_angle_cls=True,
        lang="ch",
        show_log=False,
        # Detection parameters optimized for mobile UI screens
        det_db_thresh=0.2,          # lower threshold to catch small UI text
        det_db_box_thresh=0.3,     # lower box threshold for dense elements
        det_db_unclip_ratio=1.8,   # slightly larger boxes for better cursor hit
        det_limit_side_len=960,    # reasonable limit for phone screenshots
        det_limit_type="max",      # scale up small images for better detection
        use_doc_orientation_classify=False,  # skip orientation to save CPU
        use_doc_unwarping=False,   # skip unwarping for speed
    )
    _ocr_version = "v2"
    return _ocr_engine, _ocr_version


@dataclass
class OCRTextItem:
    text: str
    confidence: float
    box: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


def serialize_ocr_items(items: list[OCRTextItem], img_w: int, img_h: int) -> list[dict]:
    out = []
    for item in items:
        x1, y1, x2, y2 = item.box
        out.append({
            "text": item.text,
            "confidence": round(float(item.confidence), 3),
            "box": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
            "box_norm": {
                "x": round(x1 / img_w, 4) if img_w else 0,
                "y": round(y1 / img_h, 4) if img_h else 0,
                "w": round((x2 - x1) / img_w, 4) if img_w else 0,
                "h": round((y2 - y1) / img_h, 4) if img_h else 0,
            },
            "center_norm": {
                "x": round(((x1 + x2) / 2) / img_w, 4) if img_w else 0,
                "y": round(((y1 + y2) / 2) / img_h, 4) if img_h else 0,
            },
        })
    return out


def run_ocr_on_image(image: Image.Image, min_confidence: float = 0.3):
    """Run OCR on a PIL Image. Returns (list[OCRTextItem], (w, h))."""
    engine, version = get_ocr_engine()
    img_size = image.size

    # Save to temp for OCR
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        image.save(tmp.name, "JPEG", quality=95)
        tmp_path = tmp.name

    try:
        items = []
        result = engine.ocr(tmp_path, cls=True)
        if result and result[0]:
            for line in result[0]:
                if len(line) >= 2:
                    text = line[1][0]
                    confidence = line[1][1]
                    bbox = line[0]
                    if confidence >= min_confidence:
                        x1 = int(min(p[0] for p in bbox))
                        y1 = int(min(p[1] for p in bbox))
                        x2 = int(max(p[0] for p in bbox))
                        y2 = int(max(p[1] for p in bbox))
                        items.append(OCRTextItem(text.strip(), confidence, (x1, y1, x2, y2)))
        return items, img_size
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════
# LLM Page Understanding
# ═══════════════════════════════════════════════════════════
import requests as http_requests  # avoid name conflict

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

LLM_SYSTEM_PROMPT = """你是一个数字世界导航助手，专门帮助中老年人理解手机App页面。

用户正在使用抖音App，你将看到当前页面的OCR识别文字列表（含位置信息）。
用户的目标是：{user_goal}
你需要：
1. 判断当前是什么页面
2. 用户要完成目标，在这个页面应该做什么
3. 用简单、清晰、老人能听懂的语言给出引导，50字以内
4. 直接用"点""选""看"等动词开头，不用"请"字

请严格按以下JSON格式回复：
{{
  "page_type": "页面类型",
  "page_summary": "一句话描述当前页面",
  "action": "用户应该做的操作",
  "guidance": "语音引导语，50字以内，口语化",
  "confidence": 0.0到1.0,
  "next_page_hint": "执行操作后预期到达的页面"
}}"""


def llm_understand_page(ocr_texts, ocr_items, user_goal, image_size=None):
    """Use LLM to understand current page and generate guidance."""
    if not DEEPSEEK_API_KEY:
        return None

    # Build OCR context with position info
    ocr_lines = []
    for i, text in enumerate(ocr_texts[:60]):
        line = f"- {text}"
        if ocr_items and i < len(ocr_items):
            item = ocr_items[i]
            bn = item.get("box_norm", {})
            if bn:
                pos = describe_position(bn)
                line += f" (位置: {pos})"
        ocr_lines.append(line)

    prompt = LLM_SYSTEM_PROMPT.format(user_goal=user_goal)
    prompt += "\n\n页面OCR识别内容（按位置排列）：\n" + "\n".join(ocr_lines)
    if image_size:
        prompt += f"\n\n画面尺寸: {image_size['width']}x{image_size['height']}"

    try:
        response = http_requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是精确的数字世界导航助手，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON (handle markdown wrapping)
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

        parsed = json.loads(content)
        return {
            "page_type": parsed.get("page_type", "unknown"),
            "page_summary": parsed.get("page_summary", ""),
            "action": parsed.get("action", ""),
            "guidance": parsed.get("guidance", ""),
            "confidence": float(parsed.get("confidence", 0.5)),
            "next_page_hint": parsed.get("next_page_hint", ""),
            "source": "llm",
        }
    except Exception as e:
        return {"error": str(e), "source": "llm"}


def describe_position(box_norm):
    """Convert normalized box to Chinese position description."""
    x = box_norm.get("x", 0.5)
    y = box_norm.get("y", 0.5)
    cx = x + box_norm.get("w", 0) / 2
    cy = y + box_norm.get("h", 0) / 2

    if cy < 0.12: v = "顶部"
    elif cy < 0.35: v = "上方"
    elif cy < 0.65: v = "中间"
    elif cy < 0.88: v = "下方"
    else: v = "底部"

    if cx < 0.25: h = "左边"
    elif cx < 0.45: h = "偏左"
    elif cx < 0.55: h = "中间"
    elif cx < 0.75: h = "偏右"
    else: h = "右边"

    if v == "中间" and h == "中间": return "屏幕中间"
    if v in ("顶部", "底部"):
        return v if h == "中间" else f"{v}{h}"
    if h in ("左边", "右边"): return h
    return f"{v}{h}"


# ═══════════════════════════════════════════════════════════
# Golden Flow / HDMap
# ═══════════════════════════════════════════════════════════

FLOWS_DIR = Path(__file__).parent / "golden_flows"


class GoldenFlow:
    def __init__(self, data: dict):
        self.flow_id = data["flow_id"]
        self.app = data["app"]
        self.task = data["task"]
        self.nodes = {n["node_id"]: n for n in data["nodes"]}
        self.node_order = [n["node_id"] for n in data["nodes"]]
        self.edges = data.get("edges", [])

    @property
    def start_node(self) -> str | None:
        for nid, node in self.nodes.items():
            if node.get("is_start"):
                return nid
        return self.node_order[0] if self.node_order else None

    def get_next_node(self, current_node_id: str) -> str | None:
        if current_node_id not in self.node_order:
            return None
        idx = self.node_order.index(current_node_id)
        if idx + 1 < len(self.node_order):
            return self.node_order[idx + 1]
        return None

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)


class HDMap:
    def __init__(self, flows_dir: str | Path):
        self._flows_dir = Path(flows_dir)
        self._flows: dict[str, GoldenFlow] = {}
        self._load_flows()

    def _load_flows(self):
        if not self._flows_dir.exists():
            return
        for f in self._flows_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                flow = GoldenFlow(data)
                key = f"{flow.app}_{flow.task}"
                self._flows[key] = flow
            except Exception as e:
                print(f"[HDMap] Failed to load {f}: {e}")

    def get_flow(self, app: str, task: str) -> GoldenFlow | None:
        return self._flows.get(f"{app}_{task}")

    def match_node(self, ocr_texts: list[str], app: str, task: str):
        flow = self.get_flow(app, task)
        if flow is None:
            return None, 0.0, None

        full_text = " ".join(ocr_texts).lower()
        # Build set of all OCR words for fuzzy matching
        ocr_words = set()
        for txt in ocr_texts:
            ocr_words.add(txt.lower())
            # Also add substrings for partial matching
            for i in range(len(txt)):
                for j in range(i + 1, len(txt) + 1):
                    substr = txt[i:j].lower()
                    if len(substr) >= 2:
                        ocr_words.add(substr)

        best_node_id = None
        best_score = 0.0
        best_node_data = None

        for node_id, node in flow.nodes.items():
            indicators = node.get("key_indicators", [])
            if not indicators:
                continue

            matched = 0
            matched_strong = 0
            for ind in indicators:
                ind_lower = ind.lower()
                # Full match
                if ind_lower in full_text:
                    matched += 1
                # Partial match: any OCR word contains this indicator
                elif any(ind_lower in w for w in ocr_words):
                    matched += 0.7
                # Reverse: indicator contains any OCR word (2+ chars)
                elif any(len(w) >= 2 and w in ind_lower for w in ocr_words):
                    matched += 0.5

                if len(ind) >= 3:
                    if ind_lower in full_text:
                        matched_strong += 1
                    elif any(ind_lower in w for w in ocr_words):
                        matched_strong += 0.7
                    elif any(len(w) >= 2 and w in ind_lower for w in ocr_words):
                        matched_strong += 0.5

            if matched_strong < 0.5:
                continue

            score = matched / len(indicators)
            strong_indicators = [ind for ind in indicators if len(ind) >= 3]
            if strong_indicators:
                score = 0.6 * (matched_strong / len(strong_indicators)) + 0.4 * score

            if score > best_score:
                best_score = score
                best_node_id = node_id
                best_node_data = node

        if best_node_id and best_score >= 0.15:
            return best_node_id, best_score, best_node_data

        return None, 0.0, None

    def get_guidance(self, node_id: str, app: str, task: str) -> tuple[str, list[str]]:
        flow = self.get_flow(app, task)
        if flow is None:
            return "未知页面", []

        node = flow.get_node(node_id)
        if node is None:
            return "未知页面", []

        guidance = node.get("guidance", {})
        action_text = guidance.get("action", "")
        risks = node.get("risks", [])
        risk_texts = [r.get("description", "") for r in risks]

        return action_text, risk_texts


hdmap = HDMap(FLOWS_DIR)


# ═══════════════════════════════════════════════════════════
# Position Guider
# ═══════════════════════════════════════════════════════════

class PositionGuider:
    def __init__(self, image_width: int, image_height: int):
        self.w = image_width
        self.h = image_height

    def locate_text(self, center_x: float, center_y: float) -> str:
        x_ratio = center_x / self.w
        y_ratio = center_y / self.h

        if y_ratio < 0.12:
            v = "顶部"
        elif y_ratio < 0.35:
            v = "上方"
        elif y_ratio < 0.65:
            v = "中间"
        elif y_ratio < 0.88:
            v = "下方"
        else:
            v = "底部"

        if x_ratio < 0.25:
            h = "左边"
        elif x_ratio < 0.45:
            h = "偏左"
        elif x_ratio < 0.55:
            h = "中间"
        elif x_ratio < 0.75:
            h = "偏右"
        else:
            h = "右边"

        if v == "中间" and h == "中间":
            return "屏幕中间"
        if v in ("顶部", "底部"):
            if h == "中间":
                return f"{v}"
            return f"{v}{h}"
        if h in ("左边", "右边"):
            return f"{h}"
        return f"{v}{h}"

    def describe_button_location(self, items: list, button_text: str) -> str | None:
        for item in items:
            if button_text in item.text or item.text in button_text:
                cx, cy = item.center
                return self.locate_text(cx, cy)
        for item in items:
            if any(c in item.text for c in button_text if len(c) > 1):
                cx, cy = item.center
                return self.locate_text(cx, cy)
        return None

    def enhance_guidance(self, guidance: str, items: list, button_keywords: list[str]) -> str:
        for keyword in button_keywords:
            pos = self.describe_button_location(items, keyword)
            if pos and pos not in guidance:
                clean = guidance.rstrip("。.,;!?")
                return f"{clean}，在{pos}"
        return guidance


# ═══════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════

@api_router.get("/health")
def health():
    return {"status": "ok", "ocr_loaded": _ocr_engine is not None}


@api_router.get("/flows")
def list_flows():
    """List available golden flows."""
    flows = []
    for key, flow in hdmap._flows.items():
        flows.append({
            "key": key,
            "app": flow.app,
            "task": flow.task,
            "node_count": len(flow.nodes),
        })
    return {"flows": flows}


@api_router.post("/analyze")
async def analyze_frame(
    file: UploadFile = File(...),
    app: str = Form(...),
    task: str = Form(...),
):
    """Analyze a single frame: OCR + node matching.

    Returns matched node, guidance text, and detected text.
    """
    try:
        # Read image
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")

        # OCR
        items, (img_w, img_h) = run_ocr_on_image(image)
        ocr_texts = [item.text for item in items]

        # Match node
        node_id, confidence, node_data = hdmap.match_node(ocr_texts, app, task)

        # Build response
        result = {
            "ocr_texts": ocr_texts,
            "ocr_items": serialize_ocr_items(items, img_w, img_h),
            "ocr_count": len(ocr_texts),
            "image_size": {"width": img_w, "height": img_h},
            "matched_node": node_id,
            "confidence": round(confidence, 3),
        }

        if node_id and node_data:
            guidance_text, risks = hdmap.get_guidance(node_id, app, task)
            enter_text = node_data.get("guidance", {}).get("enter", "")

            # Enhance guidance with position info
            guider = PositionGuider(img_w, img_h)
            # Extract button keywords from guidance (text after '点' or similar)
            button_keywords = []
            if "点" in guidance_text:
                # Simple extraction: find text after '点'
                parts = guidance_text.split("点")
                for p in parts[1:]:
                    btn = p.split("，")[0].split("。")[0].split("；")[0].strip()
                    if btn:
                        button_keywords.append(btn)

            enhanced_guidance = guider.enhance_guidance(guidance_text, items, button_keywords)

            result["guidance"] = {
                "node_id": node_id,
                "node_name": node_data.get("page_type", ""),
                "enter_text": enter_text,
                "action_text": enhanced_guidance,
                "raw_action": guidance_text,
                "risks": risks,
                "is_end": node_data.get("is_end", False),
            }
        else:
            result["guidance"] = None

        return JSONResponse(result)
    except Exception as e:
        # Catch any errors during OCR processing and return graceful error
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "ocr_texts": [],
            "ocr_count": 0,
            "image_size": {"width": 0, "height": 0},
            "matched_node": None,
            "confidence": 0.0,
            "guidance": None,
            "error": str(e),
        })


@api_router.post("/analyze_base64")
async def analyze_frame_base64(
    image_base64: str = Form(...),
    app: str = Form(...),
    task: str = Form(...),
):
    """Analyze a base64-encoded image frame."""
    try:
        # Decode base64
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        # OCR
        items, (img_w, img_h) = run_ocr_on_image(image)
        ocr_texts = [item.text for item in items]

        # Match node
        node_id, confidence, node_data = hdmap.match_node(ocr_texts, app, task)

        result = {
            "ocr_texts": ocr_texts,
            "ocr_items": serialize_ocr_items(items, img_w, img_h),
            "ocr_count": len(ocr_texts),
            "image_size": {"width": img_w, "height": img_h},
            "matched_node": node_id,
            "confidence": round(confidence, 3),
        }

        if node_id and node_data:
            guidance_text, risks = hdmap.get_guidance(node_id, app, task)
            enter_text = node_data.get("guidance", {}).get("enter", "")

            guider = PositionGuider(img_w, img_h)
            button_keywords = []
            if "点" in guidance_text:
                parts = guidance_text.split("点")
                for p in parts[1:]:
                    btn = p.split("，")[0].split("。")[0].split("；")[0].strip()
                    if btn:
                        button_keywords.append(btn)

            enhanced_guidance = guider.enhance_guidance(guidance_text, items, button_keywords)

            result["guidance"] = {
                "node_id": node_id,
                "node_name": node_data.get("page_type", ""),
                "enter_text": enter_text,
                "action_text": enhanced_guidance,
                "raw_action": guidance_text,
                "risks": risks,
                "is_end": node_data.get("is_end", False),
            }
        else:
            result["guidance"] = None

        return JSONResponse(result)
    except Exception as e:
        # Catch any errors during OCR processing and return graceful error
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "ocr_texts": [],
            "ocr_count": 0,
            "image_size": {"width": 0, "height": 0},
            "matched_node": None,
            "confidence": 0.0,
            "guidance": None,
            "error": str(e),
        })


@api_router.post("/understand")
async def understand_page(
    image_base64: str = Form(...),
    user_goal: str = Form(""),
):
    """OCR + LLM page understanding for demo mode.

    User provides their goal, system identifies current page and guides them.
    """
    try:
        # Decode and OCR
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        items, (img_w, img_h) = run_ocr_on_image(image)
        ocr_texts = [item.text for item in items]
        serialized_items = serialize_ocr_items(items, img_w, img_h)

        result = {
            "ocr_texts": ocr_texts,
            "ocr_items": serialized_items,
            "ocr_count": len(ocr_texts),
            "image_size": {"width": img_w, "height": img_h},
            "user_goal": user_goal,
        }

        # Also try Golden Flow matching if applicable
        node_id, confidence, node_data = hdmap.match_node(ocr_texts, "douyin", user_goal)
        if node_id and node_data:
            guidance_text, risks = hdmap.get_guidance(node_id, "douyin", user_goal)
            guider = PositionGuider(img_w, img_h)
            button_keywords = []
            if "点" in guidance_text:
                parts = guidance_text.split("点")
                for p in parts[1:]:
                    btn = p.split("，")[0].split("。")[0].split("；")[0].strip()
                    if btn: button_keywords.append(btn)
            enhanced = guider.enhance_guidance(guidance_text, items, button_keywords)
            result["guidance"] = {
                "node_id": node_id,
                "node_name": node_data.get("page_type", ""),
                "action_text": enhanced,
                "raw_action": guidance_text,
                "risks": risks,
                "confidence": round(confidence, 3),
                "source": "golden_flow",
            }

        # LLM understanding (runs in parallel conceptually, but sequentially here)
        if user_goal:
            llm_result = llm_understand_page(ocr_texts, serialized_items, user_goal, {"width": img_w, "height": img_h})
            if llm_result and not llm_result.get("error"):
                result["llm"] = llm_result
                # If no golden flow match, use LLM result as guidance
                if not result.get("guidance"):
                    result["guidance"] = {
                        "node_id": f"llm_{llm_result.get('page_type', 'unknown')}",
                        "node_name": llm_result.get("page_type", ""),
                        "action_text": llm_result.get("guidance", ""),
                        "raw_action": llm_result.get("action", ""),
                        "risks": [],
                        "confidence": llm_result.get("confidence", 0.5),
                        "source": "llm",
                    }

        return JSONResponse(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "ocr_texts": [],
            "ocr_count": 0,
            "image_size": {"width": 0, "height": 0},
            "guidance": None,
            "error": str(e),
        })


app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)
