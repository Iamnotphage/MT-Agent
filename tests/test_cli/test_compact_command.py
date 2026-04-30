from types import SimpleNamespace
from unittest.mock import MagicMock, call

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from rich.console import Console

from cli.commands.compact import cmd_compact
from core.context.compressor import CompressResult
from core.event_bus import EventBus, EventType


def _make_runtime(tmp_path, *, compressor=None, session_memory_manager=None):
    workspace = tmp_path / "project"
    workspace.mkdir(parents=True, exist_ok=True)
    stats = SimpleNamespace(
        model="test-model",
        turn_count=0,
        last_input_tokens=0,
        last_auto_compact_threshold=10000,
        compression_failure_count=0,
    )
    session = SimpleNamespace(
        stats=stats,
        _thread_id="test-thread",
        set_thread_id=lambda _: None,
    )
    graph = MagicMock()
    # 默认 get_state 返回足够多的消息
    graph.get_state.return_value = SimpleNamespace(
        values={"messages": [HumanMessage(content=f"msg{i}", id=f"m{i}") for i in range(6)]},
    )
    return SimpleNamespace(
        graph=graph,
        session=session,
        event_bus=EventBus(),
        compressor=compressor,
        session_memory_manager=session_memory_manager,
        context_manager=SimpleNamespace(_working_dir=str(workspace)),
    )


def _make_compressor(result_text="compressed summary"):
    compressor = MagicMock()
    result = CompressResult(
        remove_message_ids=["m0", "m1", "m2"],
        boundary_message=HumanMessage(content='<compact_boundary pre_tokens="100" post_tokens="50" reason="manual" />'),
        summary_message=HumanMessage(content=f"<conversation_history_summary>\n{result_text}\n</conversation_history_summary>"),
        summary_text=result_text,
        compressed_messages=[],
        removed_count=3,
        kept_count=3,
        split_index=3,
        pre_tokens=100,
        post_tokens=50,
        reason="manual",
    )
    compressor.compress.return_value = result
    return compressor


def test_cmd_compact_with_args_skips_session_memory_and_uses_full_compact(tmp_path):
    compressor = _make_compressor()
    smm = MagicMock()
    runtime = _make_runtime(tmp_path, compressor=compressor, session_memory_manager=smm)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "keep test failures")

    # session memory 不应被调用
    smm.try_session_memory_compact.assert_not_called()
    # full compact 应被调用，且携带 custom_instructions
    compressor.compress.assert_called_once()
    _, kwargs = compressor.compress.call_args
    assert kwargs["reason"] == "manual"
    assert kwargs["custom_instructions"] == "keep test failures"


def test_cmd_compact_without_args_prefers_session_memory(tmp_path):
    compressor = _make_compressor()
    smm = MagicMock()
    # session memory compact 返回一个有效结果
    sm_result = SimpleNamespace(
        boundary_message=HumanMessage(content="<compact_boundary />"),
        summary_message=HumanMessage(content="<session_memory_summary>ok</session_memory_summary>"),
        compacted_messages=[],
        last_summarized_message_id="m2",
        start_index=3,
        kept_tokens=50,
        post_tokens=80,
    )
    smm.try_session_memory_compact.return_value = sm_result
    smm.get_status.return_value = SimpleNamespace(
        summary_path="session-memory/summary.md",
        last_summarized_message_id=None,
        tokens_at_last_extraction=0,
        tool_calls_since_last_update=0,
        last_update_turn=0,
    )
    runtime = _make_runtime(tmp_path, compressor=compressor, session_memory_manager=smm)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "")

    # session memory 应被调用
    smm.try_session_memory_compact.assert_called_once()
    # full compact 不应被调用
    compressor.compress.assert_not_called()


