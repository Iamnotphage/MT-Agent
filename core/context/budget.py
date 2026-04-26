"""Context budget helpers."""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from core.utils.tokens import estimate_tokens


def normalize_message_content(content: object) -> str:
    """Normalize message content for heuristic token estimation."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def estimate_message_tokens(messages: list[BaseMessage]) -> int:
    """Estimate token usage for a list of LangChain messages."""
    total = 0
    for msg in messages:
        role = getattr(msg, "type", "")
        content = normalize_message_content(getattr(msg, "content", ""))
        total += estimate_tokens(f"[{role}] {content}")
    return total


def effective_context_limit(
    token_limit: int,
    reserved_summary_tokens: int = 20_000,
) -> int:
    """Return the effective context window after reserving summary headroom."""
    return max(token_limit - reserved_summary_tokens, 1)


def auto_compact_threshold(
    token_limit: int,
    reserved_summary_tokens: int = 20_000,
    buffer_tokens: int = 13_000,
) -> int:
    """Return the token threshold that should trigger auto compact."""
    effective_limit = effective_context_limit(token_limit, reserved_summary_tokens)
    return max(effective_limit - buffer_tokens, 1)


def budget_snapshot(
    messages: list[BaseMessage],
    token_limit: int,
    reserved_summary_tokens: int = 20_000,
    buffer_tokens: int = 13_000,
) -> dict[str, int]:
    """Compute the current budget snapshot for a message list."""
    raw_input_tokens = estimate_message_tokens(messages)
    effective_limit = effective_context_limit(token_limit, reserved_summary_tokens)
    compact_threshold = auto_compact_threshold(
        token_limit,
        reserved_summary_tokens,
        buffer_tokens,
    )
    return {
        "raw_input_tokens": raw_input_tokens,
        "effective_context_limit": effective_limit,
        "auto_compact_threshold": compact_threshold,
        "tokens_until_compact": max(compact_threshold - raw_input_tokens, 0),
    }
