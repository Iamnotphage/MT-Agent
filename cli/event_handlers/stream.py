"""EventBus 流式事件处理 — 渲染 + 录制

渲染规范:
  - LLM 文字: 白色 ⏺ 前缀, 后续行 4 空格缩进
  - 工具成功: 绿色 ⏺ + 工具名 + 参数 + 结果摘要
  - 工具失败: 红色 ⏺ + 工具名 + 错误信息
  - 并行工具: 缓冲所有事件, 全部完成后统一渲染
  - 思考中: 动画 spinner + 计时器
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from cli.utils.text import TOOL_DISPLAY, truncate
from core.event_bus import AgentEvent, EventBus, EventType
from core.session.schema import make_session_memory_update_record
from tools.workspace_paths import display_path

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

    # Spinner 动画帧（类似 Claude Code）
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, console: Console, event_bus: EventBus, session: SessionRecorder, *, workspace: str | Path | None = None) -> None:
        self._console = console
        self._session = session
        self._workspace = Path(workspace) if workspace else None

        # LLM 流式输出状态
        self._streaming = False
        self._thought_streaming = False
        self._content_buf: list[str] = []
        self._thought_buf: list[str] = []

        # 思考动画状态
        self._thinking = False
        self._thinking_start_time = 0.0
        self._thinking_thread: threading.Thread | None = None
        self._thinking_stop = threading.Event()

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
        event_bus.subscribe(EventType.TOOL_RESULT_PERSISTED, self.on_tool_result_persisted)
        event_bus.subscribe(EventType.CONTEXT_COMPRESSED, self.on_context_compressed)
        event_bus.subscribe(EventType.COMPACT_BOUNDARY, self.on_compact_boundary)
        event_bus.subscribe(EventType.APPROVAL_REQUEST, self.on_approval_request)
        event_bus.subscribe(EventType.APPROVAL_RESPONSE, self.on_approval_response)
        event_bus.subscribe(EventType.ERROR, self.on_error)
        event_bus.subscribe(EventType.TRANSCRIPT_MESSAGE, self.on_transcript_message)
        event_bus.subscribe(EventType.SESSION_MEMORY_UPDATED, self.on_session_memory_updated)

    # ── 流式控制 ─────────────────────────────────────────────────

    def start_thinking(self) -> None:
        """手动启动思考动画（从 REPL 调用）"""
        self._start_thinking_animation()

    def _start_thinking_animation(self) -> None:
        """启动思考动画（在后台线程中运行）"""
        if self._thinking:
            return

        self._thinking = True
        self._thinking_start_time = time.time()
        self._thinking_stop.clear()

        def _animate():
            frame_idx = 0
            while not self._thinking_stop.is_set():
                elapsed = time.time() - self._thinking_start_time
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                seconds = int(elapsed % 60)

                # 格式化时间
                if hours > 0:
                    time_str = f"{hours}h{minutes}m{seconds}s"
                elif minutes > 0:
                    time_str = f"{minutes}m{seconds}s"
                else:
                    time_str = f"{seconds}s"

                # 渲染动画帧（橙色）
                spinner = self.SPINNER_FRAMES[frame_idx % len(self.SPINNER_FRAMES)]
                line = f"{spinner} Thinking ({time_str})"

                # 清除当前行并重新渲染
                import sys
                sys.stdout.write(f"\r{' ' * 80}\r")  # 先清除
                sys.stdout.flush()

                self._console.print(
                    f"[#FFA500]{line}[/#FFA500]",
                    end="",
                    highlight=False
                )

                frame_idx += 1
                time.sleep(0.1)  # 100ms 更新一次

        self._thinking_thread = threading.Thread(target=_animate, daemon=True)
        self._thinking_thread.start()

    def _stop_thinking_animation(self) -> None:
        """停止思考动画"""
        if not self._thinking:
            return

        self._thinking_stop.set()
        if self._thinking_thread:
            self._thinking_thread.join(timeout=0.5)

        # 清除动画行
        import sys
        sys.stdout.write(f"\r{' ' * 80}\r")
        sys.stdout.flush()

        self._thinking = False

    def _end_content_stream(self) -> None:
        """仅结束 LLM 文字流式输出 (不 flush 工具缓冲)"""
        self._stop_thinking_animation()
        if self._streaming:
            self._console.print()
            self._streaming = False
        if self._thought_streaming:
            self._console.print()
            self._thought_streaming = False
        if self._thought_buf:
            self._thought_buf.clear()
        if self._content_buf:
            self._content_buf.clear()

    def end_stream(self) -> None:
        """结束所有流式输出 (含工具缓冲 flush)"""
        self._end_content_stream()
        self._flush_tool_buffer()

    def pause_for_prompt(self) -> None:
        """Stop active content/thought streaming without flushing buffered tool state."""
        self._end_content_stream()

    # ── LLM 内容输出: ⏺ 白色 + 缩进 ────────────────────────────

    def on_content(self, event: AgentEvent) -> None:
        text = event.data.get("text", "")
        if not text:
            return
        if not self._streaming:
            self._stop_thinking_animation()  # 停止思考动画
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

        self._stop_thinking_animation()
        if self._streaming:
            self._console.print()
            self._streaming = False

        if not self._thought_streaming:
            self._flush_tool_buffer()
            self._console.print()
            self._console.print("  💭 ", end="", style="dim italic")
            self._thought_streaming = True

        rendered = text.replace("\n", "\n    ")
        self._console.print(rendered, end="", style="dim italic", highlight=False, markup=False)
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

            # 工具调用时也停止思考动画
            if self._expected_count == 1:
                self._stop_thinking_animation()

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

    def on_tool_result_persisted(self, event: AgentEvent) -> None:
        return

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
        if file_path and self._workspace:
            file_path = display_path(self._workspace, Path(file_path))

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
        self._console.print(
            f"\n  [bold yellow]⚡ 上下文已压缩[/bold yellow] "
            f"[dim]({removed} 条消息摘要化, 保留 {kept} 条)[/dim]"
        )

    def on_compact_boundary(self, event: AgentEvent) -> None:
        self._session.record({
            "type": "compact_boundary",
            "reason": event.data.get("reason", "auto"),
            "pre_tokens": event.data.get("pre_tokens", 0),
            "post_tokens": event.data.get("post_tokens", 0),
        })

    def on_session_memory_updated(self, event: AgentEvent) -> None:
        self._session.record(make_session_memory_update_record(
            summary_path=event.data.get("summary_path", ""),
            last_summarized_message_id=event.data.get("last_summarized_message_id"),
            tokens_at_last_extraction=event.data.get("tokens_at_last_extraction", 0),
            tool_calls_since_last_update=event.data.get("tool_calls_since_last_update", 0),
            turn=event.data.get("turn", 0),
        ))

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
