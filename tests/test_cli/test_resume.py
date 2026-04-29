import logging
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from cli.commands import resume as resume_mod
from core.session import SessionRecorder


class _FakeGraph:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.update_called = False
        self.update_args = None

    def get_state(self, config):
        return self._snapshot

    def update_state(self, config, values, as_node=None, task_id=None):
        self.update_called = True
        self.update_args = {
            "config": config,
            "values": values,
            "as_node": as_node,
            "task_id": task_id,
        }
        merged = dict(getattr(self._snapshot, "values", {}) or {})
        merged.update(values or {})
        self._snapshot = SimpleNamespace(values=merged, next=())


def _make_recorder(tmp_path: Path) -> tuple[SessionRecorder, Path]:
    config = {
        "file_names": ["CONTEXT.md"],
        "global_dir": str(tmp_path / "global"),
        "compression_threshold": 0.50,
        "compression_preserve_ratio": 0.30,
        "token_limit": 65536,
    }
    workspace = tmp_path / "project"
    workspace.mkdir(parents=True, exist_ok=True)
    recorder = SessionRecorder(working_directory=str(workspace), config=config)
    recorder.set_thread_id("thread-restore")
    recorder.record({"type": "transcript_message", "role": "user", "content": "hello"})
    recorder.record({"type": "transcript_message", "role": "assistant", "content": "world"})
    filepath = recorder.flush()
    return recorder, filepath


def test_cmd_resume_restores_existing_checkpoint(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={"messages": recorder.build_resume_messages(filepath)},
        next=(),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id == "thread-restore"
    assert graph.update_called is False
    assert recorder._resumed_from == filepath
    assert recorder.stats.last_input_tokens > 0


def test_cmd_resume_requires_persisted_checkpoint(monkeypatch, tmp_path):
    recorder, _filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(values={}, next=()))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id is None


