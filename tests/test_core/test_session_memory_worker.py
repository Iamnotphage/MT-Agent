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


def test_queued_extract_rechecks_and_skips_after_prior_update(tmp_path):
    """两个连续请求，第二个应在执行时被 recheck 跳过。"""
    from unittest.mock import MagicMock
    from core.context.session_memory import SessionMemoryUpdateResult

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="# Session Title\nUpdated")
    manager = _manager(tmp_path, llm)
    bus = EventBus()
    seen = []
    bus.subscribe(EventType.SESSION_MEMORY_UPDATED, lambda e: seen.append(e))
    worker = SessionMemoryExtractWorker(manager, bus)

    # 模拟第一次请求完成后 manager 返回高 tokens_at_last_extraction
    original_update = manager.update_session_memory
    call_count = {"n": 0}

    def _tracking_update(**kwargs):
        call_count["n"] += 1
        result = original_update(**kwargs)
        if call_count["n"] == 1:
            # 让第一次更新后的 tokens 足够高，使第二次 should_extract_memory 返回 false
            return SessionMemoryUpdateResult(
                summary_path=result.summary_path,
                summary_text=result.summary_text,
                last_summarized_message_id=result.last_summarized_message_id,
                tokens_at_last_extraction=kwargs["current_tokens"],
                tool_calls_since_last_update=0,
                last_update_turn=kwargs["turn"],
            )
        return result

    manager.update_session_memory = _tracking_update

    worker.schedule_extract(
        messages=[HumanMessage(content="a")],
        current_tokens=12_000,
        tool_calls_since_last_update=0,
        last_turn_has_tool_calls=False,
        turn=11,
    )
    worker.schedule_extract(
        messages=[HumanMessage(content="a"), HumanMessage(content="b")],
        current_tokens=12_100,
        tool_calls_since_last_update=0,
        last_turn_has_tool_calls=False,
        turn=12,
    )

    assert worker.wait_for_idle(timeout=2.0) is True
    assert call_count["n"] == 1
    assert len(seen) == 1


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
