"""OCR with position - PaddleOCR with text location extraction."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from dataclasses import dataclass

logging.getLogger("ppocr").setLevel(logging.WARNING)
logging.getLogger("paddlenlp").setLevel(logging.WARNING)

_ocr_engine = None
_is_paddleocr_v3 = None


def _detect_version():
    global _is_paddleocr_v3
    if _is_paddleocr_v3 is not None:
        return _is_paddleocr_v3
    try:
        from paddleocr._pipelines.ocr import PaddleOCR as _test
        _is_paddleocr_v3 = True
    except (ImportError, AttributeError):
        _is_paddleocr_v3 = False
    return _is_paddleocr_v3


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    os.environ["PPOCR_DEBUG"] = "0"
    os.environ["QUICK_SETUP"] = "1"
    if _detect_version():
        from paddleocr._pipelines.ocr import PaddleOCR
        _ocr_engine = ("v3", PaddleOCR(lang="ch"))
    else:
        from paddleocr import PaddleOCR
        _ocr_engine = ("v2", PaddleOCR(use_angle_cls=True, lang="ch", show_log=False))
    return _ocr_engine


@dataclass
class OCRTextItem:
    """A single OCR result with text, confidence, and bounding box."""
    text: str
    confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels

    @property
    def center(self) -> tuple[float, float]:
        """Center point of the text box."""
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def extract_text_with_position(
    image_path: str | Path,
    min_confidence: float = 0.5,
) -> tuple[list[OCRTextItem], tuple[int, int]]:
    """Extract text with position from an image.
    
    Returns: (list of OCRTextItem, (image_width, image_height))
    """
    from PIL import Image
    img = Image.open(str(image_path))
    img_size = img.size

    engine_tuple = get_ocr_engine()
    version, engine = engine_tuple

    items = []
    if version == "v3":
        result = engine.predict(str(image_path))
        for item in result:
            texts = item.get("rec_texts", [])
            scores = item.get("rec_scores", [])
            boxes = item.get("rec_boxes", [])
            for txt, score, box in zip(texts, scores, boxes):
                if float(score) >= min_confidence:
                    box_tuple = tuple(int(x) for x in box)
                    items.append(OCRTextItem(str(txt), float(score), box_tuple))
    else:
        result = engine.ocr(str(image_path), cls=True)
        if result and result[0]:
            for line in result[0]:
                if len(line) >= 2:
                    text = line[1][0]
                    confidence = line[1][1]
                    bbox = line[0]  # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                    if confidence >= min_confidence:
                        x1 = int(min(p[0] for p in bbox))
                        y1 = int(min(p[1] for p in bbox))
                        x2 = int(max(p[0] for p in bbox))
                        y2 = int(max(p[1] for p in bbox))
                        items.append(OCRTextItem(text.strip(), confidence, (x1, y1, x2, y2)))

    return items, img_size


def extract_text_from_image(
    image_path: str | Path,
    min_confidence: float = 0.5,
) -> list[str]:
    """Extract text only (backward compatible)."""
    items, _ = extract_text_with_position(image_path, min_confidence)
    return [item.text for item in items]


def extract_text_from_images(
    frames_dir: str | Path,
    min_confidence: float = 0.5,
) -> list[list[str]]:
    frames_dir = Path(frames_dir)
    image_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    all_texts = []
    for img_path in image_files:
        texts = extract_text_from_image(img_path, min_confidence)
        all_texts.append(texts)
        print(f"  [{img_path.name}] {len(texts)} texts")
    return all_texts
