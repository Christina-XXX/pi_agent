"""配置加载：环境变量、.env 文件、模型别名解析。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_BASE_URL = "https://api.deepseek.com"

# 模型别名 -> 真实模型名（"根据任务按需选择模型"）
MODEL_ALIASES = {
    "flash": "deepseek-flash",          # 默认：快、便宜、支持工具/视觉/思考
    "pro": "deepseek-v4-pro",           # 更强推理，更贵，无视觉
    "auto": "auto",
    "deepseek-flash": "deepseek-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    # 兼容旧模型名（已被 DeepSeek-V4.1-Flash 承接）
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision-exp",
    "deepseek-chat": "deepseek-chat",
    "deepseek-reasoner": "deepseek-reasoner",
}

# "auto" 模式下的简单路由：命中这些关键词 -> 用 pro，否则用 flash
REASONING_KEYWORDS = (
    "证明", "推理", "数学", "数学题", "算法", "难题", "逻辑",
    "review", "代码审查", "复杂", "分析", "证明题", "推导",
    "proof", "prove", "reasoning", "analyze", "analysis",
    "algorithm", "complex", "hard problem", "debug", "疑难",
)


def load_dotenv(path: Path | str = ".env") -> None:
    """读取 .env 文件，把 KEY=VALUE 注入环境变量（不覆盖已存在的变量）。"""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_model(name: str) -> str:
    """把别名解析为真实模型名。"""
    return MODEL_ALIASES.get(name, name)


def auto_model(task: str) -> str:
    """根据任务内容自动选择模型。"""
    low = task.lower()
    for kw in REASONING_KEYWORDS:
        if kw in low:
            return "deepseek-v4-pro"
    return "deepseek-flash"


@dataclass
class AgentConfig:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = "deepseek-flash"          # 已解析的真实模型名
    thinking: str = "auto"                 # auto | on | off
    reasoning_effort: Optional[str] = None  # low | medium | high
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_turns: int = 20
    workspace: Path = field(default_factory=Path.cwd)
    system_prompt: Optional[str] = None
    stream: bool = True
    show_thinking: bool = False
    yes: bool = False
    interactive: bool = False
    allow_shell: bool = True
    max_tool_output: int = 8000
    timeout: int = 600

    def thinking_flag(self) -> Optional[bool]:
        """返回 thinking 参数：True/False/None（None 表示不传，用服务端默认）。"""
        if self.thinking == "on":
            return True
        if self.thinking == "off":
            return False
        return None
