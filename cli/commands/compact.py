"""/compact 命令 — 手动触发上下文压缩。

无参数: 优先 session memory compact，不可用则 full compact
有参数: 跳过 session memory，直接 full compact 并携带自定义摘要指令
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import RemoveMessage
from rich.console import Console

from core.context.compressor import CompressResult
from core.event_bus import AgentEvent, EventBus, EventType

if TYPE_CHECKING:
    from core.agent import AgentRuntime

logger = logging.getLogger(__name__)


def cmd_compact(
    console: Console,
    runtime: AgentRuntime,
    instruction_text: str = "",
) -> None:
    """手动触发上下文压缩。"""
    config = {"configurable": {"thread_id": runtime.session._thread_id or ""}}

    # 读取当前 state messages
    try:
        snapshot = runtime.graph.get_state(config)
    except Exception as exc:
        console.print(f"  [red]无法读取当前状态:[/red] {exc}")
        return

    messages = list(snapshot.values.get("messages", []))
    if len(messages) < 4:
        console.print("  [yellow]无法 compact：当前消息太少[/yellow]")
        return

    instruction_text = instruction_text.strip()
    session = runtime.session
    event_bus = runtime.event_bus
    turn = session.stats.turn_count

    if not instruction_text:
        # 无参数: 优先 session memory compact
        result = _try_session_memory_compact(
            runtime, messages, event_bus, turn,
        )
        if result is not None:
            _apply_compact_result(console, runtime, config, result, event_bus, turn)
            return

        # session memory 不可用，fallback 到 full compact
        console.print("  [dim]Session memory 不可用，尝试 full compact...[/dim]")

    # full compact（有参数或 fallback）
    compressor = runtime.compressor
    if compressor is None:
        console.print("  [red]无法 compact：compressor 未初始化[/red]")
        return

    try:
        result = compressor.compress(
            messages,
            reason="manual",
            custom_instructions=instruction_text or None,
        )
    except Exception as exc:
        console.print(f"  [red]Full compact 失败:[/red] {exc}")
        return

    if result is None:
        console.print("  [yellow]无法 compact：compressor 返回空结果[/yellow]")
        return

    # 发射事件
    event_bus.emit(AgentEvent(
        type=EventType.CONTEXT_COMPRESSED,
        data={
            "summary": result.summary_text,
            "removed_count": result.removed_count,
            "kept_count": result.kept_count,
            "trigger_reason": "manual",
            "pre_tokens": result.pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))
    event_bus.emit(AgentEvent(
        type=EventType.COMPACT_BOUNDARY,
        data={
            "reason": "manual",
            "pre_tokens": result.pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))
    event_bus.emit(AgentEvent(
        type=EventType.TRANSCRIPT_MESSAGE,
        data={
            "role": "system",
            "content": str(result.summary_message.content),
            "name": "compact_summary",
        },
        turn=turn,
    ))

    _apply_compact_result(console, runtime, config, result, event_bus, turn)


def _try_session_memory_compact(
    runtime: AgentRuntime,
    messages: list,
    event_bus: EventBus,
    turn: int,
) -> CompressResult | None:
    """尝试 session memory compact，返回 CompressResult 或 None。"""
    smm = runtime.session_memory_manager
    if smm is None:
        return None

    from config.settings import CONTEXT as CONTEXT_CONFIG

    status = smm.get_status()
    result = smm.try_session_memory_compact(
        messages=list(messages),
        status=status,
        threshold_tokens=runtime.session.stats.last_auto_compact_threshold or CONTEXT_CONFIG.get("token_limit", 65536),
        min_keep_tokens=CONTEXT_CONFIG.get("compression_preserve_min_tokens", 10000),
        max_keep_tokens=CONTEXT_CONFIG.get("compression_preserve_max_tokens", 40000),
    )
    if result is None:
        return None

    # 转换为 CompressResult
    from core.context.budget import estimate_message_tokens
    from core.nodes.reasoning import _session_memory_result_to_compress_result

    compress_result = _session_memory_result_to_compress_result(result, messages)

    # 发射事件
    pre_tokens = estimate_message_tokens(messages[:result.start_index])
    event_bus.emit(AgentEvent(
        type=EventType.CONTEXT_COMPRESSED,
        data={
            "summary": str(result.summary_message.content),
            "removed_count": result.start_index,
            "kept_count": len(messages) - result.start_index,
            "trigger_reason": "session_memory",
            "pre_tokens": pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))
    event_bus.emit(AgentEvent(
        type=EventType.COMPACT_BOUNDARY,
        data={
            "reason": "session_memory",
            "pre_tokens": pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))

    return compress_result


def _apply_compact_result(
    console: Console,
    runtime: AgentRuntime,
    config: dict,
    result: CompressResult,
    event_bus: EventBus,
    turn: int,
) -> None:
    """将压缩结果写回 graph state 并打印 CLI 输出。"""
    # 构造 message ops
    message_ops: list = [RemoveMessage(id=mid) for mid in result.remove_message_ids]
    message_ops.append(result.boundary_message)
    message_ops.append(result.summary_message)

    # 写回 graph state
    try:
        runtime.graph.update_state(config, {"messages": message_ops})
    except Exception as exc:
        console.print(f"  [red]写入压缩结果失败:[/red] {exc}")
        return

    # 更新 session stats
    runtime.session.stats.last_input_tokens = result.post_tokens

    reason_label = "session memory compact" if result.reason == "session_memory" else "full compact"
    console.print(
        f"  [green]✓ 已执行 {reason_label}[/green]"
        f" [dim]({result.pre_tokens:,} → {result.post_tokens:,} tokens)[/dim]"
    )
