"""工具系统：内置工具 + 可扩展的自定义工具注册表。"""
from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


# --------------------------------------------------------------------- #
@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    """工具执行上下文，注入到需要它的工具函数中。"""

    workspace: Path
    max_output: int = 8000


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        requires_approval: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.requires_approval = requires_approval

    def to_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            if "ctx" in inspect.signature(self.func).parameters:
                result = self.func(**args, ctx=ctx)
            else:
                result = self.func(**args)
        except TypeError as e:
            return ToolResult(f"工具参数错误：{e}", is_error=True)
        except Exception as e:  # noqa: BLE001
            return ToolResult(f"工具执行出错：{e}", is_error=True)
        if isinstance(result, ToolResult):
            return result
        return ToolResult(str(result))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def tool(
        self, name: str, description: str, parameters: dict, requires_approval: bool = False
    ):
        """装饰器：把一个函数注册为工具。"""

        def deco(func: Callable) -> Callable:
            self.register(Tool(name, description, parameters, func, requires_approval))
            return func

        return deco

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def specs(self, disabled: tuple[str, ...] = ()) -> list:
        return [t.to_spec() for n, t in self._tools.items() if n not in disabled]

    def names(self) -> list[str]:
        return list(self._tools.keys())


REGISTRY = ToolRegistry()


# --------------------------------------------------------------------- #
def _resolve(ctx: Optional[ToolContext], path: str) -> Path:
    p = Path(path)
    if not p.is_absolute() and ctx is not None:
        p = ctx.workspace / p
    return p.resolve()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字符）"


# --------------------------- 内置工具 -------------------------------- #
@REGISTRY.tool(
    name="read_file",
    description="读取文本文件内容。返回指定行范围的内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对工作目录或绝对路径）"},
            "offset": {"type": "integer", "description": "起始行号，从 1 开始", "default": 1},
            "limit": {"type": "integer", "description": "最多读取的行数", "default": 2000},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)
def read_file(path: str, offset: int = 1, limit: int = 2000, ctx: ToolContext = None) -> str:
    p = _resolve(ctx, path)
    if not p.exists():
        return f"错误：文件不存在：{p}"
    if p.is_dir():
        return f"错误：{p} 是目录，请用 list_dir 查看。"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"错误：读取失败：{e}"
    start = max(1, offset) - 1
    end = start + max(1, limit)
    chunk = lines[start:end]
    head = f"{p}（共 {len(lines)} 行，显示第 {start + 1}-{min(end, len(lines))} 行）\n"
    return head + "\n".join(f"{i + start + 1}: {ln}" for i, ln in enumerate(chunk))


@REGISTRY.tool(
    name="write_file",
    description="创建或覆盖写入文件。会自动创建父目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对工作目录或绝对路径）"},
            "content": {"type": "string", "description": "要写入的完整内容"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
)
def write_file(path: str, content: str, ctx: ToolContext = None) -> str:
    p = _resolve(ctx, path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"错误：写入失败：{e}"
    return f"已写入 {p}（{len(content)} 字符）"


@REGISTRY.tool(
    name="list_dir",
    description="列出目录内容（含文件/子目录、大小）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，默认工作目录", "default": "."},
        },
        "additionalProperties": False,
    },
)
def list_dir(path: str = ".", ctx: ToolContext = None) -> str:
    p = _resolve(ctx, path)
    if not p.exists():
        return f"错误：目录不存在：{p}"
    if not p.is_dir():
        return f"错误：{p} 不是目录。"
    rows = []
    try:
        entries = sorted(os.scandir(p), key=lambda e: e.name)
    except OSError as e:
        return f"错误：无法读取目录：{e}"
    for e in entries:
        try:
            if e.is_dir(follow_symlinks=False):
                rows.append(f"[目录] {e.name}/")
            elif e.is_file(follow_symlinks=False):
                size = e.stat(follow_symlinks=False).st_size
                rows.append(f"[文件] {e.name}  ({size} B)")
            else:
                rows.append(f"[链接] {e.name}")
        except OSError:
            rows.append(f"[?] {e.name}")
    if not rows:
        return f"{p} 为空目录。"
    return f"{p}（{len(rows)} 项）\n" + "\n".join(rows)


