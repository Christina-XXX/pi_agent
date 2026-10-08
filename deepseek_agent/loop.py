"""Agent 主循环：模型 <-> 工具 的多轮交互。"""
from __future__ import annotations

import json
from typing import Optional

from .client import DeepSeekClient
from .config import AgentConfig
from .tools import REGISTRY, ToolContext, ToolResult


class UI:
    """输出/交互接口，CLI 可以继承并自定义（颜色、交互确认等）。"""

    def content(self, text: str) -> None:
        print(text, end="", flush=True)

    def reasoning(self, text: str) -> None:
        pass

    def tool_call(self, name: str, arguments: str) -> None:
        pass

    def tool_result(self, text: str) -> None:
        pass

    def info(self, text: str) -> None:
        print(text, flush=True)

    def error(self, text: str) -> None:
        print(text, flush=True)

    def approve(self, name: str, arguments: str) -> bool:
        """是否批准执行该工具。默认自动批准。"""
        return True


def _parse_args(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_agent(
    client: DeepSeekClient,
    cfg: AgentConfig,
    task: str,
    ui: UI,
    history: Optional[list] = None,
) -> list:
    """执行一次任务，返回最终消息列表（供交互模式复用）。"""
    messages = list(history) if history else []
    messages.append({"role": "user", "content": task})

    ctx = ToolContext(workspace=cfg.workspace, max_output=cfg.max_tool_output)
    disabled = () if cfg.allow_shell else ("shell",)
    tools = REGISTRY.specs(disabled)

    def on_delta(ev: dict) -> None:
        if ev["type"] == "content":
            ui.content(ev["text"])
        elif ev["type"] == "reasoning" and cfg.show_thinking:
            ui.reasoning(ev["text"])

    for turn in range(1, cfg.max_turns + 1):
        resp = client.chat(
            messages,
            model=cfg.model,
            tools=tools,
            thinking=cfg.thinking_flag(),
            reasoning_effort=cfg.reasoning_effort,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            stream=cfg.stream,
            on_delta=on_delta,
        )

        assistant: dict = {"role": "assistant", "content": resp["content"]}
        tool_calls = resp["tool_calls"]
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ]
        # 注意：reasoning_content 不回传给下一轮
        messages.append(assistant)

        if not tool_calls:
            return messages

        for tc in tool_calls:
            name, args_raw, call_id = tc["name"], tc["arguments"], tc["id"]
            tool = REGISTRY.get(name)
            ui.tool_call(name, args_raw)

            if tool is None:
                result = ToolResult(f"未知工具：{name}", is_error=True)
            elif tool.requires_approval and not ui.approve(name, args_raw):
                result = ToolResult("用户拒绝了该操作，请换一种方式或向用户询问。", is_error=True)
            else:
                result = tool.run(_parse_args(args_raw), ctx)

            ui.tool_result(result.content)
            messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": result.content}
            )

    ui.error(f"\n已达到最大轮数（{cfg.max_turns}），任务中止。")
    return messages
