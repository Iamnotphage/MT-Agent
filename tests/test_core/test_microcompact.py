from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.context.microcompact import (
    MICROCOMPACT_PLACEHOLDER,
    find_last_assistant_timestamp_ms,
    maybe_time_based_microcompact,
)


def test_microcompact_does_not_trigger_without_long_gap():
    messages = [
        HumanMessage(content="read file"),
        AIMessage(content="done", response_metadata={"timestamp_ms": 1000}),
        ToolMessage(content="file content", tool_call_id="call_1", name="read_file"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=2_000,
        gap_threshold_minutes=60,
        keep_recent=5,
    )

    assert result.triggered is False
    assert result.messages[2].content == "file content"


def test_microcompact_does_not_trigger_without_assistant_timestamp():
    messages = [
        AIMessage(content="done"),
        ToolMessage(content="file content", tool_call_id="call_1", name="read_file"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=5,
    )

    assert result.triggered is False


def test_microcompact_uses_last_assistant_timestamp_from_messages_view():
    messages = [
        AIMessage(content="older reply", response_metadata={"timestamp_ms": 100}),
        ToolMessage(content="old grep output", tool_call_id="call_1", name="grep"),
        AIMessage(content="recent reply", response_metadata={"timestamp_ms": 3_900_000}),
        ToolMessage(content="recent read_file output", tool_call_id="call_2", name="read_file"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=5,
    )

    assert result.triggered is False
    assert result.messages[1].content == "old grep output"


def test_microcompact_clears_old_whitelisted_tool_results_after_long_gap():
    messages = [
        AIMessage(content="done", response_metadata={"timestamp_ms": 100}),
        ToolMessage(content="old grep output", tool_call_id="call_1", name="grep"),
        ToolMessage(content="old shell output", tool_call_id="call_2", name="shell"),
        ToolMessage(content="recent read_file output", tool_call_id="call_3", name="read_file"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=1,
    )

    assert result.triggered is True
    assert result.cleared_count == 2
    assert result.messages[1].content == MICROCOMPACT_PLACEHOLDER
    assert result.messages[2].content == MICROCOMPACT_PLACEHOLDER
    assert result.messages[3].content == "recent read_file output"


def test_microcompact_skips_non_whitelisted_tools():
    messages = [
        AIMessage(content="done", response_metadata={"timestamp_ms": 100}),
        ToolMessage(content="compile ok", tool_call_id="call_1", name="compile_project"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=0,
    )

    assert result.triggered is False
    assert result.messages[1].content == "compile ok"


def test_microcompact_does_not_mutate_original_messages():
    original = ToolMessage(content="old grep output", tool_call_id="call_1", name="grep")
    messages = [
        AIMessage(content="done", response_metadata={"timestamp_ms": 100}),
        original,
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=0,
    )

    assert original.content == "old grep output"
    assert result.messages[1].content == MICROCOMPACT_PLACEHOLDER
    assert result.messages[1] is not original


def test_microcompact_skips_already_placeholder_messages():
    messages = [
        AIMessage(content="done", response_metadata={"timestamp_ms": 100}),
        ToolMessage(content=MICROCOMPACT_PLACEHOLDER, tool_call_id="call_1", name="grep"),
        ToolMessage(content="real content", tool_call_id="call_2", name="grep"),
    ]

    result = maybe_time_based_microcompact(
        messages,
        now_ts_ms=4_000_000,
        gap_threshold_minutes=60,
        keep_recent=0,
    )

    assert result.triggered is True
    assert result.cleared_count == 1
    assert result.messages[1].content == MICROCOMPACT_PLACEHOLDER
    assert result.messages[2].content == MICROCOMPACT_PLACEHOLDER


def test_find_last_assistant_timestamp_ms_returns_none_for_empty():
    assert find_last_assistant_timestamp_ms([]) is None


def test_find_last_assistant_timestamp_ms_returns_last():
    messages = [
        AIMessage(content="a", response_metadata={"timestamp_ms": 100}),
        AIMessage(content="b", response_metadata={"timestamp_ms": 300}),
        HumanMessage(content="c"),
    ]
    assert find_last_assistant_timestamp_ms(messages) == 300
