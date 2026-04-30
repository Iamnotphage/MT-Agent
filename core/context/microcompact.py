"""Time-based microcompact — query-view projection layer.

Clears old whitelisted tool results from the current model-facing message view
after a long pause, without mutating canonical transcript JSONL or artifacts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

MICROCOMPACT_TOOL_WHITELIST = {
    "read_file",
    "grep",
    "glob",
    "ls",
    "shell",
    "write_file",
    "edit_file",
}
MICROCOMPACT_GAP_THRESHOLD_MINUTES = 60
MICROCOMPACT_KEEP_RECENT = 5
MICROCOMPACT_PLACEHOLDER = "[Old tool result content cleared]"


@dataclass(frozen=True)
class MicrocompactResult:
    triggered: bool
    cleared_count: int
    messages: list[BaseMessage]


def _is_whitelisted_tool_message(message: BaseMessage) -> bool:
    return (
        isinstance(message, ToolMessage)
        and str(getattr(message, "name", "") or "") in MICROCOMPACT_TOOL_WHITELIST
    )


def _has_long_gap(
    *,
    now_ts_ms: int,
    last_assistant_ts_ms: int | None,
    gap_threshold_minutes: int,
) -> bool:
    if not last_assistant_ts_ms:
        return False
    return now_ts_ms - last_assistant_ts_ms >= gap_threshold_minutes * 60 * 1000


def find_last_assistant_timestamp_ms(messages: list[BaseMessage]) -> int | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            ts = getattr(message, "response_metadata", {}).get("timestamp_ms")
            if isinstance(ts, (int, float)):
                return int(ts)
    return None


def maybe_time_based_microcompact(
    messages: list[BaseMessage],
    *,
    now_ts_ms: int | None = None,
    gap_threshold_minutes: int = MICROCOMPACT_GAP_THRESHOLD_MINUTES,
    keep_recent: int = MICROCOMPACT_KEEP_RECENT,
) -> MicrocompactResult:
    if now_ts_ms is None:
        now_ts_ms = int(time.time() * 1000)

    last_assistant_ts_ms = find_last_assistant_timestamp_ms(messages)
    if not _has_long_gap(
        now_ts_ms=now_ts_ms,
        last_assistant_ts_ms=last_assistant_ts_ms,
        gap_threshold_minutes=gap_threshold_minutes,
    ):
        return MicrocompactResult(triggered=False, cleared_count=0, messages=list(messages))

    eligible_indices = [
        idx
        for idx, msg in enumerate(messages)
        if _is_whitelisted_tool_message(msg)
        and str(msg.content or "") != MICROCOMPACT_PLACEHOLDER
    ]
    if len(eligible_indices) <= keep_recent:
        return MicrocompactResult(triggered=False, cleared_count=0, messages=list(messages))

    keep_set = set(eligible_indices[-keep_recent:]) if keep_recent > 0 else set()
    result: list[BaseMessage] = []
    cleared_count = 0

    for idx, msg in enumerate(messages):
        if idx in keep_set or idx not in eligible_indices:
            result.append(msg)
            continue
        copied = ToolMessage(
            content=MICROCOMPACT_PLACEHOLDER,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
        )
        result.append(copied)
        cleared_count += 1

    return MicrocompactResult(triggered=cleared_count > 0, cleared_count=cleared_count, messages=result)
