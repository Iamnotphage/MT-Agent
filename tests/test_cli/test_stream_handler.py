from rich.console import Console

from cli.event_handlers.stream import StreamHandler
from core.event_bus import AgentEvent, EventBus, EventType
from core.session import SessionRecorder


def _make_session(tmp_path):
    config = {
        "file_names": ["CONTEXT.md"],
        "global_dir": str(tmp_path / "global"),
        "compression_threshold": 0.50,
        "compression_preserve_ratio": 0.30,
        "token_limit": 65536,
    }
    workspace = tmp_path / "project"
    workspace.mkdir(parents=True, exist_ok=True)
    return SessionRecorder(working_directory=str(workspace), config=config)


def test_stream_handler_records_approval_events(tmp_path):
    session = _make_session(tmp_path)
    bus = EventBus()
    StreamHandler(Console(record=True, width=100), bus, session)

    bus.emit(AgentEvent(
        type=EventType.APPROVAL_REQUEST,
        data={
            "call_id": "call_1",
            "tool_name": "write_file",
            "arguments": {"file_path": "a.py"},
            "risk_level": "medium",
        },
    ))
    bus.emit(AgentEvent(
        type=EventType.APPROVAL_RESPONSE,
        data={"decisions": {"call_1": True}},
    ))

    assert session._records[0]["type"] == "approval_request"
    assert session._records[0]["tool_name"] == "write_file"
    assert session._records[1]["type"] == "approval_decision"
    assert session._records[1]["decisions"]["call_1"] is True


def test_stream_handler_renders_thought_as_single_stream(tmp_path):
    session = _make_session(tmp_path)
    bus = EventBus()
    console = Console(record=True, width=100)
    handler = StreamHandler(console, bus, session)

    bus.emit(AgentEvent(type=EventType.THOUGHT, data={"text": "The"}))
    bus.emit(AgentEvent(type=EventType.THOUGHT, data={"text": " user"}))
    bus.emit(AgentEvent(type=EventType.THOUGHT, data={"text": " wants"}))
    handler.end_stream()

    rendered = console.export_text()
    assert "💭 The user wants" in rendered
    assert rendered.count("💭") == 1
    assert session._records == []


def test_tool_result_persisted_event_is_not_recorded_separately(tmp_path):
    session = _make_session(tmp_path)
    bus = EventBus()
    StreamHandler(Console(record=True, width=100), bus, session)

    bus.emit(AgentEvent(
        type=EventType.TOOL_RESULT_PERSISTED,
        data={
            "call_id": "call_1",
            "tool_name": "grep",
            "path": "tool-results/call_1.txt",
            "original_chars": 25000,
            "preview_chars": 2000,
            "reason": "per-tool-limit",
        },
    ))

    assert session._records == []
