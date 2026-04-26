from core.session.artifacts import (
    get_session_artifact_dir,
    get_tool_result_path,
    resolve_session_relative_artifact,
    write_text_artifact,
)


def _config(tmp_path):
    return {
        "global_dir": str(tmp_path / "global"),
    }


def test_session_artifact_dir_uses_session_id(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    path = get_session_artifact_dir(str(workspace), _config(tmp_path), "session123")
    assert path.as_posix().endswith("/artifacts/session123")


def test_get_tool_result_path_uses_tool_results_subdir(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    path = get_tool_result_path(str(workspace), _config(tmp_path), "session123", "call_1")
    assert path.name == "call_1.txt"
    assert "tool-results" in path.as_posix()


def test_write_text_artifact_returns_relative_path(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    session_dir = get_session_artifact_dir(str(workspace), _config(tmp_path), "session123")
    path = get_tool_result_path(str(workspace), _config(tmp_path), "session123", "call_1")
    result = write_text_artifact(path, "hello", session_artifact_dir=session_dir)
    assert path.exists()
    assert result["relative_path"] == "tool-results/call_1.txt"
    assert result["truncated"] is False


def test_resolve_session_relative_artifact(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    path = resolve_session_relative_artifact(
        str(workspace),
        _config(tmp_path),
        "session123",
        "tool-results/call_1.txt",
    )
    assert path.name == "call_1.txt"
    assert "session123" in path.as_posix()
