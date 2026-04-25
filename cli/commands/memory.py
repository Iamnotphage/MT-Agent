"""/memory 命令处理"""

from __future__ import annotations

from rich.console import Console

from core.memory import MemoryManager


def cmd_memory(console: Console, mm: MemoryManager, args: list[str]) -> None:
    sub = args[0] if args else "list"

    if sub == "list":
        memories = mm.get_memories()
        if not memories:
            console.print("  [dim]暂无记忆。使用 /memory add <fact> 添加。[/dim]")
            return
        console.print()
        console.print(f"  [bold]Agent 记忆[/bold] ({len(memories)} 条)")
        console.print()
        for i, m in enumerate(memories, 1):
            console.print(f"    [dim]{i}.[/dim] {m}")
        console.print()

    elif sub == "add":
        fact = " ".join(args[1:]).strip() if len(args) > 1 else ""
        if not fact:
            console.print("  [red]用法:[/red] /memory add <要记住的内容>")
            return
        if mm.save_memory(fact) is None:
            console.print("  [red]✗[/red] 记忆内容不能为空")
            return
        console.print(f"  [green]✓[/green] 已保存记忆: {fact}")

    elif sub == "remove":
        if len(args) < 2:
            console.print("  [red]用法:[/red] /memory remove <序号>")
            return
        try:
            idx = int(args[1]) - 1
        except ValueError:
            console.print("  [red]序号必须是数字[/red]")
            return
        ok, _ = mm.remove_memory(idx)
        if ok:
            console.print(f"  [green]✓[/green] 已删除第 {idx + 1} 条记忆")
        else:
            console.print(f"  [red]✗[/red] 序号 {idx + 1} 不存在")

    else:
        console.print(f"  [red]未知子命令:[/red] /memory {sub}")
        console.print("  [dim]用法: /memory list | add <fact> | remove <n>[/dim]")
