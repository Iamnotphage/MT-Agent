"""Session statistics models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionStats:
    """会话期间的实时统计，退出时渲染到 CLI。"""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    start_time: float = field(default_factory=time.time)
    model: str = ""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    last_input_tokens: int = 0
    last_effective_context_limit: int = 0
    last_auto_compact_threshold: int = 0
    last_tokens_until_compact: int = 0
    last_tool_result_chars: int = 0
    compression_failure_count: int = 0

    turn_count: int = 0
    prompt_count: int = 0

    tool_calls_total: int = 0
    tool_calls_success: int = 0
    tool_calls_failed: int = 0
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.start_time

    def record_llm_usage(self, input_tokens: int, output_tokens: int, model: str = "") -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.last_input_tokens = input_tokens
        self.turn_count += 1
        if model:
            self.model = model

    def record_tool_call(self, tool_name: str, success: bool) -> None:
        self.tool_calls_total += 1
        if success:
            self.tool_calls_success += 1
        else:
            self.tool_calls_failed += 1
        self.tool_calls_by_name[tool_name] = self.tool_calls_by_name.get(tool_name, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "duration_ms": int(self.duration_seconds * 1000),
            "turns": self.turn_count,
            "prompts": self.prompt_count,
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "total": self.total_tokens,
            },
            "context": {
                "last_input_tokens": self.last_input_tokens,
                "effective_context_limit": self.last_effective_context_limit,
                "auto_compact_threshold": self.last_auto_compact_threshold,
                "tokens_until_compact": self.last_tokens_until_compact,
                "last_tool_result_chars": self.last_tool_result_chars,
                "compression_failure_count": self.compression_failure_count,
            },
            "tools": {
                "total": self.tool_calls_total,
                "success": self.tool_calls_success,
                "failed": self.tool_calls_failed,
                "by_name": dict(self.tool_calls_by_name),
            },
        }
