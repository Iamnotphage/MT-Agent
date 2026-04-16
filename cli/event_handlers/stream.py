"""EventBus 流式事件处理 — 渲染 + 录制

渲染规范:
  - LLM 文字: 白色 ⏺ 前缀, 后续行 4 空格缩进
  - 工具成功: 绿色 ⏺ + 工具名 + 参数 + 结果摘要
  - 工具失败: 红色 ⏺ + 工具名 + 错误信息
  - 并行工具: 缓冲所有事件, 全部完成后统一渲染
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rich.console import Console

from cli.utils.text import TOOL_DISPLAY, truncate
from core.event_bus import AgentEvent, EventBus, EventType

if TYPE_CHECKING:
    from core.session import SessionRecorder


@dataclass
class _ToolRecord:
    """单个工具调用的缓冲记录"""
    call_id: str
    tool_name: str
    arguments: dict = field(default_factory=dict)
    status: str = ""       # success / error / cancelled
    display: str = ""      # artifact["display"]
    error_msg: str = ""
    diff: Any = None


class StreamHandler:
    """订阅 EventBus 事件，实时渲染到 Console 并录制到 SessionRecorder。"""

    def __init__(self, console: Console, event_bus: EventBus, session: SessionRecorder) -> None:
        self._console = console
        self._session = session

        # LLM 流式输出状态
        self._streaming = False
        self._content_buf: list[str] = []
        self._thought_buf: list[str] = []

        # 工具批次缓冲 (线程安全)
        self._tool_records: dict[str, _ToolRecord] = {}  # call_id -> record
        self._expected_count = 0
        self._done_count = 0  # completed + cancelled
        self._lock = threading.Lock()

        # 订阅事件
        event_bus.subscribe(EventType.CONTENT, self.on_content)
        event_bus.subscribe(EventType.THOUGHT, self.on_thought)
        event_bus.subscribe(EventType.TOOL_CALL_REQUEST, self.on_tool_request)
        event_bus.subscribe(EventType.TOOL_CALL_COMPLETE, self.on_tool_complete)
        event_bus.subscribe(EventType.TOOL_LIVE_OUTPUT, self.on_tool_live_output)
        event_bus.subscribe(EventType.CONTEXT_COMPRESSED, self.on_context_compressed)
        event_bus.subscribe(EventType.APPROVAL_REQUEST, self.on_approval_request)
        event_bus.subscribe(EventType.APPROVAL_RESPONSE, self.on_approval_response)
        event_bus.subscribe(EventType.ERROR, self.on_error)
        event_bus.subscribe(EventType.TRANSCRIPT_MESSAGE, self.on_transcript_message)

    # ── 流式控制 ─────────────────────────────────────────────────

    def _end_content_stream(self) -> None:
        """仅结束 LLM 文字流式输出 (不 flush 工具缓冲)"""
        if self._streaming:
            self._console.print()
            self._streaming = False
        if self._thought_buf:
            self._session.record({"type": "thought", "text": "".join(self._thought_buf)})
            self._thought_buf.clear()
        if self._content_buf:
            self._content_buf.clear()

    def end_stream(self) -> None:
        """结束所有流式输出 (含工具缓冲 flush)"""
        self._end_content_stream()
        self._flush_tool_buffer()

    # ── LLM 内容输出: ⏺ 白色 + 缩进 ────────────────────────────

    def on_content(self, event: AgentEvent) -> None:
        text = event.data.get("text", "")
        if not text:
            return
        if not self._streaming:
            self._flush_tool_buffer()
            self._console.print()
            self._console.print("⏺ ", end="", style="bold white")
            self._streaming = True
        indented = text.replace("\n", "\n  ")
        self._console.print(indented, end="", highlight=False, markup=False)
        self._content_buf.append(text)

    def on_thought(self, event: AgentEvent) -> None:
        text = event.data.get("text", "")
        if not text:
            return
        self.end_stream()
        self._console.print(f"  [dim italic]{text}[/dim italic]", end="", highlight=False)
        self._thought_buf.append(text)

    # ── 工具事件: 缓冲 → 批量渲染 ──────────────────────────────

    def on_tool_request(self, event: AgentEvent) -> None:
        call_id = event.data.get("call_id", "")
        name = event.data.get("tool_name", "?")
        args = event.data.get("arguments", {})

        self._end_content_stream()

        with self._lock:
            self._tool_records[call_id] = _ToolRecord(
                call_id=call_id,
                tool_name=name,
                arguments=args,
            )
            self._expected_count += 1

        self._session.record({"type": "tool_request", "tool_name": name, "arguments": args})

    def on_tool_live_output(self, event: AgentEvent) -> None:
        if event.data.get("kind") == "diff":
            call_id = event.data.get("call_id", "")
            diff_obj = event.data["diff"]
            with self._lock:
                rec = self._tool_records.get(call_id)
                if rec:
                    rec.diff = diff_obj
            self._session.record({
                "type": "tool_diff",
                "tool_name": event.data.get("tool_name", ""),
                "unified_diff": diff_obj.unified_diff,
                "added": diff_obj.added,
                "removed": diff_obj.removed,
                "file_path": diff_obj.file_path,
                "is_new": diff_obj.is_new,
            })

    def on_tool_complete(self, event: AgentEvent) -> None:
        call_id = event.data.get("call_id", "")
        status = event.data.get("status", "success")
        display = event.data.get("display", "")
        error_msg = event.data.get("error_msg", "")

        flush_now = False
        with self._lock:
            rec = self._tool_records.get(call_id)
            if rec:
                rec.status = status
                rec.display = display
                rec.error_msg = error_msg
            self._done_count += 1
            if self._done_count >= self._expected_count > 0:
                flush_now = True

        self._session.record({
            "type": "tool_complete",
            "tool_name": event.data.get("tool_name", ""),
            "status": status,
            "display": display,
            "error_msg": error_msg,
        })

        if flush_now:
            self._flush_tool_buffer()

    # ── 渲染工具缓冲 ─────────────────────────────────────────────

    def _flush_tool_buffer(self) -> None:
        with self._lock:
            records = list(self._tool_records.values())
            self._tool_records.clear()
            self._expected_count = 0
            self._done_count = 0

        for rec in records:
            self._render_tool_block(rec)

    def _render_tool_block(self, rec: _ToolRecord) -> None:
        name = TOOL_DISPLAY.get(rec.tool_name, rec.tool_name)
        file_path = rec.arguments.get("file_path")

        if rec.status == "error":
            dot_style = "bold red"
        elif rec.status == "cancelled":
            dot_style = "bold red"
        else:
            dot_style = "bold green"

        # header: ⏺ ToolName(key_arg)
        if file_path:
            self._console.print(
                f"\n[{dot_style}]⏺[/{dot_style}] [bold]{name}[/bold]({file_path})"
            )
        else:
            args_brief = ", ".join(f"{k}={truncate(v)}" for k, v in rec.arguments.items())
            self._console.print(
                f"\n[{dot_style}]⏺[/{dot_style}] [bold]{name}[/bold]"
                f"[dim]({args_brief})[/dim]"
            )

        # body: diff / error / display
        if rec.diff is not None:
            from cli.diff_renderer import render_diff
            render_diff(self._console, rec.diff)
        elif rec.status == "error":
            self._console.print(f"  [red]{rec.error_msg or 'Error'}[/red]")
        elif rec.status == "cancelled":
            self._console.print(f"  [yellow]已取消[/yellow]")
        elif rec.display:
            self._console.print(f"  [dim]{rec.display}[/dim]")

    # ── 审批事件 ─────────────────────────────────────────────────

    def on_approval_request(self, event: AgentEvent) -> None:
        self._session.record({
            "type": "approval_request",
            "call_id": event.data.get("call_id", ""),
            "tool_name": event.data.get("tool_name", ""),
            "arguments": event.data.get("arguments", {}),
            "risk_level": event.data.get("risk_level", ""),
        })

    def on_approval_response(self, event: AgentEvent) -> None:
        decisions = event.data.get("decisions", {})
        flush_now = False
        with self._lock:
            for call_id, approved in decisions.items():
                if not approved:
                    rec = self._tool_records.get(call_id)
                    if rec:
                        rec.status = "cancelled"
                    self._done_count += 1
            flush_now = self._done_count >= self._expected_count > 0

        self._session.record({
            "type": "approval_decision",
            "decisions": decisions,
        })

        if flush_now:
            self._flush_tool_buffer()

    # ── 其他事件 ─────────────────────────────────────────────────

    def on_context_compressed(self, event: AgentEvent) -> None:
        self.end_stream()
        removed = event.data.get("removed_count", 0)
        kept = event.data.get("kept_count", 0)
        summary = event.data.get("summary", "")
        self._session.record({
            "type": "compression",
            "summary": summary,
            "removed_count": removed,
            "kept_count": kept,
        })
        self._console.print(
            f"\n  [bold yellow]⚡ 上下文已压缩[/bold yellow] "
            f"[dim]({removed} 条消息摘要化, 保留 {kept} 条)[/dim]"
        )

    def on_error(self, event: AgentEvent) -> None:
        self.end_stream()
        err = event.data.get("error", "未知错误")
        self._console.print(f"\n  [red bold]ERROR[/red bold] {err}")

    def on_transcript_message(self, event: AgentEvent) -> None:
        record = dict(event.data or {})
        if not record:
            return
        record["type"] = "transcript_message"
        self._session.record(record)
