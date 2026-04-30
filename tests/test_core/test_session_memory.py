from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.context.session_memory import (
    DEFAULT_SESSION_MEMORY_TEMPLATE,
    SessionMemoryManager,
    SessionMemoryStatus,
    build_session_memory_summary_message,
    is_session_memory_summary_message,
    should_extract_memory,
)


def _manager(tmp_path, llm=None):
    workspace = tmp_path / "project"
    workspace.mkdir()
    config = {"global_dir": str(tmp_path / "global")}
    return SessionMemoryManager(
        working_directory=str(workspace),
        config=config,
        session_id="sid-1",
        llm=llm,
    )


def test_should_extract_memory_initial_threshold():
    assert should_extract_memory(
        current_tokens=9_999,
        tokens_at_last_extraction=0,
        tool_calls_since_last_update=0,
        last_turn_has_tool_calls=False,
    ) is False
    assert should_extract_memory(
        current_tokens=10_000,
        tokens_at_last_extraction=0,
        tool_calls_since_last_update=0,
        last_turn_has_tool_calls=True,
    ) is True


def test_should_extract_memory_requires_token_growth_after_init():
    assert should_extract_memory(
        current_tokens=14_999,
        tokens_at_last_extraction=10_000,
        tool_calls_since_last_update=10,
        last_turn_has_tool_calls=True,
    ) is False


def test_should_extract_memory_at_conversation_break():
    assert should_extract_memory(
        current_tokens=15_000,
        tokens_at_last_extraction=10_000,
        tool_calls_since_last_update=1,
        last_turn_has_tool_calls=False,
    ) is True


def test_ensure_summary_file_creates_template(tmp_path):
    manager = _manager(tmp_path)
    path = manager.ensure_summary_file()
    assert path.exists()
    assert path.read_text(encoding="utf-8") == DEFAULT_SESSION_MEMORY_TEMPLATE


def test_update_session_memory_overwrites_summary(tmp_path):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="# Session Title\nUpdated\n")
    manager = _manager(tmp_path, llm=llm)
    messages = [HumanMessage(content="hello", id="m1"), AIMessage(content="world", id="m2")]

    result = manager.update_session_memory(
        messages=messages,
        current_tokens=12_000,
        tool_calls_since_last_update=4,
        turn=3,
    )

    assert result.summary_path == "session-memory/summary.md"
    assert result.last_summarized_message_id == "m2"
    assert manager.load_summary() == "# Session Title\nUpdated"


def test_try_session_memory_compact_keeps_recent_messages_and_uses_summary(tmp_path):
    manager = _manager(tmp_path)
    manager.save_summary("# Session Title\nSaved memory\n")
    messages = [
        HumanMessage(content="old user", id="u1"),
        AIMessage(content="old answer", id="a1"),
        HumanMessage(content="recent user", id="u2"),
        AIMessage(
            content="",
            id="a2",
            tool_calls=[{"name": "read_file", "args": {}, "id": "call_1", "type": "tool_call"}],
        ),
        ToolMessage(content="tool result", tool_call_id="call_1", name="read_file", id="t1"),
        AIMessage(content="recent answer", id="a3"),
    ]
    status = SessionMemoryStatus(
        summary_path="session-memory/summary.md",
        last_summarized_message_id="a1",
    )

    result = manager.try_session_memory_compact(
        messages=messages,
        status=status,
        threshold_tokens=10_000,
        min_keep_tokens=1,
        max_keep_tokens=10_000,
    )

    assert result is not None
    assert result.compacted_messages[0].content.startswith("<compact_boundary ")
    assert is_session_memory_summary_message(result.compacted_messages[1]) is True
    assert result.compacted_messages[2].content == "recent user"
    assert result.compacted_messages[3].tool_calls[0]["name"] == "read_file"
    assert result.compacted_messages[4].content == "tool result"


def test_try_session_memory_compact_respects_threshold(tmp_path):
    manager = _manager(tmp_path)
    manager.save_summary("# Session Title\nSaved memory\n")
    messages = [
        HumanMessage(content="old user", id="u1"),
        AIMessage(content="old answer", id="a1"),
        HumanMessage(content="recent user" * 5000, id="u2"),
    ]
    status = SessionMemoryStatus(
        summary_path="session-memory/summary.md",
        last_summarized_message_id="a1",
    )

    result = manager.try_session_memory_compact(
        messages=messages,
        status=status,
        threshold_tokens=10,
        min_keep_tokens=1,
        max_keep_tokens=1000,
    )

    assert result is None


def test_build_session_memory_summary_message():
    message = build_session_memory_summary_message("body", summary_path="session-memory/summary.md")
    assert is_session_memory_summary_message(message) is True
    assert 'path="session-memory/summary.md"' in message.content


def test_should_extract_memory_after_prior_completion_returns_false():
    """第一次提取完成后，紧随的第二次请求应返回 False。"""
    assert should_extract_memory(
        current_tokens=91983,
        tokens_at_last_extraction=91869,
        tool_calls_since_last_update=58,
        last_turn_has_tool_calls=False,
    ) is False
