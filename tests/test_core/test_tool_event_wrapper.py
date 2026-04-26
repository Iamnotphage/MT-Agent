from pathlib import Path

from langchain_core.messages import ToolMessage

from core.event_bus import EventBus, EventType
from core.nodes.tool_event_wrapper import create_event_bus_wrapper


class _FakeRequest:
    def __init__(self, tool_call):
        self.tool_call = tool_call


class _FakeSession:
    def __init__(self, root: Path):
        self.root = root

    def get_artifact_dir(self) -> Path:
        return self.root

    def get_tool_result_artifact_path(self, tool_call_id: str, suffix: str = ".txt") -> Path:
        ext = suffix if suffix.startswith(".") else f".{suffix}"
        return self.root / "tool-results" / f"{tool_call_id}{ext}"


def test_wrapper_persists_large_grep_result(tmp_path):
    bus = EventBus()
    session = _FakeSession(tmp_path / "session")
    seen = []
    bus.subscribe_all(lambda event: seen.append(event))
    wrapper = create_event_bus_wrapper(bus, session=session)

    request = _FakeRequest({"id": "call_1", "name": "grep"})
    result = wrapper(
        request,
        lambda _request: ToolMessage(
            content="x" * 25_000,
            tool_call_id="call_1",
            artifact={"display": "grep result"},
        ),
    )

    assert "persisted-output" in result.content
    assert (session.root / "tool-results" / "call_1.txt").exists()
    assert any(event.type == EventType.TOOL_RESULT_PERSISTED for event in seen)
    transcript_events = [event for event in seen if event.type == EventType.TRANSCRIPT_MESSAGE]
    assert len(transcript_events) == 1
    assert transcript_events[0].data["role"] == "tool"
    assert transcript_events[0].data["artifact"]["path"] == "tool-results/call_1.txt"
