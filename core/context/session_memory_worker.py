"""Background session memory extraction worker."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.event_bus import AgentEvent, EventBus, EventType

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage
    from core.context.session_memory import SessionMemoryManager, SessionMemoryStatus

logger = logging.getLogger(__name__)


@dataclass
class SessionMemoryExtractRequest:
    messages: list[BaseMessage]
    current_tokens: int
    tool_calls_since_last_update: int
    turn: int


class SessionMemoryExtractWorker:
    def __init__(self, manager: SessionMemoryManager, event_bus: EventBus) -> None:
        self._manager = manager
        self._event_bus = event_bus
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="session-memory")
        self._lock = threading.Lock()
        self._running = False
        self._pending: SessionMemoryExtractRequest | None = None

    def schedule_extract(
        self,
        *,
        messages: list[BaseMessage],
        current_tokens: int,
        tool_calls_since_last_update: int,
        turn: int,
    ) -> bool:
        request = SessionMemoryExtractRequest(
            messages=list(messages),
            current_tokens=current_tokens,
            tool_calls_since_last_update=tool_calls_since_last_update,
            turn=turn,
        )
        with self._lock:
            if self._running:
                self._pending = request
                logger.info(
                    "Session memory extract queued: turn=%d current_tokens=%d tool_calls_since_last_update=%d",
                    turn,
                    current_tokens,
                    tool_calls_since_last_update,
                )
                return False
            self._running = True
        logger.info(
            "Session memory extract scheduled: turn=%d current_tokens=%d tool_calls_since_last_update=%d",
            turn,
            current_tokens,
            tool_calls_since_last_update,
        )
        self._executor.submit(self._run_request, request)
        return True

    def get_status(self) -> SessionMemoryStatus:
        return self._manager.get_status()

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        deadline = threading.Event()
        end_time = timeout
        while end_time > 0:
            with self._lock:
                idle = (not self._running) and self._pending is None
            if idle:
                return True
            step = min(0.05, end_time)
            deadline.wait(step)
            end_time -= step
        return False

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run_request(self, request: SessionMemoryExtractRequest) -> None:
        try:
            logger.info(
                "Session memory extract started: turn=%d message_count=%d current_tokens=%d",
                request.turn,
                len(request.messages),
                request.current_tokens,
            )
            result = self._manager.update_session_memory(
                messages=request.messages,
                current_tokens=request.current_tokens,
                tool_calls_since_last_update=request.tool_calls_since_last_update,
                turn=request.turn,
            )
            status = self._manager.apply_update_result(result)
            logger.info(
                "Session memory extract completed: turn=%d summary_path=%s last_summarized_message_id=%s tokens_at_last_extraction=%d",
                request.turn,
                status.summary_path,
                status.last_summarized_message_id,
                status.tokens_at_last_extraction,
            )
            self._event_bus.emit(AgentEvent(
                type=EventType.SESSION_MEMORY_UPDATED,
                data={
                    "summary_path": status.summary_path,
                    "last_summarized_message_id": status.last_summarized_message_id,
                    "tokens_at_last_extraction": status.tokens_at_last_extraction,
                    "tool_calls_since_last_update": status.tool_calls_since_last_update,
                    "turn": status.last_update_turn,
                },
                turn=request.turn,
            ))
        except Exception as exc:
            logger.warning("Session memory extract failed: turn=%d error=%s", request.turn, exc)
        finally:
            next_request = None
            with self._lock:
                next_request = self._pending
                self._pending = None
                if next_request is None:
                    self._running = False
            if next_request is not None:
                logger.info(
                    "Session memory extract dequeued latest pending request: turn=%d current_tokens=%d",
                    next_request.turn,
                    next_request.current_tokens,
                )
                self._executor.submit(self._run_request, next_request)
