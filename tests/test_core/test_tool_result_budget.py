from pathlib import Path

from langchain_core.messages import ToolMessage

from core.context.tool_results import (
    MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
    apply_aggregate_budget,
    apply_transcript_metadata,
    candidate_from_tool_message,
    generate_preview,
    get_tool_result_threshold,
    maybe_persist_tool_result,
)


def test_thresholds():
    assert get_tool_result_threshold("grep") == 20_000
    assert get_tool_result_threshold("shell") == 30_000
    assert get_tool_result_threshold("read_file") == float("inf")
    assert get_tool_result_threshold("ls") == 50_000


def test_generate_preview_prefers_newline():
    preview, has_more = generate_preview("a\nb\nc\n" * 1000, max_chars=100)
    assert has_more is True
    assert len(preview) <= 100


def test_maybe_persist_tool_result_writes_artifact(tmp_path):
    artifact_dir = tmp_path / "session"
    artifact_path = artifact_dir / "tool-results" / "call_1.txt"
    content = "x" * 25_000
    decision = maybe_persist_tool_result(
        tool_name="grep",
        tool_call_id="call_1",
        content=content,
        display="grep result",
        artifact_dir=artifact_dir,
        artifact_path=artifact_path,
        threshold=20_000,
        reason="per-tool-limit",
    )
    assert decision.persisted is True
    assert artifact_path.exists()
    assert 'path="tool-results/call_1.txt"' in decision.content
    assert decision.tool_use_result["artifact"] == "tool-results/call_1.txt"


def test_apply_aggregate_budget_persists_largest(tmp_path):
    artifact_dir = tmp_path / "session"
    m1 = ToolMessage(content="a" * 120_000, tool_call_id="call_1", artifact={"display": "a"})
    m2 = ToolMessage(content="b" * 120_000, tool_call_id="call_2", artifact={"display": "b"})
    c1 = candidate_from_tool_message(tool_name="grep", tool_call_id="call_1", tool_message=m1)
    c2 = candidate_from_tool_message(tool_name="grep", tool_call_id="call_2", tool_message=m2)
    decisions = apply_aggregate_budget(
        [c1, c2],
        artifact_dir=artifact_dir,
        artifact_path_for_call=lambda call_id: artifact_dir / "tool-results" / f"{call_id}.txt",
        aggregate_limit=MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
    )
    assert len(decisions) == 1
    assert decisions[0].reason == "aggregate-limit"


def test_apply_transcript_metadata_updates_tool_message():
    message = ToolMessage(content="ok", tool_call_id="call_1", artifact={"display": "ok"})
    apply_transcript_metadata(
        message,
        display="ok",
        tool_use_result={"kind": "text"},
        artifact_meta={"path": "tool-results/call_1.txt"},
    )
    assert message.artifact["toolUseResult"]["kind"] == "text"
    assert message.artifact["artifact_meta"]["path"] == "tool-results/call_1.txt"
