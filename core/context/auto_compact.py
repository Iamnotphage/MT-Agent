"""Auto compact policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.context.budget import budget_snapshot

QuerySource = Literal[
    "interactive",
    "resume",
    "session_memory",
    "compact",
    "reactive_retry",
]

MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3
AUTOCOMPACT_SKIPPED_SOURCES = {"session_memory", "compact"}


@dataclass(frozen=True)
class AutoCompactDecision:
    should_compact: bool
    force_compact: bool
    blocked_by_circuit_breaker: bool
    skip_reason: str | None
    trigger_reason: str | None
    query_source: QuerySource
    raw_input_tokens: int
    effective_context_limit: int
    auto_compact_threshold: int
    tokens_until_compact: int
    consecutive_failures: int


class AutoCompactPolicy:
    """Evaluate whether auto compact should run for the current turn."""

    def __init__(
        self,
        *,
        max_consecutive_failures: int = MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
        skipped_sources: set[str] | None = None,
    ) -> None:
        self._max_consecutive_failures = max_consecutive_failures
        self._skipped_sources = skipped_sources or AUTOCOMPACT_SKIPPED_SOURCES

    @property
    def max_consecutive_failures(self) -> int:
        return self._max_consecutive_failures

    def evaluate(
        self,
        *,
        raw_input_tokens: int,
        token_limit: int,
        reserved_summary_tokens: int,
        buffer_tokens: int,
        query_source: QuerySource,
        consecutive_failures: int,
        force_compact: bool = False,
    ) -> AutoCompactDecision:
        snapshot = budget_snapshot(
            [],
            token_limit=token_limit,
            reserved_summary_tokens=reserved_summary_tokens,
            buffer_tokens=buffer_tokens,
        )
        threshold = snapshot["auto_compact_threshold"]
        effective_limit = snapshot["effective_context_limit"]
        tokens_until_compact = max(threshold - raw_input_tokens, 0)

        if force_compact:
            return AutoCompactDecision(
                should_compact=True,
                force_compact=True,
                blocked_by_circuit_breaker=False,
                skip_reason=None,
                trigger_reason="reactive_retry",
                query_source=query_source,
                raw_input_tokens=raw_input_tokens,
                effective_context_limit=effective_limit,
                auto_compact_threshold=threshold,
                tokens_until_compact=tokens_until_compact,
                consecutive_failures=consecutive_failures,
            )

        if query_source in self._skipped_sources:
            return AutoCompactDecision(
                should_compact=False,
                force_compact=False,
                blocked_by_circuit_breaker=False,
                skip_reason=f"query_source:{query_source}",
                trigger_reason=None,
                query_source=query_source,
                raw_input_tokens=raw_input_tokens,
                effective_context_limit=effective_limit,
                auto_compact_threshold=threshold,
                tokens_until_compact=tokens_until_compact,
                consecutive_failures=consecutive_failures,
            )

        if consecutive_failures >= self._max_consecutive_failures:
            return AutoCompactDecision(
                should_compact=False,
                force_compact=False,
                blocked_by_circuit_breaker=True,
                skip_reason="circuit_breaker_open",
                trigger_reason=None,
                query_source=query_source,
                raw_input_tokens=raw_input_tokens,
                effective_context_limit=effective_limit,
                auto_compact_threshold=threshold,
                tokens_until_compact=tokens_until_compact,
                consecutive_failures=consecutive_failures,
            )

        should_compact = raw_input_tokens >= threshold
        return AutoCompactDecision(
            should_compact=should_compact,
            force_compact=False,
            blocked_by_circuit_breaker=False,
            skip_reason=None if should_compact else "below_threshold",
            trigger_reason="threshold_exceeded" if should_compact else None,
            query_source=query_source,
            raw_input_tokens=raw_input_tokens,
            effective_context_limit=effective_limit,
            auto_compact_threshold=threshold,
            tokens_until_compact=tokens_until_compact,
            consecutive_failures=consecutive_failures,
        )