def test_cmd_resume_marks_interrupted_tool_execution(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={
            "messages": recorder.build_resume_messages(filepath),
            "pending_tool_calls": [{
                "call_id": "call_1",
                "tool_name": "read_file",
                "arguments": {"path": "a.py"},
                "status": "pending",
                "result": None,
                "error_msg": None,
            }],
        },
        next=("tools",),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id == "thread-restore"
    assert graph.update_called is True
    assert graph.update_args["as_node"] == "tools"
    assert graph.update_args["values"]["pending_tool_calls"] == []
    assert graph.update_args["values"]["should_continue"] is False
    assert len(graph.update_args["values"]["messages"]) == 1


def test_cmd_resume_rejects_inconsistent_awaiting_approval(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={
            "messages": recorder.build_resume_messages(filepath),
            "pending_tool_calls": [{
                "call_id": "call_1",
                "tool_name": "write_file",
                "arguments": {"file_path": "a.py"},
                "status": "awaiting_approval",
                "result": None,
                "error_msg": None,
            }],
        },
        next=("human_approval",),
        tasks=(),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id is None


def test_cmd_resume_allows_reapproval_when_interrupt_present(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={
            "messages": recorder.build_resume_messages(filepath),
            "pending_tool_calls": [{
                "call_id": "call_1",
                "tool_name": "write_file",
                "arguments": {"file_path": "a.py"},
                "status": "awaiting_approval",
                "result": None,
                "error_msg": None,
            }],
        },
        next=("human_approval",),
        tasks=[SimpleNamespace(
            interrupts=[SimpleNamespace(value=[{
                "call_id": "call_1",
                "tool_name": "write_file",
                "arguments": {"file_path": "a.py"},
                "risk_level": "medium",
            }])]
        )],
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id == "thread-restore"


def test_cmd_resume_warns_when_checkpoint_and_transcript_diverge(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={
            "messages": recorder.build_resume_messages(filepath) + recorder.build_resume_messages(filepath),
        },
        next=(),
        tasks=(),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id == "thread-restore"
    assert "历史长度不一致" in console.export_text()


def test_render_resumed_history_uses_assistant_reasoning_content():
    console = Console(record=True, width=100)

    resume_mod._render_resumed_history(console, [
        {
            "type": "transcript_message",
            "role": "assistant",
            "content": "I found the file.",
            "reasoning_content": "I should read the file first.",
        }
    ])

    rendered = console.export_text()
    assert "💭 I should read the file first." in rendered
    assert "⏺ I found the file." in rendered


def test_build_resume_messages_uses_session_memory_summary(tmp_path):
    recorder, _ = _make_recorder(tmp_path)
    summary_dir = recorder.get_session_memory_artifact_dir()
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.md").write_text("# Session Title\nSaved memory", encoding="utf-8")

    recorder.record({
        "type": "session_memory_update",
        "summary_path": "session-memory/summary.md",
        "last_summarized_message_id": "m2",
        "tokens_at_last_extraction": 12000,
        "tool_calls_since_last_update": 0,
        "turn": 1,
    })
    recorder.record({
        "type": "compact_boundary",
        "reason": "session_memory",
        "pre_tokens": 100,
        "post_tokens": 30,
    })
    recorder.record({"type": "transcript_message", "role": "user", "content": "continue"})
    filepath = recorder.flush()

    messages = recorder.build_resume_messages(filepath)

    assert messages[0].content.startswith("<compact_boundary ")
    assert messages[1].content.startswith("<session_memory_summary ")
    assert "Saved memory" in messages[1].content
    assert messages[2].content == "continue"


def test_build_resume_messages_reads_session_memory_from_resumed_session_id(tmp_path):
    old_recorder, _ = _make_recorder(tmp_path)
    summary_dir = old_recorder.get_session_memory_artifact_dir()
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.md").write_text("# Session Title\nSaved memory", encoding="utf-8")

    old_recorder.record({
        "type": "session_memory_update",
        "summary_path": "session-memory/summary.md",
        "last_summarized_message_id": "m2",
        "tokens_at_last_extraction": 12000,
        "tool_calls_since_last_update": 0,
        "turn": 1,
    })
    old_recorder.record({
        "type": "compact_boundary",
        "reason": "session_memory",
        "pre_tokens": 100,
        "post_tokens": 30,
    })
    filepath = old_recorder.flush()

    new_recorder = SessionRecorder(
        working_directory=str(tmp_path / "project"),
        config=old_recorder._config,
    )

    messages = new_recorder.build_resume_messages(filepath)

    assert len(messages) == 2
    assert messages[0].content.startswith("<compact_boundary ")
    assert messages[1].content.startswith("<session_memory_summary ")
    assert "Saved memory" in messages[1].content


def test_build_resume_messages_does_not_drop_transcript_for_session_memory_update_only(tmp_path):
    recorder, _ = _make_recorder(tmp_path)
    recorder.record({
        "type": "session_memory_update",
        "summary_path": "session-memory/summary.md",
        "last_summarized_message_id": "m2",
        "tokens_at_last_extraction": 12000,
        "tool_calls_since_last_update": 0,
        "turn": 1,
    })
    filepath = recorder.flush()

    messages = recorder.build_resume_messages(filepath)

    assert len(messages) == 2
    assert messages[0].content == "hello"
    assert messages[1].content == "world"


def test_cmd_resume_reuses_selected_session_id_when_flushing(monkeypatch, tmp_path):
    recorder, filepath = _make_recorder(tmp_path)
    old_session_id = recorder.stats.session_id

    resumed_recorder = SessionRecorder(
        working_directory=str(tmp_path / "project"),
        config=recorder._config,
    )
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={"messages": recorder.build_resume_messages(filepath)},
        next=(),
        tasks=(),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    thread_id = resume_mod.cmd_resume(console, resumed_recorder, graph)

    assert thread_id == "thread-restore"
    assert resumed_recorder.stats.session_id == old_session_id

    resumed_recorder.record({"type": "transcript_message", "role": "user", "content": "after resume"})
    new_filepath = resumed_recorder.flush()

    assert old_session_id in new_filepath.name


def test_cmd_resume_emits_info_logs(monkeypatch, tmp_path, caplog):
    recorder, filepath = _make_recorder(tmp_path)
    console = Console(record=True, width=100)
    graph = _FakeGraph(SimpleNamespace(
        values={"messages": recorder.build_resume_messages(filepath)},
        next=(),
        tasks=(),
    ))

    monkeypatch.setattr(resume_mod, "_session_picker", lambda sessions: sessions[0])
    monkeypatch.setattr(resume_mod, "_render_resumed_history", lambda console, records: None)

    caplog.set_level(logging.INFO)
    thread_id = resume_mod.cmd_resume(console, recorder, graph)

    assert thread_id == "thread-restore"
    text = caplog.text
    assert "resume: discovered sessions count=1" in text
    assert "resume: selected filepath=" in text
    assert "resume: renderable records count=2" in text
    assert "resume: built messages count=2" in text
    assert "resume: loading checkpoint thread_id=thread-restore" in text
    assert "resume_from: bound session file=" in text
    assert "resume: completed thread_id=thread-restore" in text
