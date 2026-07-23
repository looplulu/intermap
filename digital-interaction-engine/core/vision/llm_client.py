"""LLM integration - DeepSeek V4 Flash for page understanding.

When Golden Flow doesn't cover the current page, we fall back to LLM
for page understanding, next-step reasoning, and guidance generation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")


@dataclass
class LLMPageResult:
    """Result from LLM page understanding."""
    app: str
    page_type: str
    page_summary: str
    suggested_action: str
    guidance_text: str
    confidence: float
    raw_response: str = ""


# System prompt for page understanding
PAGE_UNDERSTANDING_PROMPT = """你是一个数字世界导航助手，专门帮助中老年人理解手机App页面。

用户正在使用手机App，你将看到当前页面的OCR识别文字列表。
你需要：
1. 判断这是什么App的什么页面
2. 用户要完成"{task}"任务，在这个页面应该做什么
3. 用简单、清晰、老人能听懂的语言给出引导

请严格按以下JSON格式回复，不要输出其他内容：
{{
  "app": "app名称，如taobao/jd/pdd",
  "page_type": "页面语义类型，如home/order_list/order_detail/aftersales_type/aftersales_reason/refund_submit/refund_result",
  "page_summary": "一句话描述这是什么页面",
  "suggested_action": "用户应该做什么操作",
  "guidance_text": "给老人的语音引导语，50字以内。语气要像真人在旁边说话，直接、口语化，不用'请'字。用'点''选''看'等动词开头。例如：'点底部我的淘宝''选退货退款，然后点下一步''确认信息没问题就点提交'",
  "confidence": "你对自己判断的置信度，0.0到1.0"
}}

页面OCR文字：
{ocr_texts}

当前任务：{task}
当前App（如果已知）：{app_hint}"""


class DeepSeekClient:
    """DeepSeek API client for page understanding."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or DEFAULT_API_KEY
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.model = model or DEEPSEEK_MODEL

    def understand_page(
        self,
        ocr_texts: list[str],
        task: str,
        app_hint: str = "unknown",
    ) -> LLMPageResult:
        """Use LLM to understand a page and generate guidance.
        
        Args:
            ocr_texts: List of text strings from OCR
            task: Current task (e.g. "refund")
            app_hint: Known app name (optional)
        
        Returns:
            LLMPageResult with page understanding
        """
        if not self.api_key:
            return LLMPageResult(
                app=app_hint,
                page_type="unknown",
                page_summary="DeepSeek API key is not configured",
                suggested_action="",
                guidance_text="当前页面未被收录，继续观察页面变化。",
                confidence=0.0,
                raw_response="missing DEEPSEEK_API_KEY",
            )

        prompt = PAGE_UNDERSTANDING_PROMPT.format(
            task=task,
            app_hint=app_hint,
            ocr_texts="\n".join(f"- {t}" for t in ocr_texts),
        )

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是一个精确的数字世界导航助手，只输出JSON格式回复。"},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.1,  # Low temperature for consistency
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response
            # Handle potential markdown code block wrapping
            json_str = content.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]

            parsed = json.loads(json_str)

            return LLMPageResult(
                app=parsed.get("app", app_hint),
                page_type=parsed.get("page_type", "unknown"),
                page_summary=parsed.get("page_summary", ""),
                suggested_action=parsed.get("suggested_action", ""),
                guidance_text=parsed.get("guidance_text", ""),
                confidence=float(parsed.get("confidence", 0.5)),
                raw_response=content,
            )

        except requests.RequestException as e:
            return LLMPageResult(
                app=app_hint,
                page_type="unknown",
                page_summary=f"LLM请求失败: {e}",
                suggested_action="",
                guidance_text="暂时无法识别页面，请稍后再试。",
                confidence=0.0,
                raw_response=str(e),
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return LLMPageResult(
                app=app_hint,
                page_type="unknown",
                page_summary="LLM响应解析失败",
                suggested_action="",
                guidance_text="暂时无法识别页面，请稍后再试。",
                confidence=0.0,
                raw_response=str(e),
            )
