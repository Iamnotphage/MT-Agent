import time
from threading import Event
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from core.context.session_memory import SessionMemoryManager
from core.context.session_memory_worker import SessionMemoryExtractWorker
from core.event_bus import EventBus, EventType


def _manager(tmp_path, llm):
    workspace = tmp_path / "project"
    workspace.mkdir()
    config = {"global_dir": str(tmp_path / "global")}
    return SessionMemoryManager(
        working_directory=str(workspace),
        config=config,
        session_id="sid-1",
        llm=llm,
    )


def test_schedule_extract_returns_without_blocking(tmp_path):
    started = Event()
    release = Event()

    def _invoke(_messages):
        started.set()
        release.wait(2.0)
        return MagicMock(content="# Session Title\nUpdated")

    llm = MagicMock()
    llm.invoke.side_effect = _invoke
    manager = _manager(tmp_path, llm)
    bus = EventBus()
    worker = SessionMemoryExtractWorker(manager, bus)

    t0 = time.perf_counter()
    accepted = worker.schedule_extract(
        messages=[HumanMessage(content="x" * 100)],
        current_tokens=12_000,
        tool_calls_since_last_update=0,
        turn=2,
    )
    elapsed = time.perf_counter() - t0

    assert accepted is True
    assert elapsed < 0.1
    assert started.wait(1.0) is True

    release.set()
    assert worker.wait_for_idle(2.0) is True


def test_worker_emits_update_event_and_updates_status(tmp_path):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="# Session Title\nUpdated")
    manager = _manager(tmp_path, llm)
    bus = EventBus()
    received = []
    bus.subscribe(EventType.SESSION_MEMORY_UPDATED, lambda e: received.append(e))
    worker = SessionMemoryExtractWorker(manager, bus)

    worker.schedule_extract(
        messages=[HumanMessage(content="hello", id="m1")],
        current_tokens=12_000,
        tool_calls_since_last_update=3,
        turn=4,
    )

    assert worker.wait_for_idle(2.0) is True
    status = worker.get_status()
    assert status.summary_path == "session-memory/summary.md"
    assert status.last_summarized_message_id == "m1"
    assert status.tokens_at_last_extraction == 12_000
    assert len(received) == 1
