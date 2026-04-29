"""Session memory management and compaction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from core.context.budget import estimate_message_tokens
from core.context.compressor import ContextCompressor
from core.context.message_invariants import (
    adjust_index_to_preserve_message_groups,
    adjust_index_to_preserve_tool_pairs,
    adjust_index_to_respect_boundary,
    find_compaction_working_start,
)
from core.session.artifacts import get_session_artifact_dir, get_session_memory_dir
from prompts.session_memory_prompt import (
    DEFAULT_SESSION_MEMORY_TEMPLATE,
    SESSION_MEMORY_UPDATE_SYSTEM_PROMPT,
    SESSION_MEMORY_UPDATE_USER_PROMPT,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


INITIAL_MEMORY_EXTRACTION_TOKENS = 10_000
MIN_TOKENS_BETWEEN_MEMORY_UPDATES = 5_000
MIN_TOOL_CALLS_BETWEEN_MEMORY_UPDATES = 3
SESSION_MEMORY_SUMMARY_PREFIX = "<session_memory_summary "
SESSION_MEMORY_FILENAME = "summary.md"


@dataclass
class SessionMemoryStatus:
    summary_path: str | None = None
    last_summarized_message_id: str | None = None
    tokens_at_last_extraction: int = 0
    tool_calls_since_last_update: int = 0
    last_update_turn: int = 0


@dataclass
class SessionMemoryUpdateResult:
    summary_path: str
    summary_text: str
    last_summarized_message_id: str | None
    tokens_at_last_extraction: int
    tool_calls_since_last_update: int
    last_update_turn: int


@dataclass
class SessionMemoryCompactResult:
    boundary_message: HumanMessage
    summary_message: HumanMessage
    compacted_messages: list[BaseMessage]
    last_summarized_message_id: str | None
    start_index: int
    kept_tokens: int
    post_tokens: int


def should_extract_memory(
    *,
    current_tokens: int,
    tokens_at_last_extraction: int,
    tool_calls_since_last_update: int,
    last_turn_has_tool_calls: bool,
) -> bool:
    if tokens_at_last_extraction <= 0:
        return current_tokens >= INITIAL_MEMORY_EXTRACTION_TOKENS

    if current_tokens - tokens_at_last_extraction < MIN_TOKENS_BETWEEN_MEMORY_UPDATES:
        return False

    if not last_turn_has_tool_calls:
        return True

    return tool_calls_since_last_update >= MIN_TOOL_CALLS_BETWEEN_MEMORY_UPDATES


def is_session_memory_summary_message(message: BaseMessage) -> bool:
    return isinstance(message, HumanMessage) and str(message.content or "").startswith(SESSION_MEMORY_SUMMARY_PREFIX)


def build_session_memory_summary_message(summary_text: str, *, summary_path: str) -> HumanMessage:
    return HumanMessage(
        content=(
            f'<session_memory_summary path="{summary_path}">\n'
            f"{summary_text}\n"
            "</session_memory_summary>"
        )
    )


class SessionMemoryManager:
    def __init__(
        self,
        *,
        working_directory: str,
        config: dict[str, Any],
        session_id: str,
        llm: BaseChatModel | None = None,
    ) -> None:
        self._working_directory = working_directory
        self._config = config
        self._session_id = session_id
        self._llm = llm
        self._status = SessionMemoryStatus(summary_path=self.get_summary_relative_path())
        self._status_lock = threading.Lock()

    def get_summary_path(self) -> Path:
        return get_session_memory_dir(
            self._working_directory,
            self._config,
            self._session_id,
        ) / SESSION_MEMORY_FILENAME

    def get_summary_relative_path(self) -> str:
        session_artifact_dir = get_session_artifact_dir(
            self._working_directory,
            self._config,
            self._session_id,
        )
        return self.get_summary_path().relative_to(session_artifact_dir).as_posix()

    def ensure_summary_file(self) -> Path:
        path = self.get_summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(DEFAULT_SESSION_MEMORY_TEMPLATE, encoding="utf-8")
        return path

    def load_summary(self) -> str:
        path = self.ensure_summary_file()
        return path.read_text(encoding="utf-8")

    def save_summary(self, content: str) -> Path:
        path = self.ensure_summary_file()
        path.write_text(content, encoding="utf-8")
        return path

    def get_status(self) -> SessionMemoryStatus:
        with self._status_lock:
            return SessionMemoryStatus(
                summary_path=self._status.summary_path,
                last_summarized_message_id=self._status.last_summarized_message_id,
                tokens_at_last_extraction=self._status.tokens_at_last_extraction,
                tool_calls_since_last_update=self._status.tool_calls_since_last_update,
                last_update_turn=self._status.last_update_turn,
            )

    def set_status(self, status: SessionMemoryStatus) -> None:
        with self._status_lock:
            self._status = SessionMemoryStatus(
                summary_path=status.summary_path or self.get_summary_relative_path(),
                last_summarized_message_id=status.last_summarized_message_id,
                tokens_at_last_extraction=status.tokens_at_last_extraction,
                tool_calls_since_last_update=status.tool_calls_since_last_update,
                last_update_turn=status.last_update_turn,
            )

    def apply_update_result(self, result: SessionMemoryUpdateResult) -> SessionMemoryStatus:
        status = SessionMemoryStatus(
            summary_path=result.summary_path,
            last_summarized_message_id=result.last_summarized_message_id,
            tokens_at_last_extraction=result.tokens_at_last_extraction,
            tool_calls_since_last_update=result.tool_calls_since_last_update,
            last_update_turn=result.last_update_turn,
        )
        self.set_status(status)
        return status

    def update_session_memory(
        self,
        *,
        messages: list[BaseMessage],
        current_tokens: int,
        tool_calls_since_last_update: int,
        turn: int,
    ) -> SessionMemoryUpdateResult:
        if self._llm is None:
            raise RuntimeError("SessionMemoryManager requires llm for updates")

        current_summary = self.load_summary()
        conversation = self._serialize_messages(messages)
        response = self._llm.invoke([
            SystemMessage(content=SESSION_MEMORY_UPDATE_SYSTEM_PROMPT),
            HumanMessage(content=SESSION_MEMORY_UPDATE_USER_PROMPT.format(
                current_memory=current_summary,
                conversation=conversation,
            )),
        ])
        summary_text = str(response.content or "").strip() or current_summary
        self.save_summary(summary_text)

        last_message_id = next((msg.id for msg in reversed(messages) if getattr(msg, "id", None)), None)
        return SessionMemoryUpdateResult(
            summary_path=self.get_summary_relative_path(),
            summary_text=summary_text,
            last_summarized_message_id=last_message_id,
            tokens_at_last_extraction=current_tokens,
            tool_calls_since_last_update=0,
            last_update_turn=turn,
        )

    def try_session_memory_compact(
        self,
        *,
        messages: list[BaseMessage],
        status: SessionMemoryStatus,
        threshold_tokens: int,
        min_keep_tokens: int,
        max_keep_tokens: int,
        reason: str = "session_memory",
    ) -> SessionMemoryCompactResult | None:
        summary_text = self.load_summary().strip()
        if not summary_text:
            return None
        if len(messages) < 2:
            return None

        start_index = self._calculate_keep_start_index(
            messages=messages,
            last_summarized_message_id=status.last_summarized_message_id,
            min_keep_tokens=min_keep_tokens,
            max_keep_tokens=max_keep_tokens,
        )
        if start_index >= len(messages):
            return None

        kept_messages = list(messages[start_index:])
        kept_tokens = estimate_message_tokens(kept_messages)
        boundary_message = ContextCompressor.build_compact_boundary_message(
            pre_tokens=estimate_message_tokens(messages[:start_index]),
            post_tokens=0,
            reason=reason,
        )
        summary_message = build_session_memory_summary_message(
            summary_text,
            summary_path=status.summary_path or self.get_summary_relative_path(),
        )
        compacted_messages = [boundary_message, summary_message, *kept_messages]
        post_tokens = estimate_message_tokens(compacted_messages)
        if post_tokens > threshold_tokens:
            return None

        boundary_message = ContextCompressor.build_compact_boundary_message(
            pre_tokens=estimate_message_tokens(messages[:start_index]),
            post_tokens=post_tokens,
            reason=reason,
        )
        compacted_messages = [boundary_message, summary_message, *kept_messages]
        return SessionMemoryCompactResult(
            boundary_message=boundary_message,
            summary_message=summary_message,
            compacted_messages=compacted_messages,
            last_summarized_message_id=status.last_summarized_message_id,
            start_index=start_index,
            kept_tokens=kept_tokens,
            post_tokens=post_tokens,
        )

    def _calculate_keep_start_index(
        self,
        *,
        messages: list[BaseMessage],
        last_summarized_message_id: str | None,
        min_keep_tokens: int,
        max_keep_tokens: int,
    ) -> int:
        working_start = find_compaction_working_start(messages)
        if last_summarized_message_id:
            found_index = next(
                (idx for idx, msg in enumerate(messages) if getattr(msg, "id", None) == last_summarized_message_id),
                None,
            )
            start_index = (found_index + 1) if found_index is not None else len(messages) - 1
        else:
            start_index = len(messages) - 1

        start_index = max(start_index, working_start)
        start_index = min(start_index, len(messages) - 1)

        kept_tokens = estimate_message_tokens(messages[start_index:])
        while start_index > working_start and kept_tokens < min_keep_tokens:
            candidate = start_index - 1
            adjusted = adjust_index_to_preserve_tool_pairs(messages, candidate)
            adjusted = adjust_index_to_preserve_message_groups(messages, adjusted)
            adjusted = adjust_index_to_respect_boundary(messages, adjusted)
            if adjusted < working_start:
                adjusted = working_start
            candidate_tokens = estimate_message_tokens(messages[adjusted:])
            if candidate_tokens > max_keep_tokens:
                break
            start_index = adjusted
            kept_tokens = candidate_tokens

        return start_index

    @staticmethod
    def _serialize_messages(messages: list[BaseMessage]) -> str:
        parts: list[str] = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                parts.append(f"[tool:{msg.name}] {msg.content}")
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                parts.append(f"[assistant tools={','.join(tc['name'] for tc in msg.tool_calls)}] {msg.content}")
            else:
                parts.append(f"[{msg.type}] {msg.content}")
        return "\n".join(parts)
