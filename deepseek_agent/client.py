"""DeepSeek API 客户端（仅用标准库，无第三方依赖，支持流式 SSE）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from .config import DEFAULT_BASE_URL

OnDelta = Callable[[dict], None]


class DeepSeekError(Exception):
    """API 调用错误。"""


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 600):
        if not api_key:
            raise DeepSeekError(
                "缺少 API Key。请设置环境变量 DEEPSEEK_API_KEY，或在项目根目录创建 .env 文件。"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    def _post(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if payload.get("stream"):
            headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=data, headers=headers, method="POST"
        )
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise DeepSeekError(f"API HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise DeepSeekError(f"无法连接 API（{e.reason}），请检查网络。") from e

    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list,
        model: str = "deepseek-flash",
        tools: Optional[list] = None,
        thinking: Optional[bool] = None,
        reasoning_effort: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = True,
        on_delta: Optional[OnDelta] = None,
    ) -> dict:
        """发起对话。

        - stream=True 时返回 {'content','reasoning_content','tool_calls'}；
        - stream=False 时返回原始 JSON。
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if thinking is not None:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens

        if not stream:
            resp = self._post(payload)
            return json.loads(resp.read().decode("utf-8"))

        resp = self._post(payload)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
                if on_delta:
                    on_delta({"type": "content", "text": delta["content"]})
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
                if on_delta:
                    on_delta({"type": "reasoning", "text": delta["reasoning_content"]})
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                entry = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    entry["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    entry["name"] = fn["name"]
                if fn.get("arguments"):
                    entry["arguments"] += fn["arguments"]

        return {
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
            "tool_calls": [tool_calls[i] for i in sorted(tool_calls)],
        }
