"""Helpers for preserving message invariants during compaction."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from core.context.budget import estimate_message_tokens

COMPACT_BOUNDARY_PREFIX = "<compact_boundary "
SUMMARY_PREFIX = "<conversation_history_summary>"


def is_compact_boundary_message(message: BaseMessage) -> bool:
    return isinstance(message, HumanMessage) and str(message.content or "").startswith(COMPACT_BOUNDARY_PREFIX)


def find_last_compact_boundary(messages: list[BaseMessage]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        if is_compact_boundary_message(messages[idx]):
            return idx
    return None


def find_compaction_working_start(messages: list[BaseMessage]) -> int:
    boundary_idx = find_last_compact_boundary(messages)
    if boundary_idx is None:
        return 0
    next_idx = boundary_idx + 1
    if next_idx < len(messages):
        next_message = messages[next_idx]
        if isinstance(next_message, HumanMessage) and str(next_message.content or "").startswith(SUMMARY_PREFIX):
            return next_idx + 1
    return boundary_idx + 1


def adjust_index_to_preserve_tool_pairs(
    messages: list[BaseMessage],
    index: int,
) -> int:
    if index <= 0 or index >= len(messages):
        return index

    current = messages[index]
    if isinstance(current, ToolMessage):
        probe = index - 1
        while probe >= 0:
            prev = messages[probe]
            if isinstance(prev, ToolMessage):
                probe -= 1
                continue
            if isinstance(prev, AIMessage) and prev.tool_calls:
                return probe
            break

    prev = messages[index - 1]
    if isinstance(prev, AIMessage) and prev.tool_calls:
        return index - 1

    return index


def adjust_index_to_preserve_message_groups(
    messages: list[BaseMessage],
    index: int,
) -> int:
    if index <= 0 or index >= len(messages):
        return index

    current_id = getattr(messages[index], "id", None)
    if not current_id:
        return index

    adjusted = index
    while adjusted > 0 and getattr(messages[adjusted - 1], "id", None) == current_id:
        adjusted -= 1
    return adjusted


def adjust_index_to_respect_boundary(
    messages: list[BaseMessage],
    index: int,
) -> int:
    boundary_idx = find_last_compact_boundary(messages)
    if boundary_idx is None:
        return index
    return max(index, boundary_idx + 1)


def find_safe_split_index(
    messages: list[BaseMessage],
    *,
    min_keep_tokens: int,
    max_keep_tokens: int,
) -> int | None:
    if len(messages) < 4:
        return None

    lower_bound = find_compaction_working_start(messages)
    if len(messages) - lower_bound < 3:
        return None

    keep_tokens = 0
    split_idx = len(messages)
    for idx in range(len(messages) - 1, lower_bound - 1, -1):
        keep_tokens += estimate_message_tokens([messages[idx]])
        split_idx = idx
        if keep_tokens >= min_keep_tokens:
            break

    if split_idx <= lower_bound:
        return None

    adjusted = adjust_index_to_preserve_tool_pairs(messages, split_idx)
    adjusted = adjust_index_to_preserve_message_groups(messages, adjusted)
    adjusted = adjust_index_to_respect_boundary(messages, adjusted)

    if adjusted <= lower_bound:
        return None
    if adjusted >= len(messages):
        return None
    return adjusted
