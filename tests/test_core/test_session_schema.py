from core.session.schema import (
    RECORD_COMPACT_BOUNDARY,
    RECORD_TRANSCRIPT_MESSAGE,
    is_renderable_record,
    make_compact_boundary_record,
    make_session_start_record,
    make_tool_result_artifact_record,
    make_transcript_message_record,
    normalize_compact_boundary_record,
    normalize_transcript_record,
)


def test_make_session_start_record_type():
    record = make_session_start_record(
        session_id="sid",
        thread_id="tid",
        project="/tmp/project",
        model="test-model",
        branch="main",
    )
    assert record["type"] == "session_start"
    assert record["sessionId"] == "sid"


def test_make_transcript_message_record_defaults():
    record = make_transcript_message_record(role="tool", content="ok")
    assert record["type"] == RECORD_TRANSCRIPT_MESSAGE
    assert record["tool_calls"] == []
    assert record["tool_call_id"] == ""
    assert record["name"] == ""
    assert record["toolUseResult"] is None
    assert record["artifact"] is None


def test_normalize_transcript_record_backfills_missing_fields():
    record = normalize_transcript_record({
        "type": "transcript_message",
        "role": "tool",
        "content": "hello",
        "tool_call_id": "call_1",
    })
    assert record["name"] == ""
    assert record["toolUseResult"] is None
    assert record["artifact"] is None
    assert "timestamp" in record


def test_is_renderable_record_recognizes_transcript_message():
    assert is_renderable_record({"type": "transcript_message"}) is True
    assert is_renderable_record({"type": "tool_result_artifact"}) is False


def test_make_tool_result_artifact_record():
    record = make_tool_result_artifact_record(
        tool_call_id="call_1",
        name="grep",
        artifact={"path": "tool-results/call_1.txt"},
    )
    assert record["type"] == "tool_result_artifact"
    assert record["artifact"]["path"] == "tool-results/call_1.txt"


def test_make_compact_boundary_record():
    record = make_compact_boundary_record(reason="auto", pre_tokens=100, post_tokens=20)
    assert record["type"] == RECORD_COMPACT_BOUNDARY
    assert record["pre_tokens"] == 100
    assert record["post_tokens"] == 20


def test_normalize_compact_boundary_record():
    record = normalize_compact_boundary_record({"type": "compact_boundary", "reason": "auto"})
    assert record["pre_tokens"] == 0
    assert record["post_tokens"] == 0
    assert "timestamp" in record
