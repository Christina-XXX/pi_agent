"""命令行入口。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .client import DeepSeekClient, DeepSeekError
from .config import (
    MODEL_ALIASES,
    AgentConfig,
    auto_model,
    load_dotenv,
    resolve_model,
)
from .loop import UI, run_agent
from .prompts import build_system_prompt
from .tools import REGISTRY, load_custom_tools


class ConsoleUI(UI):
    """带颜色与交互确认的控制台 UI。"""

    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    DIM = "\033[2m"
    RED = "\033[31m"
    RESET = "\033[0m"

    def __init__(self, interactive: bool, yes: bool, color: bool = True):
        self.interactive = interactive
        self.yes = yes
        self.color = color and sys.stdout.isatty()

    def _c(self, code: str, text: str) -> str:
        return f"{code}{text}{self.RESET}" if self.color else text

    def reasoning(self, text: str) -> None:
        sys.stdout.write(self._c(self.DIM, text))
        sys.stdout.flush()

    def tool_call(self, name: str, arguments: str) -> None:
        print("\n" + self._c(self.BLUE, f"🔧 {name} {arguments}"))

    def tool_result(self, text: str) -> None:
        preview = text.replace("\n", "\n  ")
        print(self._c(self.DIM, f"   ↳ {preview[:1000]}"))

    def info(self, text: str) -> None:
        print(self._c(self.GREEN, text))

    def error(self, text: str) -> None:
        print(self._c(self.RED, text), file=sys.stderr)

    def approve(self, name: str, arguments: str) -> bool:
        if self.yes or not self.interactive:
            return True
        ans = input(
            self._c(self.YELLOW, f"\n⚠ 是否执行 `{name}`？(y=执行 / n=跳过 / a=全部允许) ")
        ).strip().lower()
        if ans in ("a", "all"):
            self.yes = True
            return True
        return ans in ("y", "yes")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deepseek-agent",
        description="通用 AI 智能体，基于 DeepSeek API（支持工具调用）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  deepseek-agent "帮我看看当前目录有哪些文件"
  deepseek-agent -m pro "写一个 Python 冒泡排序并测试"
  deepseek-agent -i                     # 交互模式
  deepseek-agent --models               # 查看可用模型
""",
    )
    p.add_argument("task", nargs="*", help="要执行的任务（可多段，会拼接）")
    p.add_argument("-m", "--model", default="auto",
                   help="模型：auto / flash / pro / 或完整模型名（默认 auto 按任务自动选择）")
    p.add_argument("-i", "--interactive", action="store_true", help="交互式对话模式")
    p.add_argument("--thinking", choices=["auto", "on", "off"], default="auto",
                   help="思考模式（默认 auto=跟随服务端默认）")
    p.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default=None,
                   help="思考强度（仅思考模式下生效）")
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-turns", type=int, default=20, help="单次任务最多工具轮数（默认 20）")
    p.add_argument("-w", "--workspace", default=".", help="工作目录（文件/命令操作基于此目录）")
    p.add_argument("--system", default=None, help="自定义系统提示词")
    p.add_argument("--show-thinking", action="store_true", help="显示模型思考过程")
    p.add_argument("--no-shell", action="store_true", help="禁用 shell 工具")
    p.add_argument("--no-stream", action="store_true", help="关闭流式输出")
    p.add_argument("-y", "--yes", action="store_true", help="自动批准所有需确认的操作")
    p.add_argument("--no-color", action="store_true", help="关闭颜色输出")
    p.add_argument("--api-key", default=None, help="API Key（也可用环境变量 DEEPSEEK_API_KEY）")
    p.add_argument("--base-url", default=None, help="API 地址（默认 https://api.deepseek.com）")
    p.add_argument("--models", action="store_true", help="打印可用模型并退出")
    p.add_argument("--version", action="version", version=f"deepseek-agent {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.models:
        print("可用模型别名：")
        for k, v in MODEL_ALIASES.items():
            print(f"  {k:<28} -> {v}")
        print("\n说明：默认 deepseek-flash（快/便宜/支持工具）；")
        print("      deepseek-v4-pro 推理更强但更贵，适合复杂推理任务。")
        return 0

    # 加载配置：.env 文件 + 环境变量
    load_dotenv(Path(args.workspace) / ".env")
    load_dotenv(".env")

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = args.base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"错误：工作目录不存在：{workspace}", file=sys.stderr)
        return 2

    # 加载自定义工具（./tools 目录）
    load_custom_tools(workspace / "tools")

    task = " ".join(args.task).strip()

    # 模型选择
    model = resolve_model(args.model)
    if model == "auto":
        model = auto_model(task if task else "")

    cfg = AgentConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        thinking=args.thinking,
        reasoning_effort=args.reasoning_effort,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        workspace=workspace,
        system_prompt=args.system,
        stream=not args.no_stream,
        show_thinking=args.show_thinking,
        yes=args.yes,
        interactive=args.interactive,
        allow_shell=not args.no_shell,
    )

    try:
        client = DeepSeekClient(api_key=api_key, base_url=base_url, timeout=cfg.timeout)
    except DeepSeekError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    ui = ConsoleUI(interactive=args.interactive, yes=args.yes, color=not args.no_color)

    if not task and not args.interactive:
        # 无任务且非交互：从标准输入读取
        if not sys.stdin.isatty():
            task = sys.stdin.read().strip()
        if not task:
            print("请提供任务：deepseek-agent \"你的任务\"，或使用 -i 进入交互模式。",
                  file=sys.stderr)
            return 2

    try:
        if args.interactive:
            return _interactive(client, cfg, ui)
        ui.info(f"[模型] {cfg.model}  [工作目录] {cfg.workspace}\n")
        run_agent(client, cfg, task, ui)
        print()
        return 0
    except DeepSeekError as e:
        ui.error(f"\n错误：{e}")
        return 1
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


def _interactive(client: DeepSeekClient, cfg: AgentConfig, ui: UI) -> int:
    ui.info(f"进入交互模式（模型：{cfg.model}，输入 /quit 或 Ctrl+C 退出）\n")
    system = build_system_prompt(str(cfg.workspace), cfg.system_prompt)
    history = [{"role": "system", "content": system}]
    while True:
        try:
            line = input("你> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit", "quit", "exit"):
            return 0
        if line in ("/clear",):
            history = [{"role": "system", "content": system}]
            ui.info("对话已清空。")
            continue
        try:
            history = run_agent(client, cfg, line, ui, history=history)
            print("\n")
        except DeepSeekError as e:
            ui.error(f"错误：{e}")


if __name__ == "__main__":
    raise SystemExit(main())