@REGISTRY.tool(
    name="shell",
    description="执行一条 shell 命令并返回输出。用于运行程序、安装依赖、git 操作等。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 120},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    requires_approval=True,
)
def shell(command: str, timeout: int = 120, ctx: ToolContext = None) -> ToolResult:
    cwd = str(ctx.workspace) if ctx else None
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(f"错误：命令超时（>{timeout}s）", is_error=True)
    except OSError as e:
        return ToolResult(f"错误：命令执行失败：{e}", is_error=True)
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    out = _truncate(out.strip() or "(无输出)", ctx.max_output if ctx else 8000)
    return ToolResult(f"$ {command}\n退出码：{proc.returncode}\n{out}", is_error=proc.returncode != 0)


@REGISTRY.tool(
    name="search_files",
    description="按正则表达式在目录内搜索文件内容，返回匹配行。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "正则表达式（Python re 语法）"},
            "path": {"type": "string", "description": "搜索目录，默认工作目录", "default": "."},
            "glob": {"type": "string", "description": "文件名匹配，如 *.py", "default": "*"},
            "max_results": {"type": "integer", "description": "最多返回条数", "default": 50},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)
def search_files(
    pattern: str, path: str = ".", glob: str = "*", max_results: int = 50, ctx: ToolContext = None
) -> str:
    root = _resolve(ctx, path)
    if not root.exists():
        return f"错误：目录不存在：{root}"
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"错误：正则表达式无效：{e}"
    results = []
    try:
        for p in sorted(root.rglob(glob)):
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > 1_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    results.append(f"{p.relative_to(root)}:{i}: {line.strip()[:200]}")
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
    except OSError as e:
        return f"错误：搜索失败：{e}"
    if not results:
        return f"在 {root} 中未找到匹配 /{pattern}/ 的内容。"
    head = f"在 {root} 中找到 {len(results)} 条匹配（最多显示 {max_results} 条）：\n"
    return head + "\n".join(results)


@REGISTRY.tool(
    name="fetch_url",
    description="抓取网页/URL 的文本内容（HTTP GET）。",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的 URL"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
            "max_chars": {"type": "integer", "description": "最多返回字符数", "default": 8000},
        },
        "required": ["url"],
        "additionalProperties": False,
    },
)
def fetch_url(url: str, timeout: int = 30, max_chars: int = 8000, ctx: ToolContext = None) -> ToolResult:
    if not url.startswith(("http://", "https://")):
        return ToolResult("错误：仅支持 http/https URL。", is_error=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DeepSeek-Agent)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return ToolResult(f"错误：抓取失败：{e.reason}", is_error=True)
    except Exception as e:  # noqa: BLE001
        return ToolResult(f"错误：抓取失败：{e}", is_error=True)
    body = _truncate(body, max_chars)
    return ToolResult(f"HTTP {status}  {ctype}\n{url}\n\n{body}")


# --------------------------------------------------------------------- #
# 自定义工具加载：扫描目录下的 *.py，执行其中的 register(registry) 或 TOOLS 列表
def load_custom_tools(directory: Path) -> int:
    """从指定目录加载自定义工具，返回成功注册的数量。"""
    if not directory.exists():
        return 0
    import importlib.util
    import sys

    count = 0
    for f in sorted(directory.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"custom_tool_{f.stem}", f)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            # 方式一：模块直接提供 TOOLS 列表
            for tool in getattr(mod, "TOOLS", []) or []:
                if isinstance(tool, Tool):
                    REGISTRY.register(tool)
                    count += 1
            # 方式二：模块提供 register(registry) 函数
            register = getattr(mod, "register", None)
            if callable(register):
                before = len(REGISTRY._tools)
                register(REGISTRY)
                count += len(REGISTRY._tools) - before
        except Exception as e:  # noqa: BLE001
            print(f"[警告] 加载自定义工具 {f.name} 失败：{e}")
    return count
