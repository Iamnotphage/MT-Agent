"""MT-AutoOptimize — 交互式 CLI 入口"""

from __future__ import annotations

import asyncio
import logging
import os

from rich.console import Console
from rich.text import Text

from cli.repl import Repl

logger = logging.getLogger(__name__)

VERSION = "0.1.0"

GRADIENT = [
    (71, 150, 228),   # #4796E4
    (132, 122, 206),  # #847ACE
    (195, 103, 127),  # #C3677F
]

_BODY = [
    "████         ██████   ██████ █████████         █████     ███    ███ █████████  ████████ ",
    "  ████        ██████ ██████     ███           ██   ██    ███    ███    ███    ███    ███",
    "    ████      ███ █████ ███     ███          ███   ███   ███    ███    ███    ███    ███",
    "      ████    ███  ███  ███     ███   ████  ███████████  ███    ███    ███    ███    ███",
    "    ████      ███       ███     ███         ███     ███  ███    ███    ███    ███    ███",
    "  ████        ███       ███     ███         ███     ███  ███    ███    ███    ███    ███",
    "████         █████     █████    ███        █████   █████  ████████     ███     ████████ ",
]

_SHADOW_DY, _SHADOW_DX = 1, -1
_SHADOW_CHAR = "░"
_SHADOW_STYLE = "#555555"


def _has_block(r: int, c: int) -> bool:
    if 0 <= r < len(_BODY):
        line = _BODY[r]
        return 0 <= c < len(line) and line[c] == "█"
    return False


def _lerp(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _gradient_at(pos: float) -> str:
    """pos ∈ [0, 1] → hex color along GRADIENT stops."""
    pos = max(0.0, min(1.0, pos))
    seg = pos * (len(GRADIENT) - 1)
    idx = min(int(seg), len(GRADIENT) - 2)
    return _lerp(GRADIENT[idx], GRADIENT[idx + 1], seg - idx)


def render_banner(console: Console) -> None:
    dy, dx = _SHADOW_DY, _SHADOW_DX
    body_w = max(len(ln) for ln in _BODY)
    left_pad = max(0, -dx)
    total_h = len(_BODY) + abs(dy)
    total_w = body_w + left_pad

    for r in range(total_h):
        text = Text()
        for c in range(total_w):
            bc = c - left_pad
            if _has_block(r, bc):
                text.append("█", style=f"bold {_gradient_at(bc / max(body_w - 1, 1))}")
            elif _has_block(r - dy, bc - dx):
                text.append(_SHADOW_CHAR, style=_SHADOW_STYLE)
            else:
                text.append(" ")
        console.print(text)


# ── Agent 组装 ──────────────────────────────────────────────────


def _make_sync_executor(registry):
    """将 async ToolRegistry.execute 桥接为 sync (tool_name, args) -> str"""
    def executor(tool_name: str, arguments: dict) -> str:
        result = asyncio.run(registry.execute(tool_name, arguments))
        if result.error:
            raise RuntimeError(result.error)
        return result.output
    return executor


def _build_agent(console: Console):
    """组装完整的 Agent: Config → LLM → EventBus → Registry → Graph"""
    from langgraph.checkpoint.memory import MemorySaver

    from core.config import load_app_config
    from core.event_bus import EventBus
    from core.graph import build_agent_graph
    from core.llm import create_chat_model
    from tools import ReadFileTool, ToolRegistry

    cfg = load_app_config()

    llm = create_chat_model(cfg["code_llm"], env_prefix="CODE_LLM")

    event_bus = EventBus()

    registry = ToolRegistry()
    workspace = os.getcwd()
    registry.register(ReadFileTool(workspace=workspace))

    graph = build_agent_graph(
        llm=llm,
        event_bus=event_bus,
        tool_schemas=registry.schemas,
        executor=_make_sync_executor(registry),
        checkpointer=MemorySaver(),
    )

    console.print(f"  [dim]工作目录  {workspace}[/dim]")
    console.print(f"  [dim]已注册工具  {', '.join(registry.names)}[/dim]")
    console.print()

    return graph, event_bus


# ── App 入口 ────────────────────────────────────────────────────


class App:
    """MT-AutoOptimize 交互式 CLI"""

    def __init__(self) -> None:
        self.console = Console()

    def show_welcome(self) -> None:
        self.console.print()
        render_banner(self.console)
        self.console.print()
        self.console.print(f"  [bold]MT-AutoOptimize[/bold]  [dim]v{VERSION}[/dim]")
        self.console.print("  [dim]MT-3000 AI Coding Agent  ·  分析 → 优化 → 编译[/dim]")
        self.console.print()

    def run(self) -> None:
        self.show_welcome()

        try:
            graph, event_bus = _build_agent(self.console)
        except Exception as e:
            self.console.print(f"  [red]Agent 初始化失败:[/red] {e}")
            self.console.print("  [dim]请检查 config.json 或环境变量配置[/dim]\n")
            return

        self.console.print("  [dim]输入自然语言描述需求，或输入 /help 查看帮助[/dim]")
        self.console.print()

        repl = Repl(self.console, graph=graph, event_bus=event_bus)
        repl.run()


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
        format="%(name)s %(levelname)s: %(message)s",
    )
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
