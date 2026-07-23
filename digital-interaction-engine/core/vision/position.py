"""Visual position guidance - tells user WHERE on screen to tap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenRegion:
    """A region of the screen."""
    description: str  # e.g. "底部中间"
    x_ratio: float    # 0.0 - 1.0 center x
    y_ratio: float    # 0.0 - 1.0 center y


class PositionGuider:
    """Converts text positions into human-friendly location descriptions."""

    def __init__(self, image_width: int, image_height: int):
        self.w = image_width
        self.h = image_height

    def locate_text(self, center_x: float, center_y: float) -> str:
        """Describe where on screen a point is.
        
        Returns: e.g. "左上角", "底部中间", "右边"
        """
        x_ratio = center_x / self.w
        y_ratio = center_y / self.h

        # Vertical position
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

        # Horizontal position
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

        # Combine
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
        """Find a button by text and describe its position.
        
        Args:
            items: list of OCRTextItem from OCR
            button_text: the text on the button to find
            
        Returns: e.g. "底部右边" or None if not found
        """
        # Try exact match first
        for item in items:
            if button_text in item.text or item.text in button_text:
                cx, cy = item.center
                return self.locate_text(cx, cy)

        # Try partial match
        for item in items:
            # Check if any character in button_text is in item.text
            if any(c in item.text for c in button_text if len(c) > 1):
                cx, cy = item.center
                return self.locate_text(cx, cy)

        return None

    def add_position_to_guidance(
        self,
        guidance: str,
        items: list,
        button_keywords: list[str],
    ) -> str:
        """Enhance guidance with position info.
        
        If guidance says '点XXX' and XXX is found on screen,
        append its position. e.g.:
        '点底部我的淘宝' -> '点底部我的淘宝，在底部右边'
        
        Returns: enhanced guidance
        """
        for keyword in button_keywords:
            pos = self.describe_button_location(items, keyword)
            if pos:
                # Don't duplicate if position is already in guidance
                if pos not in guidance:
                    # Strip trailing punctuation before appending
                    clean = guidance.rstrip("。.,;!?")
                    return f"{clean}，在{pos}"
        return guidance
