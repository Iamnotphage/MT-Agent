"""MT-AutoOptimize — REPL 交互循环"""

from __future__ import annotations

from rich.console import Console

PROMPT_STYLE = "#847ACE"
PROMPT_SYMBOL = "❯"


class Repl:
    """交互式 读取-执行-打印 循环"""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.running = True

    def _prompt(self) -> str:
        return f"[{PROMPT_STYLE}]{PROMPT_SYMBOL}[/{PROMPT_STYLE}] "

    def _handle_command(self, cmd: str) -> bool:
        """处理 /command。返回 True 继续循环，False 退出。"""
        match cmd:
            case "/help" | "/h" | "/?":
                self._show_help()
            case "/exit" | "/quit" | "/q":
                self.console.print("\n  [dim]再见![/dim]\n")
                return False
            case "/version" | "/v":
                from cli.app import VERSION

                self.console.print(f"  [dim]v{VERSION}[/dim]")
            case "/clear":
                self.console.clear()
            case _:
                self.console.print(f"  [red]未知命令:[/red] {cmd}")
                self.console.print("  [dim]输入 /help 查看可用命令[/dim]")
        return True

    def _show_help(self) -> None:
        self.console.print()
        self.console.print("  [bold]可用命令[/bold]")
        self.console.print()
        cmds = [
            ("/help, /h", "显示帮助信息"),
            ("/version, /v", "显示版本号"),
            ("/clear", "清屏"),
            ("/exit, /q", "退出"),
        ]
        for name, desc in cmds:
            self.console.print(
                f"    [{PROMPT_STYLE}]{name:<16}[/{PROMPT_STYLE}] [dim]{desc}[/dim]"
            )
        self.console.print()
        self.console.print("  [bold]使用说明[/bold]")
        self.console.print()
        self.console.print("  [dim]直接输入自然语言描述优化需求，Agent 将自动执行：[/dim]")
        self.console.print("  [dim]  1. 源码分析  2. 代码优化  3. 编译测试验证[/dim]")
        self.console.print()

    def run(self) -> None:
        while self.running:
            try:
                user_input = self.console.input(self._prompt())
            except EOFError:
                break
            except KeyboardInterrupt:
                self.console.print()
                continue

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                if not self._handle_command(stripped.lower()):
                    break
                continue

            self.console.print(f"\n  [dim] 处理中...[/dim] (Agent 功能开发中)\n")
