"""Session transcript schema helpers."""

from __future__ import annotations

import time
from typing import Any

RECORD_SESSION_START = "session_start"
RECORD_SESSION_END = "session_end"
RECORD_TRANSCRIPT_MESSAGE = "transcript_message"
RECORD_COMPACT_BOUNDARY = "compact_boundary"
RECORD_TOOL_RESULT_ARTIFACT = "tool_result_artifact"
RECORD_SESSION_MEMORY_UPDATE = "session_memory_update"

RENDERABLE_RECORD_TYPES = {
    "thought",
    "tool_request",
    "tool_complete",
    "tool_diff",
    "tool_call",
    "approval_request",
    "approval_decision",
    RECORD_TRANSCRIPT_MESSAGE,
}


def _timestamp(timestamp: int | None = None) -> int:
    return timestamp if timestamp is not None else int(time.time() * 1000)


def make_session_start_record(
    *,
    session_id: str,
    thread_id: str,
    project: str,
    model: str,
    branch: str,
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_SESSION_START,
        "sessionId": session_id,
        "threadId": thread_id,
        "project": project,
        "model": model,
        "branch": branch,
        "timestamp": _timestamp(timestamp),
    }


def make_session_end_record(
    *,
    session_id: str,
    thread_id: str,
    stats: dict[str, Any],
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_SESSION_END,
        "sessionId": session_id,
        "threadId": thread_id,
        "stats": stats,
        "timestamp": _timestamp(timestamp),
    }


def make_transcript_message_record(
    *,
    role: str,
    content: Any,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning_content: str | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
    tool_use_result: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_TRANSCRIPT_MESSAGE,
        "role": role,
        "content": content,
        "tool_calls": tool_calls or [],
        "reasoning_content": reasoning_content,
        "tool_call_id": tool_call_id or "",
        "name": name or "",
        "toolUseResult": tool_use_result,
        "artifact": artifact,
        "timestamp": _timestamp(timestamp),
    }


def make_compact_boundary_record(
    *,
    reason: str,
    pre_tokens: int = 0,
    post_tokens: int = 0,
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_COMPACT_BOUNDARY,
        "reason": reason,
        "pre_tokens": pre_tokens,
        "post_tokens": post_tokens,
        "timestamp": _timestamp(timestamp),
    }


def make_tool_result_artifact_record(
    *,
    tool_call_id: str,
    name: str,
    artifact: dict[str, Any],
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_TOOL_RESULT_ARTIFACT,
        "tool_call_id": tool_call_id,
        "name": name,
        "artifact": artifact,
        "timestamp": _timestamp(timestamp),
    }


def make_session_memory_update_record(
    *,
    summary_path: str,
    last_summarized_message_id: str | None = None,
    tokens_at_last_extraction: int = 0,
    tool_calls_since_last_update: int = 0,
    turn: int = 0,
    timestamp: int | None = None,
) -> dict[str, Any]:
    return {
        "type": RECORD_SESSION_MEMORY_UPDATE,
        "summary_path": summary_path,
        "last_summarized_message_id": last_summarized_message_id,
        "tokens_at_last_extraction": tokens_at_last_extraction,
        "tool_calls_since_last_update": tool_calls_since_last_update,
        "turn": turn,
        "timestamp": _timestamp(timestamp),
    }


def get_record_type(record: dict[str, Any]) -> str:
    return str(record.get("type", ""))


def is_renderable_record(record: dict[str, Any]) -> bool:
    return get_record_type(record) in RENDERABLE_RECORD_TYPES


def is_transcript_message_record(record: dict[str, Any]) -> bool:
    return get_record_type(record) == RECORD_TRANSCRIPT_MESSAGE


def normalize_transcript_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["type"] = RECORD_TRANSCRIPT_MESSAGE
    normalized.setdefault("role", "")
    normalized.setdefault("content", "")
    normalized.setdefault("tool_calls", [])
    normalized.setdefault("reasoning_content", None)
    normalized.setdefault("tool_call_id", "")
    normalized.setdefault("name", "")
    normalized.setdefault("toolUseResult", None)
    normalized.setdefault("artifact", None)
    if "timestamp" not in normalized:
        normalized["timestamp"] = _timestamp()
    return normalized


def normalize_compact_boundary_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["type"] = RECORD_COMPACT_BOUNDARY
    normalized.setdefault("reason", "auto")
    normalized.setdefault("pre_tokens", 0)
    normalized.setdefault("post_tokens", 0)
    if "timestamp" not in normalized:
        normalized["timestamp"] = _timestamp()
    return normalized


def normalize_session_memory_update_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["type"] = RECORD_SESSION_MEMORY_UPDATE
    normalized.setdefault("summary_path", "")
    normalized.setdefault("last_summarized_message_id", None)
    normalized.setdefault("tokens_at_last_extraction", 0)
    normalized.setdefault("tool_calls_since_last_update", 0)
    normalized.setdefault("turn", 0)
    if "timestamp" not in normalized:
        normalized["timestamp"] = _timestamp()
    return normalized