def test_cmd_compact_without_args_falls_back_to_full_compact_when_session_memory_unavailable(tmp_path):
    compressor = _make_compressor()
    smm = MagicMock()
    # session memory compact 返回 None（不可用）
    smm.try_session_memory_compact.return_value = None
    smm.get_status.return_value = SimpleNamespace(
        summary_path="session-memory/summary.md",
        last_summarized_message_id=None,
        tokens_at_last_extraction=0,
        tool_calls_since_last_update=0,
        last_update_turn=0,
    )
    runtime = _make_runtime(tmp_path, compressor=compressor, session_memory_manager=smm)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "")

    # session memory 应被调用
    smm.try_session_memory_compact.assert_called_once()
    # fallback 到 full compact
    compressor.compress.assert_called_once()
    _, kwargs = compressor.compress.call_args
    assert kwargs["reason"] == "manual"
    assert kwargs["custom_instructions"] is None


def test_cmd_compact_applies_result_to_graph_state(tmp_path):
    compressor = _make_compressor()
    runtime = _make_runtime(tmp_path, compressor=compressor)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "focus on errors")

    # graph.update_state 应被调用
    runtime.graph.update_state.assert_called_once()
    config_arg, state_arg = runtime.graph.update_state.call_args[0]
    assert config_arg == {"configurable": {"thread_id": "test-thread"}}
    message_ops = state_arg["messages"]
    # 应包含 RemoveMessage ops + boundary + summary
    remove_ops = [op for op in message_ops if isinstance(op, RemoveMessage)]
    assert len(remove_ops) == 3
    human_ops = [op for op in message_ops if isinstance(op, HumanMessage)]
    assert len(human_ops) == 2
    assert human_ops[0].content.startswith("<compact_boundary")
    assert human_ops[1].content.startswith("<conversation_history_summary>")


def test_cmd_compact_emits_events(tmp_path):
    compressor = _make_compressor()
    runtime = _make_runtime(tmp_path, compressor=compressor)
    console = Console(record=True, width=100)

    events = []
    runtime.event_bus.subscribe_all(lambda e: events.append(e))

    cmd_compact(console, runtime, "test instructions")

    event_types = [e.type for e in events]
    assert EventType.CONTEXT_COMPRESSED in event_types
    assert EventType.COMPACT_BOUNDARY in event_types
    assert EventType.TRANSCRIPT_MESSAGE in event_types


def test_cmd_compact_transcript_content_includes_summary_wrapper(tmp_path):
    """TRANSCRIPT_MESSAGE.content 必须包含 <conversation_history_summary> 包装标签，
    以便 /resume 能正确识别并恢复摘要。"""
    compressor = _make_compressor("key decisions and code changes")
    runtime = _make_runtime(tmp_path, compressor=compressor)
    console = Console(record=True, width=100)

    events = []
    runtime.event_bus.subscribe_all(lambda e: events.append(e))

    cmd_compact(console, runtime, "focus on errors")

    transcript_events = [e for e in events if e.type == EventType.TRANSCRIPT_MESSAGE]
    assert len(transcript_events) == 1
    content = transcript_events[0].data["content"]
    assert content.startswith("<conversation_history_summary>")
    assert "key decisions and code changes" in content


def test_cmd_compact_updates_session_stats(tmp_path):
    compressor = _make_compressor()
    runtime = _make_runtime(tmp_path, compressor=compressor)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "instructions")

    assert runtime.session.stats.last_input_tokens == 50  # post_tokens from mock result


def test_cmd_compact_too_few_messages(tmp_path):
    compressor = _make_compressor()
    runtime = _make_runtime(tmp_path, compressor=compressor)
    # 只返回 2 条消息（少于 4）
    runtime.graph.get_state.return_value = SimpleNamespace(
        values={"messages": [HumanMessage(content="a", id="m0"), HumanMessage(content="b", id="m1")]},
    )
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "")

    compressor.compress.assert_not_called()
    rendered = console.export_text()
    assert "消息太少" in rendered


def test_cmd_compact_prints_success(tmp_path):
    compressor = _make_compressor()
    runtime = _make_runtime(tmp_path, compressor=compressor)
    console = Console(record=True, width=100)

    cmd_compact(console, runtime, "test")

    rendered = console.export_text()
    assert "full compact" in rendered
    assert "100" in rendered  # pre_tokens
    assert "50" in rendered   # post_tokens
